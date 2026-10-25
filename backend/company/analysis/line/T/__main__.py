"""CLI：聪明投机者期末持仓。

示例::

    python -m company.analysis.line.T 600519 --beg 2024-01-02
    python -m company.analysis.line.T 600519 --beg 20240102 --end 20241231
    python -m company.analysis.line.T 600519 --beg 2024-01-02 --history --json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[4]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from company.analysis.line.T.service import analyze_trader


def _fmt_shares(v: float | None) -> str:
    if v is None:
        return "—"
    if abs(v) >= 1e8:
        return f"{v / 1e8:.4f} 亿股"
    if abs(v) >= 1e4:
        return f"{v / 1e4:.4f} 万股"
    return f"{v:.4f} 股"


def _print_text(pack: dict) -> None:
    print(
        f"{pack.get('code')} {pack.get('name') or ''}  "
        f"[{pack.get('beg')} → {pack.get('end')}]  "
        f"共 {pack.get('count')} 个交易日  "
        f"（{'前复权' if pack.get('adjust') == 'qfq' else pack.get('adjust')}）"
        f"  ratio={pack.get('ratio')}"
    )
    print(f"  期末股数: {_fmt_shares(pack.get('shares'))}")
    avg = pack.get("avg_price")
    print(f"  加权均价: {avg:.6f}" if avg is not None else "  加权均价: —")
    net_avg = pack.get("net_avg_price")
    print(
        f"  净成本: {net_avg:.6f}（净投入 {pack.get('net_cost')}）"
        if net_avg is not None
        else "  净成本: —"
    )
    pnl = pack.get("pnl")
    if pnl is not None:
        print(
            f"  盈亏: {pnl:+.2f}"
            f"  （已实现 {pack.get('realized_pnl')} / "
            f"浮动 {pack.get('unrealized_pnl')} · 期末收盘 {pack.get('close')}）"
        )
    else:
        print("  盈亏: —")
    print(
        f"  累计买入 {_fmt_shares(pack.get('bought'))}  "
        f"累计卖出 {_fmt_shares(pack.get('sold'))}  "
        f"卖出回笼 {pack.get('sell_proceeds')}"
    )


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="聪明投机者：首日低买，其后每日高卖低买")
    p.add_argument("code", nargs="?", help="股票代码，如 600519")
    p.add_argument("--beg", default="", help="起始日期 YYYY-MM-DD 或 YYYYMMDD")
    p.add_argument("--end", default="", help="结束日期，默认今天")
    p.add_argument(
        "--ratio",
        type=float,
        default=0.01,
        help="每日买卖量占当日成交量比例，默认 0.01",
    )
    p.add_argument("--adjust", default="qfq", help="qfq/hfq/none，默认前复权")
    p.add_argument("--history", action="store_true", help="附带每日明细")
    p.add_argument("--json", action="store_true", help="输出完整 JSON")
    args = p.parse_args(argv)

    if not args.code or not args.beg:
        p.error("须提供 code 与 --beg")

    try:
        pack = analyze_trader(
            args.code,
            args.beg,
            args.end,
            ratio=args.ratio,
            adjust=args.adjust,
            return_history=args.history,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(pack, ensure_ascii=False, indent=2))
    else:
        _print_text(pack)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
