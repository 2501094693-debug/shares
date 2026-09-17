"""CLI: python -m agent.essence_analyst <代码或名称>"""

from __future__ import annotations

import argparse


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="生意本质智能体（官方主营 → 解释举例 → 关键因素）")
    parser.add_argument("company", help="股票代码或公司名称")
    args = parser.parse_args(argv)

    from agent.essence_analyst.graph import RECURSION_LIMIT, compile_app

    app = compile_app()
    result = app.invoke({"company": args.company.strip()}, {"recursion_limit": RECURSION_LIMIT})
    print(result.get("report_path") or (result.get("final_report") or "")[:800])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
