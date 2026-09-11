"""新浪外盘原油期货实时行情。"""

from __future__ import annotations

from typing import Any

from core.http import browser_get

from world.catalog import OIL

_SINA_URL = "https://hq.sinajs.cn/list="
_SINA_HEADERS = {"Referer": "https://finance.sina.com.cn"}


def _parse_sina_line(text: str) -> dict[str, str]:
    if '="' not in text:
        return {}
    body = text.split('="', 1)[1].rstrip('";')
    parts = body.split(",")
    return {
        "price": parts[0] if len(parts) > 0 else "",
        "open": parts[2] if len(parts) > 2 else "",
        "high": parts[3] if len(parts) > 3 else "",
        "low": parts[4] if len(parts) > 4 else "",
        "time": parts[6] if len(parts) > 6 else "",
        "prev_close": parts[7] if len(parts) > 7 else "",
        "date": parts[12] if len(parts) > 12 else "",
        "name": parts[13] if len(parts) > 13 else "",
    }


def _num(raw: str) -> float | None:
    raw = (raw or "").strip()
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


def fetch_oil() -> dict[str, Any]:
    symbols = ",".join(item["symbol"] for item in OIL)
    text = browser_get(
        f"{_SINA_URL}{symbols}",
        headers=_SINA_HEADERS,
        timeout=12,
    ).text

    chunks = [chunk.strip() for chunk in text.split(";") if chunk.strip()]
    by_symbol: dict[str, dict[str, str]] = {}
    for chunk in chunks:
        if "hq_str_" not in chunk:
            continue
        sym = chunk.split("hq_str_", 1)[1].split("=", 1)[0]
        by_symbol[sym] = _parse_sina_line(chunk)

    items: list[dict[str, Any]] = []
    for spec in OIL:
        parsed = by_symbol.get(spec["symbol"], {})
        price = _num(parsed.get("price", ""))
        prev = _num(parsed.get("prev_close", ""))
        change, change_pct = _change(price, prev)
        items.append(
            {
                "id": spec["id"],
                "name": spec["name"] or spec["id"],
                "symbol": spec["symbol"],
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
        )
    return {"items": items}
