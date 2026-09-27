"""Find any working overseas index daily kline source."""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone

from core.http import browser_get, get_json, get_text

EM_H = {
    "Referer": "https://quote.eastmoney.com/",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
}
SINA_H = {"Referer": "https://finance.sina.com.cn", "User-Agent": "Mozilla/5.0"}
TX_H = {"Referer": "https://gu.qq.com/", "User-Agent": "Mozilla/5.0"}


def try_url(label: str, url: str, *, browser: bool = False, params=None, headers=None) -> None:
    try:
        if browser:
            r = browser_get(url, timeout=12, headers=headers or {})
            text = r.text[:200]
            code = r.status_code
        elif params is not None:
            j = get_json(url, params=params, headers=headers or {}, timeout=10)
            text = str(j)[:200]
            code = "json"
        else:
            text = (get_text(url, headers=headers or {}, timeout=10) or "")[:200]
            code = "text"
        print(f"OK {label}: {code} {text!r}")
    except Exception as exc:  # noqa: BLE001
        print(f"FAIL {label}: {type(exc).__name__}: {str(exc)[:100]}")


def main() -> None:
    # EM variants
    for host in [
        "https://push2.eastmoney.com",
        "https://push2delay.eastmoney.com",
        "https://push2his.eastmoney.com",
        "https://quote.eastmoney.com",
    ]:
        try_url(
            f"em {host}",
            f"{host}/api/qt/stock/kline/get",
            params={
                "secid": "100.GDAXI",
                "fields1": "f1,f2,f3,f4,f5,f6",
                "fields2": "f51,f52,f53,f54,f55",
                "klt": "101",
                "fqt": "0",
                "end": "20500101",
                "lmt": "5",
            },
            headers=EM_H,
        )

    # EM trends2 / history via stock/trends2
    try_url(
        "em trends2",
        "https://push2.eastmoney.com/api/qt/stock/trends2/get",
        params={"secid": "100.GDAXI", "fields1": "f1,f2,f3,f4,f5,f6,f7,f8,f9,f10,f11,f12,f13", "fields2": "f51,f52,f53,f54,f55,f56,f57,f58", "iscr": "0", "ndays": "5"},
        headers=EM_H,
    )

    # Sina KKE style - often loads from cnfinance.sina
    for url in [
        "https://stock.finance.sina.com.cn/usstock/api/jsonp.php/var%20_X=/GlobalIndexService.getKLineData?symbol=znb_DAX&scale=240&ma=no&datalen=30",
        "https://stock.finance.sina.com.cn/usstock/api/jsonp.php/var%20_X=/GlobalIndexService.getDailyK?symbol=znb_DAX",
        "https://stock.finance.sina.com.cn/usstock/api/jsonp.php/var%20_X=/CN_MarketDataService.getKLineData?symbol=znb_DAX&scale=240&ma=no&datalen=30",
        "https://quotes.sina.cn/cn/api/jsonp_v2.php/var%20_X=/CN_MarketDataService.getKLineData?symbol=znb_DAX&scale=240&ma=no&datalen=30",
        "https://hq.sinajs.cn/list=znb_DAX,znb_NKY,znb_CAC,znb_UKX,znb_KOSPI,znb_SX5E,znb_SENSEX",
    ]:
        try_url(url.split("/")[-1][:50], url, headers=SINA_H)

    # Look inside sf_sdk for kline host
    sdk = get_text(
        "https://finance.sina.com.cn/sinafinancesdk/js/sf_sdk.js",
        headers=SINA_H,
        timeout=15,
    ) or ""
    hosts = sorted(set(re.findall(r"[a-z0-9.-]+\.sina(?:js)?\.cn", sdk)))
    print("sdk hosts", hosts[:40])
    for h in re.findall(r".{0,40}(?:kline|KLine|dayK|getDay).{0,80}", sdk, re.I)[:15]:
        print("sdk ctx", h.replace("\n", " ")[:140])

    # Tencent market codes via qt list search for ZS-
    # From earlier quote: ZS-FT for FTSE. Try ZS-* codes
    try_url(
        "qt ZS",
        "https://qt.gtimg.cn/q=ZS-FT,ZS-DAX,ZS-N225,ZS-CAC,ZS-KS11,ZS-SX5E,ZS-SENSEX,s_ZS-DAX",
        headers=TX_H,
    )

    # Try fqkline with ZS- prefix
    for sym in ["ZS-DAX", "ZS-N225", "ZS-CAC", "ZS-KS11", "ZS-SX5E", "ZS-SENSEX", "ZS-FT", "zsDAX", "zs_DAX"]:
        try:
            payload = (
                get_json(
                    "https://proxy.finance.qq.com/ifzqgtimg/appstock/app/newfqkline/get",
                    params={"param": f"{sym},day,,,5,"},
                    headers=TX_H,
                    timeout=6,
                )
                or {}
            )
        except Exception:
            continue
        block = ((payload.get("data") or {}).get(sym) or {})
        rows = block.get("day") or block.get("qfqday") or []
        if rows:
            print("TX HIT", sym, rows[-1][:4])


if __name__ == "__main__":
    main()
