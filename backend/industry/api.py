"""申万行业 / 检索 / 地图相关 HTTP 路由。"""

from __future__ import annotations

import os
from typing import Any

from fastapi import APIRouter, Body, Query

from core.api import err, ok
from industry.address import enrich_codes
from industry.service import service

router = APIRouter()


@router.get("/api/industries")
def industries(refresh: str = Query("0")):
    force = refresh == "1"
    try:
        tree = service.get_tree(force_refresh=force)
        return ok(tree)
    except Exception as exc:  # noqa: BLE001
        return err(str(exc), 500)


@router.get("/api/search")
def search(q: str = Query("")):
    try:
        results = service.search(q)
        return ok(results)
    except Exception as exc:  # noqa: BLE001
        return err(str(exc), 500)


@router.get("/api/stocks/search")
def stocks_search(name: str = Query(""), code: str = Query("")):
    try:
        results = service.search_stocks(name=name, code=code)
        return ok(results, index=service.get_index_status())
    except Exception as exc:  # noqa: BLE001
        return err(str(exc), 500)


@router.get("/api/stocks/index/status")
def stocks_index_status():
    return ok(service.get_index_status())


@router.post("/api/stocks/index/rebuild")
def stocks_index_rebuild(
    force: str = Query("0"),
    refresh: str = Query("0"),
):
    do_force = force == "1" or refresh == "1"
    try:
        status = service.start_build_stock_index(force=do_force)
        return ok(status)
    except Exception as exc:  # noqa: BLE001
        return err(str(exc), 500)


@router.get("/api/industries/{code:path}/stocks")
def industry_stocks(code: str, refresh: str = Query("0")):
    force = refresh == "1"
    try:
        data = service.get_constituents(code, force_refresh=force)
        return ok(data)
    except KeyError as exc:
        return err(str(exc), 404)
    except Exception as exc:  # noqa: BLE001
        return err(str(exc), 500)


@router.post("/api/stocks/geo-enrich")
def stocks_geo_enrich(payload: dict[str, Any] = Body(default_factory=dict)):
    """批量补齐公司全称与注册省市区。Body: { codes: string[], force?: 0|1 }。

    经纬度由前端高德 PlaceSearch 标注，本接口不返回可靠坐标。
    """
    raw_codes = payload.get("codes") or []
    if not isinstance(raw_codes, list):
        return err("codes 须为数组", 400)
    codes = [str(c).strip() for c in raw_codes if str(c).strip()]
    if not codes:
        return err("缺少 codes", 400)
    if len(codes) > 500:
        return err("单次最多 500 个代码", 400)
    force = str(payload.get("force") or "0") in {"1", "true", "True"}
    try:
        items = enrich_codes(codes, force=force, max_workers=4)
        return ok({"items": items, "count": len(items)})
    except Exception as exc:  # noqa: BLE001
        return err(str(exc), 500)


@router.get("/api/map/config")
def map_config():
    """前端高德地图 Key（来自环境变量 / .env）。"""
    key = (os.environ.get("AMAP_JS_KEY") or os.environ.get("AMAP_KEY") or "").strip()
    security = (
        os.environ.get("AMAP_SECURITY_CODE")
        or os.environ.get("AMAP_SECURITY_JS_CODE")
        or ""
    ).strip()
    web_key = (
        os.environ.get("AMAP_WEB_KEY") or os.environ.get("AMAP_JS_KEY") or ""
    ).strip()
    return ok(
        {
            "provider": "amap",
            "key": key,
            "securityJsCode": security,
            "configured": bool(key),
            "geocodeReady": bool(web_key),
        }
    )
