"""临时探针：同花顺五日分时接口。跑完可删。"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from company.detail.ths_mobile import (  # noqa: E402
    BASE,
    TRACE_URL,
    TREND_URL,
    _code_list,
    _post,
)

TZ = timezone(timedelta(hours=8))
CODE = "600519"


def main() -> None:
    norm, _market, codes = _code_list(CODE)
    referer = f"https://stockpage.10jqka.com.cn/{norm}/stock-quote/"

    print("=== trade_class variants on single_trend ===")
    for tc in [
        "intraday",
        "five_day",
        "fiveday",
        "5day",
        "day5",
        "trend5",
        "five",
        "multi_day",
        "history",
        "after",
        "pre",
    ]:
        payload = {
            "code_list": codes,
            "trade_class": tc,
            "trade_date": 0,
            "gpid": 1,
            "time_zone": "Asia/Shanghai",
        }
        try:
            body = _post(TREND_URL, payload, referer=referer)
            qd = (body.get("data") or {}).get("quote_data") or []
            n = len((qd[0].get("value") if qd else []) or [])
            fail = bool((body.get("data") or {}).get("fail_params"))
            print(f"  tc={tc!r:12} n={n:5} fail={fail} status={body.get('status_code')}")
            if n and tc == "intraday":
                q = qd[0]
                vals = q.get("value") or []
                print("    keys", sorted(q.keys()))
                print("    fields", q.get("data_fields"))
                print("    first", vals[0], "last", vals[-1])
                t0 = datetime.fromtimestamp(vals[0][0] / 1000, TZ)
                t1 = datetime.fromtimestamp(vals[-1][0] / 1000, TZ)
                print("    span", t0, "->", t1)
        except Exception as exc:  # noqa: BLE001
            print(f"  tc={tc!r} ERR {exc}")

    print("\n=== alternate paths under same BASE ===")
    for path in [
        "single_trend",
        "multi_trend",
        "five_day_trend",
        "trend5day",
        "five_day",
        "single_five_day",
        "history_trend",
        "multi_day_trend",
        "day_trend",
    ]:
        url = f"{BASE}/{path}"
        payload = {
            "code_list": codes,
            "trade_class": "intraday",
            "trade_date": 0,
            "gpid": 1,
            "time_zone": "Asia/Shanghai",
        }
        try:
            body = _post(url, payload, referer=referer)
            qd = (body.get("data") or {}).get("quote_data") or []
            n = len((qd[0].get("value") if qd else []) or [])
            print(
                f"  path={path:20} status={body.get('status_code')} "
                f"n={n} msg={body.get('status_msg')}"
            )
        except Exception as exc:  # noqa: BLE001
            print(f"  path={path:20} ERR {type(exc).__name__}: {exc}")

    print("\n=== single_trend with trade_class five_day + data_fields ===")
    for tc in ["five_day", "5day", "fiveday"]:
        payload = {
            "code_list": codes,
            "trade_class": tc,
            "trade_date": 0,
            "gpid": 1,
            "time_zone": "Asia/Shanghai",
            "data_fields": ["1", "10", "13", "19", "199112", "264648"],
        }
        body = _post(TREND_URL, payload, referer=referer)
        print(tc, json.dumps(body, ensure_ascii=False)[:500])

    print("\n=== single_trace large count (recent ticks) ===")
    payload = {
        "code_list": codes,
        "time_range": {"type": "end_count", "count": 1000, "end_time": 0},
        "gpid": 1,
    }
    body = _post(TRACE_URL, payload, referer=referer)
    qd = (body.get("data") or {}).get("quote_data") or []
    if qd:
        q = qd[0]
        vals = q.get("value") or []
        print("fields", q.get("data_fields"), "n", len(vals))
        if vals:
            # field 1 is usually timestamp ms
            fields = [str(x) for x in (q.get("data_fields") or [])]
            ti = fields.index("1") if "1" in fields else 0
            t0 = datetime.fromtimestamp(float(vals[0][ti]) / 1000, TZ)
            t1 = datetime.fromtimestamp(float(vals[-1][ti]) / 1000, TZ)
            print("span", t0, "->", t1)


if __name__ == "__main__":
    main()
