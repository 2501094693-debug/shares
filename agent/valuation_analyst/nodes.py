"""估值分析智能体 — 节点。数字只来自规则引擎，模型只写原因。"""

from __future__ import annotations

import logging
import re
from datetime import date
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from agent.config import OPENAI_API_KEY, REPORTS_DIR
from agent.tools.data_fetcher import resolve_company
from agent.tools.progress import report as emit_progress
from agent.tools.valuation_data import compute_valuation_pack, fetch_valuation_data
from agent.valuation_analyst.prompts import (
    SYSTEM,
    build_buffett_prompt,
    build_drivers_prompt,
    build_fundamentals_prompt,
    build_history_prompt,
    build_synthesis_prompt,
)
from agent.valuation_analyst.rules.engine import PATH_ORDER, fmt_num, fmt_pct, fmt_yi
from agent.valuation_analyst.state import ValuationState
from agent.utils.llm import get_llm

logger = logging.getLogger(__name__)


def init_company(state: ValuationState) -> dict:
    company = (state.get("company") or "").strip()
    emit_progress("va_init", f"正在解析 {company}…", phase="resolve", status="running")
    stock = resolve_company(company)
    emit_progress("va_init", f"已解析：{stock['name']} ({stock['code']})", phase="done", status="done")
    return {
        "data_cutoff_date": date.today().isoformat(),
        "stock_code": stock["code"],
        "stock_name": stock["name"],
        "stock_market": stock["market"],
        "skip_llm": bool(state.get("skip_llm") or False),
        "errors": [],
        "sources_used": [],
    }


def fetch_pack(state: ValuationState) -> dict:
    emit_progress("va_fetch", "采集盘口、近十年倍数与财报…", phase="fetch_data", status="running")
    pack = fetch_valuation_data(
        state.get("company") or "",
        {
            "code": state.get("stock_code") or "",
            "name": state.get("stock_name") or "",
            "market": state.get("stock_market") or "",
        },
    )
    engine = compute_valuation_pack(pack, understood=True)
    emit_progress(
        "va_fetch",
        f"规则引擎完成 · 态度 {((engine.get('composite') or {}).get('stance') or '—')}",
        phase="fetch_data_done",
        status="done",
    )
    return {
        "pack": pack,
        "engine": engine,
        "sources_used": list(pack.get("sources_used") or []),
        "errors": list(pack.get("errors") or []),
    }


def _template_path(path: dict[str, Any]) -> str:
    notes = path.get("notes") or []
    lines = [
        "### 假设",
        "",
        notes[0] if notes else "按规则引擎公式计价，未改数字。",
        "",
        "### 三情景含义",
        "",
    ]
    for row in path.get("scenarios") or []:
        extra = row.get("na") or row.get("formula") or ""
        lines.append(
            f"- **{row.get('name')}**：市值 {fmt_yi(row.get('mcap'))}，"
            f"股价 {fmt_num(row.get('price'))}，相对现价 {fmt_pct(row.get('upside'), ratio=True)}。"
            f"{extra}"
        )
    lines.extend(["", "### 本路可信度", "", "；".join(notes[1:]) if len(notes) > 1 else "见规则备注。"])
    return "\n".join(lines)


def _template_synth(engine: dict[str, Any]) -> str:
    composite = engine.get("composite") or {}
    return "\n".join(
        [
            "### 哪一路更可信",
            "",
            "综合中性锚取历史/财报/收入因素三路中性市值的中位数；巴菲特中性只作安全边际下限。",
            "",
            "### 现价落在什么位置",
            "",
            f"综合中性锚 {fmt_yi(composite.get('anchor_mid_mcap'))}（股价 {fmt_num(composite.get('anchor_mid_price'))}）；"
            f"巴菲特下限 {fmt_yi(composite.get('mos_floor_mcap'))}。",
            "",
            "### 综合态度为何是「"
            + str(composite.get("stance") or "观望")
            + "」",
            "",
            "；".join(composite.get("notes") or []) or "按多数路径相对悲观/乐观带位置判定，非买卖建议。",
            "",
            "### 失效观察",
            "",
            composite.get("invalidation") or "关键假设被证伪时本表作废。",
        ]
    )


def _normalize_note(text: str) -> str:
    body = (text or "").strip()
    if not body:
        return body
    lines_out: list[str] = []
    for line in body.splitlines():
        if re.match(r"^##\s+", line) and not re.match(r"^###\s+", line):
            lines_out.append("#" + line)
        else:
            lines_out.append(line)
    return "\n".join(lines_out).strip()


def _ask_llm(prompt: str, fallback: str) -> str:
    if not OPENAI_API_KEY:
        return fallback
    try:
        llm = get_llm()
        resp = llm.invoke([SystemMessage(content=SYSTEM), HumanMessage(content=prompt)])
        text = getattr(resp, "content", None)
        if isinstance(text, str) and len(text.strip()) > 60:
            return _normalize_note(text)
    except Exception as exc:  # noqa: BLE001
        logger.warning("估值解读 LLM 失败: %s", exc)
    return fallback


def _analyze_path(
    state: ValuationState,
    *,
    node: str,
    label: str,
    prompt_fn,
    field: str,
) -> dict:
    engine = state.get("engine") or {}
    path_key = {
        "history_note": "history",
        "fundamentals_note": "fundamentals",
        "buffett_note": "buffett",
        "drivers_note": "drivers",
    }[field]
    path = (engine.get("paths") or {}).get(path_key) or {}
    fallback = _template_path(path)
    emit_progress(node, f"解读{label}…", phase="llm", status="running")
    note = fallback
    if not state.get("skip_llm"):
        name = state.get("stock_name") or ""
        code = state.get("stock_code") or ""
        if field == "drivers_note":
            prompt = build_drivers_prompt(
                name,
                code,
                engine,
                (state.get("pack") or {}).get("segment_text") or "",
            )
        else:
            prompt = prompt_fn(name, code, engine)
        note = _ask_llm(prompt, fallback)
    emit_progress(node, f"{label}完成", phase="llm_done", status="done")
    return {field: note}


def analyze_history(state: ValuationState) -> dict:
    return _analyze_path(
        state,
        node="va_history",
        label="历史倍数",
        prompt_fn=build_history_prompt,
        field="history_note",
    )


def analyze_fundamentals(state: ValuationState) -> dict:
    return _analyze_path(
        state,
        node="va_fundamentals",
        label="财报正常化",
        prompt_fn=build_fundamentals_prompt,
        field="fundamentals_note",
    )


def analyze_buffett(state: ValuationState) -> dict:
    return _analyze_path(
        state,
        node="va_buffett",
        label="巴菲特路径",
        prompt_fn=build_buffett_prompt,
        field="buffett_note",
    )


def analyze_drivers(state: ValuationState) -> dict:
    return _analyze_path(
        state,
        node="va_drivers",
        label="收入关键因素",
        prompt_fn=build_drivers_prompt,
        field="drivers_note",
    )


def _assemble(state: ValuationState) -> str:
    engine = state.get("engine") or {}
    tables = engine.get("tables") or {}
    composite = engine.get("composite") or {}
    snap = engine.get("snap") or {}
    notes = {
        "history": state.get("history_note") or "",
        "fundamentals": state.get("fundamentals_note") or "",
        "buffett": state.get("buffett_note") or "",
        "drivers": state.get("drivers_note") or "",
    }
    lines = [
        f"# {state.get('stock_name') or ''}（{state.get('stock_code') or ''}）估值分析",
        "",
        f"- 数据截止：{state.get('data_cutoff_date') or ''}",
        f"- 现价 {fmt_num(snap.get('price'))} · 市值 {fmt_yi(snap.get('mcap'))}",
        f"- 生意类型 {engine.get('business_type')} · 主倍数 {engine.get('primary')}",
        f"- 综合态度 **{composite.get('stance') or '观望'}**（非买卖点）",
        f"- 综合中性锚 {fmt_yi(composite.get('anchor_mid_mcap'))} / {fmt_num(composite.get('anchor_mid_price'))}",
        f"- 巴菲特安全边际下限 {fmt_yi(composite.get('mos_floor_mcap'))} / {fmt_num(composite.get('mos_floor_price'))}",
        "",
        "## 规则引擎总览",
        "",
        tables.get("overview") or "",
        "",
        f"### {engine.get('history_window_label') or '近10年'}分位",
        "",
        tables.get("percentiles") or "",
        "",
    ]
    titles = {
        "history": "一、历史倍数",
        "fundamentals": "二、财报正常化",
        "buffett": "三、巴菲特",
        "drivers": "四、收入关键因素",
    }
    for key in PATH_ORDER:
        lines.extend(
            [
                f"## {titles[key]}",
                "",
                tables.get(key) or "",
                "",
                notes.get(key) or "",
                "",
            ]
        )
    lines.extend(
        [
            "## 五、交叉对照",
            "",
            state.get("synthesis_note") or "",
            "",
            "## 限制",
            "",
            "- 数字全部由规则引擎计算；模型不得改写",
            "- 历史分位默认近 10 年 P25/P50/P75，不是历史最低/最高",
            "- 综合锚贴近历史定价带；巴菲特路径只提供安全边际下限",
            "- 不做买卖点或仓位建议；关键假设被证伪时本表作废",
            f"- 作废条件：{composite.get('invalidation') or '—'}",
            "",
        ]
    )
    errors = state.get("errors") or []
    if errors:
        lines.extend(["## 采集问题", ""])
        lines.extend(f"- {item}" for item in errors)
        lines.append("")
    return "\n".join(lines)


def synthesize(state: ValuationState) -> dict:
    emit_progress("va_synth", "交叉对照四路估值…", phase="llm", status="running")
    engine = state.get("engine") or {}
    fallback = _template_synth(engine)
    note = fallback
    if not state.get("skip_llm"):
        prompt = build_synthesis_prompt(
            state.get("stock_name") or "",
            state.get("stock_code") or "",
            engine,
        )
        note = _ask_llm(prompt, fallback)
    report = _assemble({**state, "synthesis_note": note})
    emit_progress("va_synth", "结论完成", phase="llm_done", status="done")
    return {"synthesis_note": note, "report": report}


def save_report(state: ValuationState) -> dict:
    company = state.get("company") or ""
    cutoff = (state.get("data_cutoff_date") or date.today().isoformat()).replace("-", "")
    safe_name = re.sub(r"[^\w\u4e00-\u9fff-]", "_", state.get("stock_name") or company)
    code = state.get("stock_code") or ""
    stem = f"{safe_name}_{code}" if code and code not in safe_name else safe_name
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    path = REPORTS_DIR / f"{stem}估值分析_{cutoff}.md"
    emit_progress("va_save", "正在保存报告…", phase="save_file", status="running")
    path.write_text(state.get("report") or "", encoding="utf-8")
    emit_progress("va_save", f"已保存至 {path.name}", phase="done", status="done")
    return {"report_path": str(path)}
