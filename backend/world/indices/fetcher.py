"""全球指数实时行情：东财 stock/get，缺口用腾讯 / 新浪补。"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from core.http import browser_get, get_json, get_text

from world.indices.catalog import INDICES

_EM_HOSTS = (
    "https://push2.eastmoney.com",
    "https://push2delay.eastmoney.com",
)
_EM_FIELDS = "f57,f58,f43,f169,f170,f46,f44,f45,f60,f86"
_EM_HEADERS = {
    "Referer": "https://quote.eastmoney.com/",
    "Accept": "application/json, text/plain, */*",
}
_TX_URL = "https://qt.gtimg.cn/q="
_SINA_URL = "https://hq.sinajs.cn/list="

# 腾讯 / 新浪仅作缺口补全；东财 100.NDX 实际对应纳斯达克综指。
_TX_SYMBOLS: dict[str, str] = {
    "DJIA": "usDJI",
    "SPX": "usINX",
    "NDX": "usIXIC",
    "HSI": "hkHSI",
    "000001": "sh000001",
    "399001": "sz399001",
    "000300": "sh000300",
    "399006": "sz399006",
}
_SINA_SYMBOLS: dict[str, str] = {
    "DJIA": "gb_dji",
    "SPX": "gb_inx",
    "NDX": "gb_ixic",
    "SX5E": "znb_SX5E",
    "FTSE": "znb_UKX",
    "GDAXI": "znb_DAX",
    "FCHI": "znb_CAC",
    # N225：新浪 int_nikkei 点位与东财日K/期货不一致，改走东财
    "KS11": "znb_KOSPI",
    "HSI": "int_hangseng",
    "SENSEX": "znb_SENSEX",
    "000001": "s_sh000001",
    "399001": "s_sz399001",
    "000300": "s_sh000300",
    "399006": "s_sz399006",
}


def _num(raw: Any) -> float | None:
    if raw is None or raw == "-" or raw == "":
        return None
    try:
        return round(float(raw), 4)
    except (TypeError, ValueError):
        return None


def _empty_quote() -> dict[str, Any]:
    return {
        "price": None,
        "change_pct": None,
        "change": None,
        "open": None,
        "high": None,
        "low": None,
        "prev_close": None,
        "quote_time": None,
    }


def _from_em(data: dict[str, Any]) -> dict[str, Any]:
    quote = _empty_quote()
    quote.update(
        {
            "price": _num(data.get("f43")),
            "change": _num(data.get("f169")),
            "change_pct": _num(data.get("f170")),
            "open": _num(data.get("f46")),
            "high": _num(data.get("f44")),
            "low": _num(data.get("f45")),
            "prev_close": _num(data.get("f60")),
            "quote_time": data.get("f86"),
        }
    )
    return quote


def _fetch_em_one(secid: str) -> dict[str, Any]:
    params = {
        "fltt": "2",
        "invt": "2",
        "secid": secid,
        "fields": _EM_FIELDS,
        "ut": "fa5fd1943c7b386f172d6893dbfba10b",
    }
    for host in _EM_HOSTS:
        try:
            payload = get_json(
                f"{host}/api/qt/stock/get",
                params=params,
                headers=_EM_HEADERS,
                timeout=4,
            )
            data = payload.get("data") if isinstance(payload, dict) else None
            if isinstance(data, dict) and data.get("f43") not in (None, "-", ""):
                return _from_em(data)
        except Exception:  # noqa: BLE001
            continue
    return _empty_quote()


def _fetch_em_all(secids: list[str]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {pool.submit(_fetch_em_one, sid): sid for sid in secids}
        for fut in as_completed(futures):
            sid = futures[fut]
            try:
                quote = fut.result()
            except Exception:  # noqa: BLE001
                continue
            if quote.get("price") is not None:
                out[sid] = quote
    return out


def _parse_tencent_line(text: str) -> dict[str, Any]:
    if '="' not in text:
        return _empty_quote()
    body = text.split('="', 1)[1].rsplit('"', 1)[0]
    parts = body.split("~")
    if len(parts) < 6:
        return _empty_quote()
    quote = _empty_quote()
    quote.update(
        {
            "price": _num(parts[3] if len(parts) > 3 else None),
            "prev_close": _num(parts[4] if len(parts) > 4 else None),
            "open": _num(parts[5] if len(parts) > 5 else None),
            "change": _num(parts[31] if len(parts) > 31 else None),
            "change_pct": _num(parts[32] if len(parts) > 32 else None),
            "high": _num(parts[33] if len(parts) > 33 else None),
            "low": _num(parts[34] if len(parts) > 34 else None),
            "quote_time": parts[30] if len(parts) > 30 else None,
        }
    )
    return quote


def _fetch_tencent(codes: list[str]) -> dict[str, dict[str, Any]]:
    symbols = [_TX_SYMBOLS[code] for code in codes if code in _TX_SYMBOLS]
    if not symbols:
        return {}
    try:
        text = get_text(
            _TX_URL + ",".join(symbols),
            headers={"Referer": "https://gu.qq.com/"},
            timeout=12,
        )
    except Exception:  # noqa: BLE001
        return {}
    by_sym: dict[str, dict[str, Any]] = {}
    for chunk in text.split(";"):
        chunk = chunk.strip()
        if "v_" not in chunk or '="' not in chunk:
            continue
        sym = chunk.split("v_", 1)[1].split("=", 1)[0]
        quote = _parse_tencent_line(chunk)
        if quote.get("price") is not None:
            by_sym[sym] = quote
    out: dict[str, dict[str, Any]] = {}
    for code in codes:
        sym = _TX_SYMBOLS.get(code)
        if sym and sym in by_sym:
            out[code] = by_sym[sym]
    return out


def _parse_sina_line(text: str, symbol: str) -> dict[str, Any]:
    if '="' not in text:
        return _empty_quote()
    body = text.split('="', 1)[1].rstrip('";')
    parts = [p.strip() for p in body.split(",")]
    if len(parts) < 4 or not parts[1]:
        return _empty_quote()
    quote = _empty_quote()
    if symbol.startswith("gb_"):
        quote.update(
            {
                "price": _num(parts[1]),
                "change_pct": _num(parts[2]),
                "quote_time": parts[3],
                "change": _num(parts[4]) if len(parts) > 4 else None,
                "open": _num(parts[5]) if len(parts) > 5 else None,
                "high": _num(parts[6]) if len(parts) > 6 else None,
                "low": _num(parts[7]) if len(parts) > 7 else None,
            }
        )
        return quote
    quote.update(
        {
            "price": _num(parts[1]),
            "change": _num(parts[2]),
            "change_pct": _num(parts[3]),
            "quote_time": parts[7] if len(parts) > 7 else None,
            "prev_close": _num(parts[8]) if len(parts) > 8 else None,
            "open": _num(parts[9]) if len(parts) > 9 else None,
            "high": _num(parts[10]) if len(parts) > 10 else None,
            "low": _num(parts[11]) if len(parts) > 11 else None,
        }
    )
    return quote


def _fetch_sina(codes: list[str]) -> dict[str, dict[str, Any]]:
    symbols = [_SINA_SYMBOLS[code] for code in codes if code in _SINA_SYMBOLS]
    if not symbols:
        return {}
    try:
        text = browser_get(
            _SINA_URL + ",".join(symbols),
            headers={"Referer": "https://finance.sina.com.cn"},
            timeout=12,
        ).text
    except Exception:  # noqa: BLE001
        try:
            text = get_text(
                _SINA_URL + ",".join(symbols),
                headers={"Referer": "https://finance.sina.com.cn"},
                timeout=12,
            )
        except Exception:  # noqa: BLE001
            return {}
    by_sym: dict[str, dict[str, Any]] = {}
    for chunk in text.split(";"):
        chunk = chunk.strip()
        if "hq_str_" not in chunk or '="' not in chunk:
            continue
        sym = chunk.split("hq_str_", 1)[1].split("=", 1)[0]
        quote = _parse_sina_line(chunk, sym)
        if quote.get("price") is not None:
            by_sym[sym] = quote
    out: dict[str, dict[str, Any]] = {}
    for code in codes:
        sym = _SINA_SYMBOLS.get(code)
        if sym and sym in by_sym:
            out[code] = by_sym[sym]
    return out


def fetch_indices() -> dict[str, Any]:
    """拉取目录内全部指数，按地区分组返回。"""
    catalog_items = [
        item for block in INDICES.values() for item in block["items"]
    ]
    codes = [item["code"] for item in catalog_items]
    tx_fill: dict[str, dict[str, Any]] = {}
    sina_fill: dict[str, dict[str, Any]] = {}
    with ThreadPoolExecutor(max_workers=2) as pool:
        f_tx = pool.submit(_fetch_tencent, codes)
        f_sina = pool.submit(_fetch_sina, codes)
        try:
            tx_fill = f_tx.result()
        except Exception:  # noqa: BLE001
            tx_fill = {}
        try:
            sina_fill = f_sina.result()
        except Exception:  # noqa: BLE001
            sina_fill = {}
    still = [code for code in codes if code not in tx_fill and code not in sina_fill]
    still_secids = [
        item["secid"] for item in catalog_items if item["code"] in still
    ]
    by_secid = _fetch_em_all(still_secids) if still_secids else {}

    out: dict[str, Any] = {"regions": [], "items": []}
    for region, block in INDICES.items():
        region_items: list[dict[str, Any]] = []
        for item in block["items"]:
            quote = (
                tx_fill.get(item["code"])
                or sina_fill.get(item["code"])
                or by_secid.get(item["secid"])
                or _empty_quote()
            )
            row = {
                "region": region,
                "region_name": block["name"],
                "code": item["code"],
                "name": item["name"],
                **quote,
            }
            region_items.append(row)
            out["items"].append(row)
        out["regions"].append(
            {"id": region, "name": block["name"], "indices": region_items}
        )
    return out
