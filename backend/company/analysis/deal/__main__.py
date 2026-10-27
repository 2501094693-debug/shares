"""CLI：分时成交 × 资金动向 → 3 秒窗口约束求解还原逐笔成交。

示例::

    python -m company.analysis.deal 600519
    python -m company.analysis.deal 600519 --show 40
    python -m company.analysis.deal 600519 --view buy --json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[3]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from company.analysis.deal.service import (
    format_window_lines,
    run_deal_window_reconstruct,
)
from company.analysis.deal.window import DEFAULT_TRADE_THRESHOLD


def _print_window_rows(rows: list[dict]) -> None:
    header = (
        f"{'成交时间':<10}{'成交价格':>10}{'成交手数':>10}"
        f"{'买单编号':>10}{'卖单编号':>10}"
    )
    print(header)
    for row in rows:
        print(
            f"{str(row.get('time') or ''):<10}"
            f"{row.get('price'):>10}"
            f"{row.get('lots'):>10}"
            f"{str(row.get('buy_id') or '-'):>10}"
            f"{str(row.get('sell_id') or '-'):>10}"
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="分时成交 × 资金动向 → 逐笔成交还原")
    parser.add_argument("code", nargs="?", default="600519", help="股票代码，如 600519")
    parser.add_argument("--day", default="", help="交易日 YYYY-MM-DD，默认当日")
    parser.add_argument("--show", type=int, default=10, help="预览下方逐笔行数，0 全部")
    parser.add_argument("--json", action="store_true", help="输出完整 JSON")
    parser.add_argument(
        "--threshold",
        type=float,
        default=DEFAULT_TRADE_THRESHOLD,
        help="资金动向收录门槛（元），同时作为单笔成交额上限",
    )
    parser.add_argument(
        "--view",
        default="aggressor",
        choices=["aggressor", "buy", "sell", "both"],
        help="订单视角，aggressor=只取主动方那一行（默认）",
    )
    parser.add_argument(
        "--max-lookback",
        type=int,
        default=0,
        help="订单成交最多回溯多少个窗口，0 不限制",
    )
    parser.add_argument("--refresh", action="store_true", help="忽略磁盘缓存重新拉取")
    args = parser.parse_args(argv)

    try:
        pack = run_deal_window_reconstruct(
            args.code,
            day=args.day,
            force=args.refresh,
            threshold=args.threshold,
            max_lookback=args.max_lookback,
            view=args.view,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(pack, ensure_ascii=False, indent=2))
        return 0

    for line in format_window_lines(pack):
        print(line)
    rows = pack.get("rows") or []
    if not rows:
        print("  (无还原明细)")
        return 0
    print()
    shown = rows if args.show <= 0 else rows[: args.show]
    _print_window_rows(shown)
    if len(shown) < len(rows):
        print(f"  ... 共 {len(rows)} 行，用 --show 0 看全部")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
