"""主要国家央行利率 HTTP 路由。"""

from __future__ import annotations

from fastapi import APIRouter, Query

from core.api import err, ok
from world.central_banks.service import service

router = APIRouter()


@router.get("/api/global/central-banks")
def global_central_banks(
    region: str = Query("", description="地区代码，空=全部"),
    limit: int = Query(60, ge=1, le=240),
    refresh: str = Query("0"),
):
    try:
        if region.strip():
            if region not in {"us", "eu", "cn", "jp", "uk", "ca", "au", "nz", "kr", "in", "br", "mx", "za", "ru", "se", "no", "ch", "hk"}:
                return err(f"未知地区: {region}", 400)
            data = service.central_bank(
                region=region.strip(),
                limit=limit,
                force=refresh == "1",
            )
        else:
            data = service.all_central_banks(
                limit=limit,
                force=refresh == "1",
            )
        return ok(data)
    except ValueError as exc:
        return err(str(exc), 400)
    except Exception as exc:  # noqa: BLE001
        return err(str(exc), 500)


@router.get("/api/global/central-banks/catalog")
def central_banks_catalog():
    return ok(service.catalog())
