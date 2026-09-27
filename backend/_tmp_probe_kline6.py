"""Find working kline sources for overseas indices when EM push2his is down."""
from __future__ import annotations

import json
import re

from core.http import browser_get, get_json, get_text

SINA_H = {"Referer": "https://finance.sina.com.cn", "User-Agent": "Mozilla/5.0"}
TX_H = {"Referer": "https://gu.qq.com/"}
EM_H = {
    "Referer": "https://quote.eastmoney.com/",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
}


def probe_em_pages() -> None:
    print("=== EM quote pages ===")
    for code in ["GDAXI", "N225", "KS11", "FCHI", "FTSE", "SX5E", "SENSEX"]:
        url = f"https://quote.eastmoney.com/gb/{code}.html"
        try:
            r = browser_get(url, timeout=12, headers=EM_H)
            text = r.text
            m = re.search(r"secid[=:\s\"']+([0-9]+\.[A-Z0-9]+)", text, re.I)
            apis = re.findall(r"push2his[^\"']+", text)
            print(code, "status", r.status_code, "secid", m.group(1) if m else None, "apis", apis[:2], "len", len(text))
        except Exception as exc:  # noqa: BLE001
            print(code, type(exc).__name__, str(exc)[:100])


def probe_em_kline() -> None:
    print("=== EM kline browser ===")
    for secid in ["100.GDAXI", "100.N225", "100.KS11", "1.000001", "100.DJIA"]:
        url = (
            "https://push2his.eastmoney.com/api/qt/stock/kline/get"
            f"?secid={secid}&fields1=f1,f2,f3,f4,f5,f6&fields2=f51,f52,f53,f54,f55"
            "&klt=101&fqt=0&end=20500101&lmt=5"
        )
        try:
            r = browser_get(url, timeout=10, headers=EM_H)
            print("emk", secid, r.status_code, r.text[:140])
        except Exception as exc:  # noqa: BLE001
            print("emk", secid, type(exc).__name__, str(exc)[:80])


def probe_tx_search() -> None:
    print("=== TX smartbox overseas ===")
    queries = ["德国", "日经225", "法国CAC", "韩国", "欧洲50", "富时100", "印度"]
    for q in queries:
        try:
            t = get_text(f"https://smartbox.gtimg.cn/s3/?v=2&q={q}&t=all", headers=TX_H, timeout=6) or ""
        except Exception as exc:  # noqa: BLE001
            print("search", q, type(exc).__name__)
            continue
        # parse v_hint="a~b~c~d^..."
        hint = t.split("v_hint=", 1)[-1].strip().strip('"')
        parts = hint.split("^")
        interesting = [p for p in parts if any(x in p.lower() for x in ("dax", "n225", "cac", "kospi", "ftse", "ukx", "sensex", "sx5e", "stoxx", "nikkei"))]
        print(q, "interesting", interesting[:8] or parts[:3])


def probe_tx_kline(symbols: list[str]) -> None:
    print("=== TX kline candidates ===")
    url = "https://proxy.finance.qq.com/ifzqgtimg/appstock/app/newfqkline/get"
    for sym in symbols:
        try:
            payload = get_json(url, params={"param": f"{sym},day,,,5,"}, headers=TX_H, timeout=6) or {}
        except Exception:
            continue
        block = ((payload.get("data") or {}).get(sym) or {})
        rows = block.get("day") or block.get("qfqday") or []
        if rows:
            last = rows[-1]
            print("HIT", sym, last[:3] if isinstance(last, list) else last)


def probe_sina_daily() -> None:
    print("=== Sina US_MinKService (sample) ===")
    for sym in [".dji", ".gdaxi", "znb_DAX"]:
        url = (
            "https://stock.finance.sina.com.cn/usstock/api/jsonp.php/var%20_X=/"
            f"US_MinKService.getDailyK?symbol={sym}"
        )
        try:
            t = get_text(url, headers=SINA_H, timeout=10) or ""
            m = re.search(r"=\((.*)\)\s*;?\s*$", t, re.S)
            body = m.group(1)[:100] if m else t[:100]
            print(sym, body)
        except Exception as exc:  # noqa: BLE001
            print(sym, type(exc).__name__, exc)


def probe_stooq_browser() -> None:
    print("=== Stooq browser ===")
    for s in ["^dax", "^nkx", "^ukx"]:
        url = f"https://stooq.com/q/d/l/?s={s}&i=d"
        try:
            r = browser_get(url, timeout=12, headers={"User-Agent": "Mozilla/5.0"})
            lines = [ln for ln in r.text.splitlines() if ln and "Date" not in ln][-3:]
            print(s, r.status_code, lines)
        except Exception as exc:  # noqa: BLE001
            print(s, type(exc).__name__, exc)


if __name__ == "__main__":
    probe_em_kline()
    probe_tx_search()
    probe_sina_daily()
    probe_stooq_browser()
    # Extra TX symbols guessed from market prefixes
    probe_tx_kline(
        [
            "ukUKX",
            "ftUKX",
            "ff_UKX",
            "geGDAX",
            "gmGDAX",
            "deGDAX",
            "euSX5E",
            "frCAC",
            "jpN225",
            "krKS11",
            "inSENSEX",
            "usN225",
            "usGDAXI",
            "hkHSCEI",
        ]
    )
    probe_em_pages()
