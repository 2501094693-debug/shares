"""探针2：历史 trade_date、trace 时间窗、网页端五日接口。"""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from company.detail.ths_mobile import (  # noqa: E402
    BASE,
    TRACE_URL,
    TREND_URL,
    _code_list,
    _post,
)
from market.steep.calendar import recent_trade_dates  # noqa: E402

TZ = timezone(timedelta(hours=8))
CODE = "600519"
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)


def main() -> None:
    norm, market, codes = _code_list(CODE)
    referer = f"https://stockpage.10jqka.com.cn/{norm}/stock-quote/"
    days = recent_trade_dates(5)
    print("trade days", days)

    print("\n=== single_trend by trade_date (YYYYMMDD int) ===")
    for day in days:
        ymd = int(day.replace("-", "") if "-" in day else day)
        payload = {
            "code_list": codes,
            "trade_class": "intraday",
            "trade_date": ymd,
            "gpid": 1,
            "time_zone": "Asia/Shanghai",
        }
        body = _post(TREND_URL, payload, referer=referer)
        qd = (body.get("data") or {}).get("quote_data") or []
        n = len((qd[0].get("value") if qd else []) or [])
        fail = bool((body.get("data") or {}).get("fail_params"))
        span = ""
        if n:
            vals = qd[0]["value"]
            t0 = datetime.fromtimestamp(vals[0][0] / 1000, TZ)
            t1 = datetime.fromtimestamp(vals[-1][0] / 1000, TZ)
            span = f" {t0.isoformat()} -> {t1.isoformat()}"
            # check second resolution
            diffs = [vals[i + 1][0] - vals[i][0] for i in range(min(20, n - 1))]
            span += f" diffs={sorted(set(diffs))[:5]}"
        print(f"  day={ymd} n={n} fail={fail}{span}")

    print("\n=== single_trace time_range variants ===")
    # try begin_end over one historical day
    day = days[1] if len(days) > 1 else days[0]
    ymd = day if "-" in day else f"{day[:4]}-{day[4:6]}-{day[6:8]}"
    begin = datetime.fromisoformat(f"{ymd}T09:15:00").replace(tzinfo=TZ)
    end = datetime.fromisoformat(f"{ymd}T15:05:00").replace(tzinfo=TZ)
    for tr in [
        {"type": "end_count", "count": 500, "end_time": 0},
        {
            "type": "begin_end",
            "begin_time": int(begin.timestamp() * 1000),
            "end_time": int(end.timestamp() * 1000),
        },
        {
            "type": "begin_count",
            "begin_time": int(begin.timestamp() * 1000),
            "count": 500,
        },
        {
            "type": "end_count",
            "count": 500,
            "end_time": int(end.timestamp() * 1000),
        },
    ]:
        payload = {"code_list": codes, "time_range": tr, "gpid": 1}
        try:
            body = _post(TRACE_URL, payload, referer=referer, timeout=20)
            qd = (body.get("data") or {}).get("quote_data") or []
            n = 0
            span = ""
            fields = None
            if qd:
                q = qd[0]
                fields = q.get("data_fields")
                vals = q.get("value") or []
                n = len(vals)
                if n and fields:
                    fi = list(fields).index("1") if "1" in list(map(str, fields)) else 0
                    t0 = datetime.fromtimestamp(float(vals[0][fi]) / 1000, TZ)
                    t1 = datetime.fromtimestamp(float(vals[-1][fi]) / 1000, TZ)
                    span = f" {t0} -> {t1}"
            fail = (body.get("data") or {}).get("fail_params")
            print(f"  tr={tr} n={n} fields={fields} fail={bool(fail)}{span}")
            if n == 0:
                print("   body", json.dumps(body, ensure_ascii=False)[:400])
        except Exception as exc:  # noqa: BLE001
            print(f"  tr={tr} ERR {exc}")

    print("\n=== classic web 5-day / minute APIs ===")
    session = requests.Session()
    session.trust_env = False
    session.headers.update({"User-Agent": UA, "Referer": "https://stockpage.10jqka.com.cn/"})
    urls = [
        f"https://d.10jqka.com.cn/v6/line/hs_{norm}/01/last.js",
        f"https://d.10jqka.com.cn/v6/line/hs_{norm}/30/last.js",
        f"https://d.10jqka.com.cn/v6/time/hs_{norm}/last.js",
        f"https://d.10jqka.com.cn/v6/time/hs_{norm}/last.js?2024",
        f"https://d.10jqka.com.cn/v8/line/hs_{norm}/01/last.js",
        f"https://d.10jqka.com.cn/v2/line/hs_{norm}/01/last.js",
        f"https://d.10jqka.com.cn/v6/time/hs_{CODE}/last.js",
        f"http://d.10jqka.com.cn/v6/time/hs_{norm}/last.js",
        f"https://stockpage.10jqka.com.cn/{norm}/",
    ]
    for url in urls:
        try:
            resp = session.get(url, timeout=12)
            text = resp.text[:300].replace("\n", " ")
            print(f"  {resp.status_code} {url}")
            print(f"    {text}")
        except Exception as exc:  # noqa: BLE001
            print(f"  ERR {url}: {exc}")

    # try quote.10jqka mobile API patterns
    print("\n=== quote / m API guesses ===")
    guesses = [
        f"https://d.10jqka.com.cn/v6/time/hs_{norm}/5.js",
        f"https://d.10jqka.com.cn/v6/time/hs_{norm}/last5.js",
        f"https://d.10jqka.com.cn/v6/time/hs_{norm}/five.js",
        f"https://d.10jqka.com.cn/v6/time/hs_{norm}/5day.js",
        f"https://d.10jqka.com.cn/v6/time/hs_{norm}/l5day.js",
        f"https://d.10jqka.com.cn/v8/time/hs_{norm}/last.js",
        f"https://d.10jqka.com.cn/v6/deal/hs_{norm}/last.js",
        f"https://d.10jqka.com.cn/v6/dealinfo/hs_{norm}/last.js",
    ]
    for url in guesses:
        try:
            resp = session.get(url, timeout=10)
            print(f"  {resp.status_code} len={len(resp.content)} {url} :: {resp.text[:180]!r}")
        except Exception as exc:  # noqa: BLE001
            print(f"  ERR {url}: {exc}")


if __name__ == "__main__":
    main()
