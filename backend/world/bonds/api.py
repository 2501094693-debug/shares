"""国债与利率 HTTP 路由。"""

from __future__ import annotations

from fastapi import APIRouter, Query

from core.api import err, ok
from world.bonds.service import service

router = APIRouter()


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
