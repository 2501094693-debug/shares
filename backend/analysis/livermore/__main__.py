"""命令行运行利弗莫尔规则引擎。

    python -m analysis.livermore 000338
    python -m analysis.livermore --code 000338 --json
    python -m analysis.livermore --top 30
    python -m analysis.livermore --kind probe
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[2]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from analysis.livermore.config import ACTIONS, DEFAULT_LOOKBACK_DAYS
from analysis.livermore.engine import analyze_stock
from analysis.livermore.screen import screen_livermore


def _print_stock(row: dict) -> None:
    key = row.get("key") or {}
    rs = row.get("rs") or {}
    gate = row.get("gate") or {}
    print(
        f"{row.get('code')} {row.get('name') or ''}  "
        f"{row.get('action_label') or row.get('action')}  "
        f"{key.get('column_label') or ''}  "
        f"RS#{rs.get('rank') or '—'}  "
        f"大盘{gate.get('column_label') or gate.get('column') or ''}"
    )
    reasons = row.get("reason") or []
    if reasons:
        print("  reason:", ", ".join(str(x) for x in reasons))
    pivots = row.get("pivotal") or []
    if pivots:
        bits = [
            f"{p.get('kind')} {p.get('price')} {p.get('status')}"
            for p in pivots[:4]
        ]
        print("  pivot:", "; ".join(bits))
    if row.get("stop") is not None:
        print(f"  stop={row.get('stop')}  invalidation={row.get('invalidation')}")
    if row.get("error"):
        print("  error:", row["error"])


def _print_table(items: list[dict]) -> None:
    if not items:
        print("  无结果")
        return
    print(
        f"  {'#':>3} {'代码':<8} {'名称':<10} {'动作':<6} {'六栏':<10} "
        f"{'RS':>4} {'20日%':>8}"
    )
    for row in items:
        name = str(row.get("name") or "")[:10]
        chg = row.get("change_20d")
        chg_text = f"{chg:.1f}" if isinstance(chg, (int, float)) else ""
        rs = (row.get("rs") or {}).get("rank")
        print(
            f"  {row.get('rank') or '':>3} {row.get('code', ''):<8} {name:<10} "
            f"{str(row.get('action_label') or row.get('action') or ''):<6} "
            f"{str(row.get('column_label') or ''):<10} "
            f"{rs if rs is not None else '—':>4} {chg_text:>8}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="利弗莫尔趋势规则引擎")
    parser.add_argument("code", nargs="?", default="", help="股票代码，给出则只诊断这一只")
    parser.add_argument("--code", dest="code_opt", default="", help="股票代码")
    parser.add_argument("--days", type=int, default=DEFAULT_LOOKBACK_DAYS)
    parser.add_argument("--top", type=int, default=40, help="前 N 名，0=全部")
    parser.add_argument("--kind", choices=("all",) + ACTIONS, default="all")
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    code = (args.code_opt or args.code or "").strip()

    if code and args.kind == "all" and args.top == 40:
        data = analyze_stock(code)
        if args.json:
            print(json.dumps(data, ensure_ascii=False, indent=2))
            return
        _print_stock(data)
        return

    top = None if args.top <= 0 else args.top
    data = screen_livermore(
        days=args.days,
        code=code,
        workers=args.workers,
        top=top,
        kind=args.kind,
    )
    if args.json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return
    print(
        f"as_of={data.get('updated_at')}  analyzed={data.get('analyzed_count')}  "
        f"results={data.get('result_count')}  gate={((data.get('gate') or {}).get('column_label'))}"
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
