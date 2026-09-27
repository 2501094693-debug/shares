"""Find working kline sources for overseas indices."""
from __future__ import annotations

import json
import re

from core.http import get_json, get_text, browser_get

TX_URLS = (
    "https://web.ifzq.gtimg.cn/appstock/app/usfqkline/get",
    "https://proxy.finance.qq.com/ifzqgtimg/appstock/app/newfqkline/get",
    "https://ifzq.gtimg.cn/appstock/app/fqkline/get",
)
TX_HEADERS = {"Referer": "https://gu.qq.com/"}
SINA_H = {"Referer": "https://finance.sina.com.cn"}


def try_tx(symbol: str, limit: int = 5) -> tuple[int, str]:
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
            except Exception:
                continue
            block = ((payload.get("data") or {}).get(symbol) or {}) if isinstance(payload, dict) else {}
            for key in ("day", "qfqday", "hfqday"):
                rows = block.get(key) or []
                if rows:
                    return len(rows), f"{url.split('/')[2]}:{key}"
    return 0, ""


def try_url(label: str, url: str, **kwargs) -> None:
    try:
        if kwargs.pop("browser", False):
            resp = browser_get(url, timeout=10, headers=kwargs.get("headers") or SINA_H)
            text = resp.text[:300]
            print(f"OK {label}: {text!r}")
            return
        text = get_text(url, timeout=8, **kwargs) or ""
        print(f"OK {label}: {text[:300]!r}")
    except Exception as exc:
        print(f"FAIL {label}: {type(exc).__name__}: {exc}")


# More TX guesses
more_tx = [
    "ukUKX", "ukFTSE100", "ftFTSE",
    "deDAX30", "deGDAXI", "ffDAX",
    "frCAC40",
    "jp225", "jpNikkei", "usN225",
    "kr200", "ks200",
    "inSENSEX", "inBSESN",
    "euSTOXX50", "euSX5E", "stoxx50",
    # QQ foreign futures style
    "hf_DAX", "hf_CAC", "hf_NK", "hf_HSI",
]

print("=== more TX ===")
for s in more_tx:
    n, src = try_tx(s)
    if n:
        print(f"HIT {s} -> {n} via {src}")
    else:
        print(f"miss {s}")

print("\n=== Sina US daily (jsonp) ===")
for sym in ["dji", ".dji", "inx", ".inx", "ixic", ".ixic", "DJI", "NDX"]:
    try_url(
        f"us {sym}",
        f"https://stock.finance.sina.com.cn/usstock/api/jsonp.php/var%20_X=/US_MinKService.getDailyK?symbol={sym}&__rnd=1",
        headers=SINA_H,
    )

print("\n=== Sina quotes_service foreign ===")
# Common pattern for global indices on sina
for path in [
    "https://quotes.sina.cn/cn/api/jsonp_v2.php/var%20_X=/GlobalService.getMink?symbol=znb_DAX&scale=5d",
    "https://hq.sinajs.cn/list=znb_DAX,znb_CAC,znb_UKX,znb_KOSPI,znb_SENSEX,znb_SX5E,int_nikkei,int_hangseng",
]:
    try_url(path[:60], path, headers=SINA_H)

print("\n=== Sina CN_MarketData for znb ===")
for sym in ["znb_DAX", "znb_CAC", "znb_UKX", "znb_KOSPI", "znb_SENSEX", "znb_SX5E"]:
    try_url(
        sym,
        "https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData",
        params={"symbol": sym, "scale": "240", "ma": "no", "datalen": "5"},
        headers=SINA_H,
    )

print("\n=== finance.sina globalstock his ===")
for code in ["bse", "dax", "ftse", "nikkei", "kospi", "sensex", "cac40"]:
    try_url(
        code,
        f"https://stock.finance.sina.com.cn/usstock/api/json.php/US_MinKService.getDailyK?symbol={code}",
        headers=SINA_H,
    )
