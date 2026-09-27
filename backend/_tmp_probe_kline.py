"""Probe Tencent / Sina kline endpoints for world indices."""
from __future__ import annotations

import json
import re
from typing import Any

from core.http import get_json, get_text, browser_get

TX_URLS = (
    "https://web.ifzq.gtimg.cn/appstock/app/usfqkline/get",
    "https://proxy.finance.qq.com/ifzqgtimg/appstock/app/newfqkline/get",
    "https://ifzq.gtimg.cn/appstock/app/fqkline/get",
)
TX_HEADERS = {"Referer": "https://gu.qq.com/"}

# candidate symbols per code
CANDIDATES: dict[str, list[str]] = {
    "DJIA": ["usDJI"],
    "SPX": ["usINX"],
    "NDX": ["usIXIC"],
    "SX5E": ["ff_SX5E", "gz_SX5E", "ukSX5E", "euSX5E"],
    "FTSE": ["ukFTSE", "ff_FTSE", "gz_FTSE", "ukUKX"],
    "GDAXI": ["deDAX", "ff_DAX", "gz_DAX", "deGDAXI"],
    "FCHI": ["frCAC", "ff_CAC", "gz_CAC", "frFCHI"],
    "N225": ["jpN225", "ff_N225", "gz_N225", "jpNI225"],
    "KS11": ["krKS11", "ff_KS11", "gz_KOSPI", "krKOSPI"],
    "HSI": ["hkHSI"],
    "SENSEX": ["inSENSEX", "ff_SENSEX", "gz_SENSEX"],
    "000001": ["sh000001"],
    "399001": ["sz399001"],
    "000300": ["sh000300"],
    "399006": ["sz399006"],
}


def try_tx(symbol: str, limit: int = 5) -> int:
    fq_flags = ("qfq", "") if symbol.startswith("us") else ("",)
    for url in TX_URLS:
        if "usfqkline" in url and not symbol.startswith("us"):
            continue
        for fq in fq_flags:
            try:
                payload = get_json(
                    url,
                    params={"param": f"{symbol},day,,,{limit},{fq}"},
                    headers=TX_HEADERS,
                    timeout=6,
                ) or {}
            except Exception as exc:  # noqa: BLE001
                print(f"  tx fail {symbol} {url.split('/')[2]}: {type(exc).__name__}")
                continue
            block = ((payload.get("data") or {}).get(symbol) or {}) if isinstance(payload, dict) else {}
            rows = block.get("day") or block.get("qfqday") or block.get("hfqday") or []
            if rows:
                return len(rows)
    return 0


def try_sina_money(symbol: str) -> int:
    """Sina money.finance daily for gb_ / int_ style."""
    # https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData?symbol=sh000001&scale=240&ma=no&datalen=5
    urls = [
        (
            "https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData",
            {"symbol": symbol, "scale": "240", "ma": "no", "datalen": "10"},
        ),
    ]
    for url, params in urls:
        try:
            raw = get_text(url, params=params, headers={"Referer": "https://finance.sina.com.cn"}, timeout=6)
        except Exception as exc:  # noqa: BLE001
            print(f"  sina money fail {symbol}: {type(exc).__name__}")
            continue
        text = (raw or "").strip()
        if not text or text[0] not in "[{":
            print(f"  sina money bad {symbol}: {text[:80]!r}")
            continue
        try:
            rows = json.loads(text)
        except Exception:
            print(f"  sina money json fail {symbol}")
            continue
        if isinstance(rows, list) and rows:
            return len(rows)
    return 0


def try_em_browser(secid: str) -> int:
    url = "https://push2his.eastmoney.com/api/qt/stock/kline/get"
    params = {
        "secid": secid,
        "klt": "101",
        "fqt": "0",
        "lmt": "5",
        "end": "20500101",
        "fields1": "f1,f2,f3,f4,f5,f6",
        "fields2": "f51,f52,f53,f54,f55",
    }
    try:
        resp = browser_get(
            url,
            params=params,
            headers={"Referer": "https://quote.eastmoney.com/", "Accept": "application/json"},
            timeout=10,
        )
        payload = json.loads(resp.text)
    except Exception as exc:  # noqa: BLE001
        print(f"  em browser fail {secid}: {type(exc).__name__}: {exc}")
        return 0
    rows = ((payload.get("data") or {}).get("klines") or []) if isinstance(payload, dict) else []
    return len(rows)


def try_em_92(secid: str) -> int:
    from core.http import get_json as gj

    for host in ("https://92.push2his.eastmoney.com", "https://push2delay.eastmoney.com"):
        try:
            payload = gj(
                f"{host}/api/qt/stock/kline/get",
                params={
                    "secid": secid,
                    "klt": "101",
                    "fqt": "0",
                    "lmt": "5",
                    "end": "20500101",
                    "fields1": "f1,f2,f3,f4,f5,f6",
                    "fields2": "f51,f52,f53,f54,f55",
                },
                headers={"Referer": "https://quote.eastmoney.com/"},
                timeout=6,
            ) or {}
        except Exception as exc:  # noqa: BLE001
            print(f"  em {host} fail {secid}: {type(exc).__name__}")
            continue
        rows = ((payload.get("data") or {}).get("klines") or []) if isinstance(payload, dict) else []
        if rows:
            return len(rows)
    return 0


if __name__ == "__main__":
    print("=== EM browser DJIA ===")
    print("em browser", try_em_browser("100.DJIA"))
    print("em 92", try_em_92("100.DJIA"))
    print("em sh", try_em_92("1.000001"))

    print("\n=== Tencent candidates ===")
    for code, syms in CANDIDATES.items():
        for sym in syms:
            n = try_tx(sym)
            print(f"{code:8} {sym:14} -> {n}")

    print("\n=== Sina money (CN / gb) ===")
    for sym in ["sh000001", "sz399001", "gb_dji", "gb_inx", "gb_ixic", "int_hangseng", "int_nikkei"]:
        print(sym, try_sina_money(sym))
