"""验证：五日交易日 + single_trace 翻页到秒；single_trend 历史日。"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

import requests

from company.detail.ths_mobile import (
    TRACE_URL,
    TREND_URL,
    _HEADERS,
    fetch_trace,
    fetch_trend,
    market_of,
)
from company.line.fetcher import fetch_kline

code = "600519"
market = market_of(code)
TZ = timezone(timedelta(hours=8))
s = requests.Session()
s.trust_env = False
headers = dict(_HEADERS)
headers["Referer"] = f"https://stockpage.10jqka.com.cn/{code}/stock-quote/"
headers["Origin"] = "https://stockpage.10jqka.com.cn"

# 最近日 K → 近 5 交易日
pack = fetch_kline(code, period="day", limit=8, adjust="qfq")
days = []
for row in (pack.get("items") or pack.get("klines") or [])[-8:]:
    # 兼容不同字段
    d = row.get("day") or row.get("date") or row.get("time") or ""
    days.append(str(d)[:10])
print("kline days sample", days)
print("kline keys", pack.keys() if isinstance(pack, dict) else type(pack))
if pack.get("items"):
    print("item0", pack["items"][0])
elif pack.get("klines"):
    print("kline0", pack["klines"][0])

# 取最近 5 个交易日 YYYYMMDD
trade_days = []
for row in (pack.get("items") or [])[-5:]:
    d = str(row.get("day") or row.get("date") or "")[:10].replace("-", "")
    if d.isdigit():
        trade_days.append(d)
print("trade_days", trade_days)

print("\n=== single_trend per day ===")
for td in trade_days:
    r = s.post(
        TREND_URL,
        json={
            "code_list": [{"codes": [code], "market": market}],
            "trade_class": "intraday",
            "trade_date": int(td),
            "gpid": 1,
            "time_zone": "Asia/Shanghai",
        },
        headers=headers,
        timeout=12,
    )
    body = r.json()
    qd = (body.get("data") or {}).get("quote_data") or []
    n = len((qd[0].get("value") or [])) if qd else 0
    first = (qd[0].get("value") or [None])[0] if qd else None
    last = (qd[0].get("value") or [None])[-1] if qd else None
    print(f"  {td} n={n} first={first} last={last}")

print("\n=== single_trace paginate backward ===")
# 连续翻页，看能否跨到前几日
end_time = 0
all_items = []
seen = set()
for page in range(30):
    items = fetch_trace(code, count=200, end_time=end_time)
    if not isinstance(items, list) or not items:
        print(f"page {page} empty end={end_time}")
        break
    new = 0
    for it in items:
        eid = it.get("event_id") or (it.get("time"), it.get("seq"))
        if eid in seen:
            continue
        seen.add(eid)
        all_items.append(it)
        new += 1
    first, last = items[0], items[-1]
    print(
        f"page {page} got={len(items)} new={new} range={first.get('time')} .. {last.get('time')} "
        f"end_in={end_time}"
    )
    # 下一页：用最早一条时间戳再往前
    # stamp ms from time
    t0 = first["time"]
    dt = datetime.strptime(t0, "%Y-%m-%d %H:%M:%S").replace(tzinfo=TZ)
    next_end = int(dt.timestamp() * 1000) - 1
    if next_end == end_time:
        break
    end_time = next_end
    # 若已经早于最早交易日开盘则停
    if trade_days:
        earliest = datetime.strptime(trade_days[0] + " 09:00:00", "%Y%m%d %H:%M:%S").replace(tzinfo=TZ)
        if dt < earliest:
            print("reached before earliest day")
            break

print("total unique", len(all_items))
if all_items:
    all_items.sort(key=lambda r: (r["time"], r.get("seq") or 0))
    print("overall", all_items[0]["time"], "..", all_items[-1]["time"])
    # 按日统计
    by_day = {}
    for it in all_items:
        by_day.setdefault(it["time"][:10], 0)
        by_day[it["time"][:10]] += 1
    print("by_day", by_day)
