from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Generic, TypeVar


T = TypeVar("T")


@dataclass
class CacheEntry(Generic[T]):
    value: T
    expires_at: datetime


class MemoryCache(Generic[T]):
    def __init__(self, ttl_seconds: int) -> None:
        self.ttl_seconds = ttl_seconds
        self._entries: dict[str, CacheEntry[T]] = {}

    def get(self, key: str) -> T | None:
        entry = self._entries.get(key)
        if entry is None:
            return None
        if entry.expires_at <= datetime.now(timezone.utc):
            return None
        return entry.value

    def get_stale(self, key: str) -> T | None:
        entry = self._entries.get(key)
        return entry.value if entry else None

    def set(self, key: str, value: T) -> None:
        self._entries[key] = CacheEntry(
            value=value,
            expires_at=datetime.now(timezone.utc) + timedelta(seconds=self.ttl_seconds),
        )

    def clear(self) -> None:
        self._entries.clear()
