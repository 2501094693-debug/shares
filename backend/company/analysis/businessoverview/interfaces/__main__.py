"""统一 CLI：``python -m company.analysis.businessoverview <code>``

一个入口覆盖取数的三种形态，用子命令切换。

    report     取数 + 格式统一后的结果（默认，JSON；``--text`` 输出可读表格）
    raw        接入层原始数据（未做格式统一）
    periods    报告期列表
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from company.analysis.businessoverview.core.source import get_source, list_sources
from company.analysis.businessoverview.core.engine import analyze_business_overview


def _print(text: str) -> None:
    try:
        print(text)
    except UnicodeEncodeError:
        enc = getattr(sys.stdout, "encoding", None) or "utf-8"
        print(text.encode(enc, errors="replace").decode(enc, errors="replace"))


def _yi(value):
    return "-" if value is None else f"{value / 1e8:.2f}"


def _pct(value, digits=2):
    return "-" if value is None else f"{value * 100:.{digits}f}%"


def cmd_report(args) -> int:
    profile = analyze_business_overview(
        args.code,
        latest_n=args.latest_n,
        dimension=args.dimension,
        with_financial=not args.no_financial,
        source=args.source,
    )
    if args.out:
        path = Path(args.out)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(profile, ensure_ascii=False, indent=2), encoding="utf-8")
        _print(f"已写入 {path}")
        return 0
    if args.text:
        _print_text(profile)
        return 0
    _print(json.dumps(profile, ensure_ascii=False, indent=2))
    return 0


def _print_text(profile: dict) -> None:
    """可读视图：原样列出所有分部行，不做任何合并或归并。"""
    _print(f"{profile.get('code')} {profile.get('name') or ''}　"
           f"{profile.get('source_label')}　{profile.get('dimension') or ''}　"
           f"{profile.get('report_date')}")
    for period in profile.get("periods") or []:
        _print(f"\n[{period.get('report_date')}]　分部 {period.get('count')} 项　"
               f"占比合计={_pct(period.get('total_ratio'))}")
        for i, seg in enumerate(period.get("segments") or [], 1):
            line = f"  {i}. {seg.get('item_name')}  {_yi(seg.get('revenue'))}亿元"
            line += f"  占比={_pct(seg.get('revenue_ratio'))}"
            if seg.get("gross_margin") is not None:
                line += f"  毛利率={_pct(seg.get('gross_margin'))}"
            if seg.get("revenue_yoy") is not None:
                line += f"  同比={_pct(seg.get('revenue_yoy'))}"
            _print(line)
    for key, title in (("main_business", "主营业务"), ("product_type", "产品类型"),
                       ("scope", "经营范围")):
        if profile.get(key):
            _print(f"\n[{title}]")
            _print("  " + str(profile[key])[:400])
    for item in (profile.get("reviews") or [])[:1]:
        text = str(item.get("review") or "")
        if text:
            _print(f"\n[经营评述 {item.get('report_date') or ''}]")
            _print("  " + text[:400])


def cmd_periods(args) -> int:
    source = get_source(args.source)
    dates = source.periods(args.code)
    _print(f"{source.label}　{args.code}　共 {len(dates)} 个报告期")
    _print(", ".join(dates))
    return 0


def cmd_raw(args) -> int:
    source = get_source(args.source)
    pack = source.fetch(args.code, latest_n=args.latest_n, dimension=args.dimension)
    if args.json:
        _print(json.dumps(pack, ensure_ascii=False, indent=2))
        return 0

    _print(f"{source.label}　{pack.get('code')}　{pack.get('report_date')}　"
           f"{pack.get('dimension')}")
    _print(f"可得 {len(pack.get('all_periods') or [])} 期："
           + ", ".join((pack.get("all_periods") or [])[:10]))
    _print("\n[主营构成]")
    for i, seg in enumerate(pack.get("segments") or [], 1):
        line = f"  {i}. {seg['item_name']}  {_yi(seg.get('revenue'))}亿元"
        line += f"  占比={_pct(seg.get('revenue_ratio'))}"
        if seg.get("gross_margin") is not None:
            line += f"  毛利率={_pct(seg['gross_margin'])}"
        if seg.get("revenue_yoy") is not None:
            line += f"  同比={seg['revenue_yoy'] * 100:+.2f}%"
        _print(line)
    _print(f"  占比合计={_pct(pack.get('total_ratio'))}")
    for key, title in (("main_business", "主营业务"), ("product_type", "产品类型"),
                       ("scope", "经营范围"), ("review", "经营评述")):
        if pack.get(key):
            _print(f"\n[{title}]")
            _print("  " + str(pack[key])[:400])
    _print(f"\n接口: {source.api}")
    _print(f"页面: {pack.get('page') or source.page(args.code)}")
    return 0


def main(argv=None) -> int:
    srcs = list_sources()
    parser = argparse.ArgumentParser(
        description="主营业务取数与格式统一（无模型、无二次加工）",
        epilog="数据源: " + " | ".join(f"{s.key}={s.label}" for s in srcs),
    )
    parser.add_argument("code", help="股票代码，如 600990")
    parser.add_argument(
        "command", nargs="?", default="report",
        choices=["report", "raw", "periods"],
        help="report=统一格式JSON(默认) raw=接入层原始数据 periods=报告期列表",
    )
    parser.add_argument("-n", "--latest-n", type=int, default=2, help="取最近 N 个报告期")
    parser.add_argument("-d", "--dimension", default="", help="1按产品 2按行业 3按地区")
    parser.add_argument("-s", "--source", default="", help="数据源，留空默认同花顺（唯一）")
    parser.add_argument("--no-financial", action="store_true", help="不带八看经营情况")
    parser.add_argument("--text", action="store_true", help="report 子命令输出可读表格")
    parser.add_argument("--json", action="store_true", help="raw 子命令输出完整 JSON")
    parser.add_argument("--out", default="", help="JSON 输出路径")
    args = parser.parse_args(argv)

    handlers = {"report": cmd_report, "raw": cmd_raw, "periods": cmd_periods}
    return handlers[args.command](args)


if __name__ == "__main__":
    raise SystemExit(main())
