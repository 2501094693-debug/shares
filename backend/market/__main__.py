"""命令行看行业行情。

    python -m market tree
    python -m market quotes --level 1
    python -m market flow --level 2 --period 5d
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from market.sw.service import service


def _print_table(rows: list[dict], columns: list[tuple[str, str, int]]) -> None:
    header = "  ".join(title.ljust(width) for _, title, width in columns)
    print(header)
    print("-" * len(header))
    for row in rows:
        cells = []
        for key, _, width in columns:
            value = row.get(key)
            if isinstance(value, float):
                text = f"{value:.2f}"
            else:
                text = "" if value is None else str(value)
            cells.append(text[:width].ljust(width))
        print("  ".join(cells))


def _walk(nodes: list[dict], depth: int = 0) -> list[dict]:
    rows: list[dict] = []
    for node in nodes:
        rows.append({**node, "name": ("  " * depth) + str(node.get("name") or "")})
        rows.extend(_walk(node.get("children") or [], depth + 1))
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description="申万行业行情")
    parser.add_argument("cmd", choices=("tree", "quotes", "flow"))
    parser.add_argument("--level", type=int, default=1, choices=(1, 2, 3))
    parser.add_argument("--period", default="today")
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--limit", type=int, default=40)
    args = parser.parse_args()

    if args.cmd == "quotes":
        data = service.quotes(args.level, force=args.refresh)
        items = list(data.get("items") or [])
        cols = [
            ("name", "行业", 16),
            ("change_pct", "涨跌%", 8),
            ("price", "点位", 10),
            ("up_count", "上涨", 6),
            ("down_count", "下跌", 6),
        ]
    elif args.cmd == "flow":
        data = service.fund_flow(args.level, period=args.period, force=args.refresh)
        items = list(data.get("items") or [])
        cols = [
            ("name", "行业", 16),
            ("main_net", "主力净额", 14),
            ("flow_count", "成分", 6),
            ("leader", "最大流入", 10),
        ]
    else:
        data = service.tree(period=args.period, force=args.refresh)
        items = _walk(list(data.get("tree") or []))
        cols = [
            ("name", "行业", 22),
            ("change_pct", "涨跌%", 8),
            ("main_net", "主力净额", 14),
            ("flow_count", "成分", 6),
        ]

    if args.json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return
    print(
        f"updated={data.get('updated_at')}  count={data.get('count')}  "
        f"period={data.get('period', args.period)}"
    )
    _print_table(items[: args.limit], cols)


if __name__ == "__main__":
    main()
