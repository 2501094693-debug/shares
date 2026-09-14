"""CLI: python -m agent.comprehensive_analyst <代码或名称>"""

from __future__ import annotations

import argparse
import sys


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="综合深度研判智能体")
    parser.add_argument("company", help="股票代码或公司名称")
    args = parser.parse_args(argv)

    from agent.comprehensive_analyst.graph import compile_app

    app = compile_app()
    result = app.invoke({"company": args.company.strip()})
    print(result.get("report_path") or result.get("final_report", "")[:500])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
