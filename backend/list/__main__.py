"""命令行查龙虎榜。

    python -m list
    python -m list --date 2026-08-28
    python -m list --code 000001
    python -m list --json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from list.service import service


def _fmt_yi(value: object) -> str:
    if not isinstance(value, (int, float)):
        return ""
    abs_n = abs(value)
    sign = "-" if value < 0 else ""
    if abs_n >= 1e8:
        return f"{sign}{abs_n / 1e8:.2f}亿"
    if abs_n >= 1e4:
        return f"{sign}{abs_n / 1e4:.1f}万"
    return f"{sign}{abs_n:.0f}"


def _fmt_pct(value: object) -> str:
    if not isinstance(value, (int, float)):
        return ""
    return f"{value:+.2f}%"


def _print_seats(title: str, rows: list[dict]) -> None:
    print(f"      {title}")
    if not rows:
        print("        无")
        return
    for row in rows:
        print(
            f"        {row.get('rank', ''):>2}  {str(row.get('dept_type') or ''):<4}  "
            f"{_fmt_yi(row.get('buy')):>10} / {_fmt_yi(row.get('sell')):>10}  "
            f"{row.get('dept') or ''}"
        )


def _print_stock(row: dict) -> None:
    chg = _fmt_pct(row.get("change_pct"))
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
        f"  {row.get('date', ''):<10}  {row.get('code', ''):<8}  "
        f"{str(row.get('name') or '')[:10]:<10}  {chg:>8}  "
        f"净买 {_fmt_yi(row.get('net_amt')):<10}  {sw}"
    )
    for listing in row.get("listings") or []:
        print(f"    · {listing.get('reason') or ''}  {listing.get('explain') or ''}")
        _print_seats("买", list(listing.get("buyers") or []))
        _print_seats("卖", list(listing.get("sellers") or []))


def main() -> None:
    parser = argparse.ArgumentParser(description="东财龙虎榜")
    parser.add_argument("--date", default="", help="交易日，默认最近有数据的一天")
    parser.add_argument("--code", default="", help="股票代码，查历史上榜")
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    if args.code.strip():
        data = service.stock(args.code, force=args.refresh)
    else:
        data = service.daily(date=args.date, force=args.refresh)

    if args.json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return

    if args.code.strip():
        print(
            f"{data.get('code')} {data.get('name') or ''}  "
            f"上榜 {data.get('count')} 次  updated={data.get('updated_at')}"
        )
        for row in data.get("items") or []:
            print()
            _print_stock(row)
    else:
        print(
            f"date={data.get('date')}  上榜 {data.get('count')}  "
            f"updated={data.get('updated_at')}"
        )
        for row in data.get("items") or []:
            print()
            _print_stock(row)

    errors = data.get("errors") or []
    if errors:
        print()
        print("errors:", "; ".join(errors))


if __name__ == "__main__":
    main()
