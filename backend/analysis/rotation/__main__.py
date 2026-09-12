"""命令行：过去每天哪些三级轮到了，还有哪些没涨过。

    python -m analysis.rotation
    python -m analysis.rotation --days 20 --top 20
    python -m analysis.rotation --json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[2]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from analysis.rotation.calendar import apply_top, screen_rotation
from analysis.rotation.config import DEFAULT_LOOKBACK_DAYS


def _fmt_pct(value: object) -> str:
    if not isinstance(value, (int, float)):
        return "—"
    return f"{value:+.1f}%"


def _fmt_yi(value: object) -> str:
    if not isinstance(value, (int, float)):
        return "—"
    n = float(value)
    sign = "+" if n > 0 else ""
    return f"{sign}{n / 1e8:.2f}亿" if abs(n) >= 1e6 else f"{sign}{n:.0f}"


def _print_risen(title: str, rows: list[dict]) -> None:
    print(title)
    if not rows:
        print("  无")
        print()
        return
    print(f"  {'#':>3} {'行业':<14} {'二级':<12} {'得分':>6} {'当日':>8} {'广度':>8} {'强势':>4} {'标签':<8}")
    for i, row in enumerate(rows, 1):
        name = str(row.get("name") or "")[:14]
        l2 = str(row.get("l2_name") or "")[:12]
        sample = row.get("sample_count")
        up = row.get("up_1d")
        breadth = f"{up}/{sample}" if sample is not None else "—"
        zt = row.get("strong_1d")
        if zt is None:
            zt = row.get("limit_up_1d")
        zt_text = "—" if zt is None else str(zt)
        score = row.get("score")
        score_text = "—" if not isinstance(score, (int, float)) else f"{score:.0f}"
        print(
            f"  {i:>3} {name:<14} {l2:<12} "
            f"{score_text:>6} "
            f"{_fmt_pct(row.get('change_1d')):>8} "
            f"{breadth:>8} "
            f"{zt_text:>4} "
            f"{str(row.get('tag') or ''):<8}"
        )
    print()


def _print_untouched(rows: list[dict]) -> None:
    print("待涨（距上次上榜最久）")
    if not rows:
        print("  无")
        print()
        return
    print(
        f"  {'#':>3} {'行业':<14} {'二级':<12} {'距上次':>8} {'上次':>10} {'5日':>8} {'标签':<8}"
    )
    for i, row in enumerate(rows[:40], 1):
        name = str(row.get("name") or "")[:14]
        l2 = str(row.get("l2_name") or "")[:12]
        last = str(row.get("last_date") or "")
        idle = row.get("idle_days")
        idle_text = "从未" if not last else (f"{idle}日" if idle is not None else "—")
        print(
            f"  {i:>3} {name:<14} {l2:<12} "
            f"{idle_text:>8} "
            f"{(last or '—'):>10} "
            f"{_fmt_pct(row.get('change_5d')):>8} "
            f"{str(row.get('tag') or ''):<8}"
        )
    print()


def main() -> None:
    parser = argparse.ArgumentParser(description="申万三级：每天谁轮到了 / 还有谁没涨过")
    parser.add_argument("--days", type=int, default=DEFAULT_LOOKBACK_DAYS, help="回看交易日，20=近一个月 60=近三个月 120=近半年 245=一年 490=两年")
    parser.add_argument("--top", type=int, default=0, help="已忽略，大于60分全部进榜")
    parser.add_argument("--refresh", action="store_true", help="强制重拉当日行情树")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    data = screen_rotation(days=args.days, force=args.refresh)
    top = None if args.top <= 0 else args.top
    if top:
        data = apply_top(data, top)
    if args.json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return

    window = data.get("window") or {}
    print(
        f"as_of={data.get('updated_at')}  window={window.get('start')}~{window.get('end')}  "
        f"universe={data.get('universe_count')}  "
        f"covered={data.get('covered_count')}  untouched={data.get('untouched_count')}"
    )
    print(data.get("note") or "")
    print()
    for day in data.get("days") or []:
        _print_risen(
            f"{day.get('date')}  首次 {day.get('first_count') or 0}  上涨 {day.get('again_count') or 0}  source={day.get('source')}",
            list(day.get("first") or []) + list(day.get("again") or []),
        )
    _print_untouched(list(data.get("untouched") or []))
    errors = data.get("errors") or []
    if errors:
        print("errors:", "; ".join(str(e) for e in errors[:8]))


if __name__ == "__main__":
    main()
