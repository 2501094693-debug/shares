"""CLI: python -m agent.retail_sentiment 600519 --days 3"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="发声散户情绪：东财 / 同花顺 / 雪球评论样本")
    parser.add_argument("company", help="股票代码或公司名称")
    parser.add_argument("--days", type=int, default=3, help="回溯天数，默认 3")
    parser.add_argument("--max-pages", type=int, default=3, help="每源最多翻页，默认 3")
    parser.add_argument("--replies", action="store_true", help="附带热帖回复")
    parser.add_argument("--skip-llm", action="store_true", help="只用规则词典，不调用模型")
    parser.add_argument("--json", action="store_true", help="打印指标 JSON")
    args = parser.parse_args(argv)

    from agent.retail_sentiment.graph import compile_app
    from agent.tools.data_fetcher import resolve_company

    stock = resolve_company(args.company)
    print(f"  解析: {stock['name']} ({stock['code']})", file=sys.stderr)

    app = compile_app()
    result = app.invoke(
        {
            "company": args.company.strip(),
            "days": args.days,
            "max_pages": args.max_pages,
            "with_replies": args.replies,
            "skip_llm": args.skip_llm,
            "stock_code": stock["code"],
            "stock_name": stock["name"],
            "stock_market": stock["market"],
        }
    )
    metrics = result.get("metrics") or {}
    payload = {
        "stock_code": result.get("stock_code") or stock["code"],
        "stock_name": result.get("stock_name") or stock["name"],
        "days": args.days,
        "metrics": metrics,
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
