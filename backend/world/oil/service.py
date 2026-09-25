"""原油数据服务。"""

from __future__ import annotations

import threading
from typing import Any

from core.cache import TtlCache

from world.oil.catalog import OIL
from world.oil.fetcher import fetch_oil
from world.oil.kline import fetch_oil_klines

_SPOT_TTL = 60.0
_SERIES_TTL = 30 * 60.0


class OilService:
    def __init__(self) -> None:
        self._meta_lock = threading.Lock()
        self._key_locks: dict[str, threading.Lock] = {}
        self._cache = TtlCache(_SPOT_TTL)
        self._series_cache = TtlCache(_SERIES_TTL)

    def _lock_for(self, key: str) -> threading.Lock:
        with self._meta_lock:
            lock = self._key_locks.get(key)
            if lock is None:
                lock = threading.Lock()
                self._key_locks[key] = lock
            return lock

    def _cached(self, cache: TtlCache, key: str, loader):
        hit = cache.get(key)
        if hit is not None:
            return hit
        with self._lock_for(key):
            hit = cache.get(key)
            if hit is not None:
                return hit
            data = loader()
            cache.put(key, data)
            return data

    def catalog(self) -> list[dict[str, str]]:
        return OIL

    def quotes(self, *, force: bool = False) -> dict[str, Any]:
        if force:
            data = fetch_oil()
            self._cache.put("oil", data)
            return data
        return self._cached(self._cache, "oil", fetch_oil)

    def klines(self, *, limit: int = 90, force: bool = False) -> dict[str, Any]:
        key = f"oil-klines:{limit}"
        if force:
            data = fetch_oil_klines(limit=limit)
            self._series_cache.put(key, data)
            return data
        return self._cached(
            self._series_cache,
            key,
            lambda: fetch_oil_klines(limit=limit),
        )


service = OilService()
