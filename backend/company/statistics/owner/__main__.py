"""命令行查前十大股东。

    python -m company.statistics.owner 600519
    python -m company.statistics.owner 600519 --date 2025-12-31
    python -m company.statistics.owner 000001 --scope free --json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[3]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from company.statistics.owner.holders import fetch_top_holders


def _print_table(data: dict) -> None:
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


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass
    try:
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass

    parser = argparse.ArgumentParser(description="东财前十大股东")
    parser.add_argument("code", help="股票代码，如 600519")
    parser.add_argument("--date", default="", help="报告期 YYYY-MM-DD，默认最新")
    parser.add_argument(
        "--scope",
        default="holders",
        choices=("holders", "free"),
        help="holders 十大股东 | free 十大流通股东",
    )
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    try:
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
    else:
        _print_table(data)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
