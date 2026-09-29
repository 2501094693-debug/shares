"""估值分析数据采集：盘口、历史倍数、财报、巴菲特规则引擎、分部。"""

from __future__ import annotations

import logging
from typing import Any

from agent.buffett_analyst.rules import run_buffett_analysis
from agent.tools.data_fetcher import _fetch_profile_pack, resolve_company
from agent.tools.financials import fetch_segment_data, fetch_statement_frames, fetch_valuation_pack
from agent.tools.progress import report
from agent.valuation_analyst.rules.engine import run_valuation

logger = logging.getLogger(__name__)


def fetch_valuation_data(
    company: str,
    stock: dict[str, str] | None = None,
    *,
    progress_node: str = "va_fetch",
) -> dict[str, Any]:
    resolved = stock or resolve_company(company)
    code = resolved["code"]
    name = resolved["name"]
    sections: dict[str, str] = {}
    sources: list[str] = []
    errors: list[str] = []

    report(progress_node, f"采集 {name} 估值数据", phase="fetch_data", status="running")

    report(progress_node, "正在拉取公司画像与行业归属…", phase="fetch_section")
    profile_stock, industry, profile_text = _fetch_profile_pack(code, name)
    if "未能" not in profile_text:
        sections["公司画像与盘口"] = profile_text
        sources.extend(["东方财富盘口", "申万行业"])

    report(progress_node, "正在拉取全量定期报告…", phase="fetch_section")
    fin = fetch_statement_frames(code, limit=60, force=True)
    errors.extend(fin.get("errors") or [])
    annual = fin.get("annual") or []
    recent = fin.get("recent") or []
    merged = fin.get("merged") or []
    if merged:
        sources.append("东方财富 F10 定期报告")
    if not annual and not merged:
        errors.append("未能获取财务报表数据")

    report(progress_node, "正在运行巴菲特规则引擎…", phase="fetch_section")
    buffett = run_buffett_analysis(annual, recent, merged=merged)
    sections["巴菲特规则引擎"] = buffett.get("text") or ""
    sources.append("巴菲特规则引擎预计算")

    report(progress_node, "正在拉取主营业务分部…", phase="fetch_section")
    segment = fetch_segment_data(code)
    if segment.get("text"):
        sections["主营业务构成"] = segment["text"]
        sources.extend(segment.get("sources") or [])

    report(progress_node, "正在拉取近十年日频 PE/PB/PS…", phase="fetch_section")
    val = fetch_valuation_pack(code, name, profile_stock, industry)
    pe_items = list(val.get("pe_items") or [])
    if val.get("text"):
        sections["估值与同业"] = val["text"]
        sources.extend(val.get("sources") or [])

    text_parts = [f"## {title}\n{body}" for title, body in sections.items()]
    report(progress_node, "估值数据采集完成", phase="fetch_data_done", status="running")
    return {
        "stock_code": code,
        "stock_name": name,
        "profile": profile_stock,
        "industry": industry,
        "annual": annual,
        "recent": recent,
        "merged": merged,
        "pe_items": pe_items,
        "buffett": buffett,
        "segment_text": segment.get("text") or "",
        "sections": sections,
        "data_context": "\n\n".join(text_parts),
        "sources_used": sources,
        "errors": errors,
    }


def compute_valuation_pack(pack: dict[str, Any], *, understood: bool = True) -> dict[str, Any]:
    result = run_valuation(
        pack.get("profile") or {},
        pack.get("pe_items") or [],
        pack.get("buffett") or {},
        pack.get("industry") or {},
        understood=understood,
    )
    return result
