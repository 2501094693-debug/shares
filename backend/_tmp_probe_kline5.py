"""Probe Baidu / Eastmoney alt / Sina global futures-style for indices."""
from __future__ import annotations

import json
import re

from core.http import get_json, get_text, browser_get

SINA_H = {"Referer": "https://finance.sina.com.cn"}


def try_baidu(code: str, market_type: str = "us") -> int:
    url = "https://finance.pae.baidu.com/vapi/v1/getquotation"
    params = {
        "srcid": "5353",
        "group": "quotation_kline_ab",
        "query": code,
        "code": code,
        "market_type": market_type,
        "newFormat": "1",
        "is_index": "1",
        "finClientType": "pc",
        "ktype": "day",
    }
    try:
        payload = get_json(url, params=params, timeout=10) or {}
    except Exception as exc:
        print(f"FAIL baidu {code}: {type(exc).__name__}: {exc}")
        return 0
    # structure varies
    result = payload.get("Result") or payload.get("ResultCode")
    text = json.dumps(payload, ensure_ascii=False)[:400]
    print(f"baidu {code}/{market_type}: keys={list(payload.keys())[:8]} snippet={text}")
    # try find kline list
    def walk(obj, depth=0):
        if depth > 6:
            return 0
        if isinstance(obj, list) and obj and isinstance(obj[0], (list, dict)):
            if isinstance(obj[0], list) and len(obj[0]) >= 5:
                return len(obj)
            if isinstance(obj[0], dict) and ("close" in obj[0] or "price" in obj[0] or "date" in obj[0]):
                return len(obj)
        if isinstance(obj, dict):
            for v in obj.values():
                n = walk(v, depth + 1)
                if n:
                    return n
        return 0

    n = walk(payload)
    print(f"  -> guessed klines={n}")
    return n


def try_em_chart(secid: str) -> None:
    # alternate EM chart endpoints
    urls = [
        f"https://push2his.eastmoney.com/api/qt/stock/kline/get?secid={secid}&fields1=f1,f2,f3,f4,f5,f6&fields2=f51,f52,f53,f54,f55&klt=101&fqt=0&end=20500101&lmt=5",
        f"https://quote.eastmoney.com/newapi/stockkline?secid={secid}&klt=101&lmt=5",
        f"https://datacenter.eastmoney.com/api/data/v1/get?reportName=RPT_INDEX_DAILY&columns=ALL&filter=(SECURITY_CODE%3D%22DJIA%22)&pageSize=5",
    ]
    for url in urls:
        try:
            resp = browser_get(url, timeout=10, headers={"Referer": "https://quote.eastmoney.com/"})
            print(f"OK em-alt {url[:70]}: {resp.text[:200]!r}")
        except Exception as exc:
            print(f"FAIL em-alt: {type(exc).__name__}: {exc}")


def try_sina_hq_history() -> None:
    # Possible APIs used by sina global index pages
    candidates = [
        "https://stock.finance.sina.com.cn/usstock/api/jsonp.php/var%20_X=/US_Market_Service.getKLineData?symbol=.dji&scale=240&ma=5&datalen=10",
        "https://quotes.sina.cn/cn/api/jsonp.php/var%20_X=/CN_MarketDataService.getKLineData?symbol=znb_DAX&scale=240&ma=5&datalen=10",
        "https://hq.sinajs.cn/rn=1&list=znb_DAX",
        # money.finance for us index with leading dot already works; try asia
        "https://stock.finance.sina.com.cn/usstock/api/jsonp.php/var%20_X=/US_MinKService.getDailyK?symbol=.n225",
        "https://stock.finance.sina.com.cn/usstock/api/jsonp.php/var%20_X=/US_MinKService.getDailyK?symbol=.ks11",
        "https://stock.finance.sina.com.cn/usstock/api/jsonp.php/var%20_X=/US_MinKService.getDailyK?symbol=.hsi",
        "https://stock.finance.sina.com.cn/usstock/api/jsonp.php/var%20_X=/US_MinKService.getDailyK?symbol=.gdaxi",
        "https://stock.finance.sina.com.cn/usstock/api/jsonp.php/var%20_X=/US_MinKService.getDailyK?symbol=.fchi",
        "https://stock.finance.sina.com.cn/usstock/api/jsonp.php/var%20_X=/US_MinKService.getDailyK?symbol=.ftse",
        "https://stock.finance.sina.com.cn/usstock/api/jsonp.php/var%20_X=/US_MinKService.getDailyK?symbol=.bsesn",
        "https://stock.finance.sina.com.cn/usstock/api/jsonp.php/var%20_X=/US_MinKService.getDailyK?symbol=.sti",
        "https://stock.finance.sina.com.cn/usstock/api/jsonp.php/var%20_X=/US_MinKService.getDailyK?symbol=.axjo",
        "https://stock.finance.sina.com.cn/usstock/api/jsonp.php/var%20_X=/US_MinKService.getDailyK?symbol=.gdaxi",
        "https://stock.finance.sina.com.cn/usstock/api/jsonp.php/var%20_X=/US_MinKService.getDailyK?symbol=N225",
        "https://stock.finance.sina.com.cn/usstock/api/jsonp.php/var%20_X=/US_MinKService.getDailyK?symbol=^N225",
    ]
    for url in candidates:
        try:
            text = get_text(url, headers=SINA_H, timeout=8) or ""
            m = re.search(r"=\((.*)\)\s*;?\s*$", text, re.S)
            body = m.group(1)[:120] if m else text[:120]
            print(f"OK {url.split('=')[-1][:20]:20} {body!r}")
        except Exception as exc:
            print(f"FAIL {url[-40:]}: {exc}")


def try_tx_more() -> None:
    # Search finance.qq.com style codes via kline
    from core.http import get_json as gj

    symbols = [
        "ukUKX", "ukXINX", "ff_UKX",
        "geDAX", "gmDAX", "deGDAXI", "euDAX",
        "frFCHI", "frCAC40",
        "jp225", "jpN225", "jn225",
        "krKOSP", "krKOSPI",
        "inBSES", "inSENSE",
        "euSX5E", "euSTOXX",
    ]
    for sym in symbols:
        try:
            payload = gj(
                "https://proxy.finance.qq.com/ifzqgtimg/appstock/app/newfqkline/get",
                params={"param": f"{sym},day,,,5,"},
                headers={"Referer": "https://gu.qq.com/"},
                timeout=5,
            ) or {}
        except Exception:
            continue
        block = ((payload.get("data") or {}).get(sym) or {})
        rows = block.get("day") or block.get("qfqday") or []
        if rows:
            print(f"HIT tx {sym}: {len(rows)} {rows[-1]}")


if __name__ == "__main__":
    print("=== Baidu ===")
    for code, mkt in [
        ("DJIA", "us"),
        ("usDJIA", "us"),
        ("NDX", "us"),
        ("GDAXI", "ab"),
        ("N225", "ab"),
        ("b_DAX", "ab"),
        ("DAX", "hk"),
    ]:
        try_baidu(code, mkt)
    print("\n=== EM alt ===")
    try_em_chart("100.DJIA")
    print("\n=== Sina daily variants ===")
    try_sina_hq_history()
    print("\n=== TX more ===")
    try_tx_more()
