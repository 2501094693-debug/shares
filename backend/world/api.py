"""全球市场 HTTP 路由。"""

from __future__ import annotations

from fastapi import APIRouter, Query

from core.api import err, ok
from world.service import service

router = APIRouter()


@router.get("/api/global/catalog")
def global_catalog():
    return ok(service.catalog())


@router.get("/api/global/overview")
def global_overview(
    refresh: str = Query("0", description="1=跳过缓存强制刷新"),
    rate_limit: int = Query(24, ge=1, le=120),
    bond_limit: int = Query(60, ge=10, le=500),
):
    try:
        data = service.overview(
            rate_limit=rate_limit,
            bond_limit=bond_limit,
            force=refresh == "1",
        )
        return ok(data)
    except Exception as exc:  # noqa: BLE001
        return err(str(exc), 500)


@router.get("/api/global/indices")
def global_indices(refresh: str = Query("0")):
    try:
        return ok(service.indices(force=refresh == "1"))
    except Exception as exc:  # noqa: BLE001
        return err(str(exc), 500)


@router.get("/api/global/rates")
def global_rates(
    region: str = Query("", description="地区代码，空=全部"),
    limit: int = Query(36, ge=1, le=240),
    refresh: str = Query("0"),
):
    try:
        data = service.rates(
            region=region.strip() or None,
            limit=limit,
            force=refresh == "1",
        )
        return ok(data)
    except ValueError as exc:
        return err(str(exc), 400)
    except Exception as exc:  # noqa: BLE001
        return err(str(exc), 500)


@router.get("/api/global/bonds")
def global_bonds(
    region: str = Query("", description="地区代码，空=全部"),
    limit: int = Query(120, ge=10, le=1000),
    refresh: str = Query("0"),
):
    try:
        data = service.bonds(
            region=region.strip() or None,
            limit=limit,
            force=refresh == "1",
        )
        return ok(data)
    except ValueError as exc:
        return err(str(exc), 400)
    except Exception as exc:  # noqa: BLE001
        return err(str(exc), 500)


@router.get("/api/global/oil")
def global_oil(refresh: str = Query("0")):
    try:
        return ok(service.oil(force=refresh == "1"))
    except Exception as exc:  # noqa: BLE001
        return err(str(exc), 500)
