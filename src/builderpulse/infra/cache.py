"""
BuilderPulse 缓存层 — cache.py
支持内存缓存 + Redis 缓存 (可切换)。

用法:
    from builderpulse.infra.cache import Cache
    cache = Cache()  # 内存缓存
    cache = Cache(redis_url="redis://localhost:6379")  # Redis 缓存
    cache.set("key", "value", ttl=3600)
    value = cache.get("key")
"""

import hashlib
import json
import time
from typing import Any, Optional


class MemoryCache:
    """内存缓存 (TTL eviction)。"""

    def __init__(self, max_size: int = 1000):
        self.max_size = max_size
        self._cache: dict[str, tuple[Any, float]] = {}

    def get(self, key: str) -> Optional[Any]:
        if key in self._cache:
            value, expire_at = self._cache[key]
            if expire_at > time.time():
                return value
            else:
                del self._cache[key]
        return None

    def set(self, key: str, value: Any, ttl: int = 3600) -> None:
        if len(self._cache) >= self.max_size:
            # 简单 LRU: 删除最旧的
            oldest_key = min(self._cache, key=lambda k: self._cache[k][1])
            del self._cache[oldest_key]
        self._cache[key] = (value, time.time() + ttl)

    def delete(self, key: str) -> None:
        self._cache.pop(key, None)

    def clear(self) -> None:
        self._cache.clear()

    def size(self) -> int:
        return len(self._cache)


class RedisCache:
    """Redis 缓存 (带 key prefix)。"""

    PREFIX = "bp:"

    def __init__(self, redis_url: str = "redis://localhost:6379"):
        import redis
        self._client = redis.from_url(redis_url)

    def _prefixed(self, key: str) -> str:
        return f"{self.PREFIX}{key}"

    def get(self, key: str) -> Optional[Any]:
        value = self._client.get(self._prefixed(key))
        if value:
            return json.loads(value)
        return None

    def set(self, key: str, value: Any, ttl: int = 3600) -> None:
        self._client.setex(self._prefixed(key), ttl, json.dumps(value))

    def delete(self, key: str) -> None:
        self._client.delete(self._prefixed(key))

    def clear(self) -> None:
        """只删除 BuilderPulse 的 key (带 prefix), 不影响其他应用。"""
        for key in self._client.scan_iter(f"{self.PREFIX}*"):
            self._client.delete(key)

    def size(self) -> int:
        count = 0
        for _ in self._client.scan_iter(f"{self.PREFIX}*"):
            count += 1
        return count


class Cache:
    """统一缓存接口 (自动切换内存/Redis)。"""

    def __init__(self, redis_url: str = None, max_size: int = 1000):
        if redis_url:
            try:
                self._backend = RedisCache(redis_url)
                self._type = "redis"
            except Exception:
                self._backend = MemoryCache(max_size)
                self._type = "memory"
        else:
            self._backend = MemoryCache(max_size)
            self._type = "memory"

    def get(self, key: str) -> Optional[Any]:
        return self._backend.get(key)

    def set(self, key: str, value: Any, ttl: int = 3600) -> None:
        self._backend.set(key, value, ttl)

    def delete(self, key: str) -> None:
        self._backend.delete(key)

    def clear(self) -> None:
        self._backend.clear()

    def size(self) -> int:
        return self._backend.size()

    @property
    def type(self) -> str:
        return self._type


def make_cache_key(*args) -> str:
    """生成缓存 key。"""
    raw = ":".join(str(a) for a in args)
    return hashlib.md5(raw.encode()).hexdigest()
