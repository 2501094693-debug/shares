"""命令行看个股涨跌榜。

    python -m market.shares
    python -m market.shares --limit 50
    python -m market.shares --json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[2]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from market.shares.service import service


def _print_table(rows: list[dict], limit: int) -> None:
    print(f"    {'#':>4}  {'代码':<8} {'名称':<10} {'涨跌%':>8} {'现价':>8}  一级 / 三级")
    for row in rows[:limit]:
        chg = row.get("change_pct")
        px = row.get("price")
        chg_text = f"{chg:.2f}" if isinstance(chg, (int, float)) else ""
        px_text = f"{px:.2f}" if isinstance(px, (int, float)) else ""
        name = str(row.get("name") or "")[:10]
        sw = " / ".join(
            part
            for part in (str(row.get("l1_name") or ""), str(row.get("l3_name") or ""))
            if part
        )
        print(
            f"    {row.get('rank', ''):>4}  {row.get('code', ''):<8} {name:<10} "
            f"{chg_text:>8} {px_text:>8}  {sw}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="申万成分股涨跌榜")
    parser.add_argument("--limit", type=int, default=40)
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    data = service.list(force=args.refresh)
    if args.json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return

    print(
        f"updated={data.get('updated_at')}  count={data.get('count')}  "
        f"涨={data.get('up')}  跌={data.get('down')}"
    )
    _print_table(list(data.get("items") or []), args.limit)
    errors = data.get("errors") or []
    if errors:
        print()
        print("errors:", "; ".join(errors))


if __name__ == "__main__":
    main()
