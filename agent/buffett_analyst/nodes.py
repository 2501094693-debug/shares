"""巴菲特读表智能体 — 节点实现。"""

from __future__ import annotations

import logging
import re
from datetime import date

from langchain_core.messages import HumanMessage, SystemMessage

from agent.buffett_analyst.layout import (
    flags_as_table,
    has_prose,
    llm_text,
    render_section,
    rule_engine_fallback,
)
from agent.buffett_analyst.prompts import (
    ANALYST_SYSTEM,
    build_assemble_header,
    build_capital_prompt,
    build_honesty_prompt,
    build_owner_prompt,
    build_synthesis_prompt,
    build_understand_prompt,
)
from agent.buffett_analyst.state import BuffettAnalystState
from agent.config import REPORTS_DIR
from agent.tools.buffett_data import fetch_buffett_data
from agent.tools.data_fetcher import resolve_company
from agent.tools.progress import report as emit_progress
from agent.utils.llm import get_llm

logger = logging.getLogger(__name__)


def _invoke_llm(user_prompt: str) -> str:
    llm = get_llm()
    response = llm.invoke([SystemMessage(content=ANALYST_SYSTEM), HumanMessage(content=user_prompt)])
    return llm_text(getattr(response, "content", None))


def _named_context(data_context: str, heading: str, limit: int = 3000) -> str:
    marker = f"## {heading}"
    idx = (data_context or "").find(marker)
    if idx < 0:
        return ""
    rest = data_context[idx + len(marker) :]
    next_h = rest.find("\n## ")
    body = rest[:next_h] if next_h >= 0 else rest
    return (marker + body).strip()[:limit]


def _generate_section(title: str, prompt: str, fallback: str) -> str:
    content = _invoke_llm(prompt)
    if has_prose(content, title):
        return content
    logger.warning("巴菲特读表章节「%s」首次返回空或过短（%s 字），重试一次", title, len(content or ""))
    content = _invoke_llm(prompt)
    if has_prose(content, title):
        return content
    logger.warning("巴菲特读表章节「%s」仍无有效解读，改用规则引擎回退", title)
    return fallback


def _ctx(state: BuffettAnalystState) -> dict:
    return {
        "stock_name": state.get("stock_name", ""),
        "stock_code": state.get("stock_code", ""),
        "data_cutoff_date": state.get("data_cutoff_date", ""),
        "business_type": state.get("business_type", "未知"),
        "buffett_summary": state.get("buffett_summary", ""),
        "flags": state.get("buffett_flags") or [],
        "tables": state.get("buffett_tables") or {},
        "data_context": state.get("data_context", ""),
    }


def _understand_verdict(text: str) -> str:
    blob = text or ""
    if "部分看懂" in blob:
        return "部分看懂"
    if "看不懂" in blob:
        return "看不懂"
    if "能看懂" in blob:
        return "能看懂"
    return "未明确"


def init_company(state: BuffettAnalystState) -> dict:
    company = state["company"]
    today = date.today().isoformat()
    emit_progress("bf_init", f"正在解析 {company}…", phase="resolve", status="running")
    stock = resolve_company(company)
    emit_progress("bf_init", f"已解析：{stock['name']} ({stock['code']})", phase="done", status="done")
    return {
        "data_cutoff_date": today,
        "stock_code": stock["code"],
        "stock_name": stock["name"],
        "stock_market": stock["market"],
    }


def fetch_data(state: BuffettAnalystState) -> dict:
    company = state["company"]
    stock = {
        "code": state.get("stock_code", ""),
        "name": state.get("stock_name", ""),
        "market": state.get("stock_market", ""),
    }
    emit_progress("bf_fetch", "开始采集巴菲特读表数据…", phase="fetch_data", status="running")
    pack = fetch_buffett_data(company, stock, progress_node="bf_fetch")
    buffett = pack.get("buffett") or {}
    return {
        "data_context": pack.get("text", ""),
        "sources_used": pack.get("sources_used", []),
        "data_available": pack.get("data_available", False),
        "errors": pack.get("errors", []),
        "stock": pack.get("stock") or {},
        "industry": pack.get("industry") or {},
        "buffett_metrics": buffett.get("metrics") or {},
        "buffett_flags": buffett.get("flags") or [],
        "buffett_tables": buffett.get("tables") or {},
        "buffett_summary": buffett.get("text", ""),
        "business_type": buffett.get("business_type", "未知"),
    }


def analyze_understand(state: BuffettAnalystState) -> dict:
    emit_progress("bf_understand", "一、生意能否看懂…", phase="llm", status="running")
    ctx = _ctx(state)
    profile = "\n\n".join(
        filter(
            None,
            [
                _named_context(ctx["data_context"], "公司画像与盘口", 2500),
                _named_context(ctx["data_context"], "主营业务构成", 2500),
            ],
        )
    )
    prompt = build_understand_prompt(
        stock_name=ctx["stock_name"],
        stock_code=ctx["stock_code"],
        data_cutoff_date=ctx["data_cutoff_date"],
        business_type=ctx["business_type"],
        buffett_summary=ctx["buffett_summary"],
        flags=ctx["flags"],
        data_context=profile or ctx["data_context"],
    )
    content = _generate_section(
        "一、生意能否看懂",
        prompt,
        rule_engine_fallback("一、生意能否看懂", profile, ctx["buffett_summary"]),
    )
    emit_progress("bf_understand", "一章完成", phase="llm_done", status="done")
    return {"section_understand": content}


def analyze_owner(state: BuffettAnalystState) -> dict:
    emit_progress("bf_owner", "二、所有者盈余…", phase="llm", status="running")
    ctx = _ctx(state)
    table = ctx["tables"].get("owner_earnings", "")
    prompt = build_owner_prompt(
        stock_name=ctx["stock_name"],
        stock_code=ctx["stock_code"],
        data_cutoff_date=ctx["data_cutoff_date"],
        business_type=ctx["business_type"],
        buffett_summary=ctx["buffett_summary"],
        flags=ctx["flags"],
        table=table,
    )
    content = _generate_section(
        "二、所有者盈余",
        prompt,
        rule_engine_fallback("二、所有者盈余", table, ctx["buffett_summary"]),
    )
    emit_progress("bf_owner", "二章完成", phase="llm_done", status="done")
    return {"section_owner": content}


def analyze_capital(state: BuffettAnalystState) -> dict:
    emit_progress("bf_capital", "三、资本饥饿与四种生意…", phase="llm", status="running")
    ctx = _ctx(state)
    table = ctx["tables"].get("capital", "")
    prompt = build_capital_prompt(
        stock_name=ctx["stock_name"],
        stock_code=ctx["stock_code"],
        data_cutoff_date=ctx["data_cutoff_date"],
        business_type=ctx["business_type"],
        buffett_summary=ctx["buffett_summary"],
        flags=ctx["flags"],
        table=table,
    )
    content = _generate_section(
        "三、资本饥饿与四种生意",
        prompt,
        rule_engine_fallback("三、资本饥饿与四种生意", table, ctx["buffett_summary"]),
    )
    emit_progress("bf_capital", "三章完成", phase="llm_done", status="done")
    return {"section_capital": content}


def analyze_honesty(state: BuffettAnalystState) -> dict:
    emit_progress("bf_honesty", "四、会计诚实与资本配置…", phase="llm", status="running")
    ctx = _ctx(state)
    table = ctx["tables"].get("allocation", "")
    prompt = build_honesty_prompt(
        stock_name=ctx["stock_name"],
        stock_code=ctx["stock_code"],
        data_cutoff_date=ctx["data_cutoff_date"],
        business_type=ctx["business_type"],
        buffett_summary=ctx["buffett_summary"],
        flags=ctx["flags"],
        table=table,
    )
    content = _generate_section(
        "四、会计诚实与资本配置",
        prompt,
        rule_engine_fallback("四、会计诚实与资本配置", table, ctx["buffett_summary"]),
    )
    emit_progress("bf_honesty", "四章完成", phase="llm_done", status="done")
    return {"section_honesty": content}


def synthesize(state: BuffettAnalystState) -> dict:
    emit_progress("bf_synthesis", "五、综合判决…", phase="llm", status="running")
    tables = state.get("buffett_tables") or {}
    diagnosis = tables.get("diagnosis", "")
    understand = state.get("section_understand", "")
    prompt = build_synthesis_prompt(
        stock_name=state.get("stock_name", ""),
        stock_code=state.get("stock_code", ""),
        business_type=state.get("business_type", "未知"),
        diagnosis_table=diagnosis,
        understand_verdict=_understand_verdict(understand),
        section_understand=understand,
        section_owner=state.get("section_owner", ""),
        section_capital=state.get("section_capital", ""),
        section_honesty=state.get("section_honesty", ""),
        valuation_context=_named_context(state.get("data_context", ""), "估值与同业"),
    )
    content = _generate_section(
        "五、综合判决",
        prompt,
        rule_engine_fallback("五、综合判决", diagnosis, state.get("buffett_summary", "")),
    )
    emit_progress("bf_synthesis", "综合判决完成", phase="llm_done", status="done")
    return {"section_synthesis": content}


def assemble_report(state: BuffettAnalystState) -> dict:
    emit_progress("bf_assemble", "拼装报告…", phase="llm", status="running")
    header = build_assemble_header(
        stock_name=state.get("stock_name", ""),
        stock_code=state.get("stock_code", ""),
        industry=state.get("industry") or {},
        data_cutoff_date=state.get("data_cutoff_date", ""),
        business_type=state.get("business_type", "未知"),
    )
    tables = state.get("buffett_tables") or {}
    sections = [
        ("一、生意能否看懂", state.get("section_understand", ""), flags_as_table(state.get("buffett_flags") or [])),
        ("二、所有者盈余", state.get("section_owner", ""), tables.get("owner_earnings", "")),
        ("三、资本饥饿与四种生意", state.get("section_capital", ""), tables.get("capital", "")),
        ("四、会计诚实与资本配置", state.get("section_honesty", ""), tables.get("allocation", "")),
        ("五、综合判决", state.get("section_synthesis", ""), tables.get("diagnosis", "")),
    ]
    body = "\n".join(render_section(title, table, content) for title, content, table in sections)

    flags = state.get("buffett_flags") or []
    sources = list(
        dict.fromkeys(item.strip() for item in (state.get("sources_used") or []) if item and str(item).strip())
    )
    appendix = "\n".join(
        [
            "## 附录\n",
            "### 规则引擎预计算摘要\n",
            state.get("buffett_summary", ""),
            "\n### 风险警示清单\n",
            "\n".join(f"- {f}" for f in flags) if flags else "- 暂无",
            "\n### 数据来源\n",
            "\n".join(f"- {s}" for s in sources) or "- （无）",
            "\n### 分析局限性\n",
            "- 利润表/现金流量表为报告期累计数，非单季度\n"
            "- 所有者盈余的维持性资本开支 (c) 不可观测，只给上沿（折旧）与下沿（资本开支）区间\n"
            "- 折旧摊销取自东财现金流附注；缺列时下沿标「未披露」\n"
            "- 生意类型由规则引擎根据有形回报与 capex/D&A 判定，模型不得改写\n"
            "- 本报告以读表为主，安全边际只引用已采集估值，不做独立三情景模型",
        ]
    )
    report_text = header.rstrip() + "\n\n" + body.strip() + "\n\n" + appendix.strip() + "\n"
    emit_progress("bf_assemble", f"报告拼装完成（约 {len(report_text)} 字）", phase="llm_done", status="done")
    return {"final_report": report_text, "report": report_text}


def _report_filename(stock_name: str, company: str, code: str, cutoff: str) -> str:
    safe_name = re.sub(r"[^\w\u4e00-\u9fff-]", "_", stock_name or company)
    if code and (safe_name == code or safe_name.endswith(f"_{code}")):
        stem = safe_name
    elif code:
        stem = f"{safe_name}_{code}"
    else:
        stem = safe_name
    return f"{stem}巴菲特读表_{cutoff}.md"


def save_report(state: BuffettAnalystState) -> dict:
    company = state["company"]
    cutoff = state.get("data_cutoff_date", date.today().isoformat()).replace("-", "")
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    path = REPORTS_DIR / _report_filename(
        state.get("stock_name") or "",
        company,
        state.get("stock_code", ""),
        cutoff,
    )
    emit_progress("bf_save", "正在保存报告…", phase="save_file", status="running")
    path.write_text(state.get("final_report") or state.get("report") or "", encoding="utf-8")
    emit_progress("bf_save", f"已保存至 {path.name}", phase="done", status="done")
    return {"report_path": str(path)}
