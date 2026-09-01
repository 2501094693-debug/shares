"""命令行看最近几天涨停 / 跌停。

    python -m market.steep
    python -m market.steep --days 8
    python -m market.steep --json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[2]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from market.steep.service import DEFAULT_DAYS, service


def _print_stocks(rows: list[dict], kind: str) -> None:
    if not rows:
        print(f"  {kind}  无")
        return
    print(f"  {kind}  {len(rows)}")
    print(f"    {'代码':<8} {'名称':<10} {'涨跌%':>8} {'板':>4}  一级 / 二级 / 三级")
    for row in rows:
        chg = row.get("change_pct")
        chg_text = f"{chg:.2f}" if isinstance(chg, (int, float)) else ""
        board = row.get("board_count")
        if board is None:
            board = row.get("down_days") or 0
        name = str(row.get("name") or "")[:10]
        sw = " / ".join(
            part
            for part in (
                str(row.get("l1_name") or ""),
                str(row.get("l2_name") or ""),
                str(row.get("l3_name") or ""),
            )
            if part
        )
        print(
            f"    {row.get('code', ''):<8} {name:<10} {chg_text:>8} {board:>4}  {sw}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="最近几天涨停 / 跌停")
    parser.add_argument("--days", type=int, default=DEFAULT_DAYS)
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    data = service.recent(days=args.days, force=args.refresh)
    if args.json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return

    print(
        f"updated={data.get('updated_at')}  days={data.get('count')}  "
        f"涨停合计={data.get('limit_up_total')}  跌停合计={data.get('limit_down_total')}"
    )
    for day in data.get("items") or []:
        print()
        print(
            f"==== {day.get('date')}  涨停 {day.get('limit_up_count')}  "
            f"跌停 {day.get('limit_down_count')} ===="
        )
        _print_stocks(list(day.get("limit_up") or []), "涨停")
        _print_stocks(list(day.get("limit_down") or []), "跌停")
    errors = data.get("errors") or []
    if errors:
        print()
        print("errors:", "; ".join(errors))


if __name__ == "__main__":
    main()
