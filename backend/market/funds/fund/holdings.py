"""东财基金重仓股与行业配置（F10 页面接口）。"""

from __future__ import annotations

import json
import logging
import re
import time
from typing import Any

from core.fmt import fmt_pct, fmt_signed, to_float
from core.http import get_json, get_text
from core.paths import FUND_HOLDINGS_CACHE_DIR, FUND_HOLDINGS_TTL, ensure_cache_dirs

logger = logging.getLogger(__name__)

_HEADERS = {
    "Referer": "https://fundf10.eastmoney.com/",
    "Accept": "application/json, text/plain, */*",
}
_POSITION_API = "https://fundmobapi.eastmoney.com/FundMNewApi/FundMNInverstPosition"
_JJCC_API = "https://fundf10.eastmoney.com/FundArchivesDatas.aspx"
_INDUSTRY_API = _JJCC_API

_INDUSTRY_ROW_RE = re.compile(
    r"<tr><td>(?P<code>[^<]*)</td>"
    r"<td class='tol'>(?P<name>[^<]*)</td>"
    r"<td class='tor'>(?P<weight>[^<]*)</td>"
    r"<td class='tor'>(?P<peer>[^<]*)</td>"
    r"<td class='tor'>(?P<diff>[^<]*)</td></tr>"
)
_HOLDING_ROW_RE = re.compile(
    r"<tr><td>\d+</td>"
    r"<td><a href='//quote\.eastmoney\.com/unify/r/(?P<market_id>\d)\.(?P<code>\d+)'>(?P=code)</a></td>"
    r"<td class='tol'><a[^>]*>(?P<name>[^<]+)</a></td>"
    r".*?"
    r"<td class='tor'>(?P<weight>[^<]+)</td>"
    r"<td class='tor'>(?P<shares>[^<]+)</td>"
    r"<td class='tor'>(?P<value>[^<]+)</td></tr>",
    re.S,
)
_REPORT_DATE_RE = re.compile(r"px12'>(\d{4}-\d{2}-\d{2})</font>")


def _market_label(market_id: str | int | None) -> str:
    if str(market_id) == "1":
        return "SH"
    if str(market_id) == "0":
        return "SZ"
    return ""


def _cache_path(code: str):
    ensure_cache_dirs()
    safe = code.strip().replace("/", "_")
    return FUND_HOLDINGS_CACHE_DIR / f"{safe}.json"


def _cache_fresh(payload: dict[str, Any] | None) -> bool:
    if not payload:
        return False
    updated = payload.get("updated_at") or ""
    if not updated:
        return False
    try:
        ts = time.mktime(time.strptime(updated, "%Y-%m-%d %H:%M:%S"))
    except ValueError:
        return False
    return (time.time() - ts) < FUND_HOLDINGS_TTL


def _read_cache(code: str) -> dict[str, Any] | None:
    path = _cache_path(code)
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _write_cache(code: str, payload: dict[str, Any]) -> None:
    ensure_cache_dirs()
    _cache_path(code).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _normalize_mobile_stock(row: dict[str, Any]) -> dict[str, Any]:
    code = str(row.get("GPDM") or "").strip()
    market = _market_label(row.get("TEXCH"))
    weight = to_float(row.get("JZBL"))
    change = to_float(row.get("PCTNVCHG"))
    return {
        "code": code,
        "name": str(row.get("GPJC") or "").strip(),
        "market": market,
        "full_code": f"{code}.{market}" if code and market else code,
        "weight": fmt_pct(weight),
        "weight_raw": weight,
        "industry": str(row.get("INDEXNAME") or "").strip(),
        "shares": "",
        "market_value": "",
        "change_type": str(row.get("PCTNVCHGTYPE") or "").strip(),
        "change_weight": fmt_signed(change) + "%" if change is not None else "",
        "change_weight_raw": change,
    }


def _fetch_position_mobile(code: str) -> tuple[list[dict[str, Any]], str]:
    payload = get_json(
        _POSITION_API,
        params={
            "FCODE": code,
            "deviceid": "Wap",
            "plat": "Wap",
            "product": "EFund",
            "version": "2.0.0",
        },
        headers=_HEADERS,
        timeout=(6, 20),
        retries=1,
    )
    if not isinstance(payload, dict) or not payload.get("Success"):
        raise RuntimeError("东财移动端重仓股接口不可用")

    datas = payload.get("Datas") or {}
    stocks_raw = datas.get("fundStocks") or []
    stocks: list[dict[str, Any]] = []
    if isinstance(stocks_raw, list):
        for row in stocks_raw:
            if isinstance(row, dict):
                stocks.append(_normalize_mobile_stock(row))

    report_date = str(payload.get("Expansion") or "").strip()
    if not stocks:
        raise RuntimeError("东财移动端重仓股为空")
    return stocks, report_date


def _parse_holdings_html(text: str, *, limit: int = 10) -> tuple[list[dict[str, Any]], str]:
    dates = _REPORT_DATE_RE.findall(text)
    report_date = dates[0] if dates else ""

    stocks: list[dict[str, Any]] = []
    for market_id, code, name, weight, shares, value in _HOLDING_ROW_RE.findall(text)[:limit]:
        weight_raw = to_float(str(weight).replace("%", ""))
        stocks.append(
            {
                "code": code,
                "name": name.strip(),
                "market": _market_label(market_id),
                "full_code": f"{code}.{_market_label(market_id)}"
                if code and _market_label(market_id)
                else code,
                "weight": fmt_pct(weight_raw),
                "weight_raw": weight_raw,
                "industry": "",
                "shares": shares.strip(),
                "market_value": value.strip(),
                "change_type": "",
                "change_weight": "",
                "change_weight_raw": None,
            }
        )
    if not stocks:
        raise RuntimeError("东财 F10 重仓股解析失败")
    return stocks, report_date


def _fetch_holdings_f10(code: str) -> tuple[list[dict[str, Any]], str]:
    text = get_text(
        _JJCC_API,
        params={
            "type": "jjcc",
            "code": code,
            "topline": "10",
            "year": "",
            "month": "",
            "rt": "0.1",
        },
        headers=_HEADERS,
        timeout=(6, 20),
        retries=1,
    )
    return _parse_holdings_html(text)


def _parse_industry_rows(text: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for match in _INDUSTRY_ROW_RE.finditer(text):
        weight = to_float(str(match.group("weight")).replace("%", ""))
        peer = to_float(str(match.group("peer")).replace("%", ""))
        diff = to_float(str(match.group("diff")).replace("%", ""))
        rows.append(
            {
                "code": match.group("code").strip(),
                "name": match.group("name").strip(),
                "weight": fmt_pct(weight),
                "weight_raw": weight,
                "peer_avg": fmt_pct(peer),
                "peer_avg_raw": peer,
                "peer_diff": fmt_pct(diff),
                "peer_diff_raw": diff,
            }
        )
    return rows


def _fetch_industry(code: str) -> list[dict[str, Any]]:
    text = get_text(
        _INDUSTRY_API,
        params={"type": "hypzsy", "code": code, "rt": "0.1"},
        headers=_HEADERS,
        timeout=(6, 20),
        retries=1,
    )
    rows = _parse_industry_rows(text)
    if not rows:
        raise RuntimeError("东财行业配置无数据")
    return rows


def fetch_holdings(code: str, *, force_refresh: bool = False) -> dict[str, Any]:
    """拉取基金重仓股 + 证监会行业配置。"""
    code = code.strip()
    if not code:
        raise ValueError("缺少基金代码")

    if not force_refresh:
        cached = _read_cache(code)
        if _cache_fresh(cached):
            return cached  # type: ignore[return-value]

    stocks: list[dict[str, Any]]
    report_date = ""
    source_detail = "f10_jjcc"

    try:
        stocks, report_date = _fetch_position_mobile(code)
        source_detail = "mobile"
    except Exception as exc:  # noqa: BLE001
        logger.info("移动端重仓股失败 %s，改用 F10: %s", code, exc)
        stocks, report_date = _fetch_holdings_f10(code)

    industries = _fetch_industry(code)

    payload = {
        "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "code": code,
        "name": "",
        "report_date": report_date,
        "holdings": stocks,
        "industries": industries,
        "holdings_count": len(stocks),
        "industries_count": len(industries),
        "source": "eastmoney",
        "source_detail": source_detail,
    }
    _write_cache(code, payload)
    return payload
