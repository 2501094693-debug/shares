"""综合深度研判数据采集。"""

from __future__ import annotations

import logging
from typing import Any

from agent.comprehensive_analyst.rules import (
    analyze_balance_sheet,
    analyze_cashflow_statement,
    analyze_income_statement,
    compute_valuation_scenarios,
)
from agent.config import DATA_LOOKBACK_DAYS
from agent.tools.data_fetcher import (
    OFFICIAL_SOURCE_LABELS,
    _collect_periodic_items,
    _fetch_peer_competition_table,
    _fetch_press_coverage,
    _fetch_profile_pack,
    _format_periodic_catalog,
    resolve_company,
)
from agent.tools.financials import (
    build_valuation_helpers,
    fetch_comprehensive_financial_pack,
    fetch_segment_data,
    fetch_valuation_pack,
)
from agent.tools.progress import report

logger = logging.getLogger(__name__)

_COMPREHENSIVE_LOOKBACK_DAYS = max(DATA_LOOKBACK_DAYS, 365 * 5)


def fetch_comprehensive_data(
    company: str,
    stock: dict[str, str] | None = None,
    *,
    progress_node: str = "ca_fetch",
) -> dict[str, Any]:
    """采集综合研判所需的全部结构化数据。"""
    resolved = stock or resolve_company(company)
    code = resolved["code"]
    name = resolved["name"]
    node = progress_node
    sections: dict[str, str] = {}
    sources: list[str] = list(OFFICIAL_SOURCE_LABELS)
    errors: list[str] = []

    report(node, f"采集 {name} 综合研判数据", phase="fetch_data", status="running")

    report(node, "正在拉取公司画像与行业归属…", phase="fetch_section")
    profile_stock, industry, profile_text = _fetch_profile_pack(code, name)
    if "未能" not in profile_text:
        sections["公司画像与盘口"] = profile_text
        sources.extend(["东方财富盘口", "申万行业"])

    report(node, "正在拉取扩展财务报表（三大表 + 主要指标）…", phase="fetch_section")
    fin = fetch_comprehensive_financial_pack(code, name, limit=40)
    errors.extend(fin.get("errors") or [])
    annual = fin.get("annual") or []
    recent = fin.get("recent") or []
    merged = fin.get("merged") or []
    if fin.get("text"):
        sections["财务报表原始数据"] = fin["text"]
        sources.extend(fin.get("sources") or [])

    report(node, "正在运行三表规则引擎…", phase="fetch_section")
    balance_rules = analyze_balance_sheet(annual or merged)
    income_rules = analyze_income_statement(annual or merged)
    cashflow_rules = analyze_cashflow_statement(annual or merged)
    sections["资产负债表规则分析"] = balance_rules["text"]
    sections["利润表规则分析"] = income_rules["text"]
    sections["现金流量表规则分析"] = cashflow_rules["text"]

    if fin.get("cross_validate"):
        sections["三表交叉验证"] = fin["cross_validate"]

    report(node, "正在拉取主营业务分部数据…", phase="fetch_section")
    segment = fetch_segment_data(code)
    if segment.get("text"):
        sections["主营业务构成"] = segment["text"]
        sources.extend(segment.get("sources") or [])

    report(node, "正在拉取历史估值与同业对比…", phase="fetch_section")
    val = fetch_valuation_pack(code, name, profile_stock, industry)
    pe_items = val.get("pe_items") or []
    if val.get("text"):
        sections["估值与同业"] = val["text"]
        sources.extend(val.get("sources") or [])

    helpers = build_valuation_helpers(profile_stock, annual, pe_items)
    sections["安全边际预计算"] = helpers

    scenarios = compute_valuation_scenarios(profile_stock, annual, pe_items)
    sections["三情景估值"] = scenarios["text"]

    report(node, "正在拉取近五年定期报告公告…", phase="fetch_section")
    periodic_by_kind = _collect_periodic_items(
        code, name, days=_COMPREHENSIVE_LOOKBACK_DAYS, limit_per_kind=8
    )
    sections["定期报告公告"] = _format_periodic_catalog(
        periodic_by_kind, name, code, days=_COMPREHENSIVE_LOOKBACK_DAYS
    )

    from agent.tools.notice_pdf import ingest_notice_pdfs, pick_latest_full_report, pick_notice_pdfs
    from agent.tools.data_fetcher import _collect_business_notices

    pdf_targets: list[dict[str, Any]] = []
    for items in periodic_by_kind.values():
        picked = pick_latest_full_report(items)
        if picked:
            pdf_targets.append(picked)
    notice_items = _collect_business_notices(code, name, days=_COMPREHENSIVE_LOOKBACK_DAYS, limit=30)
    pdf_targets.extend(pick_notice_pdfs(notice_items, already=pdf_targets, limit=8))

    if pdf_targets:
        report(node, f"正在抽取 {len(pdf_targets)} 份公告 PDF 正文…", phase="fetch_pdf")
        pdf_text = ingest_notice_pdfs(
            pdf_targets,
            code=code,
            progress=lambda msg: report(node, msg, phase="fetch_pdf"),
        )
        if pdf_text:
            sections["公告 PDF 正文（MD&A / 主营业务）"] = pdf_text
            sources.append("公告 PDF 正文（巨潮/交易所）")

    report(node, "正在拉取七网相关报道…", phase="fetch_section")
    press_text = _fetch_press_coverage(code, name, days=DATA_LOOKBACK_DAYS)
    if "（无相关报道）" not in press_text and "（未能获取" not in press_text:
        sections["七网报道"] = press_text

    peer_text = _fetch_peer_competition_table(code, name)
    if peer_text and "未能" not in peer_text:
        sections["同业竞争对照"] = peer_text

    window_note = (
        f"> **综合研判数据包**：{name}（{code}）\n"
        f"> 财报：近 5 年年报 + 近 4 季季报；估值：东财日频历史序列；"
        f"公告：近 {_COMPREHENSIVE_LOOKBACK_DAYS} 天定期报告。\n"
        f"> 利润表/现金流量表为**报告期累计数**（中报=上半年，三季报=前三季度）。\n\n"
    )
    text_parts = [window_note]
    for title, body in sections.items():
        text_parts.append(f"## {title}\n{body}")

    report(node, f"采集完成：{len(sections)} 类数据", phase="fetch_data_done", status="done")

    return {
        "code": code,
        "name": name,
        "market": resolved.get("market", ""),
        "stock": profile_stock,
        "industry": industry,
        "sections": sections,
        "text": "\n\n".join(text_parts),
        "sources_used": sources,
        "errors": errors,
        "data_available": bool(sections),
        "annual": annual,
        "recent": recent,
        "merged": merged,
        "balance_rules": balance_rules,
        "income_rules": income_rules,
        "cashflow_rules": cashflow_rules,
        "valuation_scenarios": scenarios,
        "pe_items": pe_items,
        "segment": segment,
        "mda_text": sections.get("公告 PDF 正文（MD&A / 主营业务）", ""),
        "disclosure_text": sections.get("定期报告公告", ""),
    }
