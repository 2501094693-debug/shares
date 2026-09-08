#!/usr/bin/env python3
"""投研团队 LangGraph 入口。

用法:
    python main.py 美团
    python main.py "四创电子 600990" --request "重点分析估值与护城河"
    python main.py 贵州茅台 --stream
"""

from __future__ import annotations

import argparse
import sys

from config import OPENAI_API_KEY, REPORTS_DIR
from graph import compile_app
from tools.data_fetcher import resolve_company
from tools.web_search import is_web_search_available


def print_team_framework(company: str) -> None:
    print(
        f"""
╔══════════════════════════════════════════════════════════════╗
║  投研团队：{company:^20}                          ║
╠══════════════════════════════════════════════════════════════╣
║  team-lead          │ 统筹协调、汇总研判、输出最终报告        ║
║  business-analyst   │ 商业模式 & 护城河（段永平视角）         ║
║  financial-analyst  │ 财务报表 & 估值（巴菲特视角）           ║
║  industry-researcher│ 行业格局 & 竞争态势（芒格视角）         ║
║  risk-assessor      │ 风险评估 & 管理层（李录视角）           ║
╚══════════════════════════════════════════════════════════════╝
"""
    )


def print_info_richness_guide() -> None:
    print(
        """
【AI 可研究性评估】
  A级（信息充裕）→ 反面检验、非共识视角
  B级（信息适中）→ 标注置信度与数据充分度
  C级（信息稀缺）→ 第一性原理，聚焦核心问题
"""
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="AI 投研团队 LangGraph 工作流")
    parser.add_argument("company", help="目标公司名称或代码，如：美团、600990")
    parser.add_argument("--request", default="", help="额外研究要求（可选）")
    parser.add_argument("--stream", action="store_true", help="流式输出进度")
    args = parser.parse_args()

    if not OPENAI_API_KEY:
        print("错误: 请设置环境变量 OPENAI_API_KEY", file=sys.stderr)
        return 1

    stock = resolve_company(args.company)
    print(f"  解析: {stock['name']} ({stock['code']}) 市场={stock['market']}")
    print(f"  联网搜索: {'可用' if is_web_search_available() else '不可用（将依赖结构化数据）'}\n")

    print_team_framework(args.company)
    print_info_richness_guide()
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    app = compile_app()
    initial_state = {
        "company": args.company,
        "user_request": args.request or f"对{args.company}进行团队化投资研究分析",
        "stock_code": stock["code"],
        "stock_name": stock["name"],
        "stock_market": stock["market"],
        "analyst_reports": [],
        "completed_roles": [],
    }

    print("启动 4 路并行研究...\n")

    result: dict = {}
    if args.stream:
        for event in app.stream(initial_state, stream_mode="updates"):
            for node, update in event.items():
                result.update(update)
                if node in (
                    "business_analyst",
                    "financial_analyst",
                    "industry_researcher",
                    "risk_assessor",
                ):
                    roles = update.get("completed_roles", [])
                    print(f"  ✓ {', '.join(roles)} 已完成")
                elif node == "init":
                    print(
                        f"  信息丰富度: {update.get('info_richness')} — "
                        f"{update.get('info_richness_rationale')}"
                    )
                elif node == "team_lead":
                    print("  ✓ team-lead 汇总完成")
                elif node == "save":
                    print(f"  ✓ 报告已保存: {update.get('report_path')}")
                elif node == "audit":
                    print("  ✓ 审计抽检清单已提取")
    else:
        result = app.invoke(initial_state)

    print("\n" + "=" * 60)
    print("研究完成")
    print(f"报告路径: {result.get('report_path', 'N/A')}")
    print(f"信息丰富度: {result.get('info_richness')} — {result.get('info_richness_rationale')}")
    print("=" * 60)

    audit = result.get("audit_extracted", "")
    if audit:
        print("\n【数据抽检清单（前 500 字）】")
        print(audit[:500])
        print("\n完整清单见上方输出。可用 report_audit.py verdict 完成准出流程。")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
