from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..feed_cache import invalidate_feed
from ..models import Follow, Like, Post, User
from ..pagination import page_limit, parse_cursor
from ..schemas import PostPage, ProfileOut, UserOut, UserPage, UserUpdateIn
from ..security import get_current_user, get_optional_user
from ..serializers import serialize_posts
from ..storage import is_local_media_url
from .auth import find_user

router = APIRouter(prefix="/api/users", tags=["users"])


def _get_user_or_404(db: Session, username: str) -> User:
    user = find_user(db, username)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    return user


def _is_following(db: Session, follower_id: int, followee_id: int) -> bool:
    return db.get(Follow, (follower_id, followee_id)) is not None


def build_profile(db: Session, user: User, viewer: User | None) -> ProfileOut:
    follower_count = db.scalar(select(func.count()).where(Follow.followee_id == user.id))
    following_count = db.scalar(select(func.count()).where(Follow.follower_id == user.id))
    post_count = db.scalar(
        select(func.count()).where(Post.author_id == user.id, Post.repost_of_id.is_(None))
    )
    return ProfileOut(
        **UserOut.model_validate(user).model_dump(),
        follower_count=follower_count or 0,
        following_count=following_count or 0,
        post_count=post_count or 0,
        is_following=bool(viewer) and _is_following(db, viewer.id, user.id),
        follows_you=bool(viewer) and _is_following(db, user.id, viewer.id),
    )


@router.get("", response_model=list[UserOut])
def search_users(
    q: str = Query("", max_length=50),
    limit: int = Query(20, ge=1, le=50),
    db: Session = Depends(get_db),
):
    stmt = select(User).order_by(User.id.desc()).limit(limit)
    if q.strip():
        pattern = f"%{q.strip().lower()}%"
        stmt = stmt.where(
            or_(func.lower(User.username).like(pattern), func.lower(User.display_name).like(pattern))
        )
    return db.scalars(stmt).all()


@router.get("/suggestions", response_model=list[UserOut])
def who_to_follow(
    limit: int = Query(5, ge=1, le=20),
    db: Session = Depends(get_db),
    viewer: User = Depends(get_current_user),
):
    """Users the viewer doesn't follow yet, most-followed first."""
    already = select(Follow.followee_id).where(Follow.follower_id == viewer.id)
    followers = (
        select(Follow.followee_id, func.count().label("n"))
        .group_by(Follow.followee_id)
        .subquery()
    )
    stmt = (
        select(User)
        .outerjoin(followers, followers.c.followee_id == User.id)
        .where(User.id != viewer.id, User.id.not_in(already))
        .order_by(func.coalesce(followers.c.n, 0).desc(), User.id.desc())
        .limit(limit)
    )
    return db.scalars(stmt).all()


@router.patch("/me", response_model=ProfileOut)
def update_me(
    body: UserUpdateIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    changes = body.model_dump(exclude_unset=True)
    if changes.get("avatar_url") and not is_local_media_url(changes["avatar_url"]):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "avatar_url must be an uploaded file")
    if "display_name" in changes:
        changes["display_name"] = (changes["display_name"] or "").strip() or user.username
    if "bio" in changes:
        changes["bio"] = (changes["bio"] or "").strip()
    for field, value in changes.items():
        setattr(user, field, value)
    db.commit()
    return build_profile(db, user, user)


@router.get("/{username}", response_model=ProfileOut)
def get_profile(
    username: str,
    db: Session = Depends(get_db),
    viewer: User | None = Depends(get_optional_user),
):
    return build_profile(db, _get_user_or_404(db, username), viewer)


@router.post("/{username}/follow", response_model=ProfileOut)
def follow(username: str, db: Session = Depends(get_db), viewer: User = Depends(get_current_user)):
    target = _get_user_or_404(db, username)
    if target.id == viewer.id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "You can't follow yourself")
    if not _is_following(db, viewer.id, target.id):
        db.add(Follow(follower_id=viewer.id, followee_id=target.id))
        db.commit()
        invalidate_feed(viewer.id)
    return build_profile(db, target, viewer)


@router.delete("/{username}/follow", response_model=ProfileOut)
def unfollow(
    username: str, db: Session = Depends(get_db), viewer: User = Depends(get_current_user)
):
    target = _get_user_or_404(db, username)
    row = db.get(Follow, (viewer.id, target.id))
    if row is not None:
        db.delete(row)
        db.commit()
        invalidate_feed(viewer.id)
    return build_profile(db, target, viewer)


def _user_page(db: Session, stmt, cursor: str | None, limit: int) -> UserPage:
    before = parse_cursor(cursor)
    if before is not None:
        stmt = stmt.where(User.id < before)
    rows = db.scalars(stmt.order_by(User.id.desc()).limit(limit + 1)).all()
    return UserPage(
        items=[UserOut.model_validate(u) for u in rows[:limit]],
        next_cursor=str(rows[limit - 1].id) if len(rows) > limit else None,
    )


@router.get("/{username}/followers", response_model=UserPage)
def followers(
    username: str,
    cursor: str | None = None,
    limit: int = Depends(page_limit),
    db: Session = Depends(get_db),
):
    user = _get_user_or_404(db, username)
    stmt = select(User).join(Follow, Follow.follower_id == User.id).where(
        Follow.followee_id == user.id
    )
    return _user_page(db, stmt, cursor, limit)


@router.get("/{username}/following", response_model=UserPage)
def following(
    username: str,
    cursor: str | None = None,
    limit: int = Depends(page_limit),
    db: Session = Depends(get_db),
):
    user = _get_user_or_404(db, username)
    stmt = select(User).join(Follow, Follow.followee_id == User.id).where(
        Follow.follower_id == user.id
    )
    return _user_page(db, stmt, cursor, limit)


@router.get("/{username}/posts", response_model=PostPage)
def user_posts(
    username: str,
    cursor: str | None = None,
    replies: bool = False,
    limit: int = Depends(page_limit),
    db: Session = Depends(get_db),
    viewer: User | None = Depends(get_optional_user),
):
    """A user's timeline: their posts and reposts (and replies, if replies=true)."""
    user = _get_user_or_404(db, username)
    stmt = select(Post).where(Post.author_id == user.id)
    if not replies:
        stmt = stmt.where(Post.reply_to_id.is_(None))
    before = parse_cursor(cursor)
    if before is not None:
        stmt = stmt.where(Post.id < before)
    posts = db.scalars(stmt.order_by(Post.id.desc()).limit(limit + 1)).unique().all()
    return PostPage(
        items=serialize_posts(db, posts[:limit], viewer),
        next_cursor=str(posts[limit - 1].id) if len(posts) > limit else None,
    )


@router.get("/{username}/likes", response_model=PostPage)
def user_likes(
    username: str,
    cursor: str | None = None,
    limit: int = Depends(page_limit),
    db: Session = Depends(get_db),
    viewer: User | None = Depends(get_optional_user),
):
    user = _get_user_or_404(db, username)
    stmt = select(Post).join(Like, Like.post_id == Post.id).where(Like.user_id == user.id)
    before = parse_cursor(cursor)
    if before is not None:
        stmt = stmt.where(Post.id < before)
    posts = db.scalars(stmt.order_by(Post.id.desc()).limit(limit + 1)).unique().all()
    return PostPage(
        items=serialize_posts(db, posts[:limit], viewer),
        next_cursor=str(posts[limit - 1].id) if len(posts) > limit else None,
    )

