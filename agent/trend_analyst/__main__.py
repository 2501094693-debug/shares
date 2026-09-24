"""CLI: python -m agent.trend_analyst 603278 [--day 2026-09-24] [--skip-llm]"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="趋势分析：资金动向 + 分时成交 → 综合结论（不含日线）"
    )
    parser.add_argument("company", help="股票代码或公司名称")
    parser.add_argument("--day", default="", help="交易日 YYYY-MM-DD；默认最近可用缓存/当日")
    parser.add_argument("--fund-limit", type=int, default=60, help="资金流天数，默认 60")
    parser.add_argument("--minute-klt", type=int, default=5, help="分钟资金粒度 1/5/15，默认 5")
    parser.add_argument("--min-deal-amount", type=float, default=300_000, help="大单最小金额，默认 30万")
    parser.add_argument("--force", action="store_true", help="强制刷新远端数据")
    parser.add_argument("--skip-llm", action="store_true", help="只用规则模板，不调用模型")
    parser.add_argument("--json", action="store_true", help="打印结构化 JSON")
    args = parser.parse_args(argv)

    from agent.tools.data_fetcher import resolve_company
    from agent.trend_analyst.graph import compile_app

    stock = resolve_company(args.company)
    print(f"  解析: {stock['name']} ({stock['code']})", file=sys.stderr)

    app = compile_app()
    result = app.invoke(
        {
            "company": args.company.strip(),
            "day": (args.day or "").strip(),
            "fund_limit": args.fund_limit,
            "minute_klt": args.minute_klt,
            "min_deal_amount": args.min_deal_amount,
            "force": args.force,
            "skip_llm": args.skip_llm,
            "stock_code": stock["code"],
            "stock_name": stock["name"],
            "stock_market": stock["market"],
        }
    )
    payload = {
        "stock_code": result.get("stock_code") or stock["code"],
        "stock_name": result.get("stock_name") or stock["name"],
        "day": result.get("day") or args.day,
        "main_force": result.get("main_force") or {},
        "retail": result.get("retail") or {},
        "verdict": result.get("verdict") or {},
        "narrative": result.get("narrative") or "",
        "report_path": result.get("report_path") or "",
        "errors": result.get("errors") or [],
        "sources_used": result.get("sources_used") or [],
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    print("\n" + (result.get("report") or json.dumps(payload, ensure_ascii=False, indent=2)))
    path = result.get("report_path")
    if path:
        print(f"\n报告: {path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
