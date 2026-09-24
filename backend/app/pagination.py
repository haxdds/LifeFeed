from fastapi import HTTPException, Query, status


def page_limit(limit: int = Query(20, ge=1, le=100)) -> int:
    return limit


def parse_cursor(cursor: str | None) -> int | None:
    """Cursors are opaque to clients; here they're just the last id (or offset) seen."""
    if cursor is None or cursor == "":
        return None
    try:
        value = int(cursor)
    except ValueError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid cursor")
    if value < 0:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid cursor")
    return value
