"""python -m company.line.tonghuashun 600519 --limit 5
python -m company.line.tonghuashun 600519 --kline --period day --limit 5
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[3]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from company.line.tonghuashun.hq_ticks import fetch_time_and_sales


def main() -> None:
    parser = argparse.ArgumentParser(description="同花顺实时逐笔 / 日K（需实盘登录）")
    parser.add_argument("code", help="股票代码，如 600519")
    parser.add_argument("--limit", type=int, default=5, help="预览条数，0=全部")
    parser.add_argument("--count", type=int, default=0, help="最近 N 笔，0=拉全天")
    parser.add_argument("--day", default="", help="交易日，默认当天，如 2026-10-09")
    parser.add_argument("--start", default="", help="起始 HH:MM，如 09:30")
    parser.add_argument("--end", default="", help="结束 HH:MM，如 09:35")
    parser.add_argument("--kline", action="store_true", help="拉日K")
    parser.add_argument("--period", default="day", help="K线周期")
    args = parser.parse_args()

    if args.kline:
        from company.line.tonghuashun.kline import fetch_line

        pack = fetch_line(args.code, period=args.period, limit=args.limit or 320)
        print(json.dumps(pack, ensure_ascii=False, indent=2))
        return
    method, items = fetch_time_and_sales(
        args.code, day=args.day, start=args.start, end=args.end, count=args.count,
    )
    if args.limit:
        items = items[-args.limit:]
    print(json.dumps({
        "code": args.code, "period": "tick", "source": "tonghuashun",
        "method": method, "count": len(items), "items": items,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
