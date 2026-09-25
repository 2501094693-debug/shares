"""全球市场总览服务：聚合原油 / 指数 / 国债三类。"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import Any

from world.bonds.service import service as bonds_service
from world.indices.catalog import REGIONS
from world.indices.service import service as indices_service
from world.oil.service import service as oil_service


class GlobalMarketService:
    def catalog(self) -> dict[str, Any]:
        indices_cat = indices_service.catalog()
        bonds_cat = bonds_service.catalog()
        return {
            "regions": REGIONS,
            "indices": indices_cat["indices"],
            "rates": bonds_cat["rates"],
            "bonds": bonds_cat["bonds"],
            "oil": oil_service.catalog(),
        }

    def overview(
        self,
        *,
        rate_limit: int = 24,
        bond_limit: int = 60,
        force: bool = False,
    ) -> dict[str, Any]:
        result: dict[str, Any] = {}
        tasks = {
            "indices": lambda: indices_service.quotes(force=force),
            "oil": lambda: oil_service.quotes(force=force),
            "rates": lambda: bonds_service.rates(limit=rate_limit, force=force),
            "bonds": lambda: bonds_service.bonds(limit=bond_limit, force=force),
        }
        with ThreadPoolExecutor(max_workers=4) as pool:
            futures = {pool.submit(fn): name for name, fn in tasks.items()}
            for fut in as_completed(futures):
                name = futures[fut]
                result[name] = fut.result()
        result["updated_at"] = datetime.now().isoformat(timespec="seconds")
        return result


service = GlobalMarketService()
