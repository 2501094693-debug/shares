"""原油日 K：新浪外盘 / 国内期货 + oilprice.com。"""

from __future__ import annotations

import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Any

from core.http import browser_get, browser_post

from world.oil.catalog import OIL

_SINA_HEADERS = {"Referer": "https://finance.sina.com.cn", "User-Agent": "Mozilla/5.0"}
_OILPRICE_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://oilprice.com/freewidgets/get_oilprices_chart/48/4",
    "Origin": "https://oilprice.com",
}

# 外盘日 K 代码（去掉 hf_ 前缀）
_GLOBAL_KLINE: dict[str, str] = {
    "brent": "OIL",
    "wti": "CL",
    "dubai": "DBI",
}
# 国内期货日 K
_INNER_KLINE: dict[str, str] = {
    "shanghai": "SC0",
}


def _num(raw: Any) -> float | None:
    if raw is None or raw == "-" or raw == "":
        return None
    try:
        return round(float(raw), 4)
    except (TypeError, ValueError):
        return None


def _parse_jsonp(text: str) -> Any:
    m = re.search(r"=\((.*)\)\s*;?\s*$", text, re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(1))
    except json.JSONDecodeError:
        return None


def _from_sina_global(symbol: str, limit: int) -> list[dict[str, Any]]:
    url = (
        "https://stock2.finance.sina.com.cn/futures/api/jsonp.php/"
        f"var%20_{symbol}=/GlobalFuturesService.getGlobalFuturesDailyKLine?symbol={symbol}"
    )
    text = browser_get(url, headers=_SINA_HEADERS, timeout=18).text
    rows = _parse_jsonp(text)
    if not isinstance(rows, list):
        return []
    out: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        close = _num(row.get("close"))
        if close is None:
            continue
        date = str(row.get("date") or "")[:10]
        if not date:
            continue
        out.append(
            {
                "date": date,
                "open": _num(row.get("open")),
                "high": _num(row.get("high")),
                "low": _num(row.get("low")),
                "close": close,
            }
        )
    return out[-limit:]


def _from_sina_inner(symbol: str, limit: int) -> list[dict[str, Any]]:
    url = (
        "https://stock2.finance.sina.com.cn/futures/api/jsonp.php/"
        f"var%20_{symbol}=/InnerFuturesNewService.getDailyKLine?symbol={symbol}"
    )
    text = browser_get(url, headers=_SINA_HEADERS, timeout=18).text
    rows = _parse_jsonp(text)
    if not isinstance(rows, list):
        return []
    out: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        close = _num(row.get("c") if "c" in row else row.get("close"))
        if close is None:
            continue
        date = str(row.get("d") or row.get("date") or "")[:10]
        if not date:
            continue
        out.append(
            {
                "date": date,
                "open": _num(row.get("o") if "o" in row else row.get("open")),
                "high": _num(row.get("h") if "h" in row else row.get("high")),
                "low": _num(row.get("l") if "l" in row else row.get("low")),
                "close": close,
            }
        )
    return out[-limit:]


def _oilprice_csrf() -> tuple[str, str]:
    raw = browser_get(
        "https://oilprice.com/ajax/csrf",
        headers={**_OILPRICE_HEADERS, "Accept": "application/json", "X-Requested-With": "XMLHttpRequest"},
        timeout=12,
    ).text
    payload = json.loads(raw)
    return str(payload["name"]), str(payload["hash"])


def _from_oilprice(blend_id: str, limit: int) -> list[dict[str, Any]]:
    # period=7 ≈ 数年日线；不足再回退 period=5
    points: list[dict[str, Any]] = []
    for period in (7, 5, 4):
        try:
            name, token = _oilprice_csrf()
            resp = browser_post(
                "https://oilprice.com/freewidgets/json_get_oilprices",
                data={"blend_id": blend_id, "period": str(period), name: token},
                headers={
                    **_OILPRICE_HEADERS,
                    "Accept": "application/json",
                    "X-Requested-With": "XMLHttpRequest",
                    "Content-Type": "application/x-www-form-urlencoded",
                },
                timeout=20,
            )
            payload = json.loads(resp.text)
        except Exception:  # noqa: BLE001
            continue
        prices = payload.get("prices") or []
        if not isinstance(prices, list) or len(prices) < 2:
            continue
        closes: list[tuple[str, float]] = []
        for row in prices:
            if not isinstance(row, dict):
                continue
            px = _num(row.get("price"))
            ts = row.get("time")
            if px is None or ts is None:
                continue
            try:
                dt = datetime.fromtimestamp(int(ts), tz=timezone.utc)
            except (TypeError, ValueError, OSError):
                continue
            closes.append((dt.strftime("%Y-%m-%d"), px))
        if len(closes) < 2:
            continue
        out: list[dict[str, Any]] = []
        prev: float | None = None
        for date, close in closes:
            open_px = prev if prev is not None else close
            out.append(
                {
                    "date": date,
                    "open": open_px,
                    "high": max(open_px, close),
                    "low": min(open_px, close),
                    "close": close,
                }
            )
            prev = close
        points = out[-limit:]
        if len(points) >= 8:
            return points
    return points


def _fetch_one(spec: dict[str, str], limit: int) -> dict[str, Any]:
    oid = spec["id"]
    try:
        if oid in _GLOBAL_KLINE:
            points = _from_sina_global(_GLOBAL_KLINE[oid], limit)
            return {"points": points, "source": "sina", "source_label": "新浪财经"}
        if oid in _INNER_KLINE:
            points = _from_sina_inner(_INNER_KLINE[oid], limit)
            return {"points": points, "source": "sina", "source_label": "新浪财经"}
        if spec.get("source") == "oilprice" and spec.get("blend_id"):
            points = _from_oilprice(spec["blend_id"], limit)
            return {"points": points, "source": "oilprice", "source_label": "OilPrice.com"}
    except Exception:  # noqa: BLE001
        return {"points": [], "source": "", "source_label": ""}
    return {"points": [], "source": "", "source_label": ""}


def fetch_oil_klines(*, limit: int = 90) -> dict[str, Any]:
    """目录内全部原油最近日 K，按 id 索引。"""
    cap = max(20, min(int(limit), 240))
    by_id: dict[str, list[dict[str, Any]]] = {}
    source_by_id: dict[str, str] = {}
    source_label_by_id: dict[str, str] = {}
    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = {pool.submit(_fetch_one, spec, cap): spec for spec in OIL}
        for fut in as_completed(futures):
            spec = futures[fut]
            try:
                pack = fut.result()
            except Exception:  # noqa: BLE001
                pack = {"points": [], "source": "", "source_label": ""}
            by_id[spec["id"]] = pack.get("points") or []
            source_by_id[spec["id"]] = str(pack.get("source") or "")
            source_label_by_id[spec["id"]] = str(pack.get("source_label") or "")

    items: list[dict[str, Any]] = []
    for spec in OIL:
        points = by_id.get(spec["id"]) or []
        items.append(
            {
                "id": spec["id"],
                "name": spec["name"],
                "points": points,
                "source": source_by_id.get(spec["id"]) or "",
                "source_label": source_label_by_id.get(spec["id"]) or "",
            }
        )
    return {
        "limit": cap,
        "by_id": by_id,
        "source_by_id": source_by_id,
        "source_label_by_id": source_label_by_id,
        "items": items,
    }
