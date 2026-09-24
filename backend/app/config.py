"""Runtime settings, read from environment variables.

Every setting has a local default so the app runs with zero setup:
SQLite for the database, an in-process cache, and a local folder for media.
"""

import os
import secrets
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

DATABASE_URL = os.environ.get("DATABASE_URL", f"sqlite:///{BASE_DIR / 'lifefeed.db'}")

# Optional. When unset, an in-memory cache is used instead of Redis.
REDIS_URL = os.environ.get("REDIS_URL")

MEDIA_DIR = Path(os.environ.get("MEDIA_DIR", BASE_DIR / "media"))
MAX_UPLOAD_BYTES = int(os.environ.get("MAX_UPLOAD_BYTES", 5 * 1024 * 1024))


def _load_secret_key() -> str:
    """Use SECRET_KEY if set; otherwise generate one once and keep it in .secret_key."""
    if key := os.environ.get("SECRET_KEY"):
        return key
    path = BASE_DIR / ".secret_key"
    if not path.exists():
        path.write_text(secrets.token_urlsafe(48))
        path.chmod(0o600)
    return path.read_text().strip()


SECRET_KEY = _load_secret_key()
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_TTL_MINUTES = int(os.environ.get("ACCESS_TOKEN_TTL_MINUTES", 60 * 24 * 7))

FEED_CACHE_TTL_SECONDS = int(os.environ.get("FEED_CACHE_TTL_SECONDS", 60))
RANKED_FEED_WINDOW_DAYS = int(os.environ.get("RANKED_FEED_WINDOW_DAYS", 7))
RANKED_FEED_MAX_CANDIDATES = 500

HOST = os.environ.get("HOST", "127.0.0.1")
PORT = int(os.environ.get("PORT", 8000))
