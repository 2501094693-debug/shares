"""单股详情 HTTP 路由：画像、K 线、市盈率、逐笔、资讯、社区情绪。"""

from __future__ import annotations

from fastapi import APIRouter, Query

from company.emotion import (
    fetch_article as fetch_guba_article,
    fetch_company as fetch_guba_company,
    fetch_hot_list,
    fetch_posts as fetch_guba_posts,
    fetch_rank,
    fetch_replies as fetch_guba_replies,
    fetch_scores,
    search_posts as search_guba_posts,
)
from company.emotion.tonghuashun import (
    fetch_company as fetch_ths_company,
    fetch_posts as fetch_ths_posts,
    fetch_rank as fetch_ths_rank,
    fetch_scores as fetch_ths_scores,
    search_posts as search_ths_posts,
)
from company.emotion.xueqiu import (
    fetch_article as fetch_xq_article,
    fetch_company as fetch_xq_company,
    fetch_followers as fetch_xq_followers,
    fetch_hot_list as fetch_xq_hot_list,
    fetch_hot_posts as fetch_xq_hot_posts,
    fetch_posts as fetch_xq_posts,
    fetch_rank as fetch_xq_rank,
    fetch_replies as fetch_xq_replies,
    fetch_scores as fetch_xq_scores,
    search_posts as search_xq_posts,
)
from company.line import fetch_kline, fetch_ticks
from company.statistics.pe_history import fetch_pe_history
from company.statistics.turnover_history import fetch_turnover_history
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


@router.get("/api/stocks/pe")
def stocks_pe(
    code: str = Query("", description="股票代码，如 601881"),
    limit: int = Query(1500, ge=1, le=5000, description="最近交易日数量"),
    refresh: str = Query("0"),
):
    """历史估值曲线：东财日频市盈率动 / TTM / 静态、市净率 MRQ。"""
    code = code.strip()
    if not code:
        return err("缺少参数 code", 400)
    try:
        data = fetch_pe_history(code, limit=limit, force=refresh == "1")
        return ok(data)
    except ValueError as exc:
        return err(str(exc), 400)
    except Exception as exc:  # noqa: BLE001
        return err(str(exc), 500)


@router.get("/api/stocks/turnover")
def stocks_turnover(
    code: str = Query("", description="股票代码，如 601881"),
    limit: int = Query(2500, ge=1, le=5000, description="最近交易日数量"),
    refresh: str = Query("0"),
):
    """历史换手率曲线：成交量 ÷ 自由流通股。"""
    code = code.strip()
    if not code:
        return err("缺少参数 code", 400)
    try:
        data = fetch_turnover_history(code, limit=limit, force=refresh == "1")
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


@router.get("/api/stocks/emotion")
def stocks_emotion(
    code: str = Query("", description="股票代码或公司名；channel=rank 且无 code 时返回全市场人气榜"),
    source: str = Query("eastmoney", description="eastmoney 股吧 | xueqiu 雪球 | tonghuashun 同花顺圈子"),
    channel: str = Query(
        "posts",
        description="posts|article|replies|search|rank|scores|all；雪球另有 hot|fans",
    ),
    kind: str = Query(
        "all",
        description="东财帖子分类 all|news|...|hot；雪球 user|trans|all；同花顺仅手机讨论流",
    ),
    sort: str = Query("time", description="time|reply|hot；雪球另有 alpha"),
    days: int = Query(3, ge=1, le=20000),
    max_pages: int = Query(3, ge=1, le=20),
    replies: str = Query("0", description="1=帖子列表附带评论，或正文附带评论"),
    post_id: str = Query("", description="帖子 ID / URL，配合 channel=article|replies"),
    q: str = Query("", description="关键词，配合 channel=search"),
    market: str = Query("cn", description="雪球热股市场 cn|hk|us|global|follow"),
    limit: int = Query(0, ge=0, le=200, description="截断 items；0 为全部"),
):
    """社区情绪：默认东财股吧；``source=xueqiu`` 雪球；``source=tonghuashun`` 同花顺圈子。"""
    code = code.strip()
    channel = channel.strip().lower() or "posts"
    src = source.strip().lower() or "eastmoney"
    with_replies = replies == "1"
    try:
        if src in {"xueqiu", "xq", "snowball"}:
            data = _emotion_xueqiu(
                code=code,
                channel=channel,
                kind=kind,
                sort=sort,
                days=days,
                max_pages=max_pages,
                with_replies=with_replies,
                post_id=post_id.strip(),
                q=q.strip(),
                market=market,
            )
        elif src in {"tonghuashun", "ths", "10jqka"}:
            data = _emotion_tonghuashun(
                code=code,
                channel=channel,
                kind=kind,
                sort=sort,
                days=days,
                max_pages=max_pages,
                with_replies=with_replies,
                post_id=post_id.strip(),
                q=q.strip(),
            )
        elif channel == "search":
            if not q.strip() and not code:
                return err("缺少参数 q 或 code", 400)
            data = search_guba_posts(q.strip() or code, code=code, days=days, sort=sort, max_pages=max_pages)
        elif channel == "rank":
            data = fetch_rank(code) if code else fetch_hot_list()
        elif channel == "scores":
            if not code:
                return err("缺少参数 code", 400)
            data = fetch_scores(code)
        elif channel == "article":
            if not post_id.strip():
                return err("缺少参数 post_id", 400)
            data = fetch_guba_article(
                post_id.strip(),
                code=code,
                with_replies=with_replies,
                max_reply_pages=max_pages,
            )
        elif channel == "replies":
            if not post_id.strip():
                return err("缺少参数 post_id", 400)
            data = fetch_guba_replies(post_id.strip(), code=code, max_pages=max_pages)
        elif channel == "all":
            if not code:
                return err("缺少参数 code", 400)
            data = fetch_guba_company(
                code,
                kind=kind,
                sort=sort,
                days=days,
                max_pages=max_pages,
                with_replies=with_replies,
            )
        else:
            if not code:
                return err("缺少参数 code", 400)
            data = fetch_guba_posts(
                code,
                kind=kind,
                sort=sort,
                days=days,
                max_pages=max_pages,
                with_replies=with_replies,
            )
        if limit > 0 and isinstance(data, dict) and isinstance(data.get("items"), list):
            data = dict(data)
            data["items"] = data["items"][:limit]
        return ok(data)
    except ValueError as exc:
        return err(str(exc), 400)
    except Exception as exc:  # noqa: BLE001
        return err(str(exc), 500)


def _emotion_xueqiu(
    *,
    code: str,
    channel: str,
    kind: str,
    sort: str,
    days: int,
    max_pages: int,
    with_replies: bool,
    post_id: str,
    q: str,
    market: str,
):
    if channel == "search":
        if not q and not code:
            raise ValueError("缺少参数 q 或 code")
        return search_xq_posts(q or code, code=code, days=days, sort=sort, max_pages=max_pages)
    if channel == "rank":
        return fetch_xq_rank(code, market=market) if code else fetch_xq_hot_list(market=market)
    if channel == "scores":
        if not code:
            raise ValueError("缺少参数 code")
        return fetch_xq_scores(code)
    if channel == "fans":
        if not code:
            raise ValueError("缺少参数 code")
        return fetch_xq_followers(code, max_pages=max_pages)
    if channel == "hot":
        return fetch_xq_hot_posts(max_pages=max_pages)
    if channel == "article":
        if not post_id:
            raise ValueError("缺少参数 post_id")
        return fetch_xq_article(
            post_id,
            code=code,
            with_replies=with_replies,
            max_reply_pages=max_pages,
        )
    if channel == "replies":
        if not post_id:
            raise ValueError("缺少参数 post_id")
        return fetch_xq_replies(post_id, code=code, max_pages=max_pages)
    if channel == "all":
        if not code:
            raise ValueError("缺少参数 code")
        return fetch_xq_company(
            code,
            kind=kind,
            sort=sort,
            days=days,
            max_pages=max_pages,
            with_replies=with_replies,
            market=market,
        )
    if not code:
        raise ValueError("缺少参数 code")
    return fetch_xq_posts(
        code,
        kind=kind,
        sort=sort,
        days=days,
        max_pages=max_pages,
        with_replies=with_replies,
    )


def _emotion_tonghuashun(
    *,
    code: str,
    channel: str,
    kind: str,
    sort: str,
    days: int,
    max_pages: int,
    with_replies: bool,
    post_id: str,
    q: str,
):
    del kind, post_id
    api_kind = "user"
    # 讨论流按热度不是按日切；API 默认 days=3 经常把帖滤空，短窗口改按页数。
    feed_days = days if days >= 30 else None
    if channel == "search":
        if not q and not code:
            raise ValueError("缺少参数 q 或 code")
        return search_ths_posts(q or code, code=code, days=feed_days, max_pages=max_pages)
    if channel == "rank":
        if not code:
            raise ValueError("缺少参数 code")
        return fetch_ths_rank(code)
    if channel == "scores":
        if not code:
            raise ValueError("缺少参数 code")
        return fetch_ths_scores(code)
    if channel in {"article", "replies"}:
        raise ValueError("同花顺社区只提供手机讨论列表；评论预览请用 channel=posts&replies=1")
    if channel == "all":
        if not code:
            raise ValueError("缺少参数 code")
        return fetch_ths_company(
            code,
            kind=api_kind,
            sort=sort,
            days=feed_days,
            max_pages=max_pages,
            with_replies=with_replies,
        )
    if not code:
        raise ValueError("缺少参数 code")
    return fetch_ths_posts(
        code,
        kind=api_kind,
        sort=sort,
        days=feed_days,
        max_pages=max_pages,
        with_replies=with_replies,
    )
