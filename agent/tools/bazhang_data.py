"""张新民「八看」数据采集与预处理（全部 Python 实现）。"""

from __future__ import annotations

import logging
from typing import Any

from agent.bazhang_analyst.rules import run_zhang_analysis
from agent.tools.data_fetcher import (
    _fetch_profile_pack,
    resolve_company,
)
from agent.tools.financials import (
    fetch_segment_data,
    fetch_statement_frames,
    fetch_valuation_pack,
    format_periodic_financial_text,
)
from agent.tools.progress import report

logger = logging.getLogger(__name__)


def fetch_bazhang_data(
    company: str,
    stock: dict[str, str] | None = None,
    *,
    progress_node: str = "bz_fetch",
) -> dict[str, Any]:
    """采集八看分析所需的全部数据，并运行规则引擎预计算。"""
    resolved = stock or resolve_company(company)
    code = resolved["code"]
    name = resolved["name"]
    node = progress_node
    sections: dict[str, str] = {}
    sources: list[str] = []
    errors: list[str] = []

    report(node, f"采集 {name} 八看分析数据", phase="fetch_data", status="running")

    report(node, "正在拉取公司画像与行业归属…", phase="fetch_section")
    profile_stock, industry, profile_text = _fetch_profile_pack(code, name)
    if "未能" not in profile_text:
        sections["公司画像与盘口"] = profile_text
        sources.extend(["东方财富盘口", "申万行业"])

    report(node, "正在拉取最新全量定期报告（年报/半年报/季报）…", phase="fetch_section")
    fin = fetch_statement_frames(code, limit=60, force=True)
    errors.extend(fin.get("errors") or [])
    annual = fin.get("annual") or []
    recent = fin.get("recent") or []
    merged = fin.get("merged") or []
    formatted = format_periodic_financial_text(
        annual=annual,
        recent=recent,
        merged=merged,
        statements=fin.get("statements") or {},
    )
    if formatted.get("text"):
        sections["财务报表原始数据"] = formatted["text"]
        sources.extend(formatted.get("sources") or [])

    if not annual and not merged:
        errors.append("未能获取财务报表数据")

    report(node, "正在运行张新民「八看」规则引擎…", phase="fetch_section")
    zhang = run_zhang_analysis(annual, recent, merged=merged)
    sections["八看规则引擎预计算"] = zhang["text"]
    sources.append("规则引擎预计算")
    for title, table in (zhang.get("tables") or {}).items():
        sections[f"八看_{title}"] = table

    report(node, "正在拉取主营业务分部数据…", phase="fetch_section")
    segment = fetch_segment_data(code)
    if segment.get("text"):
        sections["主营业务构成"] = segment["text"]
        sources.extend(segment.get("sources") or [])

    report(node, "正在拉取估值与同业对比…", phase="fetch_section")
    val = fetch_valuation_pack(code, name, profile_stock, industry)
    if val.get("text"):
        sections["估值与同业"] = val["text"]
        sources.extend(val.get("sources") or [])

    text_parts = []
    for title, body in sections.items():
        text_parts.append(f"## {title}\n{body}")

    report(node, "八看数据采集与规则计算完成", phase="fetch_data_done", status="done")

    return {
        "stock": profile_stock or resolved,
        "industry": industry or {},
        "annual": annual,
        "recent": recent,
        "merged": merged,
        "zhang": zhang,
        "sections": sections,
        "text": "\n\n".join(text_parts),
        "sources_used": list(dict.fromkeys(item.strip() for item in sources if item and str(item).strip())),
        "errors": errors,
        "data_available": bool(annual or merged),
    }
