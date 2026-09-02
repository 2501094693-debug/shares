"""东财龙虎榜：每日上榜、个股历史、买卖席位。

    GET https://datacenter-web.eastmoney.com/api/data/v1/get
        RPT_DAILYBILLBOARD_DETAILSNEW     上榜明细（按日 / 按代码）
        RPT_BILLBOARD_DAILYDETAILSBUY     买入席位
        RPT_BILLBOARD_DAILYDETAILSSELL    卖出席位
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from core.codes import normalize_code, safe_str
from core.fmt import to_float
from core.http import get_json

_API = "https://datacenter-web.eastmoney.com/api/data/v1/get"
_HEADERS = {"Referer": "https://data.eastmoney.com/stock/lhb.html"}
_PAGE_SIZE = 500
_MAX_PAGES = 20

_DETAIL_REPORT = "RPT_DAILYBILLBOARD_DETAILSNEW"
_BUY_REPORT = "RPT_BILLBOARD_DAILYDETAILSBUY"
_SELL_REPORT = "RPT_BILLBOARD_DAILYDETAILSSELL"


def ymd(date: str | None = None) -> str:
    """``YYYYMMDD`` / ``YYYY-MM-DD`` → ``YYYYMMDD``。空则今天。"""
    text = safe_str(date).replace("-", "").replace("/", "")
    if len(text) == 8 and text.isdigit():
        return text
    if text:
        raise ValueError("日期格式须为 YYYY-MM-DD 或 YYYYMMDD")
    return datetime.now().strftime("%Y%m%d")


def ymd_dash(date: str | None = None) -> str:
    raw = ymd(date)
    return f"{raw[:4]}-{raw[4:6]}-{raw[6:8]}"


def _trade_date(value: Any) -> str:
    text = safe_str(value)
    if not text:
        return ""
    digits = text.replace("-", "").replace("/", "").replace(" ", "")[:8]
    if len(digits) == 8 and digits.isdigit():
        return f"{digits[:4]}-{digits[4:6]}-{digits[6:8]}"
    return text[:10]


def _trade_id(value: Any) -> str:
    text = safe_str(value)
    if not text:
        return ""
    if text.endswith(".0") and text[:-2].isdigit():
        return text[:-2]
    return text


def _rows(payload: Any) -> tuple[list[dict[str, Any]], int]:
    if not isinstance(payload, dict):
        return [], 1
    result = payload.get("result")
    if not isinstance(result, dict):
        return [], 1
    data = result.get("data") or []
    if isinstance(data, dict):
        data = list(data.values())
    rows = [item for item in data if isinstance(item, dict)]
    pages = to_float(result.get("pages"))
    return rows, max(1, int(pages or 1))


def _fetch_paged(
    report: str,
    filt: str,
    *,
    sort_columns: str,
    sort_types: str,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    pages = 1
    page = 1
    while page <= pages and page <= _MAX_PAGES:
        payload = get_json(
            _API,
            params={
                "reportName": report,
                "columns": "ALL",
                "filter": filt,
                "pageNumber": str(page),
                "pageSize": str(_PAGE_SIZE),
                "sortColumns": sort_columns,
                "sortTypes": sort_types,
                "source": "WEB",
                "client": "WEB",
            },
            headers=_HEADERS,
            timeout=(5, 15),
            retries=2,
        )
        rows, pages = _rows(payload)
        if not rows:
            break
        out.extend(rows)
        page += 1
    return out


def _ratio_pct(value: Any) -> float | None:
    """席位占比字段是小数（0.10 = 10%），统一成百分数。"""
    number = to_float(value)
    if number is None:
        return None
    if abs(number) <= 1.5:
        return round(number * 100.0, 4)
    return round(number, 4)


def _dept_type(name: str) -> str:
    if "机构" in name:
        return "机构"
    return "营业部"


def parse_detail(row: dict[str, Any]) -> dict[str, Any] | None:
    code = normalize_code(safe_str(row.get("SECURITY_CODE")))
    date = _trade_date(row.get("TRADE_DATE"))
    if not code or not date:
        return None
    return {
        "code": code,
        "name": safe_str(row.get("SECURITY_NAME_ABBR")),
        "date": date,
        "date_raw": date.replace("-", ""),
        "market": safe_str(row.get("MARKET")),
        "close": to_float(row.get("CLOSE_PRICE")),
        "change_pct": to_float(row.get("CHANGE_RATE")),
        "turnover": to_float(row.get("TURNOVERRATE")),
        "net_amt": to_float(row.get("BILLBOARD_NET_AMT")),
        "buy_amt": to_float(row.get("BILLBOARD_BUY_AMT")),
        "sell_amt": to_float(row.get("BILLBOARD_SELL_AMT")),
        "deal_amt": to_float(row.get("BILLBOARD_DEAL_AMT")),
        "accum_amt": to_float(row.get("ACCUM_AMOUNT")),
        "net_ratio": to_float(row.get("DEAL_NET_RATIO")),
        "deal_ratio": to_float(row.get("DEAL_AMOUNT_RATIO")),
        "free_cap": to_float(row.get("FREE_MARKET_CAP")),
        "reason": safe_str(row.get("EXPLANATION")),
        "explain": safe_str(row.get("EXPLAIN")),
        "trade_id": _trade_id(row.get("TRADE_ID")),
        "d1": to_float(row.get("D1_CLOSE_ADJCHRATE")),
        "d2": to_float(row.get("D2_CLOSE_ADJCHRATE")),
        "d5": to_float(row.get("D5_CLOSE_ADJCHRATE")),
        "d10": to_float(row.get("D10_CLOSE_ADJCHRATE")),
    }


def parse_seat(row: dict[str, Any], *, side: str) -> dict[str, Any] | None:
    code = normalize_code(safe_str(row.get("SECURITY_CODE")))
    date = _trade_date(row.get("TRADE_DATE"))
    dept = safe_str(row.get("OPERATEDEPT_NAME"))
    if not code or not date or not dept:
        return None
    return {
        "code": code,
        "date": date,
        "side": side,
        "dept_code": safe_str(row.get("OPERATEDEPT_CODE")),
        "dept": dept,
        "dept_type": _dept_type(dept),
        "reason": safe_str(row.get("EXPLANATION")),
        "trade_id": _trade_id(row.get("TRADE_ID")),
        "buy": to_float(row.get("BUY")),
        "sell": to_float(row.get("SELL")),
        "net": to_float(row.get("NET")),
        "buy_ratio": _ratio_pct(row.get("TOTAL_BUYRIO")),
        "sell_ratio": _ratio_pct(row.get("TOTAL_SELLRIO")),
        "rise_prob_3d": to_float(row.get("RISE_PROBABILITY_3DAY")),
        "appear_3d": int(to_float(row.get("TOTAL_BUYER_SALESTIMES_3DAY")) or 0),
    }


def fetch_details(*, date: str | None = None, code: str | None = None) -> list[dict[str, Any]]:
    """上榜明细。``date`` / ``code`` 至少给一个。"""
    parts: list[str] = []
    if date:
        parts.append(f"(TRADE_DATE='{ymd_dash(date)}')")
    stock = normalize_code(code or "")
    if stock:
        parts.append(f'(SECURITY_CODE="{stock}")')
    if not parts:
        raise ValueError("缺少 date 或 code")
    if date and not stock:
        sort_columns, sort_types = "BILLBOARD_NET_AMT", "-1"
    else:
        sort_columns, sort_types = "TRADE_DATE", "-1"
    rows = _fetch_paged(
        _DETAIL_REPORT,
        "".join(parts),
        sort_columns=sort_columns,
        sort_types=sort_types,
    )
    out = [parsed for row in rows if (parsed := parse_detail(row))]
    return out


def fetch_seats(
    side: str,
    *,
    date: str | None = None,
    code: str | None = None,
) -> list[dict[str, Any]]:
    """买入或卖出席位。``side`` 为 buy / sell。"""
    flag = safe_str(side).lower()
    if flag in {"buy", "买入"}:
        report, sort_col = _BUY_REPORT, "BUY"
        label = "buy"
    elif flag in {"sell", "卖出"}:
        report, sort_col = _SELL_REPORT, "SELL"
        label = "sell"
    else:
        raise ValueError("side 须为 buy 或 sell")
    parts: list[str] = []
    if date:
        parts.append(f"(TRADE_DATE='{ymd_dash(date)}')")
    stock = normalize_code(code or "")
    if stock:
        parts.append(f'(SECURITY_CODE="{stock}")')
    if not parts:
        raise ValueError("缺少 date 或 code")
    rows = _fetch_paged(
        report,
        "".join(parts),
        sort_columns=sort_col,
        sort_types="-1",
    )
    return [parsed for row in rows if (parsed := parse_seat(row, side=label))]
