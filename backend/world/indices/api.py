"""指数数据 HTTP 路由。"""

from __future__ import annotations

from fastapi import APIRouter, Query

from core.api import err, ok
from world.indices.service import service

router = APIRouter()


@router.get("/api/global/indices")
def global_indices(refresh: str = Query("0")):
    try:
        return ok(service.quotes(force=refresh == "1"))
    except Exception as exc:  # noqa: BLE001
        return err(str(exc), 500)


@router.get("/api/global/indices/history")
def global_index_history(
    limit: int = Query(90, ge=20, le=240),
    refresh: str = Query("0"),
):
    try:
        return ok(service.klines(limit=limit, force=refresh == "1"))
    except Exception as exc:  # noqa: BLE001
        return err(str(exc), 500)
