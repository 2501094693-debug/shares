"""统一查询：公告、监管、七网、市场新闻、研报。"""

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
from company.news.platforms.eastmoney.search import fetch_news as fetch_eastmoney_news
from company.news.platforms.tonghuashun.news import fetch_news as fetch_ths_news
from company.news.platforms.tonghuashun.reports import fetch_reports as fetch_ths_reports
from company.news.platforms.xueqiu.news import fetch_news as fetch_xq_news
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


def _fetch_outlet(
    outlet: dict[str, str],
    keyword: str,
    *,
    start: datetime | None,
    end: datetime | None,
    days: int | None,
    max_pages: int,
    code: str,
    name: str,
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
    start: datetime | None = None,
    end: datetime | None = None,
    days: int | None = 365,
    max_pages: int = 4,
) -> dict[str, Any]:
    """查询指定公司在七家指定披露媒体官网上的相关消息。"""
    resolved = resolve_keywords(code_or_name)
    code = resolved["code"]
    name = resolved["name"]
    keyword = resolved["keyword"]
    if not keyword:
        return {
            "code": code,
            "name": name,
            "keyword": keyword,
            "outlets": {},
            "items": [],
            "count": 0,
            "counts": {},
            "errors": {},
        }

    if start is None and days is not None:
        start = default_start(days)

    outlets = _select_outlets(outlet)
    by_outlet: dict[str, list[dict[str, Any]]] = {}
    errors: dict[str, str] = {}

    def _job(o: dict[str, str]) -> tuple[str, list[dict[str, Any]], str]:
        try:
            rows = _fetch_outlet(
                o,
                keyword,
                start=start,
                end=end,
                days=days,
                max_pages=max_pages,
                code=code,
                name=name,
            )
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

    return {
        "code": code,
        "name": name,
        "keyword": keyword,
        "outlets": by_outlet,
        "counts": {oid: len(rows) for oid, rows in by_outlet.items()},
        "items": flat,
        "count": len(flat),
        "errors": errors,
    }
