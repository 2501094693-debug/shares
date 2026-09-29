"""CLI：python -m agent.fundamentals_agent 600519"""

from __future__ import annotations

import argparse
import json
import sys


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="财务数据、盈利能力与估值诊断")
    parser.add_argument("company", help="公司名称或股票代码")
    parser.add_argument("--skip-llm", action="store_true", help="跳过 LLM，只用规则模板")
    parser.add_argument("--json", action="store_true", help="额外打印结构化摘要 JSON")
    args = parser.parse_args(argv)

    from agent.fundamentals_agent.pipeline import run_fundamentals

    result = run_fundamentals(args.company, skip_llm=args.skip_llm)
    text = result.get("report") or ""
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    print(text)
    print(f"\n[saved] {result.get('report_path')}", file=sys.stderr)
    if args.json:
        slim = {
            "stock_code": result.get("stock_code"),
            "stock_name": result.get("stock_name"),
            "stance": result.get("stance"),
            "anchor_iv": result.get("anchor_iv"),
            "anchor_mos": result.get("anchor_mos"),
            "dims": result.get("dims"),
            "report_path": result.get("report_path"),
            "errors": result.get("errors"),
        }
        print(json.dumps(slim, ensure_ascii=False, indent=2), file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
