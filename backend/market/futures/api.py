"""国内期货分类与检索 HTTP 路由。"""

from __future__ import annotations

from fastapi import APIRouter, Query

from core.api import err, ok
from market.futures.service import service

router = APIRouter()


@router.get("/api/futures/tree")
def futures_tree(refresh: str = Query("0")):
    """期货分类树（商品 / 金融 → 交易所）。"""
    try:
        tree = service.get_tree(force_refresh=refresh == "1")
        return ok(tree, categories=service.flat_categories())
    except Exception as exc:  # noqa: BLE001
        return err(str(exc), 500)


@router.get("/api/futures/categories")
def futures_categories():
    """扁平分类列表（含东财 fs / venue）。"""
    return ok(service.flat_categories())


@router.get("/api/futures/search")
def futures_search(
    name: str = Query(""),
    code: str = Query(""),
    category: str = Query("", description="分类代码，如 shfe / dce"),
    venue: str = Query("", description="交易所，如 SHFE / DCE"),
    main_only: str = Query("0", description="1=仅主力合约"),
    limit: int = Query(80, ge=1, le=500),
):
    """按名称 / 代码 / 分类 / 交易所检索期货。"""
    try:
        results = service.search(
            name=name,
            code=code,
            category=category,
            venue=venue,
            main_only=main_only == "1",
            limit=limit,
        )
        return ok(results, index=service.get_index_status())
    except Exception as exc:  # noqa: BLE001
        return err(str(exc), 500)


@router.get("/api/futures/index/status")
def futures_index_status():
    return ok(service.get_index_status())


@router.post("/api/futures/index/rebuild")
def futures_index_rebuild(
    force: str = Query("0"),
    refresh: str = Query("0"),
):
    do_force = force == "1" or refresh == "1"
    try:
        status = service.start_build_index(force=do_force)
        return ok(status)
    except Exception as exc:  # noqa: BLE001
        return err(str(exc), 500)


@router.get("/api/futures/{code}/list")
def futures_category_list(code: str, refresh: str = Query("0")):
    """某交易所下的全部期货合约。"""
    try:
        data = service.get_category_list(code, force_refresh=refresh == "1")
        return ok(data, index=service.get_index_status())
    except KeyError as exc:
        return err(str(exc), 404)
    except Exception as exc:  # noqa: BLE001
        return err(str(exc), 500)


@router.get("/api/futures/{code}")
def futures_detail(code: str):
    """按合约代码查单只期货（需先构建索引）。"""
    item = service.get_by_code(code)
    if item is None:
        return err(f"未找到期货: {code}", 404)
    return ok(item)
