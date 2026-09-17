"""张新民「八看」财报解读智能体 — 节点实现。"""

from __future__ import annotations

import re
from datetime import date

from langchain_core.messages import HumanMessage, SystemMessage

from agent.bazhang_analyst.prompts import (
    ANALYST_SYSTEM,
    build_assemble_header,
    build_cost_prompt,
    build_operating_prompt,
    build_outlook_prompt,
    build_profit_prompt,
    build_quality_prompt,
    build_risk_prompt,
    build_strategy_prompt,
    build_synthesis_prompt,
    build_value_prompt,
)
from agent.bazhang_analyst.state import BazhangAnalystState
from agent.config import REPORTS_DIR
from agent.tools.bazhang_data import fetch_bazhang_data
from agent.tools.data_fetcher import resolve_company
from agent.tools.progress import report as emit_progress
from agent.utils.llm import get_llm


def _invoke_llm(user_prompt: str) -> str:
    llm = get_llm()
    response = llm.invoke([SystemMessage(content=ANALYST_SYSTEM), HumanMessage(content=user_prompt)])
    return response.content or ""


def _zhang_ctx(state: BazhangAnalystState) -> dict:
    return {
        "stock_name": state.get("stock_name", ""),
        "stock_code": state.get("stock_code", ""),
        "data_cutoff_date": state.get("data_cutoff_date", ""),
        "strategy_type": state.get("strategy_type", "未知"),
        "zhang_summary": state.get("zhang_summary", ""),
        "flags": state.get("zhang_flags") or [],
        "tables": state.get("zhang_tables") or {},
        "data_context": state.get("data_context", ""),
    }


def init_company(state: BazhangAnalystState) -> dict:
    company = state["company"]
    today = date.today().isoformat()
    emit_progress("bz_init", f"正在解析 {company}…", phase="resolve", status="running")
    stock = resolve_company(company)
    emit_progress("bz_init", f"已解析：{stock['name']} ({stock['code']})", phase="done", status="done")
    return {
        "data_cutoff_date": today,
        "stock_code": stock["code"],
        "stock_name": stock["name"],
        "stock_market": stock["market"],
    }


def fetch_data(state: BazhangAnalystState) -> dict:
    company = state["company"]
    stock = {
        "code": state.get("stock_code", ""),
        "name": state.get("stock_name", ""),
        "market": state.get("stock_market", ""),
    }
    emit_progress("bz_fetch", "开始采集八看分析数据…", phase="fetch_data", status="running")
    pack = fetch_bazhang_data(company, stock, progress_node="bz_fetch")
    zhang = pack.get("zhang") or {}
    return {
        "data_context": pack.get("text", ""),
        "sources_used": pack.get("sources_used", []),
        "data_available": pack.get("data_available", False),
        "errors": pack.get("errors", []),
        "stock": pack.get("stock") or {},
        "industry": pack.get("industry") or {},
        "zhang_metrics": zhang.get("metrics") or {},
        "zhang_flags": zhang.get("flags") or [],
        "zhang_tables": zhang.get("tables") or {},
        "zhang_summary": zhang.get("text", ""),
        "strategy_type": zhang.get("strategy_type", "未知"),
    }


def analyze_strategy(state: BazhangAnalystState) -> dict:
    emit_progress("bz_strategy", "一看：战略分析…", phase="llm", status="running")
    ctx = _zhang_ctx(state)
    prompt = build_strategy_prompt(
        stock_name=ctx["stock_name"],
        stock_code=ctx["stock_code"],
        data_cutoff_date=ctx["data_cutoff_date"],
        strategy_type=ctx["strategy_type"],
        zhang_summary=ctx["zhang_summary"],
        flags=ctx["flags"],
        table=ctx["tables"].get("asset_structure", ""),
        data_context=ctx["data_context"],
    )
    content = _invoke_llm(prompt)
    emit_progress("bz_strategy", "一看完成", phase="llm_done", status="done")
    return {"section_strategy": content}


def analyze_operating(state: BazhangAnalystState) -> dict:
    emit_progress("bz_operating", "二看：经营资产管理…", phase="llm", status="running")
    ctx = _zhang_ctx(state)
    prompt = build_operating_prompt(
        stock_name=ctx["stock_name"],
        stock_code=ctx["stock_code"],
        data_cutoff_date=ctx["data_cutoff_date"],
        strategy_type=ctx["strategy_type"],
        zhang_summary=ctx["zhang_summary"],
        flags=ctx["flags"],
        table=ctx["tables"].get("competitiveness", ""),
    )
    content = _invoke_llm(prompt)
    emit_progress("bz_operating", "二看完成", phase="llm_done", status="done")
    return {"section_operating": content}


def analyze_profit(state: BazhangAnalystState) -> dict:
    emit_progress("bz_profit", "三看：效益与质量…", phase="llm", status="running")
    ctx = _zhang_ctx(state)
    prompt = build_profit_prompt(
        stock_name=ctx["stock_name"],
        stock_code=ctx["stock_code"],
        data_cutoff_date=ctx["data_cutoff_date"],
        strategy_type=ctx["strategy_type"],
        zhang_summary=ctx["zhang_summary"],
        flags=ctx["flags"],
        table=ctx["tables"].get("core_profit", ""),
    )
    content = _invoke_llm(prompt)
    emit_progress("bz_profit", "三看完成", phase="llm_done", status="done")
    return {"section_profit": content}


def analyze_value(state: BazhangAnalystState) -> dict:
    emit_progress("bz_value", "四看：价值创造…", phase="llm", status="running")
    ctx = _zhang_ctx(state)
    prompt = build_value_prompt(
        stock_name=ctx["stock_name"],
        stock_code=ctx["stock_code"],
        data_cutoff_date=ctx["data_cutoff_date"],
        strategy_type=ctx["strategy_type"],
        zhang_summary=ctx["zhang_summary"],
        flags=ctx["flags"],
        table=ctx["tables"].get("value", ""),
    )
    content = _invoke_llm(prompt)
    emit_progress("bz_value", "四看完成", phase="llm_done", status="done")
    return {"section_value": content}


def analyze_cost(state: BazhangAnalystState) -> dict:
    emit_progress("bz_cost", "五看：成本决定机制…", phase="llm", status="running")
    ctx = _zhang_ctx(state)
    prompt = build_cost_prompt(
        stock_name=ctx["stock_name"],
        stock_code=ctx["stock_code"],
        data_cutoff_date=ctx["data_cutoff_date"],
        strategy_type=ctx["strategy_type"],
        zhang_summary=ctx["zhang_summary"],
        flags=ctx["flags"],
        table=ctx["tables"].get("cost_structure", ""),
    )
    content = _invoke_llm(prompt)
    emit_progress("bz_cost", "五看完成", phase="llm_done", status="done")
    return {"section_cost": content}


def analyze_quality(state: BazhangAnalystState) -> dict:
    emit_progress("bz_quality", "六看：财务状况质量…", phase="llm", status="running")
    ctx = _zhang_ctx(state)
    tables = ctx["tables"]
    prompt = build_quality_prompt(
        stock_name=ctx["stock_name"],
        stock_code=ctx["stock_code"],
        data_cutoff_date=ctx["data_cutoff_date"],
        strategy_type=ctx["strategy_type"],
        zhang_summary=ctx["zhang_summary"],
        flags=ctx["flags"],
        asset_table=tables.get("asset_structure", ""),
        liab_table=tables.get("liability_structure", ""),
        cash_table=tables.get("cash_quality", ""),
    )
    content = _invoke_llm(prompt)
    emit_progress("bz_quality", "六看完成", phase="llm_done", status="done")
    return {"section_quality": content}


def analyze_risk(state: BazhangAnalystState) -> dict:
    emit_progress("bz_risk", "七看：风险分析…", phase="llm", status="running")
    ctx = _zhang_ctx(state)
    prompt = build_risk_prompt(
        stock_name=ctx["stock_name"],
        stock_code=ctx["stock_code"],
        data_cutoff_date=ctx["data_cutoff_date"],
        strategy_type=ctx["strategy_type"],
        zhang_summary=ctx["zhang_summary"],
        flags=ctx["flags"],
    )
    content = _invoke_llm(prompt)
    emit_progress("bz_risk", "七看完成", phase="llm_done", status="done")
    return {"section_risk": content}


def analyze_outlook(state: BazhangAnalystState) -> dict:
    emit_progress("bz_outlook", "八看：前景研判…", phase="llm", status="running")
    ctx = _zhang_ctx(state)
    prompt = build_outlook_prompt(
        stock_name=ctx["stock_name"],
        stock_code=ctx["stock_code"],
        data_cutoff_date=ctx["data_cutoff_date"],
        strategy_type=ctx["strategy_type"],
        zhang_summary=ctx["zhang_summary"],
        flags=ctx["flags"],
        data_context=ctx["data_context"],
    )
    content = _invoke_llm(prompt)
    emit_progress("bz_outlook", "八看完成", phase="llm_done", status="done")
    return {"section_outlook": content}


def synthesize(state: BazhangAnalystState) -> dict:
    emit_progress("bz_synthesis", "综合诊断…", phase="llm", status="running")
    tables = state.get("zhang_tables") or {}
    prompt = build_synthesis_prompt(
        stock_name=state.get("stock_name", ""),
        stock_code=state.get("stock_code", ""),
        strategy_type=state.get("strategy_type", "未知"),
        diagnosis_table=tables.get("diagnosis", ""),
        section_strategy=state.get("section_strategy", ""),
        section_operating=state.get("section_operating", ""),
        section_profit=state.get("section_profit", ""),
        section_value=state.get("section_value", ""),
        section_cost=state.get("section_cost", ""),
        section_quality=state.get("section_quality", ""),
        section_risk=state.get("section_risk", ""),
        section_outlook=state.get("section_outlook", ""),
    )
    content = _invoke_llm(prompt)
    emit_progress("bz_synthesis", "综合诊断完成", phase="llm_done", status="done")
    return {"section_synthesis": content}


def assemble_report(state: BazhangAnalystState) -> dict:
    emit_progress("bz_assemble", "拼装报告…", phase="llm", status="running")
    header = build_assemble_header(
        stock_name=state.get("stock_name", ""),
        stock_code=state.get("stock_code", ""),
        industry=state.get("industry") or {},
        data_cutoff_date=state.get("data_cutoff_date", ""),
        strategy_type=state.get("strategy_type", "未知"),
    )

    tables = state.get("zhang_tables") or {}
    sections = [
        ("一看：战略——资源配置揭示什么？", state.get("section_strategy", ""), tables.get("asset_structure", "")),
        ("二看：经营资产管理与竞争力", state.get("section_operating", ""), tables.get("competitiveness", "")),
        ("三看：效益与质量（核心利润视角）", state.get("section_profit", ""), tables.get("core_profit", "")),
        ("四看：价值创造", state.get("section_value", ""), tables.get("value", "")),
        ("五看：成本决定机制", state.get("section_cost", ""), tables.get("cost_structure", "")),
        (
            "六看：财务状况质量",
            state.get("section_quality", ""),
            "\n".join(
                filter(
                    None,
                    [
                        "#### 资产结构\n" + tables.get("asset_structure", ""),
                        "#### 负债结构\n" + tables.get("liability_structure", ""),
                        "#### 现金流质量\n" + tables.get("cash_quality", ""),
                    ],
                )
            ),
        ),
        ("七看：风险", state.get("section_risk", ""), ""),
        ("八看：前景", state.get("section_outlook", ""), ""),
        ("综合诊断", state.get("section_synthesis", ""), tables.get("diagnosis", "")),
    ]

    body_parts: list[str] = []
    for title, content, table in sections:
        part = f"## {title}\n\n"
        if table:
            part += f"### 原始数据\n\n{table}\n\n"
        part += f"### 解读\n\n{content}"
        body_parts.append(part)

    flags = state.get("zhang_flags") or []
    appendix = [
        "## 附录\n",
        "### 规则引擎预计算摘要\n",
        state.get("zhang_summary", ""),
        "\n### 风险警示清单\n",
        "\n".join(f"- {f}" for f in flags) if flags else "- 暂无",
        "\n### 数据来源\n",
        "\n".join(f"- {s}" for s in (state.get("sources_used") or [])) or "- （无）",
        "\n### 分析局限性\n",
        "- 利润表/现金流量表为报告期累计数，非单季度\n"
        "- 资产/负债分类基于东财 F10 科目映射，部分行业可能有口径差异\n"
        "- 核心利润按张新民定义计算，与净利润存在口径差异\n"
        "- 本报告为财务状况质量诊断，不构成投资建议",
    ]

    report_text = header + "\n\n" + "\n\n".join(body_parts) + "\n\n" + "\n".join(appendix)
    emit_progress("bz_assemble", f"报告拼装完成（约 {len(report_text)} 字）", phase="llm_done", status="done")
    return {"final_report": report_text, "report": report_text}


def save_report(state: BazhangAnalystState) -> dict:
    company = state["company"]
    cutoff = state.get("data_cutoff_date", date.today().isoformat()).replace("-", "")
    safe_name = re.sub(r"[^\w\u4e00-\u9fff-]", "_", state.get("stock_name") or company)
    code = state.get("stock_code", "")
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    path = REPORTS_DIR / f"{safe_name}_{code}八看财报解读_{cutoff}.md"

    emit_progress("bz_save", "正在保存报告…", phase="save_file", status="running")
    path.write_text(state.get("final_report") or state.get("report") or "", encoding="utf-8")
    emit_progress("bz_save", f"已保存至 {path.name}", phase="done", status="done")
    return {"report_path": str(path)}
