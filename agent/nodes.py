"""LangGraph 节点实现。"""

from __future__ import annotations

import re
from datetime import date

from langchain_core.messages import HumanMessage, SystemMessage

from agent.agents.prompts import (
    ROLE_META,
    TASK_SUBJECTS,
    TEAM_LEAD_SYSTEM,
    build_analyst_system_prompt,
    build_analyst_user_prompt,
    build_team_lead_user_prompt,
)
from agent.config import REPORTS_DIR
from agent.state import AnalystReport, InvestmentTeamState
from agent.tools.data_fetcher import fetch_role_data, resolve_company
from agent.tools.progress import report as emit_progress
from agent.tools.web_search import web_search_status
from agent.utils.llm import get_llm


def _extract_score(content: str) -> float | None:
    patterns = [
        r"综合评分[：:]\s*([\d.]+)\s*/?\s*5",
        r"总体评分[：:]\s*([\d.]+)\s*/?\s*5",
        r"评分[：:]\s*([\d.]+)\s*星",
    ]
    for pat in patterns:
        match = re.search(pat, content)
        if match:
            try:
                return float(match.group(1))
            except ValueError:
                pass
    return None


def init_research(state: InvestmentTeamState) -> dict:
    """初始化：解析股票、确认日期、评估信息丰富度、检测联网能力。"""
    company = state["company"]
    today = date.today().isoformat()

    emit_progress("init", "正在解析股票代码与公司信息…", phase="resolve", status="running")
    stock = resolve_company(company)
    emit_progress(
        "init",
        f"已解析：{stock['name']} ({stock['code']})，市场 {stock['market']}",
        phase="resolve",
        status="running",
    )

    web_ok, web_reason = web_search_status()
    if web_ok:
        emit_progress("init", f"联网搜索可用（{web_reason}）", phase="assess", status="running")
    else:
        emit_progress(
            "init",
            f"⚠️ 联网搜索不可用：{web_reason}",
            phase="assess",
            status="running",
            level="warn",
        )

    emit_progress("init", "正在评估信息丰富度（A/B/C）…", phase="assess", status="running")
    llm = get_llm()
    assess_prompt = f"""评估「{company}」（代码: {stock['code']}，市场: {stock['market']}）的 AI 可研究性（信息丰富度），输出 A/B/C 等级及一句话理由。

A级：上市多年、券商覆盖广
B级：上市不久、覆盖有限
C级：冷门/新上市/新兴市场

只输出两行：
等级: A/B/C
理由: （一句话）"""

    response = llm.invoke([HumanMessage(content=assess_prompt)])
    text = response.content or ""
    level_match = re.search(r"等级[：:]\s*([ABC])", text, re.I)
    rationale_match = re.search(r"理由[：:]\s*(.+)", text)

    info_level = (level_match.group(1).upper() if level_match else "B")
    rationale = rationale_match.group(1).strip() if rationale_match else "默认中等信息充分度"

    emit_progress(
        "init",
        f"信息丰富度 {info_level}：{rationale}",
        phase="done",
        status="done",
    )

    return {
        "data_cutoff_date": today,
        "web_search_available": web_ok,
        "info_richness": info_level,
        "info_richness_rationale": rationale,
        "stock_code": stock["code"],
        "stock_name": stock["name"],
        "stock_market": stock["market"],
        "analyst_reports": [],
        "completed_roles": [],
    }


def run_analyst(role: str, state: InvestmentTeamState) -> dict:
    company = state["company"]
    meta = ROLE_META[role]
    node = role.replace("-", "_")
    stock = {
        "code": state.get("stock_code", ""),
        "name": state.get("stock_name", ""),
        "market": state.get("stock_market", ""),
    }

    emit_progress(
        node,
        f"开始任务：{TASK_SUBJECTS[role].format(company=company)}",
        phase="start",
        status="running",
    )

    data_pack = fetch_role_data(
        role,
        company,
        stock,
        progress_node=node,
        enable_web_search=state.get("web_search_available", False),
    )
    data_context = data_pack["text"]
    data_available = data_pack["data_available"]
    sources = data_pack.get("sources_used", [])
    web_search_used = data_pack.get("web_search_used", False)

    emit_progress(node, "正在调用 LLM 撰写分析报告…", phase="llm", status="running")

    system = build_analyst_system_prompt(
        role=role,
        company=company,
        info_richness=state.get("info_richness", "B"),
        data_cutoff_date=state.get("data_cutoff_date", ""),
        data_available=data_available,
        web_search_available=state.get("web_search_available", False),
        web_search_used=web_search_used,
        sources=sources,
    )
    user = build_analyst_user_prompt(role, company, data_context)

    llm = get_llm()
    response = llm.invoke([SystemMessage(content=system), HumanMessage(content=user)])
    content = response.content or ""

    score = _extract_score(content)
    score_note = f"，评分 {score}/5" if score else ""
    emit_progress(
        node,
        f"报告撰写完成（约 {len(content)} 字{score_note}）",
        phase="done",
        status="done",
    )

    analyst_report: AnalystReport = {
        "role": role,
        "role_cn": meta["role_cn"],
        "framework": meta["framework"],
        "subject": TASK_SUBJECTS[role].format(company=company),
        "content": content,
        "score": score,
        "web_search_used": web_search_used,
        "confidence_note": (
            "结构化数据 + 联网搜索" if web_search_used and data_available
            else "联网搜索" if web_search_used
            else "结构化数据" if data_available
            else "数据获取失败/降级"
        ),
    }

    return {
        "analyst_reports": [analyst_report],
        "completed_roles": [role],
    }


def run_business_analyst(state: InvestmentTeamState) -> dict:
    return run_analyst("business-analyst", state)


def run_financial_analyst(state: InvestmentTeamState) -> dict:
    return run_analyst("financial-analyst", state)


def run_industry_researcher(state: InvestmentTeamState) -> dict:
    return run_analyst("industry-researcher", state)


def run_risk_assessor(state: InvestmentTeamState) -> dict:
    return run_analyst("risk-assessor", state)


def synthesize_report(state: InvestmentTeamState) -> dict:
    company = state["company"]
    reports = state.get("analyst_reports", [])

    emit_progress(
        "team_lead",
        f"正在综合 {len(reports)} 份分析师报告，撰写最终投资建议…",
        phase="synthesize",
        status="running",
    )

    llm = get_llm()
    user_prompt = build_team_lead_user_prompt(
        company=company,
        info_richness=state.get("info_richness", "B"),
        info_rationale=state.get("info_richness_rationale", ""),
        data_cutoff_date=state.get("data_cutoff_date", ""),
        reports=reports,
    )
    response = llm.invoke(
        [SystemMessage(content=TEAM_LEAD_SYSTEM), HumanMessage(content=user_prompt)]
    )
    final_report = response.content or ""

    any_web_search = any(r.get("web_search_used") for r in reports)
    header = (
        f"# {company} 投资研究报告\n\n"
        f"> 数据截止日: {state.get('data_cutoff_date', '')} | "
        f"代码: {state.get('stock_code', '')} | "
        f"信息丰富度: {state.get('info_richness', 'B')} | "
        f"数据来源: 公告/财报/新闻"
        f"{' + 联网搜索' if any_web_search else ''}\n\n"
    )
    final_report = header + final_report

    emit_progress(
        "team_lead",
        f"最终报告生成完成（约 {len(final_report)} 字）",
        phase="done",
        status="done",
    )

    return {"final_report": final_report}


def _format_role_appendix(reports: list[AnalystReport]) -> str:
    order = (
        "business-analyst",
        "financial-analyst",
        "industry-researcher",
        "risk-assessor",
    )
    by_role = {str(r.get("role") or ""): r for r in reports if r.get("role")}
    blocks = ["---", "", "# 附录：分角色完整报告", ""]
    seen: set[str] = set()
    for role in (*order, *by_role):
        if role in seen or role not in by_role:
            continue
        seen.add(role)
        report = by_role[role]
        score = report.get("score")
        score_note = f"评分 {score}/5" if score is not None else "未评分"
        conf = report.get("confidence_note") or ""
        blocks.append(f"<!-- ROLE:{role} -->")
        blocks.append(f"## {report.get('role_cn', role)}（{report.get('framework', '')}）")
        blocks.append(f"> {score_note}" + (f" · {conf}" if conf else ""))
        blocks.append("")
        blocks.append((report.get("content") or "（无正文）").rstrip())
        blocks.append("")
    return "\n".join(blocks).rstrip() + "\n"


def save_report(state: InvestmentTeamState) -> dict:
    company = state["company"]
    cutoff = state.get("data_cutoff_date", date.today().isoformat()).replace("-", "")
    safe_name = re.sub(r"[^\w\u4e00-\u9fff-]", "_", company)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    path = REPORTS_DIR / f"{safe_name}投资研究报告_{cutoff}.md"

    body = (state.get("final_report") or "").rstrip()
    reports = state.get("analyst_reports") or []
    if reports:
        body = f"{body}\n\n{_format_role_appendix(reports)}" if body else _format_role_appendix(reports)

    emit_progress("save", "正在写入报告文件…", phase="save_file", status="running")
    path.write_text(body, encoding="utf-8")
    emit_progress("save", f"已保存至 {path.name}", phase="done", status="done")

    return {"report_path": str(path)}


def run_audit_extract(state: InvestmentTeamState) -> dict:
    from agent.tools.berkshire_tools import extract_audit_items

    report_path = state.get("report_path", "")
    if not report_path:
        emit_progress("audit", "无报告文件，跳过抽检", phase="done", status="done")
        return {"audit_extracted": "（无报告文件）"}

    emit_progress("audit", "正在提取数据抽检清单（15% 抽样）…", phase="audit_extract", status="running")
    result = extract_audit_items(report_path)
    emit_progress("audit", "抽检清单提取完成", phase="done", status="done")
    return {"audit_extracted": result}
