"""产业链分析智能体 — 节点实现。"""

from __future__ import annotations

import json
import re
from datetime import date
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from agent.chain_analyst.prompts import (
    CHAIN_SYSTEM,
    MAP_CHAIN_SYSTEM,
    build_chain_user_prompt,
    build_map_chain_user_prompt,
)
from agent.chain_analyst.state import ChainAnalystState
from agent.config import REPORTS_DIR
from agent.tools.data_fetcher import (
    fetch_chain_analyst_data,
    fetch_web_chain_supplement,
    resolve_company,
)
from agent.tools.progress import report as emit_progress
from agent.utils.llm import get_llm


def _parse_json_object(text: str) -> dict[str, Any]:
    raw = (text or "").strip()
    if not raw:
        return {}
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", raw, re.I)
    if fence:
        raw = fence.group(1).strip()
    start = raw.find("{")
    end = raw.rfind("}")
    if start < 0 or end <= start:
        return {}
    try:
        data = json.loads(raw[start : end + 1])
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _player_name(item: Any) -> str:
    if isinstance(item, str):
        return item.strip()
    if isinstance(item, dict):
        return str(item.get("name") or item.get("company") or "").strip()
    return ""


def queries_from_chain_map(chain_map: dict[str, Any]) -> list[str]:
    """由结构化地图生成至多 6 条定向检索。"""
    if not isinstance(chain_map, dict):
        return []
    out: list[str] = []
    seen: set[str] = set()

    def add(query: str) -> None:
        q = " ".join(str(query).split())
        if len(q) < 4 or q in seen or len(out) >= 6:
            return
        seen.add(q)
        out.append(q)

    industry = str(chain_map.get("industry_label") or "").strip()
    if industry:
        add(f"{industry} 产业链 上下游 卡脖子 国产替代")

    for layer in chain_map.get("layers") or []:
        if not isinstance(layer, dict):
            continue
        for player in (layer.get("named_players") or [])[:2]:
            name = _player_name(player)
            if name:
                add(f"{name} 市场份额 产业链位置")
        for item in (layer.get("key_inputs") or [])[:1]:
            text = item if isinstance(item, str) else _player_name(item)
            text = str(text or "").strip()
            if text:
                add(f"{text} 价格 供需")
        if len(out) >= 6:
            break

    for hyp in chain_map.get("bottleneck_hypotheses") or []:
        text = hyp if isinstance(hyp, str) else (hyp.get("text") if isinstance(hyp, dict) else "")
        text = str(text or "").strip()
        if text:
            add(f"{text[:40]} 供需 卡脖子")
        if len(out) >= 6:
            break

    return out[:6]


def format_chain_map(chain_map: dict[str, Any], *, ok: bool) -> str:
    if not ok or not chain_map:
        return "（结构化地图未能解析，请仅依据主线资料撰写，并在报告中标明结构缺口。）"
    return json.dumps(chain_map, ensure_ascii=False, indent=2)


def init_company(state: ChainAnalystState) -> dict:
    """解析公司代码、名称与所属行业。"""
    company = state["company"]
    today = date.today().isoformat()

    emit_progress("ch_init", f"正在解析 {company}…", phase="resolve", status="running")
    stock = resolve_company(company)
    emit_progress(
        "ch_init",
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


def fetch_data(state: ChainAnalystState) -> dict:
    """采集交易所、巨潮、七网等官方资料及同层名单（主线）。"""
    company = state["company"]
    stock = {
        "code": state.get("stock_code", ""),
        "name": state.get("stock_name", ""),
        "market": state.get("stock_market", ""),
    }

    emit_progress("ch_fetch", "开始采集产业链相关资料…", phase="fetch_data", status="running")
    pack = fetch_chain_analyst_data(company, stock, progress_node="ch_fetch")

    n_sections = len(pack.get("sections") or {})
    industry_name = pack.get("industry_name") or state.get("industry_name", "")
    emit_progress(
        "ch_fetch",
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


def map_chain(state: ChainAnalystState) -> dict:
    """第一次 LLM：从主线资料抽出结构化产业链地图。失败不阻断。"""
    company = state["company"]
    emit_progress("ch_map", "正在绘制产业链地图…", phase="llm", status="running")

    user_prompt = build_map_chain_user_prompt(
        company=company,
        stock_code=state.get("stock_code", ""),
        stock_name=state.get("stock_name", ""),
        industry_name=state.get("industry_name", ""),
        data_cutoff_date=state.get("data_cutoff_date", ""),
        data_context=state.get("data_context", ""),
        sources=state.get("sources_used", []),
    )

    try:
        llm = get_llm()
        response = llm.invoke(
            [SystemMessage(content=MAP_CHAIN_SYSTEM), HumanMessage(content=user_prompt)]
        )
        parsed = _parse_json_object(response.content or "")
    except Exception as exc:  # noqa: BLE001
        emit_progress(
            "ch_map",
            f"地图生成失败，将仅用主线资料继续：{exc}",
            phase="llm_done",
            status="done",
            level="warn",
        )
        return {
            "chain_map": {},
            "chain_map_text": format_chain_map({}, ok=False),
            "chain_map_ok": False,
        }

    ok = bool(parsed.get("layers") or parsed.get("industry_label") or parsed.get("company_layer"))
    n_layers = len(parsed.get("layers") or []) if isinstance(parsed.get("layers"), list) else 0
    label = str(parsed.get("industry_label") or "").strip()
    if ok:
        emit_progress(
            "ch_map",
            f"地图已抽出：{label or '未命名'} · {n_layers} 层",
            phase="llm_done",
            status="done",
        )
    else:
        emit_progress(
            "ch_map",
            "未能解析结构化地图，后续检索将使用固定查询",
            phase="llm_done",
            status="done",
            level="warn",
        )

    return {
        "chain_map": parsed if ok else {},
        "chain_map_text": format_chain_map(parsed, ok=ok),
        "chain_map_ok": ok,
    }


def search_layers(state: ChainAnalystState) -> dict:
    """按地图动态检索 + 固定产业链查询。失败不阻断主线。"""
    company = state["company"]
    stock = {
        "code": state.get("stock_code", ""),
        "name": state.get("stock_name", ""),
        "market": state.get("stock_market", ""),
    }
    industry_name = state.get("industry_name", "")
    extra = queries_from_chain_map(state.get("chain_map") or {}) if state.get("chain_map_ok") else []

    emit_progress("ch_search", "开始定向检索上下游…", phase="web_search", status="running")
    pack = fetch_web_chain_supplement(
        company,
        stock,
        industry_name=industry_name,
        extra_queries=extra,
        progress_node="ch_search",
    )

    extra_sources = pack.get("sources_used") or []
    sources = list(state.get("sources_used") or [])
    for item in extra_sources:
        if item not in sources:
            sources.append(item)

    used = bool(pack.get("used"))
    engines = pack.get("engines") or []
    extra_note = f" · 定向 {len(extra)} 条" if extra else ""
    if used:
        emit_progress(
            "ch_search",
            f"联网补充完成（{'+'.join(engines) or '已检索'}{extra_note}）",
            phase="web_search_done",
            status="done",
        )
    else:
        emit_progress(
            "ch_search",
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


def generate_analysis(state: ChainAnalystState) -> dict:
    """调用 LLM 生成产业链分析报告。"""
    company = state["company"]
    industry_name = state.get("industry_name", "")

    emit_progress("ch_analyze", "正在生成产业链分析…", phase="llm", status="running")

    user_prompt = build_chain_user_prompt(
        company=company,
        stock_code=state.get("stock_code", ""),
        stock_name=state.get("stock_name", ""),
        industry_name=industry_name,
        data_cutoff_date=state.get("data_cutoff_date", ""),
        data_context=state.get("data_context", ""),
        sources=state.get("sources_used", []),
        chain_map_text=state.get("chain_map_text", ""),
        web_context=state.get("web_context", ""),
    )

    llm = get_llm()
    response = llm.invoke(
        [SystemMessage(content=CHAIN_SYSTEM), HumanMessage(content=user_prompt)]
    )
    content = response.content or ""

    engines = state.get("web_engines") or []
    supplement = f"联网搜索（{'+'.join(engines)}）" if state.get("web_search_used") else "联网未启用或无结果"
    map_note = "结构化地图已抽出" if state.get("chain_map_ok") else "结构化地图未解析，已标缺口"
    industry_label = industry_name or "行业"
    header = (
        f"# 分析{state.get('stock_name') or company}所在产业链\n\n"
        f"> 代码: {state.get('stock_code', '')} | "
        f"行业: {industry_label} | "
        f"数据截止: {state.get('data_cutoff_date', '')} | "
        f"范围: 上中下游 · 卡脖子 · 价值分配 | "
        f"主线: 交易所 · 巨潮 · 七网 · 公告PDF · 同层名单 | "
        f"地图: {map_note} | "
        f"补充: {supplement}\n\n"
    )
    report = header + content

    emit_progress(
        "ch_analyze",
        f"分析完成（约 {len(report)} 字）",
        phase="llm_done",
        status="done",
    )

    return {"report": report}


def save_report(state: ChainAnalystState) -> dict:
    """保存产业链分析报告。"""
    company = state["company"]
    cutoff = state.get("data_cutoff_date", date.today().isoformat()).replace("-", "")
    safe_name = re.sub(r"[^\w\u4e00-\u9fff-]", "_", state.get("stock_name") or company)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    path = REPORTS_DIR / f"{safe_name}产业链分析_{cutoff}.md"

    emit_progress("ch_save", "正在保存报告…", phase="save_file", status="running")
    path.write_text(state.get("report") or "", encoding="utf-8")
    emit_progress("ch_save", f"已保存至 {path.name}", phase="done", status="done")

    return {"report_path": str(path)}
