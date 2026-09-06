import time
import threading
from typing import Any, Optional, Callable
from functools import wraps

class TtlCache:
    """
    Thread-safe In-Memory Key-Value Cache with Time-To-Live (TTL) expiration.
    Used for caching immutable or rarely changing dictionary lookups (products, locations, recipes).
    """

    def __init__(self, default_ttl_seconds: int = 60):
        self._cache = {}
        self._lock = threading.Lock()
        self._default_ttl = default_ttl_seconds

    def get(self, key: str) -> Optional[Any]:
        with self._lock:
            if key not in self._cache:
                return None
            val, expiry = self._cache[key]
            if time.time() > expiry:
                del self._cache[key]
                return None
            return val

    def set(self, key: str, value: Any, ttl_seconds: Optional[int] = None) -> None:
        ttl = ttl_seconds if ttl_seconds is not None else self._default_ttl
        with self._lock:
            self._cache[key] = (value, time.time() + ttl)

    def delete(self, key: str) -> bool:
        with self._lock:
            return bool(self._cache.pop(key, None))

    def clear(self) -> None:
        with self._lock:
            self._cache.clear()

# Global default instance
global_cache = TtlCache(default_ttl_seconds=90)

def cached_with_ttl(ttl_seconds: int = 60, key_prefix: str = ""):
    """Decorator to cache pure lookup function results with TTL."""
    def decorator(fn: Callable):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            cache_key = f"{key_prefix or fn.__name__}:{str(args)}:{str(kwargs)}"
            cached_val = global_cache.get(cache_key)
            if cached_val is not None:
                return cached_val
            result = fn(*args, **kwargs)
            if result is not None:
                global_cache.set(cache_key, result, ttl_seconds=ttl_seconds)
            return result
        return wrapper
    return decorator
