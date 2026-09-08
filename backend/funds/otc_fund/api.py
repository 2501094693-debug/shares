"""场外开放式基金 HTTP 路由。"""

from __future__ import annotations

import re

from fastapi import APIRouter, Query

from core.api import err, ok
from funds.otc_fund.service import service

router = APIRouter()

_FUND_CODE_RE = re.compile(r"^\d{6}$")


@router.get("/api/otc-funds/tree")
def otc_funds_tree(refresh: str = Query("0")):
    try:
        tree = service.get_tree(force_refresh=refresh == "1")
        return ok(tree, categories=service.flat_categories(), index=service.get_index_status())
    except Exception as exc:  # noqa: BLE001
        return err(str(exc), 500)


@router.get("/api/otc-funds/categories")
def otc_funds_categories():
    return ok(service.flat_categories())


@router.get("/api/otc-funds/index/status")
def otc_funds_index_status():
    return ok(service.get_index_status())


@router.post("/api/otc-funds/index/rebuild")
def otc_funds_index_rebuild():
    try:
        status = service.warmup_index(force=True)
        return ok(status)
    except Exception as exc:  # noqa: BLE001
        return err(str(exc), 500)


@router.get("/api/otc-funds/search")
def otc_funds_search(
    name: str = Query(""),
    code: str = Query(""),
    type_name: str = Query("", description="基金类型关键词，如 混合型"),
    limit: int = Query(80, ge=1, le=500),
):
    try:
        results = service.search(name=name, code=code, type_name=type_name, limit=limit)
        return ok(results, index=service.get_index_status())
    except Exception as exc:  # noqa: BLE001
        return err(str(exc), 500)


@router.get("/api/otc-funds/category/{category}/list")
def otc_funds_category_list(
    category: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    sort: str = Query("rzdf"),
    refresh: str = Query("0"),
):
    try:
        data = service.get_category_list(
            category,
            page=page,
            page_size=page_size,
            sort=sort,
            force_refresh=refresh == "1",
        )
        return ok(data, index=service.get_index_status())
    except KeyError as exc:
        return err(str(exc), 404)
    except Exception as exc:  # noqa: BLE001
        return err(str(exc), 500)


@router.get("/api/otc-funds/{code}")
def otc_fund_detail(code: str):
    if not _FUND_CODE_RE.match(code.strip()):
        return err(f"无效的场外基金代码: {code}", 400)
    try:
        return ok(service.get_detail(code))
    except Exception as exc:  # noqa: BLE001
        return err(str(exc), 500)
