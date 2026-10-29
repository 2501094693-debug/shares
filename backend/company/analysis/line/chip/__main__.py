"""python -m company.analysis.line.chip 600519 --beg 2025-01-01 --bins 200

打印截至 end 的筹码统计（获利比例 / 平均成本 / 成本区间 / 集中度 / 筹码峰），
``--json`` 输出完整前端载荷（价格轴 + 筹码量 + 每日序列）。

带任一 ``--target-*`` 时进入标定模式：拿同花顺客户端读数当基准，网格搜索
``decay`` × ``peak``，打印误差最小的参数组合。
"""

from __future__ import annotations

import argparse
import json
import sys

from company.analysis.line.chip.calibrate import DEFAULT_DECAYS, calibrate
from company.analysis.line.chip.core import DEFAULT_PEAK, PEAK_MODES
from company.analysis.line.chip.service import run_symbol, to_payload

_TARGET_ARGS = {
    "avg_cost": "target_avg_cost",
    "profit_ratio": "target_profit_ratio",
    "median": "target_median",
    "peak": "target_peak",
    "cost70_low": "target_cost70_low",
    "cost70_high": "target_cost70_high",
    "cost90_low": "target_cost90_low",
    "cost90_high": "target_cost90_high",
    "concentration70": "target_concentration70",
    "concentration90": "target_concentration90",
}


def _print_calibration(result: dict) -> None:
    goal = result.get("targets") or {}
    print(
        f"{result.get('symbol')} {result.get('name')}  {result.get('date')}  "
        f"source={result.get('source')}  rows={result.get('rows')}  "
        f"bins={(result.get('grid') or {}).get('bins')}"
    )
    print("  基准：" + "  ".join(f"{key}={value}" for key, value in goal.items()))
    print("  排名  peak   decay  误差      " + "  ".join(goal))
    for rank, item in enumerate(result.get("candidates") or [], start=1):
        stats = item.get("stats") or {}
        cells = "  ".join(
            f"{stats.get(key)}" if stats.get(key) is not None else "-" for key in goal
        )
        print(
            f"  {rank:>4}  {item.get('peak'):<6} {item.get('decay'):<6} "
            f"{item.get('score'):<9} {cells}"
        )
    best = result.get("best") or {}
    if best:
        print(
            f"  最优：peak={best.get('peak')}  decay={best.get('decay')}  "
            f"误差={best.get('score')}"
        )
        print(
            "  调用：" f"/api/stocks/line-chip?code={result.get('symbol')}"
            f"&end={result.get('date')}&bins={(result.get('grid') or {}).get('bins')}"
            f"&decay={best.get('decay')}&peak={best.get('peak')}"
        )


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass
    parser = argparse.ArgumentParser(description="同花顺手机端日线筹码分布")
    parser.add_argument("code", nargs="?", default="600519", help="股票代码")
    parser.add_argument("--beg", default="", help="序列起始日 YYYY-MM-DD")
    parser.add_argument("--end", default="", help="截止日 YYYY-MM-DD，默认今天")
    parser.add_argument("--bins", type=int, default=200, help="价格分箱数")
    parser.add_argument("--decay", type=float, default=1.0, help="换手衰减系数")
    parser.add_argument(
        "--peak",
        default=DEFAULT_PEAK,
        choices=PEAK_MODES,
        help="三角峰口径：avg=成交均价（默认，通达信/同花顺口径）",
    )
    parser.add_argument(
        "--source",
        default="auto",
        choices=("auto", "ths", "fallback"),
        help="数据源：auto=同花顺手机端优先",
    )
    parser.add_argument("--series-limit", type=int, default=10, help="预览的每日序列条数")
    parser.add_argument("--json", action="store_true", help="输出完整载荷")

    for key, dest in _TARGET_ARGS.items():
        parser.add_argument(
            f"--target-{key.replace('_', '-')}",
            dest=dest,
            type=float,
            default=None,
            help=f"同花顺客户端显示的 {key}，给了就进标定模式",
        )
    parser.add_argument(
        "--decays",
        default="",
        help=f"标定用的衰减系数候选，逗号分隔，默认 {DEFAULT_DECAYS}",
    )
    parser.add_argument(
        "--peaks",
        default="",
        help=f"标定用的峰值口径候选，逗号分隔，默认全部 {'|'.join(PEAK_MODES)}",
    )
    parser.add_argument("--top", type=int, default=8, help="标定返回的候选条数")
    parser.add_argument(
        "--calib-bins",
        type=int,
        default=800,
        help="标定用的价格分箱数，默认 800（与前端一致）",
    )
    args = parser.parse_args()

    targets = {
        key: getattr(args, dest)
        for key, dest in _TARGET_ARGS.items()
        if getattr(args, dest) is not None
    }
    if targets:
        decays = [float(x) for x in args.decays.split(",") if x.strip()] or None
        peaks = [x.strip() for x in args.peaks.split(",") if x.strip()] or None
        result = calibrate(
            args.code,
            end=args.end,
            targets=targets,
            decays=decays,
            peaks=peaks,
            bins=args.calib_bins,
            source=args.source,
            top=args.top,
        )
        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2, default=float))
        else:
            _print_calibration(result)
        return 0

    out = run_symbol(
        args.code,
        beg=args.beg,
        end=args.end,
        bins=args.bins,
        decay=args.decay,
        peak=args.peak,
        source=args.source,
    )
    payload = to_payload(
        out,
        beg=args.beg,
        end=out.get("end") or args.end,
        series_limit=args.series_limit,
    )
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2, default=float))
        return 0

    stats = payload["stats"]
    print(
        f"{payload.get('symbol')} {payload.get('name')}  "
        f"{payload.get('date')}  close={stats.get('close')}  "
        f"source={payload.get('source')}  grid={len(payload['grid'])}  "
        f"peak={payload['meta'].get('peak')}"
    )
    print(f"  获利比例 {float(stats.get('profit_ratio') or 0) * 100:.2f}%")
    print(
        f"  平均成本 {stats.get('avg_cost')}  "
        f"中位 {stats.get('median')}  筹码峰 {stats.get('peak')}"
    )
    print(
        f"  70% 成本区间 [{stats.get('cost70_low')}, {stats.get('cost70_high')}]  "
        f"集中度 {stats.get('concentration70')}"
    )
    print(
        f"  90% 成本区间 [{stats.get('cost90_low')}, {stats.get('cost90_high')}]  "
        f"集中度 {stats.get('concentration90')}"
    )
    peaks = payload.get("peaks") or []
    if peaks:
        print("  筹码峰：" + "  ".join(
            f"{item['price']}({float(item['weight'] or 0) * 100:.1f}%)" for item in peaks
        ))
    series = payload.get("series") or []
    if series:
        print("  最近序列：")
        for row in series[-args.series_limit:]:
            print(
                f"    {row['date']}  close={row['close']}  "
                f"获利={float(row.get('profit_ratio') or 0) * 100:.2f}%  "
                f"均成本={row.get('avg_cost')}  峰={row.get('peak')}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
