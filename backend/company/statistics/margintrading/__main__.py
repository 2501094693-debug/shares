"""融资融券：个股两融日序列。

    python -m company.statistics.margintrading 600519
    python -m company.statistics.margintrading 600519 --limit 10 --json
    python -m company.statistics.margintrading 000001 --refresh
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[3]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from company.statistics.margintrading.history import fetch_margin_trading


def _print_rows(data: dict) -> None:
    title = f"{data.get('code') or ''} {data.get('name') or ''}".strip()
    print(f"{title}  {data.get('label') or '融资融券'}  {data.get('count') or 0} 日")
    latest = data.get("latest") or {}
    if latest:
        print(
            f"最新 {latest.get('time') or ''}  "
            f"融资余额 {latest.get('rzye_fmt') or ''}  "
            f"融券余额 {latest.get('rqye_fmt') or ''}  "
            f"融资净买 {latest.get('rzjme_fmt') or ''}  "
            f"融券净卖 {latest.get('rqjmg_fmt') or ''}"
        )
    print()
    print(
        f"{'日期':<12}{'融资余额':>12}{'融券余额':>12}"
        f"{'融资净买':>12}{'融券净卖':>12}"
    )
    print("-" * 60)
    for item in data.get("items") or []:
        print(
            f"{str(item.get('time') or ''):<12}"
            f"{str(item.get('rzye_fmt') or ''):>12}"
            f"{str(item.get('rqye_fmt') or ''):>12}"
            f"{str(item.get('rzjme_fmt') or ''):>12}"
            f"{str(item.get('rqjmg_fmt') or ''):>12}"
        )


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass
    try:
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass

    parser = argparse.ArgumentParser(description="融资融券：个股两融日序列")
    parser.add_argument("code", help="股票代码，如 600519")
    parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help="最近交易日数量（预览默认 10；接口默认 1500）",
    )
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    try:
        # CLI 预览默认少取；--json 且未改 limit 时仍按传参
        data = fetch_margin_trading(
            args.code,
            limit=args.limit,
            force=args.refresh,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"查询失败: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
    else:
        _print_rows(data)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
