"""CLI：区间评估（最大 ±band 区间 + 最低价日评分 + 股 / 指 σ 坐标）。

示例::

    python -m company.analysis.line.evaluate 600519
    python -m company.analysis.line.evaluate 600519 --band 0.09 --low-factor low
    python -m company.analysis.line.evaluate 600519 --factor all --index 000300 --json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[4]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from company.analysis.line.undulate.service import FACTORS
from company.analysis.line.evaluate.service import analyze_evaluate


def _fmt_pct(v: float | None) -> str:
    if v is None:
        return "—"
    return f"{v * 100:+.2f}%"


def _fmt_sigma(v: float | None) -> str:
    if v is None:
        return "—"
    return f"{v:+.2f}σ"


def _print_side(title: str, block: dict) -> None:
    print(f"  {title} {block.get('code') or ''} {block.get('name') or ''}")
    if block.get("error"):
        print(f"    获取失败: {block.get('error')}")
        return
    print(f"    开始日 {block.get('beg')}  结束日 {block.get('end')}")
    stats = block.get("stats") or {}
    for f in FACTORS:
        row = stats.get(f) or {}
        print(
            f"    {row.get('label') or f}: "
            f"开始日 {_fmt_pct(row.get('beg_pct'))} → {_fmt_sigma(row.get('beg_sigma'))}"
            f"（z={_fmt_sigma(row.get('beg_z'))}）  "
            f"结束日 {_fmt_pct(row.get('end_pct'))} → {_fmt_sigma(row.get('end_sigma'))}"
            f"（z={_fmt_sigma(row.get('end_z'))}）  "
            f"均值 {_fmt_pct(row.get('mean'))} σ {_fmt_pct(row.get('std'))}"
        )


def _print_text(pack: dict) -> None:
    print(
        f"{pack.get('code')} {pack.get('name') or ''}  "
        f"波动口径={pack.get('factor')}  最低价口径={pack.get('low_factor')}  "
        f"±{pack.get('band', 0) * 100:.2f}%"
    )
    if not pack.get("found"):
        print(f"  {pack.get('message')}")
        return
    rng = pack.get("range") or {}
    print(
        f"  最大区间: {rng.get('beg')} → {rng.get('end')}  "
        f"共 {rng.get('count')} 个交易日  基准 {((rng.get('base') or {}).get('close'))}"
        f" @ {(rng.get('base') or {}).get('date')}"
    )
    fail = pack.get("first_fail") or {}
    if fail.get("beg"):
        print(f"  再往前推一天即不满足: {fail.get('beg')} → {fail.get('end')}")
    low = pack.get("low_point") or {}
    if low:
        print(
            f"  区间最低{low.get('label')}: {low.get('price')} @ {low.get('date')}"
        )
    score = pack.get("score") or {}
    target = score.get("target") or {}
    if target:
        print(
            f"  最低价日评分: {target.get('score')} "
            f"（价格分 {target.get('score_price')} / 天数分 {target.get('score_days')}"
            f" / 差距分 {target.get('score_gap')}，{target.get('label')} "
            f"{target.get('date')}）"
        )
    print("  标准差坐标：")
    _print_side("个股", pack.get("stock") or {})
    _print_side("指数", pack.get("index") or {})


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="区间评估：最大波动区间 / 最低价日评分 / σ 坐标")
    p.add_argument("code", nargs="?", help="股票代码，如 600519")
    p.add_argument("--end", default="", help="结束日期，默认最新交易日")
    p.add_argument("--factor", default="close", help="波动口径 open/high/low/close/all")
    p.add_argument("--low-factor", default="close", help="最低价口径 open/high/low/close")
    p.add_argument("--band", type=float, default=0.09, help="波动带（小数，0.09=±9%%）")
    p.add_argument("--index", default="000001", help="对比指数公开码，默认上证指数")
    p.add_argument("--lookback", type=int, default=900, help="回溯自然日，默认 900")
    p.add_argument("--adjust", default="qfq", help="qfq/hfq/none，默认前复权")
    p.add_argument("--layers", type=int, default=1, help="local_extrema 层级数")
    p.add_argument("--smooth", type=int, default=1, help="local_extrema 平滑窗口")
    p.add_argument("--json", action="store_true", help="输出完整 JSON")
    args = p.parse_args(argv)

    if not args.code:
        p.error("须提供 code")

    try:
        pack = analyze_evaluate(
            args.code,
            end=args.end,
            factor=args.factor,
            low_factor=args.low_factor,
            band=args.band,
            index=args.index,
            lookback_days=args.lookback,
            adjust=args.adjust,
            layers=args.layers,
            smooth_window=args.smooth,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(pack, ensure_ascii=False, indent=2, default=str))
    else:
        _print_text(pack)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
