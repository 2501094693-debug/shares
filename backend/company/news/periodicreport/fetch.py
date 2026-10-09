"""拉取一家公司定期报告：巨潮优先，交易所回退；按报告期去重后供前端选择。"""

from __future__ import annotations

import logging
from typing import Any

from core.codes import detect_market, normalize_code, safe_str

from company.news.official.cninfo import fetch_periodic_reports as fetch_cninfo_periodic
from company.news.official.cninfo.constants import MAX_PAGES as CNINFO_MAX_PAGES
from company.news.periodicreport._common import (
    CNINFO_KINDS,
    KIND_LABELS,
    KIND_RANK,
    infer_kind,
    infer_report_year,
    is_cancelled_title,
    is_english_title,
    is_summary_title,
    period_key,
    period_label,
)

logger = logging.getLogger(__name__)

DEFAULT_DAYS = 365 * 5


def _exchange_fetch(code: str, *, days: int | None, max_pages: int) -> dict[str, Any]:
    market = detect_market(code)
    if market == "sse":
        from company.news.official.exchange.sse import fetch_periodic_reports as fetch_fn
    elif market == "szse":
        from company.news.official.exchange.szse import fetch_periodic_reports as fetch_fn
    elif market == "bse":
        from company.news.official.exchange.bse import fetch_periodic_reports as fetch_fn
    else:
        return {
            "code": normalize_code(code) or safe_str(code),
            "name": "",
            "items": [],
            "error": f"无法识别市场: {code}",
            "source": "exchange",
        }
    return fetch_fn(code, kind=list(CNINFO_KINDS), days=days, max_pages=max_pages)


def _size_num(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _normalize_item(row: dict[str, Any], *, source: str) -> dict[str, Any] | None:
    title = safe_str(row.get("title"))
    if not title or is_summary_title(title) or is_english_title(title) or is_cancelled_title(title):
        return None
    kind = infer_kind(title, safe_str(row.get("category") or row.get("heading")))
    if not kind:
        return None
    published_at = safe_str(row.get("published_at") or row.get("notice_date"))
    year = infer_report_year(title, published_at)
    if not year:
        return None
    url = safe_str(row.get("url") or row.get("pdf_url"))
    if not url:
        return None
    kind_label = KIND_LABELS.get(kind, "定期报告")
    return {
        "code": normalize_code(safe_str(row.get("code"))) or safe_str(row.get("code")),
        "name": safe_str(row.get("name")),
        "announcement_id": safe_str(
            row.get("announcement_id") or row.get("art_code") or row.get("article_id")
        ),
        "title": title,
        "published_at": published_at,
        "published_date": published_at[:10] if published_at else "",
        "url": url,
        "pdf_url": safe_str(row.get("pdf_url") or url),
        "adjunct_size": row.get("adjunct_size"),
        "source": safe_str(row.get("source"))
        or ("巨潮资讯" if source == "cninfo" else source),
        "kind": kind,
        "kind_label": kind_label,
        "report_year": year,
        "period_key": period_key(year, kind),
        "period_label": period_label(kind, year),
    }


def _is_better(candidate: dict[str, Any], current: dict[str, Any]) -> bool:
    cand_time = safe_str(candidate.get("published_at"))
    cur_time = safe_str(current.get("published_at"))
    if cand_time != cur_time:
        return cand_time > cur_time
    return _size_num(candidate.get("adjunct_size")) > _size_num(current.get("adjunct_size"))


def _build_periods(raw_items: list[Any], *, source: str) -> list[dict[str, Any]]:
    best: dict[str, dict[str, Any]] = {}
    for row in raw_items:
        if not isinstance(row, dict):
            continue
        item = _normalize_item(row, source=source)
        if not item:
            continue
        key = item["period_key"]
        prev = best.get(key)
        if prev is None or _is_better(item, prev):
            best[key] = item

    periods = list(best.values())
    # 最新披露优先；同年同披露日再按报告类型排序
    periods.sort(
        key=lambda row: (
            safe_str(row.get("published_at")),
            safe_str(row.get("report_year")),
            KIND_RANK.get(safe_str(row.get("kind")), 0),
        ),
        reverse=True,
    )
    return periods


def pick_period(periods: list[dict[str, Any]], period: str = "") -> dict[str, Any] | None:
    if not periods:
        return None
    want = safe_str(period)
    if not want:
        return periods[0]
    for row in periods:
        if row.get("period_key") == want or row.get("period_label") == want:
            return row
    return periods[0]


def shape_for_frontend(
    pack: dict[str, Any],
    *,
    source: str,
    days: int | None,
    period: str = "",
) -> dict[str, Any]:
    periods = _build_periods(pack.get("items") or [], source=source)
    selected = pick_period(periods, period)
    latest = periods[0] if periods else None
    code = normalize_code(safe_str(pack.get("code"))) or safe_str(pack.get("code"))
    name = safe_str(pack.get("name")) or (safe_str(periods[0].get("name")) if periods else "")

    out: dict[str, Any] = {
        "code": code,
        "name": name,
        "source": source,
        "channel": "periodic_report",
        "days": days if days is not None else "",
        "count": len(periods),
        "periods": [
            {
                "period_key": row["period_key"],
                "period_label": row["period_label"],
                "report_year": row["report_year"],
                "kind": row["kind"],
                "kind_label": row["kind_label"],
            }
            for row in periods
        ],
        "latest": latest,
        "selected": selected,
        "items": periods,
    }
    if pack.get("error") and not periods:
        out["error"] = safe_str(pack.get("error"))
    return out


def fetch_periodic_report(
    code: str,
    *,
    days: int | None = DEFAULT_DAYS,
    max_pages: int = CNINFO_MAX_PAGES,
    period: str = "",
) -> dict[str, Any]:
    """正文 PDF，按报告期去重；``period`` 为空时 selected=最新一期。"""
    stock = normalize_code(code) or safe_str(code)
    if not stock:
        raise ValueError("无效股票代码")

    pages = max(1, min(int(max_pages or CNINFO_MAX_PAGES), CNINFO_MAX_PAGES))
    used = "cninfo"
    try:
        pack = fetch_cninfo_periodic(
            stock,
            kind=list(CNINFO_KINDS),
            days=days,
            max_pages=pages,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("巨潮定期报告失败 %s: %s", stock, exc)
        pack = {"code": stock, "items": [], "error": str(exc)}

    if pack.get("error") or not (pack.get("items") or []):
        try:
            fallback = _exchange_fetch(stock, days=days, max_pages=pages)
            if fallback.get("items"):
                pack = fallback
                used = "exchange"
        except Exception as exc:  # noqa: BLE001
            logger.warning("交易所定期报告回退失败 %s: %s", stock, exc)

    return shape_for_frontend(pack, source=used, days=days, period=period)
