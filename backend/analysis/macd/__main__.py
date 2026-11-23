"""命令行运行 MACD 金叉 + 稳定区间筛选。

    python -m analysis.macd
    python -m analysis.macd --band 0.09 --json
    python -m analysis.macd --codes 600519,000001
    python -m analysis.macd --end 2026-11-20
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path
from typing import Any

_BACKEND = Path(__file__).resolve().parents[2]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from analysis.macd.analyze import analyze_macd_stable
from analysis.macd.config import (
    ALLOWED_CROSS_TYPES,
    DEFAULT_BAND,
    DEFAULT_CROSS_TYPE,
    DEFAULT_FACTOR,
    DEFAULT_INDEX,
    DEFAULT_LOOKBACK_DAYS,
    DEFAULT_NEAR_RATIO,
    DEFAULT_W_DIV,
    DEFAULT_W_PRIOR,
    DEFAULT_WORKERS,
)
from analysis.macd.mine import default_group_name, write_mine_group
from analysis.macd.screen import cross_type_matches, screen_macd_stable, slim_row
from company.analysis.line.undulate.service import _iso, _today_iso


def _end_arg(value: str) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    try:
        return _iso(raw)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc


def _configure_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except Exception:  # noqa: BLE001
                pass


def _log(message: str) -> None:
    print(message, flush=True)


def _fmt_score(value: Any) -> str:
    if isinstance(value, (int, float)):
        return f"{float(value):.1f}"
    return "—"


def _print_hit(row: dict[str, Any], *, prefix: str = "命中") -> None:
    _log(
        f"  [{prefix}] {row.get('code')} {row.get('name') or ''}  "
        f"信号={row.get('macd_signal') or '—'}  "
        f"预测下日金叉={row.get('pred_next_cross') if row.get('pred_next_cross') is not None else '—'}  "
        f"区间={row.get('beg') or '—'}~{row.get('end') or '—'} "
        f"({row.get('count') or 0}日)  "
        f"前低={_fmt_score(row.get('score_prior'))} "
        f"(收{_fmt_score(row.get('score_close'))}/低{_fmt_score(row.get('score_low'))})  "
        f"反向={row.get('reverse_count') if row.get('reverse_count') is not None else '—'}  "
        f"总分={_fmt_score(row.get('score_total'))}"
    )


def _print_table(items: list[dict[str, Any]], *, limit: int = 50) -> None:
    if not items:
        _log("  无结果")
        return
    _log(
        f"  {'#':>3} {'代码':<8} {'名称':<10} {'信号':<10} "
        f"{'总分':>6} {'前低':>6} {'反向':>4} {'天数':>4}"
    )
    for i, row in enumerate(items[:limit], 1):
        name = str(row.get("name") or "")[:10]
        sig = str(row.get("macd_signal") or "")[:10]
        total_s = _fmt_score(row.get("score_total"))
        prior_s = _fmt_score(row.get("score_prior"))
        rev = row.get("reverse_count")
        rev_s = str(rev) if rev is not None else "—"
        _log(
            f"  {i:>3} {row.get('code', ''):<8} {name:<10} {sig:<10} "
            f"{total_s:>6} {prior_s:>6} {rev_s:>4} {row.get('count') or 0:>4}"
        )
    if len(items) > limit:
        _log(f"  … 共 {len(items)} 条，仅显示前 {limit}")


def _print_miss(code: str, pack: dict[str, Any]) -> None:
    cross = ((pack.get("macd") or {}).get("cross") or {})
    _log(
        f"  [未入选] {code} {pack.get('name') or ''}  "
        f"reason={pack.get('reason') or '—'}  "
        f"信号={cross.get('primary') or '无'}  "
        f"{pack.get('message') or ''}"
    )


class _ProgressPrinter:
    """全市场扫描：进度 + 新命中明细。"""

    def __init__(self) -> None:
        self._started = time.time()
        self._seen: set[str] = set()
        self._last_analyzed = -1

    def __call__(self, payload: dict[str, Any]) -> None:
        analyzed = int(payload.get("analyzed_count") or 0)
        total = int(payload.get("candidate_count") or 0)
        found = int(payload.get("found_count") or 0)
        errors = int(payload.get("error_count") or 0)
        items = list(payload.get("items") or [])

        for row in items:
            code = str(row.get("code") or "")
            if not code or code in self._seen:
                continue
            self._seen.add(code)
            _print_hit(row)

        # 避免同一进度重复刷屏（on_update 可能在 found 变化时也触发）
        if analyzed == self._last_analyzed and analyzed not in (0, total):
            return
        self._last_analyzed = analyzed

        elapsed = time.time() - self._started
        pct = (analyzed / total * 100.0) if total else 0.0
        rate = (analyzed / elapsed) if elapsed > 0 else 0.0
        eta = ((total - analyzed) / rate) if rate > 0 and analyzed < total else 0.0
        _log(
            f"[进度] {analyzed}/{total} ({pct:.1f}%)  "
            f"命中 {found}  错误 {errors}  "
            f"耗时 {elapsed:.0f}s  "
            f"{rate:.1f} 只/s  "
            f"ETA {eta:.0f}s"
        )


def main() -> None:
    _configure_stdio()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
        stream=sys.stderr,
        force=True,
    )

    parser = argparse.ArgumentParser(
        description="MACD 水下/水上金叉或即将金叉 + 最大稳定区间综合分筛选"
    )
    parser.add_argument("--band", type=float, default=DEFAULT_BAND, help="波动带（小数）")
    parser.add_argument("--index", type=str, default=DEFAULT_INDEX, help="对比指数")
    parser.add_argument("--factor", type=str, default=DEFAULT_FACTOR, help="波动口径")
    parser.add_argument(
        "--lookback", type=int, default=DEFAULT_LOOKBACK_DAYS, help="回溯自然日"
    )
    parser.add_argument(
        "--end",
        type=_end_arg,
        default="",
        help="截止交易日 YYYY-MM-DD/YYYYMMDD；空=最新交易日",
    )
    parser.add_argument(
        "--near-ratio",
        type=float,
        default=DEFAULT_NEAR_RATIO,
        help="相对缺口阈值；与速度外推任一命中即可",
    )
    parser.add_argument("--w-prior", type=float, default=DEFAULT_W_PRIOR)
    parser.add_argument("--w-div", type=float, default=DEFAULT_W_DIV)
    parser.add_argument(
        "--cross-type",
        type=str,
        choices=ALLOWED_CROSS_TYPES,
        default=DEFAULT_CROSS_TYPE,
        help="信号类别：all=全部 / under=水下类 / over=水上类",
    )
    parser.add_argument("--workers", type=int, default=DEFAULT_WORKERS)
    parser.add_argument("--codes", type=str, default="", help="逗号分隔代码，仅测这些")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--top", type=int, default=50, help="表格展示条数")
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="不打印扫描进度与命中明细（仍输出最终汇总表）",
    )
    parser.add_argument(
        "--to-mine",
        action="store_true",
        help="把命中结果写入「我的」分组（默认名 MACD金叉_YYYY-MM-DD）",
    )
    parser.add_argument(
        "--group",
        type=str,
        default="",
        help="写入分组名；空则用 MACD金叉_今日日期",
    )
    parser.add_argument(
        "--no-replace",
        action="store_true",
        help="写入分组时不清空原有股票",
    )
    args = parser.parse_args()

    codes = [c.strip() for c in str(args.codes or "").split(",") if c.strip()]

    if not args.json and not args.quiet:
        _log(
            f"参数 band={args.band} index={args.index} factor={args.factor} "
            f"lookback={args.lookback} end={args.end or _today_iso()} "
            f"near_ratio={args.near_ratio} "
            f"w_prior={args.w_prior} w_div={args.w_div} "
            f"cross_type={args.cross_type} workers={args.workers}"
        )

    if codes:
        if not args.json and not args.quiet:
            _log(f"单票模式：共 {len(codes)} 只")
        items: list[dict[str, Any]] = []
        for code in codes:
            if not args.json and not args.quiet:
                _log(f"→ 分析 {code} …")
            t0 = time.time()
            pack = analyze_macd_stable(
                code,
                end=args.end,
                band=args.band,
                index=args.index,
                factor=args.factor,
                lookback_days=args.lookback,
                near_ratio=args.near_ratio,
                w_prior=args.w_prior,
                w_div=args.w_div,
            )
            elapsed = time.time() - t0
            macd = pack.get("macd") if isinstance(pack.get("macd"), dict) else {}
            cross = macd.get("cross") if isinstance(macd.get("cross"), dict) else {}
            if not cross_type_matches(cross, args.cross_type):
                pack = {
                    **pack,
                    "found": False,
                    "reason": "cross_type_mismatch",
                    "message": f"信号类别不属于 {args.cross_type}",
                }
            row = slim_row(pack)
            if row:
                items.append(row)
                if not args.json and not args.quiet:
                    _print_hit(row, prefix=f"命中 {elapsed:.1f}s")
            else:
                if args.json:
                    items.append(
                        {
                            "code": code,
                            "found": False,
                            "reason": pack.get("reason"),
                            "message": pack.get("message"),
                            "macd_signal": (pack.get("macd") or {})
                            .get("cross", {})
                            .get("primary"),
                        }
                    )
                elif not args.quiet:
                    _print_miss(code, pack)
                    _log(f"    耗时 {elapsed:.1f}s")
        data = {
            "params": {
                "band": args.band,
                "index": args.index,
                "factor": args.factor,
                "end": args.end or _today_iso(),
                "near_ratio": args.near_ratio,
                "cross_type": args.cross_type,
                "codes": codes,
            },
            "found_count": sum(1 for r in items if r.get("score_total") is not None),
            "result_count": len(items),
            "items": items,
        }
    else:
        on_update = None if (args.json or args.quiet) else _ProgressPrinter()
        if not args.json and not args.quiet:
            _log("全市场扫描开始…")
        data = screen_macd_stable(
            band=args.band,
            index=args.index,
            factor=args.factor,
            lookback_days=args.lookback,
            end=args.end,
            near_ratio=args.near_ratio,
            w_prior=args.w_prior,
            w_div=args.w_div,
            cross_type=args.cross_type,
            workers=args.workers,
            on_update=on_update,
        )

    items = [
        r
        for r in list(data.get("items") or [])
        if isinstance(r, dict) and r.get("score_total") is not None
    ]

    if args.to_mine or args.group:
        group_name = str(args.group or "").strip() or default_group_name()
        written = write_mine_group(
            items,
            group_name=group_name,
            replace=not args.no_replace,
            limit=max(0, int(args.top)) if int(args.top) > 0 else 0,
        )
        if written is None:
            _log(f"分组「{group_name}」无命中，跳过写入")
        else:
            _log(
                f"分组「{written['group_name']}」({written['group_id']}) "
                f"现有 {written['count']} 只 · 新加 {written['added']} · "
                f"跳过 {written['skipped']} · 清空 {written['removed']}"
            )
            data["mine"] = {
                "group_name": written["group_name"],
                "group_id": written["group_id"],
                "count": written["count"],
                "added": written["added"],
                "skipped": written["skipped"],
                "removed": written["removed"],
            }

    if args.json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return

    _log("")
    _log(
        f"完成 updated={data.get('updated_at') or '—'}  "
        f"candidates={data.get('candidate_count') or len(codes)}  "
        f"found={data.get('found_count') or data.get('result_count')}  "
        f"errors={data.get('error_count') or 0}"
    )
    if data.get("note"):
        _log(str(data["note"]))
    _log("")
    _print_table(list(data.get("items") or []), limit=max(1, int(args.top)))


if __name__ == "__main__":
    main()
