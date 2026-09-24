"""Tiny key/value cache: Redis when REDIS_URL is set, otherwise in-process memory."""

import json
import threading
import time
from typing import Any, Protocol

from . import config


class Cache(Protocol):
    def get(self, key: str) -> Any | None: ...
    def set(self, key: str, value: Any, ttl: int) -> None: ...
    def delete(self, *keys: str) -> None: ...


class MemoryCache:
    def __init__(self) -> None:
        self._data: dict[str, tuple[float, Any]] = {}
        self._lock = threading.Lock()

    def get(self, key: str) -> Any | None:
        with self._lock:
            entry = self._data.get(key)
            if entry is None:
                return None
            expires_at, value = entry
            if expires_at < time.monotonic():
                del self._data[key]
                return None
            return value

    def set(self, key: str, value: Any, ttl: int) -> None:
        with self._lock:
            self._data[key] = (time.monotonic() + ttl, value)

    def delete(self, *keys: str) -> None:
        with self._lock:
            for key in keys:
                self._data.pop(key, None)


class RedisCache:
    def __init__(self, url: str) -> None:
        import redis  # optional dependency: `uv sync --extra redis`

        self._client = redis.Redis.from_url(url)

    def get(self, key: str) -> Any | None:
        raw = self._client.get(key)
        return None if raw is None else json.loads(raw)

    def set(self, key: str, value: Any, ttl: int) -> None:
        self._client.set(key, json.dumps(value), ex=ttl)

    def delete(self, *keys: str) -> None:
        if keys:
            self._client.delete(*keys)


cache: Cache = RedisCache(config.REDIS_URL) if config.REDIS_URL else MemoryCache()
