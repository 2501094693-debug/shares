"""解析 last5 / 5d，并探测秒级成交通道。"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

import requests

from company.detail.ths_mobile import TRACE_URL, TREND_URL, _HEADERS, market_of, fetch_trace

code = "600519"
market = market_of(code)
ua = _HEADERS["User-Agent"]
s = requests.Session()
s.trust_env = False
headers = {
    "User-Agent": ua,
    "Referer": "https://stockpage.10jqka.com.cn/",
}


def unwrap_jsonp(text: str):
    text = text.strip()
    m = re.match(r"^[^(]+\((.*)\)\s*;?\s*$", text, re.S)
    if m:
        text = m.group(1)
    return json.loads(text)


for url in [
    f"https://d.10jqka.com.cn/v6/time/hs_{code}/last5.js",
    f"https://d.10jqka.com.cn/v8/time/hs_{code}/5d.js",
    f"https://d.10jqka.com.cn/v6/time/hs_{code}/5day.js",
    f"https://d.10jqka.com.cn/v6/time/hs_{code}/last.js",
]:
    r = s.get(url, headers=headers, timeout=15)
    print(f"\n==== {url} http={r.status_code} len={len(r.text)} ====")
    if r.status_code != 200 or r.text.lstrip().startswith("<"):
        print(r.text[:200])
        continue
    try:
        data = unwrap_jsonp(r.text)
    except Exception as exc:
        print("parse fail", exc, r.text[:200])
        continue
    key = next(iter(data))
    block = data[key]
    print("top keys:", sorted(block.keys()))
    for k, v in block.items():
        if k in ("data", "price", "vol", "amount", "dates", "days", "time"):
            if isinstance(v, str):
                parts = v.split(";")
                print(f"  {k}: str parts={len(parts)} first={parts[0][:80]!r} last={parts[-1][:80]!r}")
                if parts:
                    print("    cols", parts[0].split(","))
                    if len(parts) > 1:
                        print("    cols2", parts[1].split(","))
            elif isinstance(v, list):
                print(f"  {k}: list n={len(v)} sample={v[:2]} ... {v[-1:]}")
            else:
                print(f"  {k}: {type(v).__name__}={v!r}"[:200])
        else:
            sv = repr(v)
            if len(sv) > 120:
                sv = sv[:120] + "..."
            print(f"  {k}: {sv}")

print("\n==== fetch_trace sample ====")
try:
    items = fetch_trace(code, count=5)
    print("n", len(items) if isinstance(items, list) else type(items))
    if isinstance(items, list) and items:
        print(json.dumps(items[:2], ensure_ascii=False, indent=2))
        print("last", items[-1])
except Exception as exc:
    print("trace err", exc)

print("\n==== single_trace fail_params dump ====")
headers2 = dict(_HEADERS)
headers2["Referer"] = f"https://stockpage.10jqka.com.cn/{code}/stock-quote/"
headers2["Origin"] = "https://stockpage.10jqka.com.cn"
for payload in [
    {
        "code_list": [{"codes": [code], "market": market}],
        "time_range": {"type": "end_count", "count": 60, "end_time": 0},
        "gpid": 1,
    },
    {
        "code_list": [{"codes": [code], "market": market}],
        "time_range": {"type": "end_count", "count": 60, "end_time": 0},
        "gpid": 1,
        "trade_class": "intraday",
    },
]:
    r = s.post(TRACE_URL, json=payload, headers=headers2, timeout=12)
    body = r.json()
    print(json.dumps(body, ensure_ascii=False)[:800])

# 历史日逐分钟：拼五日
print("\n==== stitch 5 days via single_trend ====")
# 先从 last5 拿日期
r = s.get(f"https://d.10jqka.com.cn/v6/time/hs_{code}/last5.js", headers=headers, timeout=15)
data = unwrap_jsonp(r.text)
block = data[f"hs_{code}"]
print("date field", block.get("date"), "dates", block.get("dates"), "days", block.get("days"))
