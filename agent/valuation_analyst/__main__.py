"""CLI: python -m agent.valuation_analyst 600519 [--skip-llm]"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="估值分析：四路悲观/中性/乐观")
    parser.add_argument("company", help="股票代码或公司名称")
    parser.add_argument("--skip-llm", action="store_true", help="只用规则引擎模板，不调用模型")
    parser.add_argument("--json", action="store_true", help="打印结构化 JSON")
    args = parser.parse_args(argv)

    from agent.tools.data_fetcher import resolve_company
    from agent.valuation_analyst.graph import compile_app

    stock = resolve_company(args.company)
    print(f"  解析: {stock['name']} ({stock['code']})", file=sys.stderr)
    app = compile_app()
    result = app.invoke(
        {
            "company": args.company.strip(),
            "skip_llm": args.skip_llm,
            "stock_code": stock["code"],
            "stock_name": stock["name"],
            "stock_market": stock["market"],
        }
    )
    engine = result.get("engine") or {}
    composite = engine.get("composite") or {}
    payload = {
        "stock_code": result.get("stock_code") or stock["code"],
        "stock_name": result.get("stock_name") or stock["name"],
        "stance": composite.get("stance"),
        "primary": engine.get("primary"),
        "business_type": engine.get("business_type"),
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
