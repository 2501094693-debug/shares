"""全球指数日 K：东财 push2his，缺口用腾讯 fqkline。"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from core.http import get_json

from world.indices.catalog import INDICES

_TX_KLINE_SYMBOLS: dict[str, str] = {
    "DJIA": "usDJI",
    "SPX": "usINX",
    "NDX": "usIXIC",
    "HSI": "hkHSI",
    "000001": "sh000001",
    "399001": "sz399001",
    "000300": "sh000300",
    "399006": "sz399006",
}

_EM_HIS_HOSTS = (
    "https://push2his.eastmoney.com",
    "https://92.push2his.eastmoney.com",
)
_EM_HEADERS = {
    "Referer": "https://quote.eastmoney.com/",
    "Accept": "application/json, text/plain, */*",
}
_TX_KLINE = (
    "https://web.ifzq.gtimg.cn/appstock/app/usfqkline/get",
    "https://proxy.finance.qq.com/ifzqgtimg/appstock/app/newfqkline/get",
    "https://ifzq.gtimg.cn/appstock/app/fqkline/get",
)
_TX_HEADERS = {"Referer": "https://gu.qq.com/"}


def _num(raw: Any) -> float | None:
    if raw is None or raw == "-" or raw == "":
        return None
    try:
        return round(float(raw), 4)
    except (TypeError, ValueError):
        return None


def _from_em(secid: str, limit: int) -> list[dict[str, Any]]:
    params = {
        "secid": secid,
        "klt": "101",
        "fqt": "0",
        "lmt": str(limit),
        "end": "20500101",
        "fields1": "f1,f2,f3,f4,f5,f6",
        "fields2": "f51,f52,f53,f54,f55",
    }
    for host in _EM_HIS_HOSTS:
        try:
            payload = get_json(
                f"{host}/api/qt/stock/kline/get",
                params=params,
                headers=_EM_HEADERS,
                timeout=10,
            )
        except Exception:  # noqa: BLE001
            continue
        data = payload.get("data") if isinstance(payload, dict) else None
        rows = (data or {}).get("klines") or []
        out: list[dict[str, Any]] = []
        for raw in rows:
            parts = str(raw).split(",")
            if len(parts) < 3:
                continue
            close = _num(parts[2])
            if close is None:
                continue
            out.append(
                {
                    "date": parts[0][:10],
                    "open": _num(parts[1]),
                    "close": close,
                    "high": _num(parts[3]) if len(parts) > 3 else None,
                    "low": _num(parts[4]) if len(parts) > 4 else None,
                }
            )
        if len(out) >= 2:
            return out[-limit:]
    return []


def _from_tencent(symbol: str, limit: int) -> list[dict[str, Any]]:
    best: list[dict[str, Any]] = []
    fq_flags = ("qfq", "") if symbol.startswith("us") else ("",)
    for url in _TX_KLINE:
        if "usfqkline" in url and not symbol.startswith("us"):
            continue
        for fq in fq_flags:
            try:
                payload = (
                    get_json(
                        url,
                        params={"param": f"{symbol},day,,,{limit},{fq}"},
                        headers=_TX_HEADERS,
                        timeout=10,
                    )
                    or {}
                )
            except Exception:  # noqa: BLE001
                continue
            block = ((payload.get("data") or {}).get(symbol) or {}) if isinstance(payload, dict) else {}
            rows = block.get("day") or block.get("qfqday") or block.get("hfqday") or []
            out: list[dict[str, Any]] = []
            for row in rows:
                if not isinstance(row, (list, tuple)) or len(row) < 3:
                    continue
                close = _num(row[2])
                if close is None:
                    continue
                out.append(
                    {
                        "date": str(row[0])[:10],
                        "open": _num(row[1]),
                        "close": close,
                        "high": _num(row[3]) if len(row) > 3 else None,
                        "low": _num(row[4]) if len(row) > 4 else None,
                    }
                )
            if len(out) > len(best):
                best = out
            if len(best) >= 8:
                return best[-limit:]
    return best[-limit:]


def _fetch_one(item: dict[str, str], limit: int) -> dict[str, Any]:
    points: list[dict[str, Any]] = []
    try:
        points = _from_em(item["secid"], limit)
        if len(points) >= 8:
            return {"points": points, "source": "eastmoney", "source_label": "东方财富"}
    except Exception:  # noqa: BLE001
        points = []
    symbol = _TX_KLINE_SYMBOLS.get(item["code"])
    if not symbol:
        return {
            "points": points,
            "source": "eastmoney" if points else "",
            "source_label": "东方财富" if points else "",
        }
    try:
        tx = _from_tencent(symbol, limit)
    except Exception:  # noqa: BLE001
        return {
            "points": points,
            "source": "eastmoney" if points else "",
            "source_label": "东方财富" if points else "",
        }
    if len(tx) > len(points):
        return {"points": tx, "source": "tencent", "source_label": "腾讯财经"}
    return {
        "points": points,
        "source": "eastmoney" if points else "",
        "source_label": "东方财富" if points else "",
    }


def fetch_index_klines(*, limit: int = 90) -> dict[str, Any]:
    """目录内全部指数最近日 K，按 code 索引。"""
    cap = max(20, min(int(limit), 240))
    catalog_items = [item for block in INDICES.values() for item in block["items"]]
    by_code: dict[str, list[dict[str, Any]]] = {}
    source_by_code: dict[str, str] = {}
    source_label_by_code: dict[str, str] = {}
    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = {pool.submit(_fetch_one, item, cap): item for item in catalog_items}
        for fut in as_completed(futures):
            item = futures[fut]
            try:
                pack = fut.result()
            except Exception:  # noqa: BLE001
                pack = {"points": [], "source": "", "source_label": ""}
            by_code[item["code"]] = pack.get("points") or []
            source_by_code[item["code"]] = str(pack.get("source") or "")
            source_label_by_code[item["code"]] = str(pack.get("source_label") or "")

    items: list[dict[str, Any]] = []
    for region, block in INDICES.items():
        for item in block["items"]:
            points = by_code.get(item["code"]) or []
            items.append(
                {
                    "region": region,
                    "region_name": block["name"],
                    "code": item["code"],
                    "name": item["name"],
                    "points": points,
                    "source": source_by_code.get(item["code"]) or "",
                    "source_label": source_label_by_code.get(item["code"]) or "",
                }
            )
    return {
        "limit": cap,
        "by_code": by_code,
        "source_by_code": source_by_code,
        "source_label_by_code": source_label_by_code,
        "items": items,
    }
