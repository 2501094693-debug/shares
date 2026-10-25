"""A 股指数 HTTP 路由（同花顺 / 东财双数据源）。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query

from core.api import err, ok

router = APIRouter()


def _service(source: str) -> Any:
    key = (source or "eastmoney").strip().lower()
    if key in ("eastmoney", "em", "east", "dc"):
        from exponent.eastmoney.service import service

        return service
    if key in ("tonghuashun", "ths", "th"):
        from exponent.tonghuashun.service import service

        return service
    raise ValueError(f"source 须为 eastmoney|tonghuashun，收到 {source!r}")


@router.get("/api/exponent/catalog")
def exponent_catalog(
    source: str = Query("eastmoney", description="eastmoney | tonghuashun"),
):
    """常用指数目录（宽基 / 规模 / 其他）。"""
    try:
        return ok(_service(source).catalog())
    except Exception as exc:  # noqa: BLE001
        return err(str(exc), 500)


@router.get("/api/exponent/quotes")
def exponent_quotes(
    codes: str = Query(
        "",
        description="逗号分隔公开码，如 000001,000300；空=目录全部",
    ),
    source: str = Query("eastmoney", description="eastmoney | tonghuashun"),
    refresh: str = Query("0", description="1=跳过缓存"),
):
    try:
        wanted = [c.strip() for c in codes.split(",") if c.strip()] or None
        return ok(_service(source).quotes(wanted, force=refresh == "1"))
    except Exception as exc:  # noqa: BLE001
        return err(str(exc), 500)


@router.get("/api/exponent/kline")
def exponent_kline(
    code: str = Query(..., description="公开码或源内标识，如 000300 / 1.000300"),
    period: str = Query("day", description="day|week|month|…|1m|5m|…"),
    limit: int = Query(120, ge=1, le=5000),
    beg: str = Query("", description="起始 YYYYMMDD，与 end 联用"),
    end: str = Query("", description="结束 YYYYMMDD"),
    source: str = Query("eastmoney", description="eastmoney | tonghuashun"),
    refresh: str = Query("0"),
):
    try:
        return ok(
            _service(source).kline(
                code,
                period=period,
                limit=limit,
                beg=beg,
                end=end,
                force=refresh == "1",
            )
        )
    except Exception as exc:  # noqa: BLE001
        return err(str(exc), 500)


@router.get("/api/exponent/list")
def exponent_list(
    markets: str = Query(
        "",
        description="同花顺：USHI,USZI,…；东财：important,sse,szse,csi",
    ),
    source: str = Query("eastmoney", description="eastmoney | tonghuashun"),
    refresh: str = Query("0"),
):
    try:
        wanted = [m.strip() for m in markets.split(",") if m.strip()] or None
        return ok(_service(source).list_all(wanted, force=refresh == "1"))
    except Exception as exc:  # noqa: BLE001
        return err(str(exc), 500)


@router.get("/api/exponent/search")
def exponent_search(
    q: str = Query(..., description="名称或代码，如 沪深300 / 000905"),
    limit: int = Query(20, ge=1, le=100),
    source: str = Query("eastmoney", description="eastmoney | tonghuashun"),
):
    try:
        return ok(_service(source).search(q, limit=limit))
    except Exception as exc:  # noqa: BLE001
        return err(str(exc), 500)
