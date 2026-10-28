"""``python -m company.detail``：同花顺手机端成交明细探针。"""

from __future__ import annotations

import argparse
import json

from company.detail.ths_mobile import fetch_snapshot, fetch_trace, fetch_trend


def main() -> int:
    parser = argparse.ArgumentParser(description="同花顺手机端行情通道探针")
    parser.add_argument("code", help="股票代码，如 600519")
    parser.add_argument("--count", type=int, default=20, help="最近 N 条成交明细")
    parser.add_argument("--end-time", default="0", help="0=最新；或 ISO 时间 / 毫秒时间戳")
    parser.add_argument("--raw", action="store_true", help="打印原始 JSON")
    parser.add_argument(
        "--mode",
        choices=("trace", "snapshot", "trend"),
        default="trace",
        help="trace=成交明细，snapshot=实时快照，trend=分时",
    )
    args = parser.parse_args()

    if args.mode == "snapshot":
        data = fetch_snapshot(args.code, raw=args.raw)
    elif args.mode == "trend":
        data = fetch_trend(args.code, raw=args.raw)
    else:
        data = fetch_trace(args.code, count=args.count, end_time=args.end_time, raw=args.raw)
    print(json.dumps(data, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
