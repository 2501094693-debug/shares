"""综合深度研判智能体 — 节点实现。"""

from __future__ import annotations

import json
import re
from datetime import date

from langchain_core.messages import HumanMessage, SystemMessage

from agent.comprehensive_analyst.prompts import (
    ANALYST_SYSTEM,
    build_assemble_header,
    build_balance_prompt,
    build_business_prompt,
    build_cashflow_prompt,
    build_income_prompt,
    build_outlook_prompt,
    build_synthesis_prompt,
    build_valuation_prompt,
)
from agent.comprehensive_analyst.state import ComprehensiveAnalystState
from agent.config import REPORTS_DIR
from agent.tools.comprehensive_data import fetch_comprehensive_data
from agent.tools.data_fetcher import resolve_company
from agent.tools.progress import report as emit_progress
from agent.utils.llm import get_llm


def _invoke_llm(user_prompt: str) -> str:
    llm = get_llm()
    response = llm.invoke([SystemMessage(content=ANALYST_SYSTEM), HumanMessage(content=user_prompt)])
    return response.content or ""


def _extract_key_drivers(text: str) -> list[dict]:
    match = re.search(r"```json\s*(\[.*?\])\s*```", text, re.DOTALL)
    if not match:
        match = re.search(r"(\[\s*\{.*?\}\s*\])", text, re.DOTALL)
    if not match:
        return []
    try:
        data = json.loads(match.group(1))
        return data if isinstance(data, list) else []
    except json.JSONDecodeError:
        return []


def init_company(state: ComprehensiveAnalystState) -> dict:
    company = state["company"]
    today = date.today().isoformat()
    emit_progress("ca_init", f"正在解析 {company}…", phase="resolve", status="running")
    stock = resolve_company(company)
    emit_progress(
        "ca_init",
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


def fetch_data(state: ComprehensiveAnalystState) -> dict:
    company = state["company"]
    stock = {
        "code": state.get("stock_code", ""),
        "name": state.get("stock_name", ""),
        "market": state.get("stock_market", ""),
    }
    emit_progress("ca_fetch", "开始采集综合研判数据…", phase="fetch_data", status="running")
    pack = fetch_comprehensive_data(company, stock, progress_node="ca_fetch")

    return {
        "data_context": pack["text"],
        "sources_used": pack.get("sources_used", []),
        "data_available": pack.get("data_available", False),
        "errors": pack.get("errors", []),
        "stock": pack.get("stock") or {},
        "industry": pack.get("industry") or {},
        "balance_rules_text": (pack.get("balance_rules") or {}).get("text", ""),
        "income_rules_text": (pack.get("income_rules") or {}).get("text", ""),
        "cashflow_rules_text": (pack.get("cashflow_rules") or {}).get("text", ""),
        "valuation_scenarios_text": (pack.get("valuation_scenarios") or {}).get("text", ""),
        "mda_text": pack.get("mda_text", ""),
    }


def analyze_business(state: ComprehensiveAnalystState) -> dict:
    emit_progress("ca_business", "正在分析业务构成与关键驱动…", phase="llm", status="running")
    prompt = build_business_prompt(
        stock_name=state.get("stock_name", ""),
        stock_code=state.get("stock_code", ""),
        data_cutoff_date=state.get("data_cutoff_date", ""),
        data_context=state.get("data_context", ""),
        mda_text=state.get("mda_text", ""),
    )
    content = _invoke_llm(prompt)
    drivers = _extract_key_drivers(content)
    emit_progress("ca_business", f"业务分析完成（{len(drivers)} 个驱动因素）", phase="llm_done", status="done")
    return {"business_analysis": content, "key_drivers": drivers}


def analyze_balance(state: ComprehensiveAnalystState) -> dict:
    emit_progress("ca_balance", "正在解读资产负债表…", phase="llm", status="running")
    prompt = build_balance_prompt(
        stock_name=state.get("stock_name", ""),
        stock_code=state.get("stock_code", ""),
        rules_text=state.get("balance_rules_text", ""),
        data_context=state.get("data_context", ""),
    )
    content = _invoke_llm(prompt)
    emit_progress("ca_balance", "资产负债表解读完成", phase="llm_done", status="done")
    return {"balance_analysis": content}


def analyze_income(state: ComprehensiveAnalystState) -> dict:
    emit_progress("ca_income", "正在解读利润表…", phase="llm", status="running")
    prompt = build_income_prompt(
        stock_name=state.get("stock_name", ""),
        stock_code=state.get("stock_code", ""),
        rules_text=state.get("income_rules_text", ""),
        data_context=state.get("data_context", ""),
    )
    content = _invoke_llm(prompt)
    emit_progress("ca_income", "利润表解读完成", phase="llm_done", status="done")
    return {"income_analysis": content}


def analyze_cashflow(state: ComprehensiveAnalystState) -> dict:
    emit_progress("ca_cashflow", "正在解读现金流量表…", phase="llm", status="running")
    prompt = build_cashflow_prompt(
        stock_name=state.get("stock_name", ""),
        stock_code=state.get("stock_code", ""),
        rules_text=state.get("cashflow_rules_text", ""),
        data_context=state.get("data_context", ""),
    )
    content = _invoke_llm(prompt)
    emit_progress("ca_cashflow", "现金流量表解读完成", phase="llm_done", status="done")
    return {"cashflow_analysis": content}


def synthesize_financials(state: ComprehensiveAnalystState) -> dict:
    emit_progress("ca_synthesis", "正在汇总三表分析…", phase="llm", status="running")
    cross = ""
    ctx = state.get("data_context", "")
    if "## 三表交叉验证" in ctx:
        cross = ctx.split("## 三表交叉验证", 1)[1].split("##", 1)[0][:3000]

    prompt = build_synthesis_prompt(
        stock_name=state.get("stock_name", ""),
        stock_code=state.get("stock_code", ""),
        balance_analysis=state.get("balance_analysis", ""),
        income_analysis=state.get("income_analysis", ""),
        cashflow_analysis=state.get("cashflow_analysis", ""),
        cross_validate=cross,
    )
    content = _invoke_llm(prompt)
    emit_progress("ca_synthesis", "三表汇总完成", phase="llm_done", status="done")
    return {"financial_synthesis": content}


def analyze_valuation(state: ComprehensiveAnalystState) -> dict:
    emit_progress("ca_valuation", "正在解读估值与三情景…", phase="llm", status="running")
    prompt = build_valuation_prompt(
        stock_name=state.get("stock_name", ""),
        stock_code=state.get("stock_code", ""),
        scenarios_text=state.get("valuation_scenarios_text", ""),
        data_context=state.get("data_context", ""),
    )
    content = _invoke_llm(prompt)
    emit_progress("ca_valuation", "估值分析完成", phase="llm_done", status="done")
    return {"valuation_report": content}


def search_market(state: ComprehensiveAnalystState) -> dict:
    from agent.tools.progress import report
    from agent.tools.web_search import search_for_comprehensive, web_search_status

    company = state["company"]
    stock = {
        "code": state.get("stock_code", ""),
        "name": state.get("stock_name", ""),
    }
    industry = state.get("industry") or {}
    industry_name = str(industry.get("name") or industry.get("l3_name") or "")

    available, hint = web_search_status()
    if not available:
        report("ca_search", hint, phase="web_search_skip", status="done")
        return {"market_intel": ""}

    report("ca_search", f"联网检索市场信息（{hint}）…", phase="web_search", status="running")
    text, engines = search_for_comprehensive(
        company,
        industry_name=industry_name,
        stock_code=stock["code"],
        progress_cb=lambda q: report("ca_search", f"检索：{q}", phase="web_search"),
    )
    report("ca_search", "市场信息检索完成", phase="web_search_done", status="done")
    out: dict = {"market_intel": text}
    if engines:
        out["sources_used"] = list(state.get("sources_used") or []) + [f"联网补充（{', '.join(engines)}）"]
    return out


def analyze_outlook(state: ComprehensiveAnalystState) -> dict:
    emit_progress("ca_outlook", "正在研判未来前景…", phase="llm", status="running")
    prompt = build_outlook_prompt(
        stock_name=state.get("stock_name", ""),
        stock_code=state.get("stock_code", ""),
        key_drivers=state.get("key_drivers") or [],
        business_analysis=state.get("business_analysis", ""),
        financial_synthesis=state.get("financial_synthesis", ""),
        valuation_report=state.get("valuation_report", ""),
        market_intel=state.get("market_intel", ""),
    )
    content = _invoke_llm(prompt)
    emit_progress("ca_outlook", "前景研判完成", phase="llm_done", status="done")
    return {"outlook_report": content}


def assemble_report(state: ComprehensiveAnalystState) -> dict:
    emit_progress("ca_assemble", "正在拼装最终报告…", phase="llm", status="running")

    header = build_assemble_header(
        stock_name=state.get("stock_name", ""),
        stock_code=state.get("stock_code", ""),
        industry=state.get("industry") or {},
        data_cutoff_date=state.get("data_cutoff_date", ""),
    )

    sections = [
        ("一、公司概览与业务构成", state.get("business_analysis", "")),
        ("二、资产负债表分析", state.get("balance_analysis", "")),
        ("三、利润表分析", state.get("income_analysis", "")),
        ("四、现金流量表分析", state.get("cashflow_analysis", "")),
        ("五、财务综合分析", state.get("financial_synthesis", "")),
        ("六、估值分析（三情景）", state.get("valuation_report", "")),
        ("七、市场前景与风险提示", state.get("outlook_report", "")),
    ]

    body_parts = []
    for title, content in sections:
        body_parts.append(f"## {title}\n\n{content}")

    appendix = [
        "## 八、附录\n",
        "### A. 三情景估值（程序预计算）\n",
        state.get("valuation_scenarios_text", ""),
        "\n### B. 规则引擎输出\n",
        "#### 资产负债表\n",
        state.get("balance_rules_text", ""),
        "\n#### 利润表\n",
        state.get("income_rules_text", ""),
        "\n#### 现金流量表\n",
        state.get("cashflow_rules_text", ""),
        "\n### C. 数据来源\n",
        "\n".join(f"- {s}" for s in (state.get("sources_used") or [])) or "- （无）",
        "\n### D. 分析局限性\n",
        "- 利润表/现金流量表为报告期累计数，非单季度\n"
        "- 分部数据依赖东财 F10，部分公司可能未披露\n"
        "- 估值情景基于历史分位与假设增速，实际可能与假设偏离\n"
        "- 联网补充信息仅供参考，硬事实以法定披露为准",
    ]

    report = header + "\n\n".join(body_parts) + "\n\n" + "\n".join(appendix)
    emit_progress("ca_assemble", f"报告拼装完成（约 {len(report)} 字）", phase="llm_done", status="done")
    return {"final_report": report, "report": report}


def save_report(state: ComprehensiveAnalystState) -> dict:
    company = state["company"]
    cutoff = state.get("data_cutoff_date", date.today().isoformat()).replace("-", "")
    safe_name = re.sub(r"[^\w\u4e00-\u9fff-]", "_", state.get("stock_name") or company)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    path = REPORTS_DIR / f"{safe_name}综合深度分析_{cutoff}.md"

    emit_progress("ca_save", "正在保存报告…", phase="save_file", status="running")
    path.write_text(state.get("final_report") or state.get("report") or "", encoding="utf-8")
    emit_progress("ca_save", f"已保存至 {path.name}", phase="done", status="done")
    return {"report_path": str(path)}
