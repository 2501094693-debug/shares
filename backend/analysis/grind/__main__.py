"""命令行运行阴跌 / 横盘筛选。

    python -m analysis.grind
    python -m analysis.grind --days 60 --top 40
    python -m analysis.grind --kind decline
    python -m analysis.grind --code 000636
    python -m analysis.grind --json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[2]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from analysis.grind.config import DEFAULT_LOOKBACK_DAYS
from analysis.grind.screen import screen_grind


def _print_table(items: list[dict]) -> None:
    if not items:
        print("  无结果")
        return

    print(
        f"  {'#':>3} {'代码':<8} {'名称':<10} {'形态':<8} {'总分':>6} "
        f"{'阴跌':>6} {'横盘':>6} {'阴跌天':>6} {'横盘天':>6} {'窗口%':>8}"
    )
    for row in items:
        detected = row.get("detected") or {}
        dec = detected.get("decline") or {}
        cons = detected.get("consolidation") or {}
        window = detected.get("window") or {}
        scores = row.get("scores") or {}
        win_pct = window.get("total_pct")
        win_text = f"{win_pct:.1f}" if isinstance(win_pct, (int, float)) else ""
        name = str(row.get("name") or "")[:10]
        rank = row.get("rank") or ""
        print(
            f"  {rank:>3} {row.get('code', ''):<8} {name:<10} "
            f"{str(row.get('kind_label') or ''):<8} "
            f"{scores.get('total', 0):>6.1f} "
            f"{scores.get('decline', 0):>6.1f} "
            f"{scores.get('consolidation', 0):>6.1f} "
            f"{dec.get('days', 0):>6} {cons.get('days', 0):>6} "
            f"{win_text:>8}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="阴跌 / 横盘软评分筛选")
    parser.add_argument("--days", type=int, default=DEFAULT_LOOKBACK_DAYS, help="回看窗口（交易日）")
    parser.add_argument("--top", type=int, default=40, help="前 N 名，0=全部")
    parser.add_argument(
        "--kind",
        choices=("all", "decline", "consolidation"),
        default="all",
        help="形态过滤",
    )
    parser.add_argument("--code", default="", help="只分析一只股票")
    parser.add_argument("--workers", type=int, default=8, help="并发分析线程数")
    parser.add_argument("--json", action="store_true", help="JSON 输出")
    args = parser.parse_args()

    top = None if args.top <= 0 else args.top
    data = screen_grind(
        days=args.days,
        code=args.code.strip(),
        workers=args.workers,
        top=top,
        kind=args.kind,
    )

    if args.json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return

    print(
        f"as_of={data.get('updated_at')}  lookback={data.get('lookback_days')}d  "
        f"candidates={data.get('candidate_count')}  analyzed={data.get('analyzed_count')}  "
        f"results={data.get('result_count')}"
    )
    print(data.get("note") or "")
    print()
    _print_table(list(data.get("items") or []))
    errors = data.get("errors") or []
    if errors:
        print()
        print("errors:", "; ".join(errors[:12]))


if __name__ == "__main__":
    main()
