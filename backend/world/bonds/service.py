"""国债与利率数据服务。"""

from __future__ import annotations

import threading
from typing import Any

from core.cache import TtlCache

from world.bonds.catalog import BONDS, RATES
from world.bonds.fetcher import fetch_bond_region, fetch_bonds
from world.bonds.rates import fetch_rate_series, fetch_rates

_SERIES_TTL = 30 * 60.0


class BondsService:
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
        return {"bonds": BONDS, "rates": RATES}

    def bonds(
        self,
        *,
        region: str | None = None,
        limit: int = 120,
        force: bool = False,
    ) -> dict[str, Any]:
        if region:
            if region not in BONDS:
                raise ValueError(f"未知地区: {region}")
            key = f"bonds:{region}:{limit}"
            if force:
                data = fetch_bond_region(region, limit=limit)
                self._cache.put(key, data)
                return data
            return self._cached(key, lambda: fetch_bond_region(region, limit=limit))

        key = f"bonds:all:{limit}"
        if force:
            data = fetch_bonds(limit=limit)
            self._cache.put(key, data)
            return data
        return self._cached(key, lambda: fetch_bonds(limit=limit))

    def rates(
        self,
        *,
        region: str | None = None,
        limit: int = 36,
        force: bool = False,
    ) -> dict[str, Any]:
        if region:
            if region not in RATES:
                raise ValueError(f"未知地区: {region}")
            key = f"rates:{region}:{limit}"
            if force:
                data = fetch_rate_series(region, limit=limit)
                self._cache.put(key, data)
                return data
            return self._cached(key, lambda: fetch_rate_series(region, limit=limit))

        key = f"rates:all:{limit}"
        if force:
            data = fetch_rates(limit=limit)
            self._cache.put(key, data)
            return data
        return self._cached(key, lambda: fetch_rates(limit=limit))


service = BondsService()
