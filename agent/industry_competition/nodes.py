"""行业竞争分析智能体 — 节点实现。"""

from __future__ import annotations

import re
from datetime import date

from langchain_core.messages import HumanMessage, SystemMessage

from agent.config import REPORTS_DIR
from agent.industry_competition.prompts import COMPETITION_SYSTEM, build_competition_user_prompt
from agent.industry_competition.state import IndustryCompetitionState
from agent.tools.data_fetcher import (
    fetch_industry_competition_data,
    fetch_web_competition_supplement,
    resolve_company,
)
from agent.tools.progress import report as emit_progress
from agent.utils.llm import get_llm


def init_company(state: IndustryCompetitionState) -> dict:
    """解析公司代码、名称与所属行业。"""
    company = state["company"]
    today = date.today().isoformat()

    emit_progress("ic_init", f"正在解析 {company}…", phase="resolve", status="running")
    stock = resolve_company(company)
    emit_progress(
        "ic_init",
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


def fetch_data(state: IndustryCompetitionState) -> dict:
    """采集交易所、巨潮、七网等官方资料及同业对照（主线）。"""
    company = state["company"]
    stock = {
        "code": state.get("stock_code", ""),
        "name": state.get("stock_name", ""),
        "market": state.get("stock_market", ""),
    }

    emit_progress("ic_fetch", "开始采集行业竞争相关资料…", phase="fetch_data", status="running")
    pack = fetch_industry_competition_data(company, stock, progress_node="ic_fetch")

    n_sections = len(pack.get("sections") or {})
    industry_name = pack.get("industry_name") or state.get("industry_name", "")
    emit_progress(
        "ic_fetch",
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


def search_web_supplement(state: IndustryCompetitionState) -> dict:
    """联网搜索补充最新行业数据与竞争动态。失败不阻断主线。"""
    company = state["company"]
    stock = {
        "code": state.get("stock_code", ""),
        "name": state.get("stock_name", ""),
        "market": state.get("stock_market", ""),
    }
    industry_name = state.get("industry_name", "")

    emit_progress("ic_search", "开始联网检索最新行业数据…", phase="web_search", status="running")
    pack = fetch_web_competition_supplement(
        company,
        stock,
        industry_name=industry_name,
        progress_node="ic_search",
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
            "ic_search",
            f"联网补充完成（{'+'.join(engines) or '已检索'}）",
            phase="web_search_done",
            status="done",
        )
    else:
        emit_progress(
            "ic_search",
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


def generate_analysis(state: IndustryCompetitionState) -> dict:
    """调用 LLM 生成行业竞争格局分析报告。"""
    company = state["company"]
    industry_name = state.get("industry_name", "")

    emit_progress("ic_analyze", "正在生成行业竞争分析…", phase="llm", status="running")

    user_prompt = build_competition_user_prompt(
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
        [SystemMessage(content=COMPETITION_SYSTEM), HumanMessage(content=user_prompt)]
    )
    content = response.content or ""

    engines = state.get("web_engines") or []
    supplement = f"联网搜索（{'+'.join(engines)}）" if state.get("web_search_used") else "联网未启用或无结果"
    industry_label = industry_name or "行业"
    header = (
        f"# 分析{industry_label}行业格局与{state.get('stock_name') or company}竞争态势\n\n"
        f"> 代码: {state.get('stock_code', '')} | "
        f"行业: {industry_label} | "
        f"数据截止: {state.get('data_cutoff_date', '')} | "
        f"范围: 行业格局 · 竞争态势 · 产业链 | "
        f"主线: 交易所 · 巨潮 · 七网 · 公告PDF · 同业对照 | "
        f"补充: {supplement}\n\n"
    )
    report = header + content

    emit_progress(
        "ic_analyze",
        f"分析完成（约 {len(report)} 字）",
        phase="llm_done",
        status="done",
    )

    return {"report": report}


def save_report(state: IndustryCompetitionState) -> dict:
    """保存行业竞争分析报告。"""
    company = state["company"]
    cutoff = state.get("data_cutoff_date", date.today().isoformat()).replace("-", "")
    safe_name = re.sub(r"[^\w\u4e00-\u9fff-]", "_", state.get("stock_name") or company)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    path = REPORTS_DIR / f"{safe_name}行业竞争分析_{cutoff}.md"

    emit_progress("ic_save", "正在保存报告…", phase="save_file", status="running")
    path.write_text(state.get("report") or "", encoding="utf-8")
    emit_progress("ic_save", f"已保存至 {path.name}", phase="done", status="done")

    return {"report_path": str(path)}
