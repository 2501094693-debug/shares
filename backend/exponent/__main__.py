"""CLI：A 股指数行情 / K 线 / 列表（东财默认，可切同花顺）。

    python -m exponent quotes 000001,000300,000905
    python -m exponent quotes -s ths 000001
    python -m exponent kline 000300 --limit 5
    python -m exponent list --markets important
    python -m exponent list -s ths --markets USHI,USZI
    python -m exponent search 中证1000
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))


def _dump(data: object) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2, default=str))


def _pkg(source: str) -> Any:
    key = (source or "eastmoney").strip().lower()
    if key in ("eastmoney", "em", "east", "dc"):
        import exponent.eastmoney as pkg

        return pkg
    if key in ("tonghuashun", "ths", "th"):
        import exponent.tonghuashun as pkg

        return pkg
    raise SystemExit(f"未知 source: {source}（eastmoney|tonghuashun）")


def _add_source(p: argparse.ArgumentParser) -> None:
    p.add_argument(
        "--source",
        "-s",
        default="eastmoney",
        help="eastmoney|em / tonghuashun|ths（默认 eastmoney）",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="A 股指数数据（东财 / 同花顺）")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_quotes = sub.add_parser("quotes", help="实时行情")
    _add_source(p_quotes)
    p_quotes.add_argument(
        "codes",
        nargs="?",
        default="",
        help="逗号分隔代码，空=目录全部",
    )

    p_kline = sub.add_parser("kline", help="历史 K 线")
    _add_source(p_kline)
    p_kline.add_argument("code", help="如 000001 / 000300 / 1.000300")
    p_kline.add_argument("--period", default="day")
    p_kline.add_argument("--limit", type=int, default=10)
    p_kline.add_argument("--beg", default="")
    p_kline.add_argument("--end", default="")

    p_list = sub.add_parser("list", help="枚举指数分类/市场")
    _add_source(p_list)
    p_list.add_argument(
        "--markets",
        default="",
        help="东财: important,sse,szse,csi；同花顺: USHI,USZI,UZZI,USTI",
    )

    p_search = sub.add_parser("search", help="按名称/代码搜索")
    _add_source(p_search)
    p_search.add_argument("keyword")
    p_search.add_argument("--limit", type=int, default=10)

    p_cat = sub.add_parser("catalog", help="打印常用目录")
    _add_source(p_cat)

    args = parser.parse_args(argv)
    pkg = _pkg(getattr(args, "source", "eastmoney"))

    if args.cmd == "catalog":
        _dump(pkg.catalog())
        return 0

    if args.cmd == "quotes":
        codes = [c.strip() for c in str(args.codes).split(",") if c.strip()] or None
        _dump(pkg.fetch_quotes(codes))
        return 0

    if args.cmd == "kline":
        _dump(
            pkg.fetch_kline(
                args.code,
                period=args.period,
                limit=args.limit,
                beg=args.beg,
                end=args.end,
            )
        )
        return 0

    if args.cmd == "list":
        markets = [m.strip() for m in str(args.markets).split(",") if m.strip()] or None
        data = pkg.list_indices(markets)
        groups = data.get("groups") or []
        summary_groups = []
        for g in groups:
            sample = (g.get("items") or [])[:5]
            summary_groups.append(
                {
                    "id": g.get("category") or g.get("market"),
                    "name": g.get("category_name") or g.get("market_name"),
                    "count": g.get("count"),
                    "sample": sample,
                }
            )
        _dump(
            {
                "source": data.get("source"),
                "count": data.get("count"),
                "groups": summary_groups,
            }
        )
        return 0

    if args.cmd == "search":
        _dump(pkg.search_indices(args.keyword, limit=args.limit))
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
