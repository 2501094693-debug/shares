"""CLI：最新收盘价 / 最低价的最近最低回溯。

示例::

    python -m company.analysis.line.local_extrema 600519
    python -m company.analysis.line.local_extrema 600519 --end 2026-11-10
    python -m company.analysis.line.local_extrema 600519 --json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[4]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from company.analysis.line.local_extrema.recent_low import analyze_recent_low


def _print_text(pack: dict) -> None:
    print(
        f"{pack.get('code')} {pack.get('name') or ''}  "
        f"最新交易日 {pack.get('date')}  "
        f"（{'前复权' if pack.get('adjust') == 'qfq' else pack.get('adjust')}）  "
        f"历史 {pack.get('history_count')} 日"
    )
    lookback = pack.get("lookback") or {}
    for key in ("close", "low"):
        row = lookback.get(key) or {}
        days = row.get("days")
        price = row.get("price")
        since = row.get("since") or "—"
        prior = row.get("prior_lower_date")
        prior_txt = (
            f"更低日 {prior} @ {row.get('prior_lower_price')}"
            if prior
            else "上市以来最低"
        )
        print(
            f"  {row.get('label') or key}: {price}  "
            f"最近 {days} 个交易日最低  "
            f"（自 {since}）  {prior_txt}"
        )


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="最新收盘价 / 最低价：各自是最近多少个交易日的最低价"
    )
    p.add_argument("code", nargs="?", help="股票代码，如 600519")
    p.add_argument("--end", default="", help="截止日 YYYY-MM-DD / YYYYMMDD，默认最新")
    p.add_argument("--adjust", default="qfq", help="qfq/hfq/none，默认前复权")
    p.add_argument("--json", action="store_true", help="输出完整 JSON")
    args = p.parse_args(argv)

    if not args.code:
        p.error("须提供 code")

    try:
        pack = analyze_recent_low(args.code, adjust=args.adjust, end=args.end)
    except Exception as exc:  # noqa: BLE001
        print(f"错误: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(pack, ensure_ascii=False, indent=2))
    else:
        _print_text(pack)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
