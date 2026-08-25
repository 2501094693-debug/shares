"""单股详情 HTTP 路由：画像、K 线、逐笔、资讯。"""

from __future__ import annotations

from fastapi import APIRouter, Query

from company.line import fetch_kline, fetch_ticks
from company.news.feed import collect_company_messages
from company.news.profile import query_company_profile
from company.news.taxonomy.constants import ALL_SECTIONS, DEFAULT_SECTIONS
from company.profile import get_stock_profile
from core.api import err, ok

router = APIRouter()


@router.get("/api/stocks/profile")
def stocks_profile(
    code: str = Query(""),
    industry: str = Query(""),
    name: str = Query(""),
):
    code = code.strip()
    industry = industry.strip()
    name = name.strip()
    if not code:
        return err("缺少参数 code", 400)
    try:
        data = get_stock_profile(code, industry_code=industry, name=name)
        return ok(data)
    except ValueError as exc:
        return err(str(exc), 400)
    except Exception as exc:  # noqa: BLE001
        return err(str(exc), 500)


@router.get("/api/stocks/line")
@router.get("/api/stocks/kline")
def stocks_line(
    code: str = Query("", description="股票代码，如 601881"),
    period: str = Query(
        "day",
        description="1m|5m|15m|30m|60m|120m|day|week|month|quarter|halfyear|year",
    ),
    adjust: str = Query("qfq", description="none|qfq|hfq"),
    limit: int = Query(320, ge=1, le=10000),
    beg: str = Query("", description="开始日期 YYYYMMDD 或 YYYY-MM-DD"),
    end: str = Query("", description="结束日期 YYYYMMDD 或 YYYY-MM-DD"),
    refresh: str = Query("0"),
):
    """日/周/月/分钟 K 线。腾讯优先，东财兜底。``/kline`` 为旧路径别名。"""
    code = code.strip()
    if not code:
        return err("缺少参数 code", 400)
    try:
        data = fetch_kline(
            code,
            period=period,
            adjust=adjust,
            limit=limit,
            beg=beg.strip(),
            end=end.strip(),
            force=refresh == "1",
        )
        return ok(data)
    except ValueError as exc:
        return err(str(exc), 400)
    except Exception as exc:  # noqa: BLE001
        return err(str(exc), 500)


@router.get("/api/stocks/ticks")
def stocks_ticks(
    code: str = Query("", description="股票代码，如 601881"),
    pos: str = Query("0", description="0=当天全部；-20 或 20=最近 20 笔"),
    refresh: str = Query("0"),
):
    """当日成交明细（实时逐笔）。东财优先，腾讯兜底。"""
    code = code.strip()
    if not code:
        return err("缺少参数 code", 400)
    try:
        data = fetch_ticks(code, pos=pos, force=refresh == "1")
        return ok(data)
    except ValueError as exc:
        return err(str(exc), 400)
    except Exception as exc:  # noqa: BLE001
        return err(str(exc), 500)


@router.get("/api/stocks/news")
def stocks_news(
    code: str = Query(""),
    name: str = Query(""),
    refresh: str = Query("0"),
    days: int = Query(3, ge=1, le=20000),
    kind: str = Query(""),
):
    code = code.strip()
    name = name.strip()
    force = refresh == "1"
    if not code:
        return err("缺少参数 code", 400)
    try:
        data = collect_company_messages(
            code,
            name,
            force_refresh=force,
            days=days,
            kind=kind,
        )
        return ok(data)
    except ValueError as exc:
        return err(str(exc), 400)
    except Exception as exc:  # noqa: BLE001
        return err(str(exc), 500)


@router.get("/api/stocks/profile-messages")
def stocks_profile_messages(
    code: str = Query("", description="股票代码或公司名"),
    name: str = Query(""),
    days: int = Query(90, ge=1, le=20000),
    sections: str = Query(
        "default",
        description=(
            "采集段：default="
            + ",".join(DEFAULT_SECTIONS)
            + "；all 或逗号组合="
            + ",".join(ALL_SECTIONS)
        ),
    ),
    max_pages: int = Query(3, ge=1, le=20),
):
    """系统性分类视图（disclosure/regulatory/press/news/research）。数据来自 company.news。"""
    code = code.strip()
    name = name.strip()
    if not code:
        return err("缺少参数 code", 400)
    try:
        data = query_company_profile(
            code,
            name=name,
            days=days,
            sections=sections,
            max_pages=max_pages,
        )
        return ok(data)
    except ValueError as exc:
        return err(str(exc), 400)
    except Exception as exc:  # noqa: BLE001
        return err(str(exc), 500)
