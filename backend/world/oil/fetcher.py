"""原油实时/延迟行情：新浪期货 + oilprice.com。"""

from __future__ import annotations

import re
from typing import Any

from core.http import browser_get

from world.oil.catalog import OIL

_SINA_URL = "https://hq.sinajs.cn/list="
_SINA_HEADERS = {"Referer": "https://finance.sina.com.cn"}
_OILPRICE_URL = "https://oilprice.com/oil-price-charts/"
_OILPRICE_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "text/html,application/xhtml+xml",
    "Referer": "https://oilprice.com/",
}


def _parse_sina_hf(text: str) -> dict[str, str]:
    """外盘期货字段：现价,空,买,卖,高,低,时间,昨结,开盘,...日期,名称。"""
    if '="' not in text:
        return {}
    body = text.split('="', 1)[1].rstrip('";')
    parts = body.split(",")
    return {
        "price": parts[0] if len(parts) > 0 else "",
        "high": parts[4] if len(parts) > 4 else "",
        "low": parts[5] if len(parts) > 5 else "",
        "time": parts[6] if len(parts) > 6 else "",
        "prev_close": parts[7] if len(parts) > 7 else "",
        "open": parts[8] if len(parts) > 8 else "",
        "date": parts[12] if len(parts) > 12 else "",
        "name": parts[13] if len(parts) > 13 else "",
    }


def _parse_sina_nf(text: str) -> dict[str, str]:
    """国内期货字段（nf_SC0）：开高低现价与昨结位置与外盘不同。"""
    if '="' not in text:
        return {}
    body = text.split('="', 1)[1].rstrip('";')
    parts = body.split(",")
    return {
        "name": parts[0] if len(parts) > 0 else "",
        "open": parts[2] if len(parts) > 2 else "",
        "high": parts[3] if len(parts) > 3 else "",
        "low": parts[4] if len(parts) > 4 else "",
        "price": parts[8] if len(parts) > 8 else "",
        "prev_close": parts[10] if len(parts) > 10 else "",
        "date": parts[17] if len(parts) > 17 else "",
        "time": "",
    }


def _num(raw: str) -> float | None:
    raw = (raw or "").strip().replace(",", "")
    if not raw or raw == "-":
        return None
    try:
        return round(float(raw), 4)
    except ValueError:
        return None


def _change(price: float | None, prev: float | None) -> tuple[float | None, float | None]:
    if price is None or prev is None or prev == 0:
        return None, None
    delta = round(price - prev, 4)
    pct = round(delta / prev * 100.0, 4)
    return delta, pct


def _fetch_sina_map(symbols: list[str]) -> dict[str, str]:
    if not symbols:
        return {}
    text = browser_get(
        f"{_SINA_URL}{','.join(symbols)}",
        headers=_SINA_HEADERS,
        timeout=12,
    ).text
    by_symbol: dict[str, str] = {}
    for chunk in text.split(";"):
        chunk = chunk.strip()
        if "hq_str_" not in chunk or '="' not in chunk:
            continue
        sym = chunk.split("hq_str_", 1)[1].split("=", 1)[0]
        by_symbol[sym] = chunk
    return by_symbol


def _fetch_oilprice_blends(blend_ids: set[str]) -> dict[str, dict[str, float | None]]:
    if not blend_ids:
        return {}
    text = browser_get(_OILPRICE_URL, headers=_OILPRICE_HEADERS, timeout=18).text
    out: dict[str, dict[str, float | None]] = {}
    for blend_id in blend_ids:
        m = re.search(rf"data-id='{re.escape(blend_id)}'[\s\S]{{0,2500}}?</tr>", text)
        if not m:
            continue
        block = m.group(0)
        cells = [
            re.sub(r"<[^>]+>", "", c).strip()
            for c in re.findall(r"<td[^>]*>(.*?)</td>", block, re.S)
        ]
        # cells: flag, name, price, change, pct%(delay), delay
        price = _num(cells[2] if len(cells) > 2 else "")
        change = _num(cells[3] if len(cells) > 3 else "")
        pct_raw = cells[4] if len(cells) > 4 else ""
        pct_m = re.search(r"([-+]?\d+(?:\.\d+)?)\s*%", pct_raw)
        change_pct = _num(pct_m.group(1)) if pct_m else None
        if price is None and change is None:
            continue
        prev = None
        if price is not None and change is not None:
            prev = round(price - change, 4)
        out[blend_id] = {
            "price": price,
            "change": change,
            "change_pct": change_pct,
            "prev_close": prev,
            "open": None,
            "high": None,
            "low": None,
        }
    return out


def _item_from_sina(spec: dict[str, str], parsed: dict[str, str]) -> dict[str, Any]:
    price = _num(parsed.get("price", ""))
    prev = _num(parsed.get("prev_close", ""))
    change, change_pct = _change(price, prev)
    return {
        "id": spec["id"],
        "name": spec["name"] or spec["id"],
        "symbol": spec.get("symbol") or "",
        "source": spec.get("source") or "",
        "price": price,
        "open": _num(parsed.get("open", "")),
        "high": _num(parsed.get("high", "")),
        "low": _num(parsed.get("low", "")),
        "prev_close": prev,
        "change": change,
        "change_pct": change_pct,
        "quote_time": parsed.get("time") or None,
        "quote_date": parsed.get("date") or None,
    }


def _item_from_oilprice(spec: dict[str, str], row: dict[str, float | None] | None) -> dict[str, Any]:
    row = row or {}
    return {
        "id": spec["id"],
        "name": spec["name"] or spec["id"],
        "symbol": f"oilprice:{spec.get('blend_id', '')}",
        "source": "oilprice",
        "price": row.get("price"),
        "open": row.get("open"),
        "high": row.get("high"),
        "low": row.get("low"),
        "prev_close": row.get("prev_close"),
        "change": row.get("change"),
        "change_pct": row.get("change_pct"),
        "quote_time": None,
        "quote_date": None,
    }


def fetch_oil() -> dict[str, Any]:
    hf_syms = [s["symbol"] for s in OIL if s.get("source") == "sina_hf" and s.get("symbol")]
    nf_syms = [s["symbol"] for s in OIL if s.get("source") == "sina_nf" and s.get("symbol")]
    blend_ids = {s["blend_id"] for s in OIL if s.get("source") == "oilprice" and s.get("blend_id")}

    sina_raw: dict[str, str] = {}
    try:
        sina_raw = _fetch_sina_map(hf_syms + nf_syms)
    except Exception as err:
        print(f"[oil] sina fetch failed: {err}")

    oilprice_rows: dict[str, dict[str, float | None]] = {}
    try:
        oilprice_rows = _fetch_oilprice_blends(blend_ids)
    except Exception as err:
        print(f"[oil] oilprice fetch failed: {err}")

    items: list[dict[str, Any]] = []
    for spec in OIL:
        source = spec.get("source") or "sina_hf"
        if source == "sina_hf":
            raw = sina_raw.get(spec.get("symbol", ""), "")
            items.append(_item_from_sina(spec, _parse_sina_hf(raw)))
        elif source == "sina_nf":
            raw = sina_raw.get(spec.get("symbol", ""), "")
            items.append(_item_from_sina(spec, _parse_sina_nf(raw)))
        elif source == "oilprice":
            items.append(_item_from_oilprice(spec, oilprice_rows.get(spec.get("blend_id", ""))))
        else:
            items.append(_item_from_oilprice(spec, None))
    return {"items": items}
