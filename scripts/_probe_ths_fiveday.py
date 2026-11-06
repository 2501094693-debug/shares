"""临时探针：同花顺五日分时 / 成交接口。用完可删。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

import requests

from company.detail.ths_mobile import BASE, TRACE_URL, TREND_URL, _HEADERS, market_of

code = "600519"
market = market_of(code)
headers = dict(_HEADERS)
headers["Referer"] = f"https://stockpage.10jqka.com.cn/{code}/stock-quote/"
headers["Origin"] = "https://stockpage.10jqka.com.cn"
s = requests.Session()
s.trust_env = False


def post(url: str, payload: dict):
    r = s.post(url, json=payload, headers=headers, timeout=12)
    try:
        body = r.json()
    except Exception:
        return r.status_code, {"raw": r.text[:300]}
    return r.status_code, body


def summarize(body: dict) -> str:
    sc = body.get("status_code")
    msg = body.get("status_msg")
    data = body.get("data")
    if not isinstance(data, dict):
        return f"sc={sc} msg={msg} data_type={type(data).__name__} keys={list(body)[:8]}"
    qd = data.get("quote_data")
    n = 0
    fields = None
    sample = None
    extra = {}
    if isinstance(qd, list) and qd and isinstance(qd[0], dict):
        q0 = qd[0]
        vals = q0.get("value") or []
        n = len(vals) if isinstance(vals, list) else -1
        fields = q0.get("data_fields")
        extra = {k: q0.get(k) for k in ("base_price", "code", "market", "delay") if k in q0}
        if n and isinstance(vals, list):
            sample = (vals[0], vals[min(3, n - 1)], vals[-1])
    other = {k: (len(v) if isinstance(v, list) else type(v).__name__) for k, v in data.items() if k != "quote_data"}
    return f"sc={sc} msg={msg} n={n} fields={fields} extra={extra} other={other} sample={sample}"


print("=== alternate endpoints ===")
for name in [
    "multi_trend",
    "five_trend",
    "five_day_trend",
    "multi_day_trend",
    "history_trend",
    "single_five_trend",
    "trend_five",
    "five_day",
    "intraday_five",
    "multi_trace",
    "history_trace",
    "range_trend",
    "day_trend",
    "single_history_trend",
    "multi_day_trace",
]:
    url = f"{BASE}/{name}"
    for payload in [
        {
            "code_list": [{"codes": [code], "market": market}],
            "trade_class": "five_day",
            "trade_date": 0,
            "gpid": 1,
        },
        {
            "code_list": [{"codes": [code], "market": market}],
            "trade_class": "intraday",
            "trade_date": 0,
            "gpid": 1,
        },
        {
            "code_list": [{"codes": [code], "market": market}],
            "gpid": 1,
            "time_range": {"type": "end_count", "count": 100, "end_time": 0},
        },
    ]:
        try:
            http, body = post(url, payload)
        except Exception as exc:
            print(f"{name} ERR {exc}")
            break
        if http == 404:
            continue
        info = summarize(body) if isinstance(body, dict) else str(body)[:120]
        print(f"{name} http={http} {info} payload={list(payload)}")
        if isinstance(body, dict) and "n=" in info and "n=0" not in info.split()[2:4]:
            # keep probing other payloads if empty
            pass

print("\n=== single_trend trade_class / trade_date ===")
for tc in ["intraday", "five_day", "FiveDay", "FIVE_DAY", "5", "week", "5d", "days_5"]:
    for td in [0, 20251105, 20251104]:
        payload = {
            "code_list": [{"codes": [code], "market": market}],
            "trade_class": tc,
            "trade_date": td,
            "gpid": 1,
            "time_zone": "Asia/Shanghai",
        }
        http, body = post(TREND_URL, payload)
        info = summarize(body)
        if "n=0" not in info or tc in ("five_day", "intraday"):
            print(f"tc={tc!r} td={td} {info}")

print("\n=== single_trace large / range ===")
for payload in [
    {
        "code_list": [{"codes": [code], "market": market}],
        "time_range": {"type": "end_count", "count": 1000, "end_time": 0},
        "gpid": 1,
    },
    {
        "code_list": [{"codes": [code], "market": market}],
        "time_range": {
            "type": "begin_end",
            "begin_time": 0,
            "end_time": 0,
        },
        "gpid": 1,
    },
    {
        "code_list": [{"codes": [code], "market": market}],
        "time_range": {
            "type": "begin_end",
            "begin_time": 1761984000000,  # ~2025-11-01
            "end_time": 0,
        },
        "gpid": 1,
    },
    {
        "code_list": [{"codes": [code], "market": market}],
        "time_range": {"type": "end_count", "count": 5000, "end_time": 0},
        "gpid": 1,
    },
]:
    http, body = post(TRACE_URL, payload)
    print(summarize(body), "payload_tr", payload["time_range"])

print("\n=== classic d.10jqka hosts ===")
for url in [
    f"https://d.10jqka.com.cn/v6/time/hs_{code}/last.js",
    f"https://d.10jqka.com.cn/v6/time/hs_{code}/5.js",
    f"https://d.10jqka.com.cn/v6/time/hs_{code}/last5.js",
    f"https://d.10jqka.com.cn/v8/time/hs_{code}/last.js",
    f"https://d.10jqka.com.cn/v8/time/hs_{code}/5d.js",
    f"https://d.10jqka.com.cn/v6/line/hs_{code}/01/last.js",
    f"https://d.10jqka.com.cn/v4/time/hs_{code}/last.js",
    f"https://d.10jqka.com.cn/v2/time/hs_{code}/last.js",
]:
    try:
        r = s.get(url, headers={"User-Agent": headers["User-Agent"], "Referer": "https://stockpage.10jqka.com.cn/"}, timeout=10)
        text = r.text[:200].replace("\n", " ")
        print(f"{r.status_code} {url} -> {text}")
    except Exception as exc:
        print(f"ERR {url} {exc}")
