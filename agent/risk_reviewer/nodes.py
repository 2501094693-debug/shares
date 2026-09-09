"""投资风险与管理层质量评估智能体 — 节点实现。"""

from __future__ import annotations

import re
from datetime import date

from langchain_core.messages import HumanMessage, SystemMessage

from agent.config import REPORTS_DIR
from agent.risk_reviewer.prompts import RISK_REVIEWER_SYSTEM, build_risk_reviewer_user_prompt
from agent.risk_reviewer.state import RiskReviewerState
from agent.tools.data_fetcher import (
    fetch_risk_reviewer_data,
    fetch_web_risk_supplement,
    resolve_company,
)
from agent.tools.progress import report as emit_progress
from agent.utils.llm import get_llm


def init_company(state: RiskReviewerState) -> dict:
    """解析公司代码、名称与所属行业。"""
    company = state["company"]
    today = date.today().isoformat()

    emit_progress("rr_init", f"正在解析 {company}…", phase="resolve", status="running")
    stock = resolve_company(company)
    emit_progress(
        "rr_init",
        f"已解析：{stock['name']} ({stock['code']})",
        phase="done",
        status="done",
    )

    return {
        "data_cutoff_date": today,
        "stock_code": stock["code"],
        "stock_name": stock["name"],
        "stock_market": stock["market"],
        "industry_name": stock.get("industry_name", ""),
        "industry_code": stock.get("industry_code", ""),
    }


def fetch_data(state: RiskReviewerState) -> dict:
    """采集交易所、巨潮、七网等官方资料（主线）。"""
    company = state["company"]
    stock = {
        "code": state.get("stock_code", ""),
        "name": state.get("stock_name", ""),
        "market": state.get("stock_market", ""),
    }

    emit_progress("rr_fetch", "开始采集风险与治理相关资料…", phase="fetch_data", status="running")
    pack = fetch_risk_reviewer_data(company, stock, progress_node="rr_fetch")

    n_sections = len(pack.get("sections") or {})
    industry_name = pack.get("industry_name") or state.get("industry_name", "")
    emit_progress(
        "rr_fetch",
        f"主线采集完成：{n_sections} 类数据 · 行业={industry_name or '待确认'}",
        phase="fetch_data_done",
        status="done",
    )

    return {
        "data_context": pack["text"],
        "sources_used": pack.get("sources_used", []),
        "data_available": pack.get("data_available", False),
        "industry_name": industry_name,
        "industry_code": pack.get("industry_code") or state.get("industry_code", ""),
    }


def search_web_supplement(state: RiskReviewerState) -> dict:
    """联网搜索补充最新监管动态与管理层言论。失败不阻断主线。"""
    company = state["company"]
    stock = {
        "code": state.get("stock_code", ""),
        "name": state.get("stock_name", ""),
        "market": state.get("stock_market", ""),
    }
    industry_name = state.get("industry_name", "")

    emit_progress("rr_search", "开始联网检索最新监管动态…", phase="web_search", status="running")
    pack = fetch_web_risk_supplement(
        company,
        stock,
        industry_name=industry_name,
        progress_node="rr_search",
    )

    extra = pack.get("sources_used") or []
    sources = list(state.get("sources_used") or [])
    for item in extra:
        if item not in sources:
            sources.append(item)

    used = bool(pack.get("used"))
    engines = pack.get("engines") or []
    if used:
        emit_progress(
            "rr_search",
            f"联网补充完成（{'+'.join(engines) or '已检索'}）",
            phase="web_search_done",
            status="done",
        )
    else:
        emit_progress(
            "rr_search",
            "未获得联网补充，将仅依据官方披露撰写",
            phase="web_search_done",
            status="done",
        )

    return {
        "web_context": pack.get("text") or "",
        "web_engines": engines,
        "web_search_used": used,
        "sources_used": sources,
    }


def generate_report(state: RiskReviewerState) -> dict:
    """调用 LLM 生成投资风险与管理层质量评估报告。"""
    company = state["company"]
    industry_name = state.get("industry_name", "")

    emit_progress("rr_analyze", "正在生成风险与管理层评估…", phase="llm", status="running")

    user_prompt = build_risk_reviewer_user_prompt(
        company=company,
        stock_code=state.get("stock_code", ""),
        stock_name=state.get("stock_name", ""),
        industry_name=industry_name,
        data_cutoff_date=state.get("data_cutoff_date", ""),
        data_context=state.get("data_context", ""),
        sources=state.get("sources_used", []),
        web_context=state.get("web_context", ""),
    )

    llm = get_llm()
    response = llm.invoke(
        [SystemMessage(content=RISK_REVIEWER_SYSTEM), HumanMessage(content=user_prompt)]
    )
    content = response.content or ""

    engines = state.get("web_engines") or []
    supplement = f"联网搜索（{'+'.join(engines)}）" if state.get("web_search_used") else "联网未启用或无结果"
    stock_name = state.get("stock_name") or company
    header = (
        f"# 评估{stock_name}投资风险与管理层质量\n\n"
        f"> 代码: {state.get('stock_code', '')} | "
        f"行业: {industry_name or '待确认'} | "
        f"数据截止: {state.get('data_cutoff_date', '')} | "
        f"范围: 管理层 · 监管 · 竞争 · 业务 · 宏观 · 治理 · 长期确定性 | "
        f"主线: 交易所 · 巨潮 · 七网 · 公告PDF | "
        f"补充: {supplement}\n\n"
    )
    report = header + content

    emit_progress(
        "rr_analyze",
        f"评估完成（约 {len(report)} 字）",
        phase="llm_done",
        status="done",
    )

    return {"report": report}


def save_report(state: RiskReviewerState) -> dict:
    """保存风险评估报告。"""
    company = state["company"]
    cutoff = state.get("data_cutoff_date", date.today().isoformat()).replace("-", "")
    safe_name = re.sub(r"[^\w\u4e00-\u9fff-]", "_", state.get("stock_name") or company)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    path = REPORTS_DIR / f"{safe_name}风险与管理层评估_{cutoff}.md"

    emit_progress("rr_save", "正在保存报告…", phase="save_file", status="running")
    path.write_text(state.get("report") or "", encoding="utf-8")
    emit_progress("rr_save", f"已保存至 {path.name}", phase="done", status="done")

    return {"report_path": str(path)}
