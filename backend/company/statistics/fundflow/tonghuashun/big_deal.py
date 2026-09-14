"""同花顺数据中心大单追踪（ddzz）逐笔大单。"""

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
_SIDE_MAP = {
    "买盘": "buy",
    "卖盘": "sell",
    "中性": "neutral",
    "中性盘": "neutral",
}


def _ddzz_headers(code: str = "") -> dict[str, str]:
    referer = f"{_DATA_HOST}/funds/ddzz/"
    if code:
        referer = f"{_DATA_HOST}/funds/ddzz/stock/{code}/"
    return {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html, */*; q=0.01",
        "Accept-Language": "zh-CN,zh;q=0.9",
        "Referer": referer,
        "X-Requested-With": "XMLHttpRequest",
        "hexin-v": make_hexin_v(),
    }


def _ddzz_url(page: int, *, order: str = "desc") -> str:
    page = max(int(page or 1), 1)
    direction = "asc" if str(order).strip().lower() == "asc" else "desc"
    if page == 1:
        return f"{_DATA_HOST}/funds/ddzz/field/time/order/{direction}/ajax/1/free/1/"
    return (
        f"{_DATA_HOST}/funds/ddzz/field/time/order/{direction}/page/{page}/ajax/1/free/1/"
    )


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


def _fetch_page(page: int, *, order: str, code: str = "") -> list[dict[str, Any]]:
    url = _ddzz_url(page, order=order)
    try:
        html = get_text(url, timeout=15, headers=_ddzz_headers(code))
    except Exception as exc:
        logger.info("ths ddzz skip page %s: %s", page, exc)
        return []
    if not html or "J-ajax-table" not in html:
        return []
    return _parse_table(html)


def fetch_big_deals(
    code: str = "",
    *,
    page: int = 1,
    limit: int = 50,
    order: str = "desc",
    max_pages: int = 10,
) -> dict[str, Any]:
    """逐笔大单。``code`` 为空返回全市场单页；有 code 时翻页过滤直至凑够 ``limit`` 条。"""
    norm = normalize_code(code) if code else ""
    page = max(int(page or 1), 1)
    limit = min(max(int(limit or 50), 1), 200)
    scan_cap = 1 if not norm else min(max(int(max_pages or 10), 1), 100)

    items: list[dict[str, Any]] = []
    pages_fetched = 0
    for offset in range(scan_cap):
        current_page = page + offset
        batch = _fetch_page(current_page, order=order, code=norm)
        pages_fetched += 1
        if not batch:
            break
        if norm:
            batch = [row for row in batch if row.get("code") == norm]
        items.extend(batch)
        if not norm or len(items) >= limit:
            break

    items = items[:limit]

    return {
        "code": norm,
        "name": items[0].get("name", "") if norm and items else "",
        "period": "big_deal",
        "source": "tonghuashun" if items else "",
        "count": len(items),
        "page": page,
        "pages_fetched": pages_fetched,
        "order": "asc" if str(order).strip().lower() == "asc" else "desc",
        "limit": limit,
        "items": items,
        "note": (
            "同花顺 ddzz 为全市场流；指定 code 时客户端翻页过滤"
            if norm
            else "同花顺数据中心大单追踪（全市场）"
        ),
    }
