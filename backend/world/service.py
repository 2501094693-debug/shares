"""全球市场数据服务（指数 / 利率 / 国债 / 原油）。"""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from core.cache import TtlCache

from world.catalog import BONDS, INDICES, OIL, RATES, REGIONS
from world.fetchers.bonds import fetch_bond_region, fetch_bonds
from world.fetchers.indices import fetch_indices
from world.fetchers.oil import fetch_oil
from world.fetchers.rates import fetch_rate_series, fetch_rates

_SPOT_TTL = 60.0
_SERIES_TTL = 30 * 60.0


class GlobalMarketService:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._spot_cache = TtlCache(_SPOT_TTL)
        self._series_cache = TtlCache(_SERIES_TTL)

    def _cached(self, cache: TtlCache, key: str, loader):
        hit = cache.get(key)
        if hit is not None:
            return hit
        with self._lock:
            hit = cache.get(key)
            if hit is not None:
                return hit
            data = loader()
            cache.put(key, data)
            return data

    def catalog(self) -> dict[str, Any]:
        return {
            "regions": REGIONS,
            "indices": INDICES,
            "rates": RATES,
            "bonds": BONDS,
            "oil": OIL,
        }

    def indices(self, *, force: bool = False) -> dict[str, Any]:
        if force:
            data = fetch_indices()
            self._spot_cache.put("indices", data)
            return data
        return self._cached(self._spot_cache, "indices", fetch_indices)

    def oil(self, *, force: bool = False) -> dict[str, Any]:
        if force:
            data = fetch_oil()
            self._spot_cache.put("oil", data)
            return data
        return self._cached(self._spot_cache, "oil", fetch_oil)

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
                self._series_cache.put(key, data)
                return data
            return self._cached(
                self._series_cache,
                key,
                lambda: fetch_rate_series(region, limit=limit),
            )

        key = f"rates:all:{limit}"
        if force:
            data = fetch_rates(limit=limit)
            self._series_cache.put(key, data)
            return data
        return self._cached(self._series_cache, key, lambda: fetch_rates(limit=limit))

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
                self._series_cache.put(key, data)
                return data
            return self._cached(
                self._series_cache,
                key,
                lambda: fetch_bond_region(region, limit=limit),
            )

        key = f"bonds:all:{limit}"
        if force:
            data = fetch_bonds(limit=limit)
            self._series_cache.put(key, data)
            return data
        return self._cached(self._series_cache, key, lambda: fetch_bonds(limit=limit))

    def overview(
        self,
        *,
        rate_limit: int = 24,
        bond_limit: int = 60,
        force: bool = False,
    ) -> dict[str, Any]:
        if force:
            self._spot_cache = TtlCache(_SPOT_TTL)
            self._series_cache = TtlCache(_SERIES_TTL)

        result: dict[str, Any] = {}
        tasks = {
            "indices": lambda: self.indices(force=force),
            "oil": lambda: self.oil(force=force),
            "rates": lambda: self.rates(limit=rate_limit, force=force),
            "bonds": lambda: self.bonds(limit=bond_limit, force=force),
        }
        with ThreadPoolExecutor(max_workers=4) as pool:
            futures = {pool.submit(fn): name for name, fn in tasks.items()}
            for fut in as_completed(futures):
                name = futures[fut]
                result[name] = fut.result()
        result["updated_at"] = __import__("datetime").datetime.now().isoformat(
            timespec="seconds"
        )
        return result


service = GlobalMarketService()
