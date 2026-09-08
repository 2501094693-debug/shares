"""东财场外基金：代码索引 + 分类排行。"""

from __future__ import annotations

import json
import logging
import re
import time
from datetime import date, timedelta
from typing import Any

from core.fmt import fmt_pct, fmt_price
from core.http import get_json, get_text

logger = logging.getLogger(__name__)

_SEARCH_URL = "https://fund.eastmoney.com/js/fundcode_search.js"
_RANK_URL = "https://fund.eastmoney.com/data/rankhandler.aspx"
_NAV_URL = "https://api.fund.eastmoney.com/f10/lsjz"
_HEADERS = {
    "Referer": "https://fund.eastmoney.com/",
    "Accept": "application/json, text/plain, */*",
}
_NAV_HEADERS = {
    "Referer": "https://fundf10.eastmoney.com/",
    "Accept": "application/json, text/plain, */*",
}
_RANK_ROW_FIELDS = (
    "code",
    "name",
    "pinyin",
    "nav_date",
    "unit_nav",
    "acc_nav",
    "day_pct",
    "week_pct",
    "month_pct",
    "quarter_pct",
    "half_year_pct",
    "year_pct",
    "two_year_pct",
    "three_year_pct",
    "ytd_pct",
    "since_pct",
    "establish_date",
)


def _rank_date_range() -> tuple[str, str]:
    end = date.today()
    start = end - timedelta(days=365)
    return start.isoformat(), end.isoformat()


def _parse_search_js(text: str) -> list[dict[str, Any]]:
    match = re.search(r"var r\s*=\s*(\[.*\])", text, re.S)
    if not match:
        raise RuntimeError("东财场外基金代码表解析失败")
    raw = json.loads(match.group(1))
    items: list[dict[str, Any]] = []
    for row in raw:
        if not isinstance(row, list) or len(row) < 4:
            continue
        code = str(row[0] or "").strip()
        if not code.isdigit():
            continue
        items.append(
            {
                "code": code,
                "pinyin": str(row[1] or "").strip(),
                "name": str(row[2] or "").strip(),
                "type_name": str(row[3] or "").strip(),
                "pinyin_full": str(row[4] or "").strip() if len(row) > 4 else "",
            }
        )
    return items


def fetch_fund_index() -> list[dict[str, Any]]:
    text = get_text(_SEARCH_URL, headers=_HEADERS, timeout=(8, 40), retries=1)
    items = _parse_search_js(text)
    if not items:
        raise RuntimeError("东财场外基金代码表为空")
    return items


def _parse_rank_rows(text: str) -> tuple[list[str], int]:
    data_match = re.search(r'datas:\s*\[(.*?)\]\s*,\s*allRecords', text, re.S)
    if not data_match:
        raise RuntimeError("东财场外基金排行解析失败")
    rows = re.findall(r'"([^"]*)"', data_match.group(1))
    total_match = re.search(r"allRecords:\s*(\d+)", text)
    total = int(total_match.group(1)) if total_match else len(rows)
    return rows, total


def _normalize_rank_row(raw: str, category_code: str) -> dict[str, Any]:
    parts = raw.split(",")
    if len(parts) < 16:
        return {}
    data = dict(zip(_RANK_ROW_FIELDS, parts[: len(_RANK_ROW_FIELDS)]))
    return {
        "code": data.get("code", ""),
        "name": data.get("name", ""),
        "pinyin": data.get("pinyin", ""),
        "category_code": category_code,
        "nav_date": data.get("nav_date", ""),
        "unit_nav": fmt_price(data.get("unit_nav"), digits=4),
        "acc_nav": fmt_price(data.get("acc_nav"), digits=4),
        "day_pct": fmt_pct(data.get("day_pct")),
        "week_pct": fmt_pct(data.get("week_pct")),
        "month_pct": fmt_pct(data.get("month_pct")),
        "quarter_pct": fmt_pct(data.get("quarter_pct")),
        "half_year_pct": fmt_pct(data.get("half_year_pct")),
        "year_pct": fmt_pct(data.get("year_pct")),
        "ytd_pct": fmt_pct(data.get("ytd_pct")),
        "since_pct": fmt_pct(data.get("since_pct")),
        "establish_date": data.get("establish_date", ""),
    }


def fetch_rank_list(
    ft: str,
    category_code: str,
    *,
    page: int = 1,
    page_size: int = 50,
    sort: str = "rzdf",
) -> tuple[list[dict[str, Any]], int]:
    start, end = _rank_date_range()
    params = {
        "op": "ph",
        "dt": "kf",
        "ft": ft,
        "rs": "",
        "gs": "0",
        "sc": sort,
        "st": "desc",
        "sd": start,
        "ed": end,
        "qdii": "",
        "tabSubtype": ",,,,,",
        "pi": str(max(1, page)),
        "pn": str(max(1, min(page_size, 200))),
        "dx": "1",
        "v": str(time.time()),
    }
    text = get_text(_RANK_URL, params=params, headers=_HEADERS, timeout=(6, 25), retries=1)
    rows, total = _parse_rank_rows(text)
    items = [
        item
        for item in (_normalize_rank_row(raw, category_code) for raw in rows)
        if item.get("code")
    ]
    return items, total


def fetch_latest_nav(code: str) -> dict[str, Any]:
    payload = get_json(
        _NAV_URL,
        params={"fundCode": code, "pageIndex": 1, "pageSize": 1},
        headers=_NAV_HEADERS,
        timeout=(6, 20),
        retries=1,
    )
    data = payload.get("Data") if isinstance(payload, dict) else None
    rows = data.get("LSJZList") if isinstance(data, dict) else None
    if not isinstance(rows, list) or not rows:
        raise RuntimeError("东财净值接口无数据")
    row = rows[0] if isinstance(rows[0], dict) else {}
    return {
        "nav_date": str(row.get("FSRQ") or "").strip(),
        "unit_nav": fmt_price(row.get("DWJZ"), digits=4),
        "acc_nav": fmt_price(row.get("LJJZ"), digits=4),
        "day_pct": fmt_pct(row.get("JZZZL")),
        "purchase_status": str(row.get("SGZT") or "").strip(),
        "redeem_status": str(row.get("SHZT") or "").strip(),
    }


def fetch_category_total(ft: str) -> int:
    _, total = fetch_rank_list(ft, "tmp", page=1, page_size=1)
    return total
