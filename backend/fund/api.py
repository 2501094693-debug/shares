"""场内基金（ETF / LOF）分类与检索 HTTP 路由。"""

from __future__ import annotations

from fastapi import APIRouter, Query

from core.api import err, ok
from fund.service import service

router = APIRouter()


@router.get("/api/funds/tree")
def funds_tree(refresh: str = Query("0")):
    """场内基金分类树（ETF / LOF 及细分类型）。"""
    try:
        tree = service.get_tree(force_refresh=refresh == "1")
        return ok(tree, categories=service.flat_categories())
    except Exception as exc:  # noqa: BLE001
        return err(str(exc), 500)


@router.get("/api/funds/categories")
def funds_categories():
    """扁平分类列表（含东财 fs 参数）。"""
    return ok(service.flat_categories())


@router.get("/api/funds/search")
def funds_search(
    name: str = Query(""),
    code: str = Query(""),
    category: str = Query("", description="分类代码，如 stock_etf / sh_lof"),
    market: str = Query("", description="SH 或 SZ"),
    limit: int = Query(80, ge=1, le=500),
):
    """按名称 / 代码 / 分类 / 市场检索场内基金。"""
    try:
        results = service.search(
            name=name,
            code=code,
            category=category,
            market=market,
            limit=limit,
        )
        return ok(results, index=service.get_index_status())
    except Exception as exc:  # noqa: BLE001
        return err(str(exc), 500)


@router.get("/api/funds/index/status")
def funds_index_status():
    return ok(service.get_index_status())


@router.post("/api/funds/index/rebuild")
def funds_index_rebuild(
    force: str = Query("0"),
    refresh: str = Query("0"),
):
    do_force = force == "1" or refresh == "1"
    try:
        status = service.start_build_index(force=do_force)
        return ok(status)
    except Exception as exc:  # noqa: BLE001
        return err(str(exc), 500)


@router.get("/api/funds/{code}/list")
def funds_category_list(code: str, refresh: str = Query("0")):
    """某分类下的全部场内基金。"""
    try:
        data = service.get_category_list(code, force_refresh=refresh == "1")
        return ok(data, index=service.get_index_status())
    except KeyError as exc:
        return err(str(exc), 404)
    except Exception as exc:  # noqa: BLE001
        return err(str(exc), 500)


@router.get("/api/funds/{code}")
def fund_detail(code: str):
    """按代码查单只场内基金（需先构建索引）。"""
    item = service.get_by_code(code)
    if item is None:
        return err(f"未找到基金: {code}", 404)
    return ok(item)
