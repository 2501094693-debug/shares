"""近一年财报解读智能体 — 节点实现。"""

from __future__ import annotations

import re
from datetime import date

from langchain_core.messages import HumanMessage, SystemMessage

from agent.config import REPORTS_DIR
from agent.earnings_reviewer.prompts import REVIEWER_SYSTEM, build_reviewer_user_prompt
from agent.earnings_reviewer.state import EarningsReviewerState
from agent.tools.data_fetcher import fetch_earnings_reviewer_data, resolve_company
from agent.tools.progress import report as emit_progress
from agent.utils.llm import get_llm


def init_company(state: EarningsReviewerState) -> dict:
    """解析公司代码与名称。"""
    company = state["company"]
    today = date.today().isoformat()

    emit_progress("er_init", f"正在解析 {company}…", phase="resolve", status="running")
    stock = resolve_company(company)
    emit_progress(
        "er_init",
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


def fetch_data(state: EarningsReviewerState) -> dict:
    """采集近一年财报原始科目、估值与定期报告公告。"""
    company = state["company"]
    stock = {
        "code": state.get("stock_code", ""),
        "name": state.get("stock_name", ""),
        "market": state.get("stock_market", ""),
    }

    emit_progress("er_fetch", "开始采集财报与估值原始数据…", phase="fetch_data", status="running")
    pack = fetch_earnings_reviewer_data(company, stock, progress_node="er_fetch")

    n_sections = len(pack.get("sections") or {})
    emit_progress(
        "er_fetch",
        f"采集完成：{n_sections} 类数据",
        phase="fetch_data_done",
        status="done",
    )

    return {
        "data_context": pack["text"],
        "sources_used": pack.get("sources_used", []),
        "data_available": pack.get("data_available", False),
    }


def generate_review(state: EarningsReviewerState) -> dict:
    """调用 LLM 生成附带原始数据的财报解读。"""
    company = state["company"]

    emit_progress("er_explain", "正在生成财报解读…", phase="llm", status="running")

    user_prompt = build_reviewer_user_prompt(
        company=company,
        stock_code=state.get("stock_code", ""),
        stock_name=state.get("stock_name", ""),
        data_cutoff_date=state.get("data_cutoff_date", ""),
        data_context=state.get("data_context", ""),
        sources=state.get("sources_used", []),
    )

    llm = get_llm()
    response = llm.invoke(
        [SystemMessage(content=REVIEWER_SYSTEM), HumanMessage(content=user_prompt)]
    )
    content = response.content or ""

    header = (
        f"# {state.get('stock_name') or company} 近一年财报解读\n\n"
        f"> 代码: {state.get('stock_code', '')} | "
        f"数据截止: {state.get('data_cutoff_date', '')} | "
        f"范围: 近一年定期报告 · 近3-5年趋势对照 · 巴菲特视角估值 | "
        f"来源: 东财F10报表 · 盘口估值 · 巨潮/交易所公告\n\n"
    )
    report = header + content

    emit_progress(
        "er_explain",
        f"解读完成（约 {len(report)} 字）",
        phase="llm_done",
        status="done",
    )

    return {"report": report}


def save_review(state: EarningsReviewerState) -> dict:
    """保存财报解读报告。"""
    company = state["company"]
    cutoff = state.get("data_cutoff_date", date.today().isoformat()).replace("-", "")
    safe_name = re.sub(r"[^\w\u4e00-\u9fff-]", "_", state.get("stock_name") or company)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    path = REPORTS_DIR / f"{safe_name}财报解读_{cutoff}.md"

    emit_progress("er_save", "正在保存解读…", phase="save_file", status="running")
    path.write_text(state.get("report") or "", encoding="utf-8")
    emit_progress("er_save", f"已保存至 {path.name}", phase="done", status="done")

    return {"report_path": str(path)}
