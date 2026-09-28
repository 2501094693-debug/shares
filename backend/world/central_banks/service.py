"""主要国家央行利率数据服务。"""

from __future__ import annotations

import threading
from typing import Any

from core.cache import TtlCache

from world.central_banks.catalog import CENTRAL_BANKS
from world.central_banks.fetcher import (
    fetch_central_bank_series,
    fetch_central_banks,
)

_SERIES_TTL = 30 * 60.0


class CentralBanksService:
    def __init__(self) -> None:
        self._meta_lock = threading.Lock()
        self._key_locks: dict[str, threading.Lock] = {}
        self._cache = TtlCache(_SERIES_TTL)

    def _lock_for(self, key: str) -> threading.Lock:
        with self._meta_lock:
            lock = self._key_locks.get(key)
            if lock is None:
                lock = threading.Lock()
                self._key_locks[key] = lock
            return lock

    def _cached(self, key: str, loader):
        hit = self._cache.get(key)
        if hit is not None:
            return hit
        with self._lock_for(key):
            hit = self._cache.get(key)
            if hit is not None:
                return hit
            data = loader()
            self._cache.put(key, data)
            return data

    def catalog(self) -> dict[str, Any]:
        return {"central_banks": CENTRAL_BANKS}

    def central_bank(
        self,
        *,
        region: str,
        limit: int = 60,
        force: bool = False,
    ) -> dict[str, Any]:
        if region not in CENTRAL_BANKS:
            raise ValueError(f"未知央行: {region}")
        key = f"central_bank:{region}:{limit}"
        if force:
            data = fetch_central_bank_series(region, limit=limit)
            self._cache.put(key, data)
            return data
        return self._cached(key, lambda: fetch_central_bank_series(region, limit=limit))

    def all_central_banks(
        self,
        *,
        limit: int = 60,
        force: bool = False,
    ) -> dict[str, Any]:
        key = f"central_banks:all:{limit}"
        if force:
            data = fetch_central_banks(limit=limit)
            self._cache.put(key, data)
            return data
        return self._cached(key, lambda: fetch_central_banks(limit=limit))


service = CentralBanksService()
