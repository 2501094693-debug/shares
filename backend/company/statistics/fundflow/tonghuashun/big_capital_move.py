"""同花顺手机端个股资金 - 大资金动向（数据中心 ddzz 逐笔大单）。

手机 App 个股详情「资金」页中的「大资金动向」，数据源为同花顺数据中心大单追踪：
``data.10jqka.com.cn/funds/ddzz``。接口返回全市场大单流，指定股票时需客户端翻页过滤。
"""

from __future__ import annotations

import logging
import re
from typing import Any

from core.codes import normalize_code
from core.fmt import to_float
from core.http import get_text

from company.statistics.fundflow.tonghuashun._common import wan_to_yuan
from company.statistics.fundflow.tonghuashun._hexin import make_hexin_v

logger = logging.getLogger(__name__)

_DATA_HOST = "http://data.10jqka.com.cn"
_DEFAULT_MAX_PAGES = 50
_NOTE = (
    "同花顺手机端大资金动向，数据源为数据中心大单追踪（ddzz）；"
    "全市场流按股票代码翻页过滤"
)
_MOBILE_UA = (
    "Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Mobile Safari/537.36 "
    "Hexin_Gphone/11.20.40 (Phone; Android 13; zh)"
)
_SIDE_MAP = {
    "买盘": "buy",
    "卖盘": "sell",
    "中性": "neutral",
    "中性盘": "neutral",
}


def _ddzz_headers(code: str) -> dict[str, str]:
    return {
        "User-Agent": _MOBILE_UA,
        "Accept": "text/html, */*; q=0.01",
        "Accept-Language": "zh-CN,zh;q=0.9",
        "Referer": f"{_DATA_HOST}/funds/ddzz/stock/{code}/",
        "X-Requested-With": "XMLHttpRequest",
        "hexin-v": make_hexin_v(),
    }


def _ddzz_url(page: int, *, order: str, code: str) -> str:
    page = max(int(page or 1), 1)
    direction = "asc" if str(order).strip().lower() == "asc" else "desc"
    base = f"{_DATA_HOST}/funds/ddzz/stock/{code}"
    if page == 1:
        return f"{base}/field/time/order/{direction}/ajax/1/free/1/"
    return f"{base}/field/time/order/{direction}/page/{page}/ajax/1/free/1/"


def _parse_pct(text: str) -> float | None:
    value = str(text or "").strip().rstrip("%")
    return to_float(value)


def _parse_row(cells: list[str]) -> dict[str, Any] | None:
    if len(cells) < 9:
        return None
    code = normalize_code(cells[1]) or cells[1].strip()
    if not code or code in {"股票代码", "成交时间"}:
        return None
    side_raw = cells[6].strip()
    return {
        "time": cells[0].strip(),
        "code": code,
        "name": cells[2].strip(),
        "price": to_float(cells[3]),
        "volume": to_float(cells[4]),
        "amount": wan_to_yuan(cells[5]),
        "side": _SIDE_MAP.get(side_raw, side_raw or "unknown"),
        "side_label": side_raw,
        "change_pct": _parse_pct(cells[7]),
        "change": to_float(cells[8]),
    }


def _parse_table(html: str) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for row in re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.S):
        cells = [
            re.sub(r"<[^>]+>", "", cell).strip()
            for cell in re.findall(r"<td[^>]*>(.*?)</td>", row, re.S)
        ]
        if not cells:
            continue
        parsed = _parse_row(cells)
        if parsed:
            items.append(parsed)
    return items


def _fetch_page(page: int, *, order: str, code: str) -> list[dict[str, Any]]:
    url = _ddzz_url(page, order=order, code=code)
    try:
        html = get_text(url, timeout=15, headers=_ddzz_headers(code))
    except Exception as exc:
        logger.info("ths ddzz skip page %s: %s", page, exc)
        return []
    if not html or "J-ajax-table" not in html:
        return []
    return _parse_table(html)


def fetch_big_capital_move(
    code: str,
    *,
    page: int = 1,
    limit: int = 20,
    order: str = "desc",
    max_pages: int = _DEFAULT_MAX_PAGES,
) -> dict[str, Any]:
    """个股大资金动向（逐笔大单列表）。"""
    norm = normalize_code(code)
    if not norm:
        raise ValueError("无效股票代码")
    page = max(int(page or 1), 1)
    limit = min(max(int(limit or 20), 1), 200)
    scan_cap = min(max(int(max_pages or _DEFAULT_MAX_PAGES), 1), 100)

    items: list[dict[str, Any]] = []
    pages_fetched = 0
    for offset in range(scan_cap):
        current_page = page + offset
        batch = _fetch_page(current_page, order=order, code=norm)
        pages_fetched += 1
        if not batch:
            break
        items.extend(row for row in batch if row.get("code") == norm)
        if len(items) >= limit:
            break

    items = items[:limit]

    return {
        "code": norm,
        "name": items[0].get("name", "") if items else "",
        "period": "big_capital_move",
        "source": "tonghuashun" if items else "",
        "count": len(items),
        "page": page,
        "pages_fetched": pages_fetched,
        "max_pages": scan_cap,
        "order": "asc" if str(order).strip().lower() == "asc" else "desc",
        "limit": limit,
        "items": items,
        "note": _NOTE,
    }
