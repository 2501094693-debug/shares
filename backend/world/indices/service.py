"""指数数据服务。"""

from __future__ import annotations

import threading
from typing import Any

from core.cache import TtlCache

from world.indices.catalog import INDICES, REGIONS
from world.indices.fetcher import fetch_indices
from world.indices.kline import fetch_index_klines

_SPOT_TTL = 60.0
_SERIES_TTL = 30 * 60.0


class IndicesService:
    def __init__(self) -> None:
        self._meta_lock = threading.Lock()
        self._key_locks: dict[str, threading.Lock] = {}
        self._spot_cache = TtlCache(_SPOT_TTL)
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

    def catalog(self) -> dict[str, Any]:
        return {"regions": REGIONS, "indices": INDICES}

    def quotes(self, *, force: bool = False) -> dict[str, Any]:
        if force:
            data = fetch_indices()
            self._spot_cache.put("indices", data)
            return data
        return self._cached(self._spot_cache, "indices", fetch_indices)

    def klines(self, *, limit: int = 90, force: bool = False) -> dict[str, Any]:
        key = f"index-klines:{limit}"
        if force:
            data = fetch_index_klines(limit=limit)
            self._series_cache.put(key, data)
            return data
        return self._cached(
            self._series_cache,
            key,
            lambda: fetch_index_klines(limit=limit),
        )


service = IndicesService()
