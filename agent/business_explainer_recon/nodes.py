"""业务解读智能体（复原版）— 节点实现。

节点逻辑为冻结版；仅「生成解读」的头文案与落盘文件名按报告复原
（原版为「业务简述」，本复原版为「业务解读」）。
"""

from __future__ import annotations

import re
from datetime import date

from langchain_core.messages import HumanMessage, SystemMessage

from .config import REPORTS_DIR
from .data_fetcher import fetch_business_explainer_data, resolve_company
from .prompts import EXPLAINER_SYSTEM, build_explainer_user_prompt
from .state import BusinessExplainerState
from .tools.progress import report as emit_progress
from .utils.llm import get_llm


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
    """采集近一年财报、公告、新闻等资料。"""
    company = state["company"]
    stock = {
        "code": state.get("stock_code", ""),
        "name": state.get("stock_name", ""),
        "market": state.get("stock_market", ""),
    }

    emit_progress("be_fetch", "开始采集近一年公开资料…", phase="fetch_data", status="running")
    pack = fetch_business_explainer_data(company, stock, progress_node="be_fetch")

    n_sections = len(pack.get("sections") or {})
    emit_progress(
        "be_fetch",
        f"采集完成：{n_sections} 类数据",
        phase="fetch_data_done",
        status="done",
    )

    return {
        "data_context": pack["text"],
        "sources_used": pack.get("sources_used", []),
        "data_available": pack.get("data_available", False),
    }


def generate_explanation(state: BusinessExplainerState) -> dict:
    """调用 LLM 生成通俗业务解读。"""
    company = state["company"]

    emit_progress("be_explain", "正在生成业务解读…", phase="llm", status="running")

    user_prompt = build_explainer_user_prompt(
        company=company,
        stock_code=state.get("stock_code", ""),
        stock_name=state.get("stock_name", ""),
        data_cutoff_date=state.get("data_cutoff_date", ""),
        data_context=state.get("data_context", ""),
        sources=state.get("sources_used", []),
    )

    llm = get_llm()
    response = llm.invoke(
        [SystemMessage(content=EXPLAINER_SYSTEM), HumanMessage(content=user_prompt)]
    )
    content = response.content or ""

    # 复原版头部（对应报告首行）
    header = (
        f"# {state.get('stock_name') or company} 公司业务解读\n\n"
        f"> 代码: {state.get('stock_code', '')} | "
        f"数据截止: {state.get('data_cutoff_date', '')} | "
        f"资料窗口: 近一年年报/半年报/季报 + 公告 + 新闻\n\n"
    )
    brief = header + content

    emit_progress(
        "be_explain",
        f"解读完成（约 {len(brief)} 字）",
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
    path = REPORTS_DIR / f"{safe_name}业务解读_{cutoff}.md"

    emit_progress("be_save", "正在保存解读…", phase="save_file", status="running")
    path.write_text(state.get("brief") or state.get("explanation", ""), encoding="utf-8")
    emit_progress("be_save", f"已保存至 {path.name}", phase="done", status="done")

    return {"report_path": str(path)}
