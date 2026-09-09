"""业务简述智能体 — 节点实现。"""

from __future__ import annotations

import re
from datetime import date

from langchain_core.messages import HumanMessage, SystemMessage

from agent.business_explainer.prompts import EXPLAINER_SYSTEM, build_explainer_user_prompt
from agent.business_explainer.state import BusinessExplainerState
from agent.config import REPORTS_DIR
from agent.tools.data_fetcher import (
    fetch_business_explainer_data,
    fetch_web_supplement,
    resolve_company,
)
from agent.tools.progress import report as emit_progress
from agent.utils.llm import get_llm


def init_company(state: BusinessExplainerState) -> dict:
    """解析公司代码与名称。"""
    company = state["company"]
    today = date.today().isoformat()

    emit_progress("be_init", f"正在解析 {company}…", phase="resolve", status="running")
    stock = resolve_company(company)
    emit_progress(
        "be_init",
        f"已解析：{stock['name']} ({stock['code']})",
        phase="done",
        status="done",
    )

    return {
        "data_cutoff_date": today,
        "stock_code": stock["code"],
        "stock_name": stock["name"],
        "stock_market": stock["market"],
    }


def fetch_data(state: BusinessExplainerState) -> dict:
    """采集近一年交易所、巨潮、七网等官方资料（主线）。"""
    company = state["company"]
    stock = {
        "code": state.get("stock_code", ""),
        "name": state.get("stock_name", ""),
        "market": state.get("stock_market", ""),
    }

    emit_progress("be_fetch", "开始采集近一年官方披露…", phase="fetch_data", status="running")
    pack = fetch_business_explainer_data(company, stock, progress_node="be_fetch")

    n_sections = len(pack.get("sections") or {})
    emit_progress(
        "be_fetch",
        f"主线采集完成：{n_sections} 类官方数据",
        phase="fetch_data_done",
        status="done",
    )

    return {
        "data_context": pack["text"],
        "sources_used": pack.get("sources_used", []),
        "data_available": pack.get("data_available", False),
    }


def search_web_supplement(state: BusinessExplainerState) -> dict:
    """联网搜索补充最新财报与行业公开信息。失败不阻断主线。"""
    company = state["company"]
    stock = {
        "code": state.get("stock_code", ""),
        "name": state.get("stock_name", ""),
        "market": state.get("stock_market", ""),
    }

    emit_progress("be_search", "开始联网补充检索…", phase="web_search", status="running")
    pack = fetch_web_supplement(company, stock, progress_node="be_search")

    extra = pack.get("sources_used") or []
    sources = list(state.get("sources_used") or [])
    for item in extra:
        if item not in sources:
            sources.append(item)

    used = bool(pack.get("used"))
    engines = pack.get("engines") or []
    if used:
        emit_progress(
            "be_search",
            f"联网补充完成（{'+'.join(engines) or '已检索'}）",
            phase="web_search_done",
            status="done",
        )
    else:
        emit_progress(
            "be_search",
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


def generate_explanation(state: BusinessExplainerState) -> dict:
    """调用 LLM 生成通俗、全面的业务解读，并以段永平视角收尾。"""
    company = state["company"]

    emit_progress("be_explain", "正在生成业务简述…", phase="llm", status="running")

    user_prompt = build_explainer_user_prompt(
        company=company,
        stock_code=state.get("stock_code", ""),
        stock_name=state.get("stock_name", ""),
        data_cutoff_date=state.get("data_cutoff_date", ""),
        data_context=state.get("data_context", ""),
        sources=state.get("sources_used", []),
        web_context=state.get("web_context", ""),
    )

    llm = get_llm()
    response = llm.invoke(
        [SystemMessage(content=EXPLAINER_SYSTEM), HumanMessage(content=user_prompt)]
    )
    content = response.content or ""

    engines = state.get("web_engines") or []
    supplement = f"联网搜索（{'+'.join(engines)}）" if state.get("web_search_used") else "联网未启用或无结果"
    header = (
        f"# {state.get('stock_name') or company} 业务简述\n\n"
        f"> 代码: {state.get('stock_code', '')} | "
        f"数据截止: {state.get('data_cutoff_date', '')} | "
        f"范围: 仅该公司 · 商业模式 / 护城河 / 用户价值 / 近一年经营 | "
        f"主线: 交易所 · 巨潮 · 七网 · 公告PDF正文 | "
        f"补充: {supplement} | "
        f"视角: 段永平好生意标准\n\n"
    )
    brief = header + content

    emit_progress(
        "be_explain",
        f"简述完成（约 {len(brief)} 字）",
        phase="llm_done",
        status="done",
    )

    return {"brief": brief, "explanation": brief}


def save_explanation(state: BusinessExplainerState) -> dict:
    """保存解读报告。"""
    company = state["company"]
    cutoff = state.get("data_cutoff_date", date.today().isoformat()).replace("-", "")
    safe_name = re.sub(r"[^\w\u4e00-\u9fff-]", "_", state.get("stock_name") or company)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    path = REPORTS_DIR / f"{safe_name}业务简述_{cutoff}.md"

    emit_progress("be_save", "正在保存简述…", phase="save_file", status="running")
    path.write_text(state.get("brief") or state.get("explanation", ""), encoding="utf-8")
    emit_progress("be_save", f"已保存至 {path.name}", phase="done", status="done")

    return {"report_path": str(path)}
