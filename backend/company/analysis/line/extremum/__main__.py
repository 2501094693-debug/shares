"""CLI：四价前低回溯 / 区间极值位置百分比。



示例::



    python -m company.analysis.line.extremum 600519 --date 2026-10-23

    python -m company.analysis.line.extremum 600519 --beg 2026-01-06

    python -m company.analysis.line.extremum 600519 --beg 20260106 --end 20261023 --json

"""



from __future__ import annotations



import argparse

import json

import sys

from pathlib import Path



_BACKEND = Path(__file__).resolve().parents[4]

if str(_BACKEND) not in sys.path:

    sys.path.insert(0, str(_BACKEND))



from company.analysis.line.extremum.position import analyze_position

from company.analysis.line.extremum.service import FACTORS, analyze_extremum





def _fmt_pct(v: float | None) -> str:

    if v is None:

        return "—"

    return f"{v:.2f}%"





def _print_prior(pack: dict) -> None:

    print(

        f"{pack.get('code')} {pack.get('name') or ''}  "

        f"{pack.get('date')}（{'前复权' if pack.get('adjust') == 'qfq' else pack.get('adjust')}）"

    )

    if pack.get("snapped"):

        print(f"  （输入日 {pack.get('input_date')} 非交易日，已取最近交易日）")

    ext = pack.get("extremum") or {}

    for f in FACTORS:

        row = ext.get(f) or {}

        label = row.get("label") or f

        price = row.get("target_price")

        date = row.get("date")

        found = row.get("found_price")

        gap = row.get("gap")

        if date is None:

            print(f"  {label}: {price}  →  之前无更低价")

        else:

            print(

                f"  {label}: {price}  →  最近更低 {found} @ {date}"

                f"（间隔 {gap} 个交易日）"

            )





def _print_position(pack: dict) -> None:

    print(

        f"{pack.get('code')} {pack.get('name') or ''}  "

        f"[{pack.get('beg')} → {pack.get('end')}]  "

        f"共 {pack.get('count')} 个交易日  "

        f"（{'前复权' if pack.get('adjust') == 'qfq' else pack.get('adjust')}）"

    )

    if pack.get("snapped"):

        print(f"  （结束日 {pack.get('input_end')} 非交易日，已取最近交易日）")

    pos = pack.get("position") or {}

    for f in FACTORS:

        row = pos.get(f) or {}

        label = row.get("label") or f

        rank = row.get("rank")
        n = row.get("n")
        rank_txt = f"{rank}/{n}" if rank is not None and n else "—"
        print(
            f"  {label}: 最低 {row.get('min')} @ {row.get('min_date')}"
            f"  ~  最高 {row.get('max')} @ {row.get('max_date')}"
            f"  |  结束 {row.get('end_price')}"
            f"  →  {_fmt_pct(row.get('pct'))}"
            f"  ·  排名 {rank_txt}"
        )





def main(argv: list[str] | None = None) -> int:

    p = argparse.ArgumentParser(description="四价前低回溯 / 区间极值位置百分比")

    p.add_argument("code", nargs="?", help="股票代码，如 600519")

    p.add_argument("--date", default="", help="前低回溯：交易日期 YYYY-MM-DD 或 YYYYMMDD")

    p.add_argument("--beg", default="", help="位置百分比：起始日期")

    p.add_argument("--end", default="", help="位置百分比：结束日期，默认今天")

    p.add_argument("--adjust", default="qfq", help="qfq/hfq/none，默认前复权")

    p.add_argument("--json", action="store_true", help="输出完整 JSON")

    args = p.parse_args(argv)



    if not args.code:

        p.error("须提供 code")

    if args.beg and args.date:

        p.error("--date 与 --beg 不能同时使用")

    if not args.beg and not args.date:

        p.error("须提供 --date（前低回溯）或 --beg（位置百分比）")



    try:

        if args.beg:

            pack = analyze_position(

                args.code, args.beg, args.end, adjust=args.adjust

            )

        else:

            pack = analyze_extremum(args.code, args.date, adjust=args.adjust)

    except Exception as exc:  # noqa: BLE001

        print(f"ERROR: {exc}", file=sys.stderr)

        return 1



    if args.json:

        print(json.dumps(pack, ensure_ascii=False, indent=2))

    elif args.beg:

        _print_position(pack)

    else:

        _print_prior(pack)

    return 0





if __name__ == "__main__":

    raise SystemExit(main())

