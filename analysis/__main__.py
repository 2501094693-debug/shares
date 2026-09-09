"""命令行运行阴跌→横盘→涨停筛选。

    python -m analysis
    python -m analysis --days 15 --top 20
    python -m analysis --json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from analysis.config import DEFAULT_LOOKBACK_DAYS
from analysis.screen import screen_yindie


def _print_table(items: list[dict]) -> None:
    if not items:
        print("无结果")
        return

    print(
        f"{'代码':<8} {'名称':<10} {'涨停日':<12} {'总分':>6} "
        f"{'阴跌天':>6} {'横盘天':>6} {'阴跌%':>8} {'横盘幅%':>8} {'板':>3}"
    )
    for row in items:
        detected = row.get("detected") or {}
        dec = detected.get("decline") or {}
        cons = detected.get("consolidation") or {}
        scores = row.get("scores") or {}
        dec_pct = dec.get("total_pct")
        cons_rng = cons.get("range_pct")
        dec_text = f"{dec_pct:.1f}" if isinstance(dec_pct, (int, float)) else ""
        cons_text = f"{cons_rng:.1f}" if isinstance(cons_rng, (int, float)) else ""
        name = str(row.get("name") or "")[:10]
        print(
            f"{row.get('code', ''):<8} {name:<10} {row.get('limit_up_date', ''):<12} "
            f"{scores.get('total', 0):>6.1f} "
            f"{dec.get('days', 0):>6} {cons.get('days', 0):>6} "
            f"{dec_text:>8} {cons_text:>8} {row.get('board_count') or 0:>3}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="阴跌→横盘→涨停形态筛选（软评分）")
    parser.add_argument("--days", type=int, default=DEFAULT_LOOKBACK_DAYS, help="近期涨停窗口（交易日）")
    parser.add_argument("--top", type=int, default=30, help="输出前 N 名，0=全部")
    parser.add_argument("--workers", type=int, default=8, help="并发分析线程数")
    parser.add_argument("--refresh", action="store_true", help="强制刷新涨跌停池缓存")
    parser.add_argument("--json", action="store_true", help="JSON 输出")
    args = parser.parse_args()

    top = None if args.top <= 0 else args.top
    data = screen_yindie(
        days=args.days,
        force=args.refresh,
        workers=args.workers,
        top=top,
    )

    if args.json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return

    print(
        f"updated={data.get('updated_at')}  lookback={data.get('lookback_days')}d  "
        f"candidates={data.get('candidate_count')}  results={data.get('result_count')}"
    )
    print(data.get("note") or "")
    print()
    _print_table(list(data.get("items") or []))
    errors = data.get("errors") or []
    if errors:
        print()
        print("errors:", "; ".join(errors))


if __name__ == "__main__":
    main()
