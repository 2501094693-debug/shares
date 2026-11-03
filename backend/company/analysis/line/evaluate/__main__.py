"""CLI：区间评估（最大 ±band 区间 + 最低价日评分 + 股指四价走势 + 股指偏离分）。

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

from company.analysis.line.evaluate.service import analyze_evaluate

_PATH_ORDER = ("open", "high", "low", "close")
_PATH_LABEL = {"open": "开", "high": "高", "low": "低", "close": "收"}


def _fmt_paths(paths: dict) -> str:
    parts = []
    for key in _PATH_ORDER:
        parts.append(f"{_PATH_LABEL[key]}{paths.get(key) or '—'}")
    return " ".join(parts)


def _print_paths(block: dict) -> None:
    print("  四价波动走势（区间内，相对起始日前收）：")
    if block.get("error"):
        print(f"    获取失败: {block.get('error')}")
        return
    stock = block.get("stock") or {}
    index = block.get("index") or {}
    print(
        f"    个股 {stock.get('code') or ''} {stock.get('name') or ''}  "
        f"{_fmt_paths(stock.get('paths') or {})}"
    )
    print(
        f"    指数 {index.get('code') or ''} {index.get('name') or ''}  "
        f"{_fmt_paths(index.get('paths') or {})}"
    )


def _print_divergence(block: dict) -> None:
    print("  股指偏离分：")
    if block.get("error"):
        print(f"    获取失败: {block.get('error')}")
        return
    stock = block.get("stock") or {}
    index = block.get("index") or {}
    dirs = block.get("dirs") or {}
    score = block.get("score")
    score_txt = "—" if score is None else f"{score:.2f}"
    print(
        f"    {score_txt}  "
        f"（反向 {block.get('reverse_count', 0)} / "
        f"共 {block.get('count', 0)} 日，口径 {block.get('factor')}）"
    )
    print(
        f"    个股 {stock.get('code') or ''} {stock.get('name') or ''}  "
        f"指数 {index.get('code') or ''} {index.get('name') or ''}"
    )
    print(
        f"    同涨 {dirs.get('same_up', 0)}  同跌 {dirs.get('same_down', 0)}  "
        f"股涨指跌 {dirs.get('stock_up_index_down', 0)}  "
        f"股跌指涨 {dirs.get('stock_down_index_up', 0)}"
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
            f"（近谷 {target.get('date')} 谷分 {target.get('score_valley')} "
            f"× 因子 {target.get('score_factor')}，"
            f"|相对价距| {target.get('dist_rel')}；"
            f"价格分 {target.get('score_price')} / 天数分 {target.get('score_days')}"
            f" / 差距分 {target.get('score_gap')}）"
        )
    _print_paths(pack.get("paths") or {})
    _print_divergence(pack.get("divergence") or {})


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="区间评估：最大波动区间 / 最低价日评分 / 股指四价走势 / 股指偏离分"
    )
    p.add_argument("code", nargs="?", help="股票代码，如 600519")
    p.add_argument("--end", default="", help="结束日期，默认最新交易日")
    p.add_argument("--factor", default="close", help="波动口径 open/high/low/close/all")
    p.add_argument("--low-factor", default="close", help="最低价口径 open/high/low/close")
    p.add_argument("--band", type=float, default=0.09, help="波动带（小数，0.09=±9%%）")
    p.add_argument("--index", default="000001", help="对比指数公开码，默认上证指数")
    p.add_argument("--lookback", type=int, default=900, help="回溯自然日，默认 900")
    p.add_argument("--adjust", default="qfq", help="qfq/hfq/none，默认前复权")
    p.add_argument("--layers", type=int, default=3, help="local_extrema 层级数（谷序列默认 3）")
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
