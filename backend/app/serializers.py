"""Turn Post rows into PostOut, batching the per-viewer lookups."""

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Like, Post, User
from .schemas import PostOut, UserOut


def serialize_posts(db: Session, posts: Sequence[Post], viewer: User | None) -> list[PostOut]:
    if not posts:
        return []

    # The posts whose counters/likes matter: each post itself, plus the original of a repost.
    related = {p.id: p for p in posts}
    for p in posts:
        if p.repost_of is not None:
            related[p.repost_of.id] = p.repost_of
    ids = list(related)

    liked: set[int] = set()
    reposted: set[int] = set()
    if viewer is not None:
        liked = set(
            db.scalars(select(Like.post_id).where(Like.user_id == viewer.id, Like.post_id.in_(ids)))
        )
        reposted = set(
            db.scalars(
                select(Post.repost_of_id).where(
                    Post.author_id == viewer.id, Post.repost_of_id.in_(ids)
                )
            )
        )

    parent_ids = {p.reply_to_id for p in related.values() if p.reply_to_id is not None}
    reply_usernames: dict[int, str] = {}
    if parent_ids:
        reply_usernames = dict(
            db.execute(
                select(Post.id, User.username)
                .join(User, User.id == Post.author_id)
                .where(Post.id.in_(parent_ids))
            ).all()
        )

    def one(p: Post, depth: int = 0) -> PostOut:
        return PostOut(
            id=p.id,
            author=UserOut.model_validate(p.author),
            content=p.content,
            media_url=p.media_url,
            reply_to_id=p.reply_to_id,
            reply_to_username=reply_usernames.get(p.reply_to_id) if p.reply_to_id else None,
            like_count=p.like_count,
            reply_count=p.reply_count,
            repost_count=p.repost_count,
            created_at=p.created_at,
            liked_by_me=p.id in liked,
            reposted_by_me=p.id in reposted,
            repost_of=one(p.repost_of, depth + 1) if p.repost_of is not None and depth == 0 else None,
        )

    return [one(p) for p in posts]


def serialize_post(db: Session, post: Post, viewer: User | None) -> PostOut:
    return serialize_posts(db, [post], viewer)[0]
