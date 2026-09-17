"""段永平看业务智能体 — 节点实现。"""

from __future__ import annotations

import logging
import re
from datetime import date

from langchain_core.messages import HumanMessage, SystemMessage

from agent.duan_analyst.layout import (
    flags_as_table,
    has_prose,
    llm_text,
    render_section,
    rule_engine_fallback,
    skipped_section,
)
from agent.duan_analyst.prompts import (
    ANALYST_SYSTEM,
    build_assemble_header,
    build_business_prompt,
    build_culture_prompt,
    build_price_prompt,
    build_synthesis_prompt,
)
from agent.duan_analyst.rules import (
    REJECT,
    SKIPPED,
    WEAK,
    hint_to_fallback_verdict,
    parse_filter_verdict,
    parse_price_verdict,
    resolve_final_attitude,
)
from agent.duan_analyst.state import DuanAnalystState
from agent.config import REPORTS_DIR
from agent.tools.data_fetcher import resolve_company
from agent.tools.duan_data import fetch_duan_data
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
    logger.warning("段永平看业务章节「%s」首次返回空或过短（%s 字），重试一次", title, len(content or ""))
    content = _invoke_llm(prompt)
    if has_prose(content, title):
        return content
    logger.warning("段永平看业务章节「%s」仍无有效解读，改用规则引擎回退", title)
    return fallback


def _understand_verdict(text: str) -> str:
    blob = text or ""
    if "部分看懂" in blob:
        return "部分看懂"
    if "看不懂" in blob:
        return "看不懂"
    if "看懂" in blob:
        return "看懂"
    return "未明确"


def init_company(state: DuanAnalystState) -> dict:
    company = state["company"]
    today = date.today().isoformat()
    emit_progress("dy_init", f"正在解析 {company}…", phase="resolve", status="running")
    stock = resolve_company(company)
    emit_progress("dy_init", f"已解析：{stock['name']} ({stock['code']})", phase="done", status="done")
    return {
        "data_cutoff_date": today,
        "stock_code": stock["code"],
        "stock_name": stock["name"],
        "stock_market": stock["market"],
    }


def fetch_data(state: DuanAnalystState) -> dict:
    company = state["company"]
    stock = {
        "code": state.get("stock_code", ""),
        "name": state.get("stock_name", ""),
        "market": state.get("stock_market", ""),
    }
    emit_progress("dy_fetch", "开始采集段永平看业务数据…", phase="fetch_data", status="running")
    pack = fetch_duan_data(company, stock, progress_node="dy_fetch")
    duan = pack.get("duan") or {}
    return {
        "data_context": pack.get("text", ""),
        "web_context": pack.get("web_context", ""),
        "web_engines": pack.get("web_engines") or [],
        "web_search_used": bool(pack.get("web_search_used")),
        "sources_used": pack.get("sources_used", []),
        "data_available": pack.get("data_available", False),
        "errors": pack.get("errors", []),
        "stock": pack.get("stock") or {},
        "industry": pack.get("industry") or {},
        "duan_metrics": duan.get("metrics") or {},
        "duan_flags": duan.get("flags") or [],
        "duan_tables": duan.get("tables") or {},
        "duan_summary": duan.get("text", ""),
        "numeric_hint": duan.get("numeric_hint") or "数据不足",
    }


def filter_business(state: DuanAnalystState) -> dict:
    emit_progress("dy_business", "一、刮彩票：生意模式…", phase="llm", status="running")
    tables = state.get("duan_tables") or {}
    table = tables.get("long_term", "")
    profile = "\n\n".join(
        filter(
            None,
            [
                _named_context(state.get("data_context", ""), "公司画像与盘口", 2500),
                _named_context(state.get("data_context", ""), "主营业务构成", 2500),
            ],
        )
    )
    hint = state.get("numeric_hint") or "数据不足"
    prompt = build_business_prompt(
        stock_name=state.get("stock_name", ""),
        stock_code=state.get("stock_code", ""),
        data_cutoff_date=state.get("data_cutoff_date", ""),
        numeric_hint=hint,
        duan_summary=state.get("duan_summary", ""),
        flags=state.get("duan_flags") or [],
        table=table,
        data_context=profile or state.get("data_context", ""),
        web_context=state.get("web_context", ""),
    )
    fallback_verdict = hint_to_fallback_verdict(hint)
    content = _generate_section(
        "一、刮彩票：生意模式",
        prompt,
        rule_engine_fallback("一、刮彩票：生意模式", table, state.get("duan_summary", ""))
        + f"\n\n过滤器判决：{fallback_verdict}",
    )
    verdict = parse_filter_verdict(content, fallback_verdict)
    emit_progress("dy_business", f"生意模式：{verdict}", phase="llm_done", status="done")
    return {"section_business": content, "business_verdict": verdict}


def filter_culture(state: DuanAnalystState) -> dict:
    emit_progress("dy_culture", "二、企业文化…", phase="llm", status="running")
    profile = "\n\n".join(
        filter(
            None,
            [
                _named_context(state.get("data_context", ""), "公司画像与盘口", 2000),
                _named_context(state.get("data_context", ""), "联网补充", 2500),
            ],
        )
    )
    prompt = build_culture_prompt(
        stock_name=state.get("stock_name", ""),
        stock_code=state.get("stock_code", ""),
        data_cutoff_date=state.get("data_cutoff_date", ""),
        numeric_hint=state.get("numeric_hint") or "数据不足",
        duan_summary=state.get("duan_summary", ""),
        flags=state.get("duan_flags") or [],
        business_verdict=state.get("business_verdict", ""),
        section_business=state.get("section_business", ""),
        data_context=profile or state.get("data_context", ""),
        web_context=state.get("web_context", ""),
    )
    content = _generate_section(
        "二、企业文化",
        prompt,
        rule_engine_fallback("二、企业文化", flags_as_table(state.get("duan_flags") or []))
        + f"\n\n过滤器判决：{WEAK}",
    )
    verdict = parse_filter_verdict(content, WEAK)
    emit_progress("dy_culture", f"企业文化：{verdict}", phase="llm_done", status="done")
    return {"section_culture": content, "culture_verdict": verdict}


def filter_price(state: DuanAnalystState) -> dict:
    emit_progress("dy_price", "三、好价钱…", phase="llm", status="running")
    valuation = _named_context(state.get("data_context", ""), "估值与同业", 4000)
    prompt = build_price_prompt(
        stock_name=state.get("stock_name", ""),
        stock_code=state.get("stock_code", ""),
        data_cutoff_date=state.get("data_cutoff_date", ""),
        numeric_hint=state.get("numeric_hint") or "数据不足",
        duan_summary=state.get("duan_summary", ""),
        flags=state.get("duan_flags") or [],
        business_verdict=state.get("business_verdict", ""),
        culture_verdict=state.get("culture_verdict", ""),
        valuation_context=valuation,
    )
    content = _generate_section(
        "三、好价钱",
        prompt,
        rule_engine_fallback("三、好价钱", valuation)
        + "\n\n价格判决：还行",
    )
    verdict = parse_price_verdict(content, "还行")
    emit_progress("dy_price", f"价钱：{verdict}", phase="llm_done", status="done")
    return {"section_price": content, "price_verdict": verdict}


def skip_after_business(state: DuanAnalystState) -> dict:
    verdict = state.get("business_verdict") or REJECT
    reason = (
        f"生意模式过滤器结果是「{verdict}」。"
        "段永平：先看商业模式，刮到谢字就不用再往下刮。企业文化与价钱跳过。"
    )
    emit_progress("dy_culture", "刮到谢字，跳过企业文化", phase="skip", status="skipped")
    emit_progress("dy_price", "前关未过，跳过价钱", phase="skip", status="skipped")
    return {
        "culture_verdict": SKIPPED,
        "price_verdict": SKIPPED,
        "skip_reason": reason,
        "section_culture": skipped_section("二、企业文化", reason, SKIPPED),
        "section_price": skipped_section("三、好价钱", reason, SKIPPED),
    }


def skip_after_culture(state: DuanAnalystState) -> dict:
    verdict = state.get("culture_verdict") or REJECT
    reason = (
        f"企业文化过滤器结果是「{verdict}」。"
        "任意一关不喜欢就不再继续看。价钱跳过。"
    )
    emit_progress("dy_price", "文化未过，跳过价钱", phase="skip", status="skipped")
    return {
        "price_verdict": SKIPPED,
        "skip_reason": reason,
        "section_price": skipped_section("三、好价钱", reason, SKIPPED),
    }


def synthesize(state: DuanAnalystState) -> dict:
    emit_progress("dy_synthesis", "四、能不能看懂…", phase="llm", status="running")
    business = state.get("business_verdict") or WEAK
    culture = state.get("culture_verdict") or SKIPPED
    price = state.get("price_verdict") or SKIPPED
    locked = resolve_final_attitude(business, culture, price)
    tables = state.get("duan_tables") or {}
    prompt = build_synthesis_prompt(
        stock_name=state.get("stock_name", ""),
        stock_code=state.get("stock_code", ""),
        numeric_hint=state.get("numeric_hint") or "数据不足",
        locked_attitude=locked,
        business_verdict=business,
        culture_verdict=culture,
        price_verdict=price,
        diagnosis_table=tables.get("diagnosis", ""),
        section_business=state.get("section_business", ""),
        section_culture=state.get("section_culture", ""),
        section_price=state.get("section_price", ""),
    )
    content = _generate_section(
        "四、能不能看懂",
        prompt,
        rule_engine_fallback("四、能不能看懂", tables.get("diagnosis", ""), state.get("duan_summary", ""))
        + f"\n\n综合态度：{locked}",
    )
    understand = _understand_verdict(content)
    emit_progress("dy_synthesis", f"综合态度：{locked}", phase="llm_done", status="done")
    return {
        "section_synthesis": content,
        "final_attitude": locked,
        "understand_verdict": understand,
    }


def assemble_report(state: DuanAnalystState) -> dict:
    emit_progress("dy_assemble", "拼装报告…", phase="llm", status="running")
    header = build_assemble_header(
        stock_name=state.get("stock_name", ""),
        stock_code=state.get("stock_code", ""),
        industry=state.get("industry") or {},
        data_cutoff_date=state.get("data_cutoff_date", ""),
        numeric_hint=state.get("numeric_hint") or "数据不足",
        business_verdict=state.get("business_verdict") or WEAK,
        culture_verdict=state.get("culture_verdict") or SKIPPED,
        price_verdict=state.get("price_verdict") or SKIPPED,
        final_attitude=state.get("final_attitude")
        or resolve_final_attitude(
            state.get("business_verdict") or WEAK,
            state.get("culture_verdict") or SKIPPED,
            state.get("price_verdict") or SKIPPED,
        ),
    )
    tables = state.get("duan_tables") or {}
    sections = [
        ("一、刮彩票：生意模式", state.get("section_business", ""), tables.get("long_term", "")),
        ("二、企业文化", state.get("section_culture", ""), flags_as_table(state.get("duan_flags") or [])),
        ("三、好价钱", state.get("section_price", ""), _named_context(state.get("data_context", ""), "估值与同业", 2500)),
        ("四、能不能看懂", state.get("section_synthesis", ""), tables.get("diagnosis", "")),
    ]
    body = "\n".join(render_section(title, table, content) for title, content, table in sections)
    flags = state.get("duan_flags") or []
    sources = list(
        dict.fromkeys(item.strip() for item in (state.get("sources_used") or []) if item and str(item).strip())
    )
    engines = state.get("web_engines") or []
    supplement = f"联网搜索（{'+'.join(engines)}）" if state.get("web_search_used") else "联网未启用或无结果"
    appendix = "\n".join(
        [
            "## 附录\n",
            "### 规则引擎预计算摘要\n",
            state.get("duan_summary", ""),
            "\n### 数字警示\n",
            "\n".join(f"- {f}" for f in flags) if flags else "- 暂无",
            "\n### 数据来源\n",
            "\n".join(f"- {s}" for s in sources) or "- （无）",
            f"\n- 补充：{supplement}",
            "\n### 分析局限性\n",
            "- 过滤器是必要条件：生意模式或企业文化未过，后面章节按流程跳过\n"
            "- 数字提示只覆盖长期毛利率、净现金流、杠杆；差异化必须当消费者判断\n"
            "- 重资产不等于坏生意，资本开支高但净现金好不能据此离开\n"
            "- 本报告不给买卖建议，综合态度不是投资指令",
        ]
    )
    report_text = header.rstrip() + "\n\n" + body.strip() + "\n\n" + appendix.strip() + "\n"
    emit_progress("dy_assemble", f"报告拼装完成（约 {len(report_text)} 字）", phase="llm_done", status="done")
    return {"final_report": report_text, "report": report_text}


def _report_filename(stock_name: str, company: str, code: str, cutoff: str) -> str:
    safe_name = re.sub(r"[^\w\u4e00-\u9fff-]", "_", stock_name or company)
    if code and (safe_name == code or safe_name.endswith(f"_{code}")):
        stem = safe_name
    elif code:
        stem = f"{safe_name}_{code}"
    else:
        stem = safe_name
    return f"{stem}段永平看业务_{cutoff}.md"


def save_report(state: DuanAnalystState) -> dict:
    company = state["company"]
    cutoff = state.get("data_cutoff_date", date.today().isoformat()).replace("-", "")
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    path = REPORTS_DIR / _report_filename(
        state.get("stock_name") or "",
        company,
        state.get("stock_code", ""),
        cutoff,
    )
    emit_progress("dy_save", "正在保存报告…", phase="save_file", status="running")
    path.write_text(state.get("final_report") or state.get("report") or "", encoding="utf-8")
    emit_progress("dy_save", f"已保存至 {path.name}", phase="done", status="done")
    return {"report_path": str(path)}
