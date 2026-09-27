"""Decode sina gbIndexSb and find TKChart data API."""
from __future__ import annotations

import json
import re

from core.http import browser_get, get_text

SINA_H = {"Referer": "https://finance.sina.com.cn", "User-Agent": "Mozilla/5.0"}


def gb_index_sb(sb: str) -> str:
    """Mirror of page JS: keep alnum/_; encode other chars somehow."""
    out = []
    for char in sb:
        if re.match(r"^[0-9a-zA-Z_]$", char):
            out.append(char)
        else:
            # fallback — inspect page for full logic
            out.append(char)
    return "".join(out)


def main() -> None:
    text = browser_get(
        "https://finance.sina.com.cn/stock/globalindex/quotes/DAX",
        headers=SINA_H,
        timeout=15,
    ).text
    idx = text.find("function gbIndexSb")
    chunk = text[idx : idx + 1200]
    open("_tmp_gbindex.txt", "w", encoding="utf-8").write(chunk)
    print("wrote _tmp_gbindex.txt", len(chunk))

    # Find KKE / tkchart script urls on page
    scripts = re.findall(r"src=[\"']([^\"']+)[\"']", text)
    open("_tmp_scripts.txt", "w", encoding="utf-8").write("\n".join(scripts))
    print("scripts", len(scripts))

    # Try common sinaTKChart endpoints with znb_DAX
    symbol = "znb_DAX"
    cands = [
        f"https://stock.finance.sina.com.cn/usstock/api/jsonp.php/var%20_X=/Global_Service.getMinKline?symbol={symbol}",
        f"https://stock.finance.sina.com.cn/usstock/api/jsonp.php/var%20_X=/CN_MarketDataService.getKLineData?symbol={symbol}&scale=240&ma=no&datalen=90",
        f"https://quotes.sina.cn/cn/api/jsonp_v2.php/_/CN_MarketDataService.getKLineData?symbol={symbol}&scale=240&ma=no&datalen=90",
        f"https://finance.sina.com.cn/realstock/company/{symbol}/hisdata/klc_kl.js",
        f"https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData?symbol={symbol}&scale=240&ma=no&datalen=90",
        # encoded variants sometimes use base64-ish
        "https://stock.finance.sina.com.cn/usstock/api/jsonp.php/var%20_X=/US_MinKService.getDailyK?symbol=znb_DAX",
    ]
    for url in cands:
        try:
            t = get_text(url, headers=SINA_H, timeout=8) or ""
        except Exception as exc:  # noqa: BLE001
            print("FAIL", url[-60:], type(exc).__name__)
            continue
        print("OK", url[-70:], "=>", t[:120].replace("\n", " "))

    # Search CDN for sinaTKChart
    for url in [
        "https://finance.sina.com.cn/sinafinancesdk/js/plugins/sinaTKChart.js",
        "https://finance.sina.com.cn/sinafinancesdk/js/sf_sdk.js",
    ]:
        try:
            t = get_text(url, headers=SINA_H, timeout=10) or ""
        except Exception as exc:  # noqa: BLE001
            print("sdk", url, type(exc).__name__)
            continue
        print("sdk", url, "len", len(t))
        apis = sorted(set(re.findall(r"https?://[^\"'\\]+", t)))
        for a in apis:
            if any(k in a.lower() for k in ("kline", "day", "api", "hq", "json")):
                print("  api", a)
        # also relative path patterns
        paths = sorted(set(re.findall(r"[\"'](/[^\"']*(?:kline|KLine|day)[^\"']*)[\"']", t, re.I)))
        print("  paths", paths[:20])
        open("_tmp_sdk_snippet.txt", "w", encoding="utf-8").write(t[:5000])


if __name__ == "__main__":
    main()
