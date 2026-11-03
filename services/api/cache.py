"""Small bounded, thread-safe in-process cache with TTL and invalidation."""

from collections import OrderedDict
from copy import deepcopy
from threading import RLock
from time import monotonic
from typing import Generic, Hashable, TypeVar


Key = TypeVar("Key", bound=Hashable)
Value = TypeVar("Value")


class TTLCache(Generic[Key, Value]):
    def __init__(self, ttl_seconds: float, max_entries: int = 512) -> None:
        if ttl_seconds <= 0 or max_entries <= 0:
            raise ValueError("ttl_seconds and max_entries must be positive")
        self._ttl_seconds = ttl_seconds
        self._max_entries = max_entries
        self._entries: OrderedDict[Key, tuple[float, Value]] = OrderedDict()
        self._generation = 0
        self._lock = RLock()

    def generation(self) -> int:
        with self._lock:
            return self._generation

    def get(self, key: Key) -> Value | None:
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                return None
            expires_at, value = entry
            if expires_at <= monotonic():
                del self._entries[key]
                return None
            self._entries.move_to_end(key)
            return deepcopy(value)

    def set(self, key: Key, value: Value, generation: int) -> None:
        with self._lock:
            if generation != self._generation:
                return
            now = monotonic()
            expired_keys = [
                cache_key
                for cache_key, (expires_at, _) in self._entries.items()
                if expires_at <= now
            ]
            for cache_key in expired_keys:
                del self._entries[cache_key]
            self._entries.pop(key, None)
            while len(self._entries) >= self._max_entries:
                self._entries.popitem(last=False)
            self._entries[key] = (now + self._ttl_seconds, deepcopy(value))

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()
            self._generation += 1