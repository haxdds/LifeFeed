"""Home feed: posts and reposts from the people you follow (and yourself).

- chronological: newest first, keyset-paginated by post id.
- ranked: recent candidates scored by engagement with time decay. The ordered id
  list is cached per user for FEED_CACHE_TTL_SECONDS and paginated by offset.
"""

from datetime import datetime, timedelta, timezone
from enum import Enum

from fastapi import APIRouter, Depends
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from .. import config
from ..cache import cache
from ..db import get_db
from ..feed_cache import ranked_feed_key
from ..models import Follow, Post, User
from ..pagination import page_limit, parse_cursor
from ..schemas import PostPage
from ..security import get_current_user
from ..serializers import serialize_posts

router = APIRouter(prefix="/api/feed", tags=["feed"])


class FeedMode(str, Enum):
    chronological = "chronological"
    ranked = "ranked"


def _home_posts(user_id: int):
    followees = select(Follow.followee_id).where(Follow.follower_id == user_id)
    return select(Post).where(
        or_(Post.author_id == user_id, Post.author_id.in_(followees)),
        Post.reply_to_id.is_(None),
    )


def score(likes: int, reposts: int, replies: int, age_hours: float) -> float:
    """Hacker-News-style gravity: engagement divided by a power of age."""
    return (1 + likes + 2 * reposts + replies) / (age_hours + 2) ** 1.5


def rank_post_ids(db: Session, user_id: int, now: datetime | None = None) -> list[int]:
    now = now or datetime.now(timezone.utc)
    since = now - timedelta(days=config.RANKED_FEED_WINDOW_DAYS)
    candidates = db.scalars(
        _home_posts(user_id)
        .where(Post.created_at >= since)
        .order_by(Post.id.desc())
        .limit(config.RANKED_FEED_MAX_CANDIDATES)
    ).all()

    # Score each original once; if several people you follow reposted it, keep the best entry.
    best: dict[int, tuple[float, int]] = {}
    for post in candidates:
        original = post.repost_of or post
        age_hours = max((now - post.created_at).total_seconds() / 3600, 0)
        s = score(original.like_count, original.repost_count, original.reply_count, age_hours)
        if original.id not in best or s > best[original.id][0]:
            best[original.id] = (s, post.id)

    ranked = sorted(best.values(), key=lambda pair: (pair[0], pair[1]), reverse=True)
    return [post_id for _, post_id in ranked]


@router.get("", response_model=PostPage)
def home_feed(
    mode: FeedMode = FeedMode.chronological,
    cursor: str | None = None,
    limit: int = Depends(page_limit),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    position = parse_cursor(cursor)

    if mode is FeedMode.chronological:
        stmt = _home_posts(user.id)
        if position is not None:
            stmt = stmt.where(Post.id < position)
        posts = db.scalars(stmt.order_by(Post.id.desc()).limit(limit + 1)).all()
        return PostPage(
            items=serialize_posts(db, posts[:limit], user),
            next_cursor=str(posts[limit - 1].id) if len(posts) > limit else None,
        )

    # Ranked: the first page always recomputes if the cache is cold; later pages
    # reuse the cached order so pagination stays stable while scrolling.
    key = ranked_feed_key(user.id)
    ids = cache.get(key)
    if ids is None:
        ids = rank_post_ids(db, user.id)
        cache.set(key, ids, config.FEED_CACHE_TTL_SECONDS)

    offset = position or 0
    page_ids = ids[offset : offset + limit]
    by_id = {p.id: p for p in db.scalars(select(Post).where(Post.id.in_(page_ids))).all()}
    posts = [by_id[i] for i in page_ids if i in by_id]  # skip anything deleted since caching
    next_offset = offset + limit
    return PostPage(
        items=serialize_posts(db, posts, user),
        next_cursor=str(next_offset) if next_offset < len(ids) else None,
    )
