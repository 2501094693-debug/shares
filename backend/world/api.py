"""全球市场 HTTP 路由：聚合原油 / 指数 / 国债三类。"""

from __future__ import annotations

from fastapi import APIRouter, Query

from core.api import err, ok
from world.bonds.api import router as bonds_router
from world.indices.api import router as indices_router
from world.oil.api import router as oil_router
from world.service import service

router = APIRouter()

# 扁平挂载子路由，避免嵌套 include_router 在部分 FastAPI 版本下丢失路由
for _child in (oil_router, indices_router, bonds_router):
    router.routes.extend(_child.routes)


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
