from .cache import cache


def ranked_feed_key(user_id: int) -> str:
    return f"feed:ranked:{user_id}"


def invalidate_feed(user_id: int) -> None:
    cache.delete(ranked_feed_key(user_id))
