"""东财指数服务：目录 / 行情 / K 线 / 分类列表，带短 TTL 缓存。"""

from __future__ import annotations

import threading
from typing import Any

from core.cache import TtlCache

from exponent.eastmoney.catalog import catalog
from exponent.eastmoney.fetcher import fetch_quotes
from exponent.eastmoney.kline import fetch_kline
from exponent.eastmoney.list import list_indices, search_indices

_SPOT_TTL = 60.0
_SERIES_TTL = 30 * 60.0
_LIST_TTL = 6 * 60 * 60.0


class ExponentService:
    def __init__(self) -> None:
        self._meta_lock = threading.Lock()
        self._key_locks: dict[str, threading.Lock] = {}
        self._spot_cache = TtlCache(_SPOT_TTL)
        self._series_cache = TtlCache(_SERIES_TTL)
        self._list_cache = TtlCache(_LIST_TTL)

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
        return catalog()

    def quotes(
        self,
        codes: list[str] | None = None,
        *,
        force: bool = False,
    ) -> dict[str, Any]:
        key = "quotes:" + (",".join(codes) if codes else "catalog")
        if force:
            data = fetch_quotes(codes)
            self._spot_cache.put(key, data)
            return data
        return self._cached(self._spot_cache, key, lambda: fetch_quotes(codes))

    def kline(
        self,
        code: str,
        *,
        period: str = "day",
        limit: int = 120,
        beg: str = "",
        end: str = "",
        force: bool = False,
    ) -> dict[str, Any]:
        key = f"kline:{code}:{period}:{limit}:{beg}:{end}"
        if force:
            data = fetch_kline(code, period=period, limit=limit, beg=beg, end=end)
            self._series_cache.put(key, data)
            return data
        return self._cached(
            self._series_cache,
            key,
            lambda: fetch_kline(code, period=period, limit=limit, beg=beg, end=end),
        )

    def list_all(
        self,
        categories: list[str] | None = None,
        *,
        force: bool = False,
    ) -> dict[str, Any]:
        key = "list:" + (",".join(categories) if categories else "default")
        if force:
            data = list_indices(categories)
            self._list_cache.put(key, data)
            return data
        return self._cached(self._list_cache, key, lambda: list_indices(categories))

    def search(self, keyword: str, *, limit: int = 20) -> dict[str, Any]:
        return search_indices(keyword, limit=limit)


service = ExponentService()
