#!/usr/bin/env python3
"""业务简述智能体 CLI 入口。

用法:
    python explain_business.py 600519
    python explain_business.py 贵州茅台 --stream
"""

from __future__ import annotations

import argparse
import sys

from business_explainer.graph import compile_app
from config import OPENAI_API_KEY, REPORTS_DIR
from tools.data_fetcher import resolve_company


def main() -> int:
    parser = argparse.ArgumentParser(description="业务简述智能体")
    parser.add_argument("company", help="目标公司名称或代码")
    parser.add_argument("--stream", action="store_true", help="流式输出进度")
    args = parser.parse_args()

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

    print("启动业务简述...\n")

    result: dict = {}
    if args.stream:
        for event in app.stream(initial_state, stream_mode="updates"):
            for node, update in event.items():
                result.update(update)
                labels = {
                    "init": "解析公司",
                    "fetch": "采集官方披露",
                    "search": "联网补充",
                    "explain": "生成简述",
                    "save": "保存报告",
                }
                print(f"  ✓ {labels.get(node, node)} 完成")
    else:
        result = app.invoke(initial_state)

    print("\n" + "=" * 60)
    print("业务简述完成")
    print(f"报告路径: {result.get('report_path', 'N/A')}")
    print("=" * 60)

    brief = result.get("brief") or result.get("explanation", "")
    if brief:
        print("\n【简述摘要（前 800 字）】")
        print(brief[:800])
        if len(brief) > 800:
            print("\n…（完整内容见报告文件）")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
