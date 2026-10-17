"""东方财富分红：请求、解析与字段映射。

接入两套东财接口（均为公开 Web 接口）：

- datacenter ``RPT_SHAREBONUS_DET``：按**报告期**的结构化分红明细，
  给出每 10 股税前派息、分红进度、除权除息日、总股本，可直接算出现金分红总额。
- F10 ``BonusFinancing/PageAjax``：``fhyx`` 逐次方案 + ``lnfhrz`` 历年现金分红总额
  与增发 / 配股 / IPO 次数（用于摊薄判断）。

金额统一为**元**。
"""

from __future__ import annotations

import logging
from typing import Any

from core.codes import em_code, normalize_code
from core.fmt import to_float
from core.http import browser_get, get_json

logger = logging.getLogger(__name__)

_DC_URL = "https://datacenter-web.eastmoney.com/api/data/v1/get"
_DC_REPORT = "RPT_SHAREBONUS_DET"
_DC_HEADERS = {"Referer": "https://data.eastmoney.com/"}

_F10_URL = "https://emweb.securities.eastmoney.com/PC_HSF10/BonusFinancing/PageAjax"
_F10_HEADERS = {"Referer": "https://emweb.securities.eastmoney.com/"}

# 分红进度：命中「实施」视为已落地，命中「预案/预披露」视为未落地。
_IMPLEMENTED_KEYS = ("实施",)
_PLANNED_KEYS = ("预案", "预披露", "意向", "董事会", "股东大会")


def _date(value: Any) -> str:
    text = str(value or "").strip()
    return text[:10] if len(text) >= 10 else text


def _progress_flag(progress: Any) -> str:
    text = str(progress or "")
    if any(key in text for key in _IMPLEMENTED_KEYS):
        return "implemented"
    if any(key in text for key in _PLANNED_KEYS):
        return "planned"
    return "other"


def per10_to_total(per10: Any, shares: Any) -> float | None:
    """每 10 股派息（元）× 总股本 ÷ 10 → 现金分红总额（元）。"""
    rate = to_float(per10)
    total_shares = to_float(shares)
    if rate is None or total_shares is None:
        return None
    return rate * total_shares / 10.0


def parse_detail_row(row: dict[str, Any]) -> dict[str, Any] | None:
    """``RPT_SHAREBONUS_DET`` 单行 → 结构化分红明细。"""
    if not isinstance(row, dict):
        return None
    report = _date(row.get("REPORT_DATE"))
    if not report:
        return None
    per10 = to_float(row.get("PRETAX_BONUS_RMB"))
    shares = to_float(row.get("TOTAL_SHARES"))
    progress = str(row.get("ASSIGN_PROGRESS") or "").strip()
    return {
        "report_date": report,
        "year": report[:4],
        "progress": progress,
        "status": _progress_flag(progress),
        "plan": str(row.get("IMPL_PLAN_PROFILE") or "").strip(),
        "pretax_bonus_per10": per10,
        "total_shares": shares,
        "cash_total": per10_to_total(per10, shares),
        "equity_record_date": _date(row.get("EQUITY_RECORD_DATE")),
        "ex_dividend_date": _date(row.get("EX_DIVIDEND_DATE")),
        "bonus_ratio": to_float(row.get("BONUS_RATIO")),
        "it_ratio": to_float(row.get("IT_RATIO")),
        "dividend_ratio": to_float(row.get("DIVIDENT_RATIO")),
        "notice_date": _date(row.get("NOTICE_DATE")),
        "publish_date": _date(row.get("PUBLISH_DATE")),
    }


def parse_history_row(row: dict[str, Any]) -> dict[str, Any] | None:
    """F10 ``fhyx`` 单行 → 逐次分红方案。"""
    if not isinstance(row, dict):
        return None
    notice = _date(row.get("NOTICE_DATE"))
    if not notice:
        return None
    progress = str(row.get("ASSIGN_PROGRESS") or "").strip()
    return {
        "notice_date": notice,
        "plan": str(row.get("IMPL_PLAN_PROFILE") or "").strip(),
        "progress": progress,
        "status": _progress_flag(progress),
        "equity_record_date": _date(row.get("EQUITY_RECORD_DATE")),
        "ex_dividend_date": _date(row.get("EX_DIVIDEND_DATE")),
        "pay_cash_date": _date(row.get("PAY_CASH_DATE")),
    }


def parse_summary_row(row: dict[str, Any]) -> dict[str, Any] | None:
    """F10 ``lnfhrz`` 单行 → 历年分红融资。"""
    if not isinstance(row, dict):
        return None
    year = str(row.get("STATISTICS_YEAR") or "").strip()
    if not year:
        return None
    return {
        "year": year,
        "total_dividend": to_float(row.get("TOTAL_DIVIDEND")),
        "seo_num": to_float(row.get("SEO_NUM")),
        "allotment_num": to_float(row.get("ALLOTMENT_NUM")),
        "ipo_num": to_float(row.get("IPO_NUM")),
    }


def _meta_from(rows: list[dict[str, Any]]) -> dict[str, str]:
    for row in rows:
        if isinstance(row, dict):
            return {
                "code": str(row.get("SECURITY_CODE") or "").strip(),
                "name": str(row.get("SECURITY_NAME_ABBR") or "").strip(),
            }
    return {"code": "", "name": ""}


def fetch_detail_rows(code: str, *, page_size: int = 60) -> tuple[list[dict[str, Any]], dict[str, str]]:
    """从 datacenter 拉 ``RPT_SHAREBONUS_DET`` 并按报告期倒序。"""
    norm = normalize_code(code)
    if not norm:
        return [], {}
    try:
        payload = get_json(
            _DC_URL,
            params={
                "reportName": _DC_REPORT,
                "columns": "ALL",
                "filter": f'(SECURITY_CODE="{norm}")',
                "pageNumber": "1",
                "pageSize": str(max(1, min(int(page_size or 60), 200))),
                "sortColumns": "REPORT_DATE",
                "sortTypes": "-1",
                "source": "WEB",
                "client": "WEB",
            },
            headers=_DC_HEADERS,
            timeout=20,
            retries=1,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("东财分红明细拉取失败 %s: %s", code, exc)
        return [], {}
    result = payload.get("result") if isinstance(payload, dict) else None
    rows = (result or {}).get("data") if isinstance(result, dict) else None
    raw = [row for row in (rows or []) if isinstance(row, dict)]
    items = [parsed for row in raw if (parsed := parse_detail_row(row))]
    items.sort(key=lambda d: str(d.get("report_date") or ""), reverse=True)
    return items, _meta_from(raw)


def fetch_f10_pack(code: str) -> dict[str, Any]:
    """从东财 F10「分红融资」页拉原始 JSON（``fhyx`` / ``lnfhrz`` / …）。"""
    ec = em_code(code)
    if not ec:
        return {}
    try:
        resp = browser_get(_F10_URL, params={"code": ec}, headers=_F10_HEADERS, timeout=25)
        resp.raise_for_status()
        payload = resp.json()
    except Exception as exc:  # noqa: BLE001
        logger.warning("东财分红融资页拉取失败 %s: %s", code, exc)
        return {}
    return payload if isinstance(payload, dict) else {}


def parse_f10_history(pack: dict[str, Any]) -> list[dict[str, Any]]:
    rows = pack.get("fhyx") if isinstance(pack, dict) else None
    items = [parsed for row in (rows or []) if (parsed := parse_history_row(row))]
    items.sort(key=lambda d: str(d.get("notice_date") or ""), reverse=True)
    return items


def parse_f10_summary(pack: dict[str, Any]) -> list[dict[str, Any]]:
    rows = pack.get("lnfhrz") if isinstance(pack, dict) else None
    items = [parsed for row in (rows or []) if (parsed := parse_summary_row(row))]
    items.sort(key=lambda d: str(d.get("year") or ""), reverse=True)
    return items


def cash_by_year(detail: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """按报告期年份汇总已落地的现金分红总额，供留存 1 美元测试直接使用。"""
    buckets: dict[str, dict[str, Any]] = {}
    for item in detail:
        year = str(item.get("year") or "")
        if not year:
            continue
        bucket = buckets.setdefault(year, {"year": year, "cash_dividend": 0.0, "periods": 0})
        amount = item.get("cash_total")
        if item.get("status") == "implemented" and amount is not None:
            bucket["cash_dividend"] += float(amount)
            bucket["periods"] += 1
    return [buckets[key] for key in sorted(buckets, reverse=True)]


def dilution_flags(summary: list[dict[str, Any]]) -> dict[str, Any]:
    """从历年分红融资汇总增发 / 配股 / IPO 次数。"""
    seo = sum(int(item.get("seo_num") or 0) for item in summary)
    allot = sum(int(item.get("allotment_num") or 0) for item in summary)
    ipo = sum(int(item.get("ipo_num") or 0) for item in summary)
    return {
        "seo_num": seo,
        "allotment_num": allot,
        "ipo_num": ipo,
        "has_dilution": bool(seo or allot),
    }
