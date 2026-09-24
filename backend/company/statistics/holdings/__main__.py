"""持股信息：前十大股东、股东户数、基金持股。

    python -m company.statistics.holdings 600519
    python -m company.statistics.holdings 600519 --date 2025-12-31
    python -m company.statistics.holdings 000001 --scope free --json
    python -m company.statistics.holdings 600519 --holder-num
    python -m company.statistics.holdings 600519 --holder-num --limit 8 --json
    python -m company.statistics.holdings 600519 --fund
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[3]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from company.statistics.holdings.fund_holders import fetch_fund_holders
from company.statistics.holdings.holder_num import fetch_holder_num
from company.statistics.holdings.holders import fetch_top_holders


def _print_holders(data: dict) -> None:
    title = f"{data.get('code') or ''} {data.get('name') or ''}".strip()
    print(
        f"{title}  {data.get('label') or '十大股东'}  "
        f"报告期 {data.get('report_date') or ''}  "
        f"{data.get('count') or 0} 人"
    )
    if data.get("total_shares_fmt"):
        print(f"总股本 {data['total_shares_fmt']}")
    dates = data.get("report_dates") or []
    if len(dates) > 1:
        print("近几期 " + " / ".join(str(day) for day in dates[:8]))
    print()
    print(
        f"{'排名':<4}{'股东':<36}{'持股':>10}{'占总股本':>10}"
        f"{'变动':>12}{'类型':>10}{'市值':>12}"
    )
    print("-" * 98)
    for item in data.get("items") or []:
        rank = item.get("rank") or ""
        name = str(item.get("name") or "")
        if len(name) > 34:
            name = name[:33] + "…"
        print(
            f"{rank:<4}{name:<36}{str(item.get('shares_fmt') or ''):>10}"
            f"{str(item.get('ratio_fmt') or ''):>10}"
            f"{str(item.get('change_fmt') or ''):>12}"
            f"{str(item.get('shares_type') or item.get('holder_type') or ''):>10}"
            f"{str(item.get('market_value_fmt') or ''):>12}"
        )


def _print_holder_num(data: dict) -> None:
    title = f"{data.get('code') or ''} {data.get('name') or ''}".strip()
    print(f"{title}  {data.get('label') or '股东户数'}  {data.get('count') or 0} 期")
    latest = data.get("latest") or {}
    if latest:
        print(
            f"最新 {latest.get('time') or ''}  "
            f"户数 {latest.get('holder_num_fmt') or latest.get('holder_num') or ''}  "
            f"变动 {latest.get('change_fmt') or ''} "
            f"({latest.get('change_ratio_fmt') or ''})  "
            f"户均 {latest.get('avg_hold_num_fmt') or ''}"
        )
    print()
    print(
        f"{'报告期':<12}{'股东户数':>12}{'变动':>12}{'环比':>10}{'户均持股':>12}"
    )
    print("-" * 60)
    for item in data.get("items") or []:
        print(
            f"{str(item.get('time') or ''):<12}"
            f"{str(item.get('holder_num_fmt') or item.get('holder_num') or ''):>12}"
            f"{str(item.get('change_fmt') or ''):>12}"
            f"{str(item.get('change_ratio_fmt') or ''):>10}"
            f"{str(item.get('avg_hold_num_fmt') or ''):>12}"
        )


def _print_fund_holders(data: dict) -> None:
    title = f"{data.get('code') or ''}".strip()
    print(
        f"{title}  基金持股  报告期 {data.get('report_date') or ''}  "
        f"{data.get('count') or 0} 只"
    )
    print()
    print(
        f"{'#':<4}{'代码':<10}{'基金':<36}{'占净值':>10}"
        f"{'占流通':>10}{'市值':>12}"
    )
    print("-" * 86)
    for idx, item in enumerate(data.get("items") or [], start=1):
        name = str(item.get("name") or "")
        if len(name) > 34:
            name = name[:33] + "…"
        print(
            f"{idx:<4}{str(item.get('code') or ''):<10}{name:<36}"
            f"{str(item.get('weight') or ''):>10}"
            f"{str(item.get('free_float_ratio') or ''):>10}"
            f"{str(item.get('market_value') or ''):>12}"
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

    parser = argparse.ArgumentParser(description="持股信息：十大股东 / 股东户数 / 基金持股")
    parser.add_argument("code", help="股票代码，如 600519")
    parser.add_argument("--date", default="", help="报告期 YYYY-MM-DD，默认最新")
    parser.add_argument(
        "--scope",
        default="holders",
        choices=("holders", "free"),
        help="holders 十大股东 | free 十大流通股东",
    )
    parser.add_argument(
        "--holder-num",
        action="store_true",
        help="查股东户数走势（报告期序列）",
    )
    parser.add_argument(
        "--fund",
        action="store_true",
        help="查基金持股明细",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=80,
        help="股东户数最近报告期数量（仅 --holder-num）",
    )
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    try:
        if args.holder_num:
            data = fetch_holder_num(
                args.code,
                limit=args.limit,
                force=args.refresh,
            )
        elif args.fund:
            data = fetch_fund_holders(
                args.code,
                report_date=args.date.strip() or None,
                force=args.refresh,
            )
        else:
            data = fetch_top_holders(
                args.code,
                report_date=args.date.strip() or None,
                scope=args.scope,
                force=args.refresh,
            )
    except Exception as exc:  # noqa: BLE001
        print(f"查询失败: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
    elif args.holder_num:
        _print_holder_num(data)
    elif args.fund:
        _print_fund_holders(data)
    else:
        _print_holders(data)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
