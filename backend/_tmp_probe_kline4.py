"""Probe Stooq / EM IP refresh / Sina global for remaining indices."""
from __future__ import annotations

import csv
import io
import json
import socket

from core.http import get_text, get_json, browser_get
from core import resolve

SINA_H = {"Referer": "https://finance.sina.com.cn"}


def try_stooq(symbol: str) -> int:
    url = f"https://stooq.com/q/d/l/?s={symbol}&i=d"
    try:
        text = get_text(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"}) or ""
    except Exception as exc:
        print(f"FAIL stooq {symbol}: {type(exc).__name__}")
        return 0
    if "Date" not in text[:40] and "No data" in text:
        print(f"miss stooq {symbol}: no data")
        return 0
    rows = list(csv.DictReader(io.StringIO(text)))
    print(f"{'HIT' if rows else 'miss'} stooq {symbol}: {len(rows)} last={rows[-1] if rows else None}")
    return len(rows)


def try_em_hosts(secid: str) -> None:
    hosts = [
        "push2his.eastmoney.com",
        "92.push2his.eastmoney.com",
        "85.push2his.eastmoney.com",
        "70.push2his.eastmoney.com",
        "push2delay.eastmoney.com",
    ]
    params = {
        "secid": secid,
        "klt": "101",
        "fqt": "0",
        "lmt": "3",
        "end": "20500101",
        "fields1": "f1,f2,f3,f4,f5,f6",
        "fields2": "f51,f52,f53,f54,f55",
    }
    for host in hosts:
        url = f"https://{host}/api/qt/stock/kline/get"
        try:
            payload = get_json(
                url,
                params=params,
                headers={"Referer": "https://quote.eastmoney.com/"},
                timeout=6,
            ) or {}
            rows = ((payload.get("data") or {}).get("klines") or [])
            print(f"HIT em {host} {secid}: {len(rows)}")
            if rows:
                print(" ", rows[-1])
        except Exception as exc:
            print(f"FAIL em {host} {secid}: {type(exc).__name__}: {exc}")


def try_resolve_push2his() -> None:
    host = "push2his.eastmoney.com"
    print("dial_ips", resolve.dial_ips(host))
    try:
        print("system DNS", socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)[:4])
    except Exception as exc:
        print("system DNS fail", exc)


def try_sina_global_page() -> None:
    # Common: https://finance.sina.com.cn/stock/globalindex/hq/b_DAX.js
    for path in [
        "https://finance.sina.com.cn/stock/globalindex/hq/b_DAX.js",
        "https://finance.sina.com.cn/stock/globalindex/hq/b_N225.js",
        "https://vip.stock.finance.sina.com.cn/forex/api/jsonp.php/var%20_X=/NewForexService.getDayKLine?symbol=fx_seurusd",
    ]:
        try:
            text = get_text(path, headers=SINA_H, timeout=8) or ""
            print(f"OK {path[:70]}: {text[:180]!r}")
        except Exception as exc:
            print(f"FAIL {path[:50]}: {exc}")


def try_yahoo_browser(symbol: str) -> int:
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval=1d&range=3mo"
    try:
        resp = browser_get(url, timeout=12, headers={"User-Agent": "Mozilla/5.0"})
        payload = json.loads(resp.text)
    except Exception as exc:
        print(f"FAIL yahoo-b {symbol}: {type(exc).__name__}: {exc}")
        return 0
    result = ((payload.get("chart") or {}).get("result") or [None])[0] or {}
    ts = result.get("timestamp") or []
    print(f"{'HIT' if ts else 'miss'} yahoo-b {symbol}: {len(ts)}")
    return len(ts)


if __name__ == "__main__":
    print("=== resolve ===")
    try_resolve_push2his()
    print("\n=== EM hosts ===")
    try_em_hosts("100.DJIA")
    try_em_hosts("1.000001")
    print("\n=== Stooq ===")
    for s in ["^dji", "^spx", "^ndq", "^ftse", "^dax", "^cac", "^nkx", "^kospi", "^sensex", "^stoxx50", "^hsi"]:
        try_stooq(s)
    print("\n=== Yahoo browser ===")
    for s in ["^GDAXI", "^N225", "^KS11"]:
        try_yahoo_browser(s)
    print("\n=== Sina global ===")
    try_sina_global_page()
