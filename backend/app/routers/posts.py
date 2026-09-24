from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from ..db import get_db
from ..feed_cache import invalidate_feed
from ..models import Like, Post, User
from ..pagination import page_limit, parse_cursor
from ..schemas import PostIn, PostOut, PostPage
from ..security import get_current_user, get_optional_user
from ..serializers import serialize_post, serialize_posts
from ..storage import is_local_media_url

router = APIRouter(prefix="/api/posts", tags=["posts"])


def _get_post_or_404(db: Session, post_id: int) -> Post:
    post = db.get(Post, post_id)
    if post is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Post not found")
    return post


def _original(db: Session, post_id: int) -> Post:
    """Likes, replies and reposts always target the original, never a repost row."""
    post = _get_post_or_404(db, post_id)
    return post.repost_of if post.repost_of is not None else post


def _bump(db: Session, post_id: int, column, delta: int) -> None:
    db.execute(update(Post).where(Post.id == post_id).values({column: column + delta}))


@router.post("", response_model=PostOut, status_code=status.HTTP_201_CREATED)
def create_post(body: PostIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    content = body.content.strip()
    if not content and not body.media_url:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Post can't be empty")
    if body.media_url and not is_local_media_url(body.media_url):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "media_url must be an uploaded file")

    reply_to_id = None
    if body.reply_to_id is not None:
        reply_to_id = _original(db, body.reply_to_id).id

    post = Post(author_id=user.id, content=content, media_url=body.media_url, reply_to_id=reply_to_id)
    db.add(post)
    if reply_to_id is not None:
        _bump(db, reply_to_id, Post.reply_count, 1)
    db.commit()
    invalidate_feed(user.id)
    db.refresh(post)
    return serialize_post(db, post, user)


@router.get("", response_model=PostPage)
def explore(
    cursor: str | None = None,
    limit: int = Depends(page_limit),
    db: Session = Depends(get_db),
    viewer: User | None = Depends(get_optional_user),
):
    """Everyone's latest top-level posts, newest first."""
    stmt = select(Post).where(Post.reply_to_id.is_(None), Post.repost_of_id.is_(None))
    before = parse_cursor(cursor)
    if before is not None:
        stmt = stmt.where(Post.id < before)
    posts = db.scalars(stmt.order_by(Post.id.desc()).limit(limit + 1)).unique().all()
    return PostPage(
        items=serialize_posts(db, posts[:limit], viewer),
        next_cursor=str(posts[limit - 1].id) if len(posts) > limit else None,
    )


@router.get("/{post_id}", response_model=PostOut)
def get_post(
    post_id: int, db: Session = Depends(get_db), viewer: User | None = Depends(get_optional_user)
):
    return serialize_post(db, _get_post_or_404(db, post_id), viewer)


@router.get("/{post_id}/thread", response_model=list[PostOut])
def get_ancestors(
    post_id: int, db: Session = Depends(get_db), viewer: User | None = Depends(get_optional_user)
):
    """The chain of posts this one replies to, oldest first (excluding the post itself)."""
    post = _get_post_or_404(db, post_id)
    chain: list[Post] = []
    seen = {post.id}
    while post.reply_to_id is not None and post.reply_to_id not in seen and len(chain) < 50:
        parent = db.get(Post, post.reply_to_id)
        if parent is None:
            break
        chain.append(parent)
        seen.add(parent.id)
        post = parent
    return serialize_posts(db, list(reversed(chain)), viewer)


@router.get("/{post_id}/replies", response_model=PostPage)
def get_replies(
    post_id: int,
    cursor: str | None = None,
    limit: int = Depends(page_limit),
    db: Session = Depends(get_db),
    viewer: User | None = Depends(get_optional_user),
):
    """Direct replies, oldest first so conversations read top to bottom."""
    _get_post_or_404(db, post_id)
    stmt = select(Post).where(Post.reply_to_id == post_id)
    after = parse_cursor(cursor)
    if after is not None:
        stmt = stmt.where(Post.id > after)
    posts = db.scalars(stmt.order_by(Post.id.asc()).limit(limit + 1)).unique().all()
    return PostPage(
        items=serialize_posts(db, posts[:limit], viewer),
        next_cursor=str(posts[limit - 1].id) if len(posts) > limit else None,
    )


@router.delete("/{post_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_post(post_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    post = _get_post_or_404(db, post_id)
    if post.author_id != user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You can only delete your own posts")
    if post.reply_to_id is not None:
        _bump(db, post.reply_to_id, Post.reply_count, -1)
    if post.repost_of_id is not None:
        _bump(db, post.repost_of_id, Post.repost_count, -1)
    # Replies, reposts and likes of this post cascade in the database.
    db.execute(delete(Post).where(Post.id == post.id))
    db.commit()
    invalidate_feed(user.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{post_id}/like", response_model=PostOut)
def like(post_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    post = _original(db, post_id)
    if db.get(Like, (user.id, post.id)) is None:
        db.add(Like(user_id=user.id, post_id=post.id))
        _bump(db, post.id, Post.like_count, 1)
        db.commit()
        db.refresh(post)
    return serialize_post(db, post, user)


@router.delete("/{post_id}/like", response_model=PostOut)
def unlike(post_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    post = _original(db, post_id)
    result = db.execute(delete(Like).where(Like.user_id == user.id, Like.post_id == post.id))
    if result.rowcount:
        _bump(db, post.id, Post.like_count, -1)
        db.commit()
        db.refresh(post)
    return serialize_post(db, post, user)


def _find_repost(db: Session, user_id: int, original_id: int) -> Post | None:
    return db.scalar(
        select(Post).where(Post.author_id == user_id, Post.repost_of_id == original_id)
    )


@router.post("/{post_id}/repost", response_model=PostOut)
def repost(post_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    post = _original(db, post_id)
    if _find_repost(db, user.id, post.id) is None:
        db.add(Post(author_id=user.id, repost_of_id=post.id))
        _bump(db, post.id, Post.repost_count, 1)
        db.commit()
        invalidate_feed(user.id)
        db.refresh(post)
    return serialize_post(db, post, user)


@router.delete("/{post_id}/repost", response_model=PostOut)
def unrepost(post_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    post = _original(db, post_id)
    existing = _find_repost(db, user.id, post.id)
    if existing is not None:
        db.execute(delete(Post).where(Post.id == existing.id))
        _bump(db, post.id, Post.repost_count, -1)
        db.commit()
        invalidate_feed(user.id)
        db.refresh(post)
    return serialize_post(db, post, user)
