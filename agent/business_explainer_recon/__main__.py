#!/usr/bin/env python3
"""业务解读智能体（复原版）CLI 入口。

用法（在仓库根目录执行）:
    python -m agent.business_explainer_recon 600990
    python -m agent.business_explainer_recon 四创电子 --stream
"""

from __future__ import annotations

import argparse
import sys

from .config import OPENAI_API_KEY, REPORTS_DIR
from .data_fetcher import resolve_company
from .graph import compile_app


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="业务解读智能体（复原版）")
    parser.add_argument("company", help="目标公司名称或代码")
    parser.add_argument("--stream", action="store_true", help="流式输出进度")
    args = parser.parse_args(argv)

    if not OPENAI_API_KEY:
        print("错误: 请设置环境变量 OPENAI_API_KEY", file=sys.stderr)
        return 1

    stock = resolve_company(args.company)
    print(f"  解析: {stock['name']} ({stock['code']}) 市场={stock['market']}\n")

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    app = compile_app()
    initial_state = {
        "company": args.company,
        "stock_code": stock["code"],
        "stock_name": stock["name"],
        "stock_market": stock["market"],
    }

    print("启动业务解读...\n")

    result: dict = {}
    if args.stream:
        for event in app.stream(initial_state, stream_mode="updates"):
            for node, update in event.items():
                result.update(update)
                labels = {
                    "init": "解析公司",
                    "fetch": "采集资料",
                    "explain": "生成解读",
                    "save": "保存报告",
                }
                print(f"  ✓ {labels.get(node, node)} 完成")
    else:
        result = app.invoke(initial_state)

    print("\n" + "=" * 60)
    print("业务解读完成")
    print(f"报告路径: {result.get('report_path', 'N/A')}")
    print("=" * 60)

    brief = result.get("brief") or result.get("explanation", "")
    if brief:
        print("\n【解读摘要（前 800 字）】")
        print(brief[:800])
        if len(brief) > 800:
            print("\n…（完整内容见报告文件）")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
