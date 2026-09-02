"""统一查询：交易所 / 巨潮公告、监管、七网、市场新闻、研报。"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import Any, Callable, Iterable, Literal

from core.codes import detect_market, normalize_code, safe_str

from company.news._items import (
    as_news,
    as_notice,
    as_press,
    as_regulatory,
    as_report,
    default_start,
    dedupe,
    sort_key,
    unpack,
    within_range,
)
from company.news.official.cninfo import fetch_announcements as fetch_cninfo_announcements
from company.news.official.cninfo import resolve_org
from company.news.official.cninfo.parse import item_why
from company.news.official.exchange import (
    fetch_bse_announcements,
    fetch_bse_inquiries,
    fetch_sse_announcements,
    fetch_sse_inquiries,
    fetch_szse_announcements,
    fetch_szse_inquiries,
)
from company.news.official.press import (
    fetch_chinadaily_news,
    fetch_cnstock_news,
    fetch_cs_news,
    fetch_financialnews_news,
    fetch_jjckb_news,
    fetch_stcn_news,
    fetch_zqrb_news,
)
from company.news.platforms.eastmoney.f10 import fetch_f10 as fetch_eastmoney_f10
from company.news.platforms.eastmoney.notices import fetch_notices as fetch_eastmoney_notices
from company.news.platforms.eastmoney.search import fetch_news as fetch_eastmoney_news
from company.news.platforms.tonghuashun.news import fetch_news as fetch_ths_news
from company.news.platforms.tonghuashun.notices import fetch_notices as fetch_ths_notices
from company.news.platforms.tonghuashun.reports import fetch_reports as fetch_ths_reports
from company.news.platforms.xueqiu.news import fetch_news as fetch_xq_news
from company.news.platforms.xueqiu.notices import fetch_notices as fetch_xq_notices
from company.news.platforms.xueqiu.reports import fetch_reports as fetch_xq_reports
from company.news.taxonomy.constants import PRESS_OUTLETS, REGULATORY_TITLE_KEYWORDS
from company.news.taxonomy.keywords import infer_subcategory

logger = logging.getLogger(__name__)

Channel = Literal["sse", "szse", "bse", "cninfo", "auto"]

PRESS_FETCHERS: dict[str, Callable[..., dict[str, Any]]] = {
    "cs": fetch_cs_news,
    "cnstock": fetch_cnstock_news,
    "stcn": fetch_stcn_news,
    "zqrb": fetch_zqrb_news,
    "financialnews": fetch_financialnews_news,
    "jjckb": fetch_jjckb_news,
    "chinadaily": fetch_chinadaily_news,
}
PRESS_BY_ID = {o["id"]: o for o in PRESS_OUTLETS}

_EXCHANGE_FETCH = {
    "sse": fetch_sse_announcements,
    "szse": fetch_szse_announcements,
    "bse": fetch_bse_announcements,
}
_INQUIRY_FETCH = {
    "sse": fetch_sse_inquiries,
    "szse": fetch_szse_inquiries,
    "bse": fetch_bse_inquiries,
}
_EXCHANGE_LABELS = {
    "sse": "上海证券交易所",
    "szse": "深圳证券交易所",
    "bse": "北京证券交易所",
}


def resolve_keywords(code_or_name: str) -> dict[str, str]:
    """返回 code / name / keyword（优先简称）。"""
    raw = safe_str(code_or_name)
    code = normalize_code(raw)
    name = ""
    if raw:
        try:
            org = resolve_org(raw)
        except Exception as exc:  # noqa: BLE001
            logger.info("解析公司简称失败 %s: %s", raw, exc)
            org = None
        if org:
            code = safe_str(org.get("code")) or code
            name = safe_str(org.get("name"))
    if not name and (not code or raw != code):
        name = raw
    keyword = name or code or raw
    return {"code": code, "name": name, "keyword": keyword}


def _resolve_channels(code: str, channel: Channel | str) -> list[str]:
    ch = (channel or "auto").lower().strip()
    if ch == "auto":
        market = detect_market(code)
        if market in {"sse", "szse", "bse"}:
            return [market, "cninfo"]
        return ["cninfo"]
    if ch in {"sse", "szse", "bse", "cninfo"}:
        return [ch]
    if ch in {"all", "*"}:
        return ["sse", "szse", "bse", "cninfo"]
    raise ValueError(f"不支持的 channel: {channel}")


def _fetch_pack(
    fetcher: Callable[..., dict[str, Any]],
    target: str,
    *,
    start: datetime | None = None,
    end: datetime | None = None,
    days: int | None = None,
    max_pages: int | None = None,
    **extra: Any,
) -> list[dict[str, Any]]:
    kwargs: dict[str, Any] = dict(extra)
    if max_pages is not None:
        kwargs["max_pages"] = max_pages
    if start is not None:
        kwargs["start"] = start
    if end is not None:
        kwargs["end"] = end
    if days is not None and start is None:
        kwargs["days"] = days
    elif start is not None:
        kwargs["days"] = None
    try:
        return unpack(fetcher(target, **kwargs))
    except TypeError:
        kwargs.pop("days", None)
        if "max_pages" in kwargs:
            try:
                return unpack(fetcher(target, **kwargs))
            except TypeError:
                kwargs.pop("max_pages", None)
        return unpack(fetcher(target, **kwargs))


def _safe_unpack(fetcher: Callable[..., dict[str, Any]], target: str, **kwargs: Any) -> list[dict[str, Any]]:
    try:
        return _fetch_pack(fetcher, target, **kwargs)
    except Exception as exc:  # noqa: BLE001
        logger.warning("%s 失败 %s: %s", getattr(fetcher, "__name__", fetcher), target, exc)
        return []


def query_announcements(
    code: str,
    *,
    channel: Channel | str = "auto",
    start: datetime | None = None,
    end: datetime | None = None,
    days: int | None = 365,
    max_pages: int = 20,
) -> list[dict[str, Any]]:
    """查询指定公司交易所 / 巨潮公告。"""
    code = normalize_code(code)
    if not code:
        return []
    if start is None and days is not None:
        start = default_start(days)

    collected: list[dict[str, Any]] = []
    for ch in _resolve_channels(code, channel):
        if ch == "cninfo":
            rows = _fetch_pack(
                fetch_cninfo_announcements,
                code,
                start=start,
                end=end,
                days=days,
                max_pages=max_pages,
            )
        else:
            fetcher = _EXCHANGE_FETCH.get(ch)
            if fetcher is None:
                continue
            rows = _fetch_pack(
                fetcher,
                code,
                start=start,
                end=end,
                days=days,
                max_pages=max_pages,
            )
        name = rows[0].get("name", "") if rows else ""
        collected.extend(
            as_notice(row, channel=ch, code=code, name=name) for row in rows
        )

    filtered = [x for x in collected if within_range(x, start, end)]
    return sorted(dedupe(filtered), key=sort_key)


def query_cninfo(
    code: str,
    *,
    tab: str = "fulltext",
    category: str | None = None,
    keyword: str = "",
    start: datetime | str | None = None,
    end: datetime | str | None = None,
    days: int | None = 365,
    plate: str = "",
    column: str | None = None,
    max_pages: int = 20,
    limit: int = 0,
) -> dict[str, Any]:
    """巨潮公告：页签 / 分类 / 关键词 / 日期，保持原包字段并收成统一公告条目。"""
    raw = safe_str(code)
    stock = normalize_code(raw) or raw
    if not stock:
        raise ValueError("缺少公司代码 code")
    pack = fetch_cninfo_announcements(
        stock,
        start=start,
        end=end,
        days=days,
        column=column,
        tab=tab or "fulltext",
        category=category or None,
        keyword=keyword,
        plate=plate,
        max_pages=max_pages,
    )
    name = safe_str(pack.get("name"))
    tab_name = safe_str(pack.get("tab")) or (tab or "fulltext")
    items = []
    for row in unpack(pack):
        if isinstance(row, dict):
            row["tab"] = row.get("tab") or tab_name
            row["why"] = item_why(row.get("tab") or tab_name, safe_str(row.get("category")))
        items.append(
            as_notice(row, channel="cninfo", code=safe_str(pack.get("code")) or stock, name=name)
        )
    if limit > 0:
        items = items[: int(limit)]
    out = dict(pack)
    out["kind"] = "cninfo"
    out["items"] = items
    out["count"] = len(items)
    return out


def _normalize_exchange_tab(tab: str | None) -> str:
    raw = safe_str(tab).lower()
    if raw in {"inquiry", "inquiries", "问询", "问询函", "监管"}:
        return "inquiries"
    return "bulletin"


def _exchange_empty(
    code: str,
    *,
    market: str,
    tab: str,
    category: str = "",
    keyword: str = "",
    error: str = "",
) -> dict[str, Any]:
    return {
        "code": code,
        "name": "",
        "kind": "exchange",
        "market": market,
        "market_label": _EXCHANGE_LABELS.get(market, ""),
        "tab": tab,
        "category": category,
        "keyword": keyword,
        "items": [],
        "count": 0,
        "total": 0,
        "error": error,
        "se_date": "",
        "page": "",
    }


def query_exchange(
    code: str,
    *,
    tab: str = "bulletin",
    category: str | None = None,
    keyword: str = "",
    start: datetime | str | None = None,
    end: datetime | str | None = None,
    days: int | None = 365,
    max_pages: int = 20,
    limit: int = 0,
) -> dict[str, Any]:
    """按股票所属交易所查一手公告：分类 / 关键词 / 日期 / 问询函。"""
    raw = safe_str(code)
    stock = normalize_code(raw) or raw
    if not stock:
        raise ValueError("缺少公司代码 code")
    tab_name = _normalize_exchange_tab(tab)
    cat = safe_str(category)
    kw = safe_str(keyword)
    market = detect_market(stock)
    if market not in _EXCHANGE_FETCH:
        return _exchange_empty(
            stock,
            market=market or "unknown",
            tab=tab_name,
            category=cat,
            keyword=kw,
            error="无法识别所属交易所，仅支持沪深北上市公司",
        )

    if tab_name == "inquiries":
        fetcher = _INQUIRY_FETCH[market]
        kwargs: dict[str, Any] = {
            "start": start,
            "end": end,
            "days": days,
            "max_pages": max_pages,
        }
        if market == "bse":
            kwargs["keyword"] = "问询函"
        pack = fetcher(stock, **kwargs)
    else:
        pack = _EXCHANGE_FETCH[market](
            stock,
            start=start,
            end=end,
            days=days,
            category=cat or None,
            keyword=kw,
            max_pages=max_pages,
        )

    name = safe_str(pack.get("name"))
    items: list[dict[str, Any]] = []
    for row in unpack(pack):
        title = safe_str(row.get("title"))
        if tab_name == "inquiries" and kw and kw not in title:
            continue
        if isinstance(row, dict) and not row.get("why"):
            row["why"] = safe_str(row.get("category") or row.get("heading")) or (
                "问询函" if tab_name == "inquiries" else "公告"
            )
        items.append(
            as_notice(
                row,
                channel=market,
                code=safe_str(pack.get("code")) or stock,
                name=name,
            )
        )
    if limit > 0:
        items = items[: int(limit)]

    begin = safe_str(pack.get("begin_date"))
    finish = safe_str(pack.get("end_date"))
    out = dict(pack)
    out["kind"] = "exchange"
    out["market"] = market
    out["market_label"] = _EXCHANGE_LABELS.get(market, "")
    out["tab"] = tab_name
    out["category"] = cat
    out["keyword"] = kw
    out["items"] = items
    out["count"] = len(items)
    out["total"] = int(pack.get("total") or 0) or len(items)
    out["se_date"] = f"{begin} ~ {finish}" if begin or finish else ""
    return out


def _regulatory_kind(title: str) -> str:
    sub = infer_subcategory(title, fallback="regulatory")
    if sub in {"inquiry", "penalty"}:
        return sub
    return "regulatory"


def _is_regulatory_title(title: str) -> bool:
    return any(k in title for k in REGULATORY_TITLE_KEYWORDS)


def query_regulatory(
    code: str,
    *,
    start: datetime | None = None,
    end: datetime | None = None,
    days: int | None = 365 * 2,
    max_pages: int = 20,
) -> list[dict[str, Any]]:
    """问询函、监管措施、处罚相关信息披露。"""
    code = normalize_code(code)
    if not code:
        return []
    if start is None and days is not None:
        start = default_start(days)

    collected: list[dict[str, Any]] = []
    market = detect_market(code)
    page_cap = min(20, max_pages)
    inquiry = _INQUIRY_FETCH.get(market)
    if inquiry is not None:
        rows = _fetch_pack(
            inquiry,
            code,
            start=start,
            end=end,
            days=days,
            max_pages=page_cap,
        )
        name = rows[0].get("name", "") if rows else ""
        collected.extend(
            as_regulatory(row, kind="inquiry", code=code, name=name) for row in rows
        )

    cn_rows = _fetch_pack(
        fetch_cninfo_announcements,
        code,
        start=start,
        end=end,
        days=days,
        max_pages=max_pages,
    )
    for row in cn_rows:
        title = safe_str(row.get("title"))
        if not _is_regulatory_title(title):
            continue
        collected.append(
            as_regulatory(
                row,
                kind=_regulatory_kind(title),
                code=code,
                name=safe_str(row.get("name")),
            )
        )

    filtered = [x for x in collected if within_range(x, start, end)]
    return sorted(dedupe(filtered), key=sort_key)


def query_company_messages(
    code: str,
    *,
    channel: Channel | str = "auto",
    include_regulatory: bool = True,
    start: datetime | None = None,
    end: datetime | None = None,
    days: int | None = 365,
    max_pages: int = 20,
) -> dict[str, Any]:
    """一次返回公告 +（可选）监管信息。"""
    code = normalize_code(code)
    notices = query_announcements(
        code,
        channel=channel,
        start=start,
        end=end,
        days=days,
        max_pages=max_pages,
    )
    regulatory: list[dict[str, Any]] = []
    if include_regulatory:
        regulatory = query_regulatory(
            code,
            start=start,
            end=end,
            days=days if days is not None else 365 * 2,
            max_pages=max_pages,
        )
    return {
        "code": code,
        "market": detect_market(code),
        "channel": channel,
        "notices": notices,
        "regulatory": regulatory,
        "notice_count": len(notices),
        "regulatory_count": len(regulatory),
    }


def query_market_news(
    code: str,
    name: str = "",
    *,
    start: datetime | None = None,
    end: datetime | None = None,
    days: int | None = 365,
    max_pages: int = 5,
    em_kind: str = "old",
) -> list[dict[str, Any]]:
    """东方财富 / 同花顺 / 雪球新闻。"""
    code = normalize_code(code) or safe_str(code)
    name = safe_str(name)
    target = code or name
    if not target:
        return []
    if start is None and days is not None:
        start = default_start(days)

    side_pages = min(max_pages, 8)
    jobs: list[Callable[[], list[dict[str, Any]]]] = [
        lambda: _safe_unpack(
            fetch_eastmoney_news,
            target,
            start=start,
            end=end,
            days=days,
            max_pages=max_pages,
            kind=em_kind,
        ),
    ]
    if name and name != target:
        jobs.append(
            lambda: _safe_unpack(
                fetch_eastmoney_news,
                name,
                start=start,
                end=end,
                days=days,
                max_pages=max_pages,
                kind=em_kind,
            )
        )
    if code:
        jobs.extend(
            [
                lambda: _safe_unpack(
                    fetch_ths_news,
                    code,
                    start=start,
                    end=end,
                    days=days,
                    max_pages=side_pages,
                ),
                lambda: _safe_unpack(
                    fetch_xq_news,
                    code,
                    start=start,
                    end=end,
                    days=days,
                    max_pages=side_pages,
                ),
            ]
        )

    collected: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=min(4, len(jobs))) as pool:
        for fut in as_completed([pool.submit(fn) for fn in jobs]):
            collected.extend(fut.result())

    tagged = [as_news(x, code=code, name=name) for x in collected]
    return sorted(dedupe([x for x in tagged if within_range(x, start, end)]), key=sort_key)


def query_reports(
    code: str,
    name: str = "",
    *,
    start: datetime | None = None,
    end: datetime | None = None,
    days: int | None = None,
    max_pages: int = 8,
) -> list[dict[str, Any]]:
    """同花顺 / 雪球研报。"""
    code = normalize_code(code) or safe_str(code)
    name = safe_str(name)
    if not code:
        return []
    if start is None and days is not None:
        start = default_start(days)

    collected: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=2) as pool:
        futs = [
            pool.submit(
                _safe_unpack,
                fetch_ths_reports,
                code,
                start=start,
                end=end,
                days=days,
            ),
            pool.submit(
                _safe_unpack,
                fetch_xq_reports,
                code,
                start=start,
                end=end,
                days=days,
                max_pages=min(max_pages, 8),
            ),
        ]
        for fut in as_completed(futs):
            collected.extend(fut.result())

    tagged = [as_report(x, code=code, name=name) for x in collected]
    return sorted(dedupe([x for x in tagged if within_range(x, start, end)]), key=sort_key)


def _select_outlets(outlet: str | Iterable[str] | None) -> list[dict[str, str]]:
    if outlet is None or outlet == "all":
        return list(PRESS_OUTLETS)
    if isinstance(outlet, str):
        ids = [x.strip() for x in outlet.split(",") if x.strip()]
    else:
        ids = [str(x).strip() for x in outlet if str(x).strip()]
    if not ids or ids == ["all"]:
        return list(PRESS_OUTLETS)
    selected: list[dict[str, str]] = []
    for oid in ids:
        if oid not in PRESS_BY_ID:
            raise ValueError(
                f"未知媒体 id: {oid}；可选: {', '.join(PRESS_BY_ID)}"
            )
        selected.append(PRESS_BY_ID[oid])
    return selected


_OUTLET_EXTRA_KEYS: dict[str, tuple[str, ...]] = {
    "cs": ("field", "sort"),
    "cnstock": ("type_",),
    "stcn": ("type_", "sort"),
    "zqrb": ("src", "field", "sort", "fuzzy"),
    "financialnews": ("field", "sort"),
    "jjckb": (),
    "chinadaily": ("type_", "sort"),
}


def _outlet_extras(outlet_id: str, extra: dict[str, Any]) -> dict[str, Any]:
    allowed = _OUTLET_EXTRA_KEYS.get(outlet_id, ())
    out: dict[str, Any] = {}
    type_val = extra.get("type_") or extra.get("type")
    for key in allowed:
        val = type_val if key == "type_" else extra.get(key)
        if val is None or val == "":
            continue
        out[key] = val
    return out


def _fetch_outlet(
    outlet: dict[str, str],
    keyword: str,
    *,
    start: datetime | str | None,
    end: datetime | str | None,
    days: int | None,
    max_pages: int,
    code: str,
    name: str,
    extra: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    fetcher = PRESS_FETCHERS.get(outlet["id"])
    if fetcher is None:
        return []
    kwargs: dict[str, Any] = {"max_pages": max_pages}
    if start is not None:
        kwargs["start"] = start
    if end is not None:
        kwargs["end"] = end
    if days is not None and start is None:
        kwargs["days"] = days
    elif start is not None:
        kwargs["days"] = None
    kwargs.update(_outlet_extras(outlet["id"], extra or {}))
    try:
        pack = fetcher(keyword, **kwargs)
    except TypeError:
        for key in _OUTLET_EXTRA_KEYS.get(outlet["id"], ()):
            kwargs.pop(key, None)
        pack = fetcher(keyword, **kwargs)
    rows = unpack(pack)
    return [
        as_press(
            row,
            outlet_id=outlet["id"],
            paper=outlet.get("paper", ""),
            code=code or safe_str(row.get("code")),
            name=name or safe_str(row.get("name")),
        )
        for row in rows
    ]


def query_press(
    code_or_name: str,
    *,
    outlet: str | Iterable[str] | None = "all",
    start: datetime | str | None = None,
    end: datetime | str | None = None,
    days: int | None = 365,
    max_pages: int = 4,
    keyword: str = "",
    field: str | None = None,
    type_: str | None = None,
    sort: str | None = None,
    src: str | None = None,
    fuzzy: bool | None = None,
    limit: int = 0,
) -> dict[str, Any]:
    """查询指定公司在七家指定披露媒体官网上的相关消息。"""
    resolved = resolve_keywords(code_or_name)
    code = resolved["code"]
    name = resolved["name"]
    search_kw = resolved["keyword"]
    title_kw = safe_str(keyword)
    if not search_kw:
        return {
            "code": code,
            "name": name,
            "keyword": title_kw,
            "search_keyword": search_kw,
            "kind": "press",
            "outlets": {},
            "items": [],
            "count": 0,
            "counts": {},
            "errors": {},
        }

    if start is None and days is not None:
        start = default_start(days)

    extra = {
        "field": field,
        "type_": type_,
        "sort": sort,
        "src": src,
        "fuzzy": fuzzy,
    }
    outlets = _select_outlets(outlet)
    by_outlet: dict[str, list[dict[str, Any]]] = {}
    errors: dict[str, str] = {}

    def _job(o: dict[str, str]) -> tuple[str, list[dict[str, Any]], str]:
        try:
            rows = _fetch_outlet(
                o,
                search_kw,
                start=start,
                end=end,
                days=days,
                max_pages=max_pages,
                code=code,
                name=name,
                extra=extra,
            )
            if title_kw:
                rows = [x for x in rows if title_kw in safe_str(x.get("title"))]
            return o["id"], sorted(dedupe(rows), key=sort_key), ""
        except Exception as exc:  # noqa: BLE001
            logger.warning("七网采集失败 %s: %s", o["id"], exc)
            return o["id"], [], str(exc)

    workers = min(7, max(1, len(outlets)))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = [pool.submit(_job, o) for o in outlets]
        for fut in as_completed(futs):
            oid, rows, err = fut.result()
            by_outlet[oid] = rows
            if err:
                errors[oid] = err

    for o in outlets:
        by_outlet.setdefault(o["id"], [])

    flat: list[dict[str, Any]] = []
    for rows in by_outlet.values():
        flat.extend(rows)
    flat = sorted(dedupe(flat), key=sort_key)
    if limit > 0:
        flat = flat[: int(limit)]
    begin = safe_str(start)[:10]
    finish = safe_str(end)[:10]
    se_date = f"{begin} ~ {finish}" if begin or finish else ""

    return {
        "code": code,
        "name": name,
        "keyword": title_kw,
        "search_keyword": search_kw,
        "kind": "press",
        "outlet": outlets[0]["id"] if len(outlets) == 1 else "all",
        "outlets": by_outlet,
        "counts": {oid: len(rows) for oid, rows in by_outlet.items()},
        "items": flat,
        "count": len(flat),
        "total": len(flat),
        "errors": errors,
        "error": next(iter(errors.values()), "") if len(outlets) == 1 else "",
        "se_date": se_date,
    }


_PLATFORM_ALIASES = {
    "ths": "tonghuashun",
    "tonghuashun": "tonghuashun",
    "10jqka": "tonghuashun",
    "xq": "xueqiu",
    "xueqiu": "xueqiu",
    "snowball": "xueqiu",
    "em": "eastmoney",
    "eastmoney": "eastmoney",
}
_PLATFORM_TABS = {
    "tonghuashun": ("news", "notices", "reports"),
    "xueqiu": ("news", "notices", "reports"),
    "eastmoney": ("news", "f10", "notices"),
}
_PLATFORM_LABELS = {
    "tonghuashun": "同花顺",
    "xueqiu": "雪球",
    "eastmoney": "东方财富",
}
_PLATFORM_FETCHERS: dict[str, dict[str, Callable[..., dict[str, Any]]]] = {
    "tonghuashun": {
        "news": fetch_ths_news,
        "notices": fetch_ths_notices,
        "reports": fetch_ths_reports,
    },
    "xueqiu": {
        "news": fetch_xq_news,
        "notices": fetch_xq_notices,
        "reports": fetch_xq_reports,
    },
    "eastmoney": {
        "news": fetch_eastmoney_news,
        "f10": fetch_eastmoney_f10,
        "notices": fetch_eastmoney_notices,
    },
}


def resolve_platform(source: str) -> str:
    key = (source or "").strip().lower()
    if key not in _PLATFORM_ALIASES:
        raise ValueError("未知平台；可选 ths / xueqiu / eastmoney")
    return _PLATFORM_ALIASES[key]


def _platform_extra(
    source: str,
    tab: str,
    *,
    classify: str | None = None,
    kind: str | None = None,
    scope: str | None = None,
    sort: str | None = None,
    strict: bool = False,
) -> dict[str, Any]:
    extra: dict[str, Any] = {}
    if source == "tonghuashun" and tab == "notices":
        if classify:
            extra["classify"] = classify
    if source == "eastmoney" and tab == "news":
        extra["kind"] = kind or "old"
        extra["scope"] = scope or "default"
        extra["sort"] = sort or "time"
    if source == "xueqiu" and tab == "reports" and sort:
        extra["sort"] = sort
    if tab in {"news", "notices"} and source != "eastmoney":
        extra["strict"] = bool(strict)
    elif source == "eastmoney" and tab == "news":
        extra["strict"] = bool(strict)
    return extra


def _call_platform_fetcher(
    fetcher: Callable[..., dict[str, Any]],
    target: str,
    *,
    start: datetime | str | None,
    end: datetime | str | None,
    days: int | None,
    max_pages: int,
    extra: dict[str, Any],
) -> dict[str, Any]:
    kwargs: dict[str, Any] = dict(extra)
    kwargs["max_pages"] = max_pages
    if start is not None:
        kwargs["start"] = start
    if end is not None:
        kwargs["end"] = end
    if days is not None and start is None:
        kwargs["days"] = days
    elif start is not None:
        kwargs["days"] = None
    try:
        pack = fetcher(target, **kwargs)
    except TypeError:
        for key in list(kwargs):
            if key not in {"start", "end", "days", "max_pages"}:
                kwargs.pop(key, None)
        try:
            pack = fetcher(target, **kwargs)
        except TypeError:
            kwargs.pop("max_pages", None)
            kwargs.pop("days", None)
            pack = fetcher(target, **kwargs)
    return pack if isinstance(pack, dict) else {"items": [], "error": "返回格式异常"}


def _tag_platform_item(
    row: dict[str, Any],
    *,
    tab: str,
    source: str,
    code: str,
    name: str,
) -> dict[str, Any]:
    channel = safe_str(row.get("channel"))
    if tab == "reports" or channel == "report":
        return as_report(row, code=code, name=name)
    if tab == "notices" or channel in {"notice", "f10_notice"}:
        return as_notice(row, channel=source, code=code, name=name)
    tagged = as_news(row, code=code, name=name)
    if channel == "f10_news":
        tagged["why"] = tagged.get("why") or "F10资讯"
    return tagged


def query_platform(
    code_or_name: str,
    *,
    source: str,
    tab: str = "news",
    start: datetime | str | None = None,
    end: datetime | str | None = None,
    days: int | None = 31,
    max_pages: int = 8,
    keyword: str = "",
    classify: str | None = None,
    kind: str | None = None,
    scope: str | None = None,
    sort: str | None = None,
    strict: bool = False,
    limit: int = 0,
) -> dict[str, Any]:
    """按同花顺 / 雪球 / 东方财富各自的新闻查询方式拉个股资讯。"""
    src = resolve_platform(source)
    tab_name = (tab or "news").strip().lower()
    allowed = _PLATFORM_TABS[src]
    if tab_name not in allowed:
        raise ValueError(f"{_PLATFORM_LABELS[src]}不支持页签 {tab}；可选 {', '.join(allowed)}")

    resolved = resolve_keywords(code_or_name)
    code = resolved["code"]
    name = resolved["name"]
    target = code or resolved["keyword"] or safe_str(code_or_name)
    title_kw = safe_str(keyword)
    label = _PLATFORM_LABELS[src]
    begin = safe_str(start)[:10]
    finish = safe_str(end)[:10]
    se_date = f"{begin} ~ {finish}" if begin or finish else ""
    empty = {
        "code": code,
        "name": name,
        "keyword": title_kw,
        "search_keyword": resolved["keyword"],
        "kind": "platform",
        "source": src,
        "source_label": label,
        "tab": tab_name,
        "items": [],
        "count": 0,
        "total": 0,
        "se_date": se_date,
        "error": "",
    }
    if not target:
        empty["error"] = "缺少股票代码"
        return empty

    if start is None and days is not None:
        start = default_start(days)

    fetcher = _PLATFORM_FETCHERS[src][tab_name]
    extra = _platform_extra(
        src,
        tab_name,
        classify=classify,
        kind=kind,
        scope=scope,
        sort=sort,
        strict=strict,
    )
    try:
        pack = _call_platform_fetcher(
            fetcher,
            target,
            start=start,
            end=end,
            days=days,
            max_pages=max_pages,
            extra=extra,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("%s %s 采集失败 %s: %s", src, tab_name, target, exc)
        empty["error"] = str(exc)
        return empty

    rows = unpack(pack)
    items = [
        _tag_platform_item(row, tab=tab_name, source=src, code=code or safe_str(row.get("code")), name=name or safe_str(row.get("name")))
        for row in rows
    ]
    if title_kw:
        items = [x for x in items if title_kw in safe_str(x.get("title"))]
    items = sorted(dedupe(items), key=sort_key)
    if limit > 0:
        items = items[: int(limit)]

    begin = safe_str(pack.get("begin_date")) or begin
    finish = safe_str(pack.get("end_date")) or finish
    return {
        "code": pack.get("code") or code,
        "name": pack.get("name") or name,
        "keyword": title_kw,
        "search_keyword": pack.get("keyword") or resolved["keyword"],
        "kind": "platform",
        "source": src,
        "source_label": label,
        "tab": tab_name,
        "classify": extra.get("classify") or "",
        "em_kind": extra.get("kind") or "",
        "scope": extra.get("scope") or "",
        "sort": extra.get("sort") or "",
        "items": items,
        "count": len(items),
        "total": int(pack.get("total") or 0) or len(items),
        "page": pack.get("page") or "",
        "se_date": f"{begin} ~ {finish}" if begin or finish else se_date,
        "error": safe_str(pack.get("error")),
    }
