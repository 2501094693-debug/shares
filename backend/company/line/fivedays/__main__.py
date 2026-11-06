"""python -m company.line.fivedays 600519
python -m company.line.fivedays 600519 --days 5 --limit 3
python -m company.line.fivedays 600519 --day 2026-11-05
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[3]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from company.line.fivedays.ths import fetch_day, fetch_fivedays


def main() -> int:
    parser = argparse.ArgumentParser(description="同花顺五日分时成交（秒级）")
    parser.add_argument("code", help="股票代码，如 600519")
    parser.add_argument("--days", type=int, default=5, help="交易日数，默认 5")
    parser.add_argument("--day", default="", help="只拉单日，如 2026-11-05")
    parser.add_argument("--limit", type=int, default=5, help="预览每段首尾条数，0=全量打印")
    parser.add_argument("--no-thsdk", action="store_true", help="跳过 thsdk，只用 quota-h")
    parser.add_argument("--no-trends", action="store_true", help="不附带分钟分时")
    parser.add_argument("--raw", action="store_true", help="打印完整 JSON")
    args = parser.parse_args()

    prefer = not args.no_thsdk
    include_trends = not args.no_trends
    if args.day:
        pack = fetch_day(
            args.code,
            args.day,
            prefer_thsdk=prefer,
            include_trends=include_trends,
        )
    else:
        pack = fetch_fivedays(
            args.code,
            days=args.days,
            prefer_thsdk=prefer,
            include_trends=include_trends,
        )

    if args.raw or args.limit == 0:
        print(json.dumps(pack, ensure_ascii=False, indent=2))
        return 0 if pack.get("count") or pack.get("items") else 1

    summary = {
        "code": pack.get("code"),
        "days": pack.get("days") or [pack.get("day")],
        "source": pack.get("source"),
        "methods": pack.get("methods"),
        "count": pack.get("count"),
        "partial": pack.get("partial"),
        "first": pack.get("first"),
        "last": pack.get("last"),
        "trend_count": pack.get("trend_count"),
    }
    if "by_day" in pack:
        summary["by_day"] = {
            day: {
                "source": info.get("source"),
                "partial": info.get("partial"),
                "count": info.get("count"),
                "first": info.get("first"),
                "last": info.get("last"),
                "trend_count": info.get("trend_count"),
                "error": info.get("error") or None,
            }
            for day, info in (pack.get("by_day") or {}).items()
        }
    else:
        summary["day"] = pack.get("day")
        summary["error"] = pack.get("error") or None

    items = list(pack.get("items") or [])
    n = max(0, int(args.limit))
    if n and items:
        head = items[:n]
        tail = items[-n:] if len(items) > n else []
        summary["preview_head"] = head
        if tail and (not head or tail[0] != head[0]):
            summary["preview_tail"] = tail
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if items else 1


if __name__ == "__main__":
    raise SystemExit(main())
