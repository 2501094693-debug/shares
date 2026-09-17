"""生意本质 LangGraph 节点：取数是工具，判断走起草-质疑循环。"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from agent.config import REPORTS_DIR
from agent.essence_analyst.critic import apply_hard_rules, parse_critic
from agent.essence_analyst.layout import assemble_markdown
from agent.essence_analyst.prompts import (
    CRITIC_SYSTEM,
    WRITER_SYSTEM,
    build_critic_prompt,
    build_writer_prompt,
)
from agent.essence_analyst.stages import (
    MAX_ROUNDS,
    STAGE_AGENT,
    STAGE_TITLE,
    next_stage,
)
from agent.essence_analyst.state import EssenceState
from agent.tools.progress import report as emit
from agent.utils.llm import get_llm

_WEB_QUERIES = (
    "产品 干什么 客户 使用场景 例子 不是什么",
    "商业模式 谁付钱 定价 成本",
    "关键影响因素 价格 需求 政策 竞争",
)


def _message_text(resp: Any) -> str:
    content = getattr(resp, "content", resp)
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict) and item.get("text"):
                parts.append(str(item["text"]))
            else:
                text = getattr(item, "text", None)
                if text:
                    parts.append(str(text))
        return "\n".join(parts).strip()
    return str(content or "").strip()


def _ask(system: str, user: str) -> str:
    llm = get_llm()
    resp = llm.invoke([SystemMessage(content=system), HumanMessage(content=user)])
    return _message_text(resp)


def _agent(stage: str) -> str:
    return STAGE_AGENT.get(stage, "es_businesses")


def resolve_company_node(state: EssenceState) -> dict[str, Any]:
    from agent.tools.data_fetcher import resolve_company

    company = (state.get("company") or "").strip()
    emit("es_resolve", f"正在解析 {company}…", phase="resolve", status="running")
    stock = resolve_company(company)
    today = date.today().isoformat()
    emit(
        "es_resolve",
        f"已解析：{stock['name']}（{stock['code']}）",
        phase="done",
        status="done",
    )
    return {
        "stock_code": stock["code"],
        "stock_name": stock["name"],
        "market": stock.get("market") or "",
        "data_cutoff": today,
        "stage": "businesses",
        "round": 0,
        "extra_searches": 0,
        "chapters": {},
        "confirm_log": [],
        "sources_used": [],
        "errors": [],
        "web_fetched": False,
        "all_done": False,
        "draft": "",
        "extra_text": "",
    }


def fetch_official_node(state: EssenceState) -> dict[str, Any]:
    from agent.essence_analyst.fetch import fetch_essence_official

    company = state["company"]
    stock = {
        "code": state["stock_code"],
        "name": state["stock_name"],
        "market": state.get("market") or "",
        "keyword": state["stock_name"],
    }
    emit("es_official", "拉取交易所 / 巨潮 / 七网 / 公告 PDF…", phase="fetch_data", status="running")
    pack = fetch_essence_official(company, stock, progress_node="es_official")
    emit(
        "es_official",
        f"官方披露已就绪（公告 PDF {pack.get('pdf_count') or 0} 份）",
        phase="fetch_data_done",
        status="done",
    )
    return {
        "official_text": pack.get("text") or "",
        "sources_used": list(pack.get("sources_used") or []),
        "errors": list(pack.get("errors") or []),
        "stage": "businesses",
        "round": 0,
    }


def fetch_web_node(state: EssenceState) -> dict[str, Any]:
    from agent.tools.web_search import search_company_info, web_search_status

    node = "es_web"
    available, engine = web_search_status()
    if not available:
        emit(node, engine, phase="web_search_skip", status="done")
        return {"web_text": "", "web_fetched": True}

    emit(node, f"联网补充（{engine}）…", phase="web_search", status="running")
    name, code = state["stock_name"], state["stock_code"]
    blocks: list[str] = []
    engines: list[str] = []
    for query in _WEB_QUERIES:
        emit(node, f"检索：{query}", phase="web_search")
        text, used = search_company_info(name, query, stock_code=code)
        if text and not text.startswith("（"):
            blocks.append(f"### 检索：{query}\n{text}")
            if used and used not in engines:
                engines.append(used)
    header = (
        f"> 补充范围：{name}（{code}）公开网页；业务认定若与交易所/巨潮冲突，以官方为准。\n\n"
    )
    body = header + "\n\n".join(blocks) if blocks else ""
    sources = list(state.get("sources_used") or [])
    if engines:
        sources.append("联网搜索（" + "+".join(engines) + "）")
    emit(node, "联网补充完成" if body else "联网无有效结果", phase="web_search_done", status="done")
    return {"web_text": body, "web_fetched": True, "sources_used": sources}


def extra_search_node(state: EssenceState) -> dict[str, Any]:
    from agent.tools.web_search import search_web, web_search_status

    stage = state.get("stage") or "businesses"
    query = (state.get("search_query") or "").strip()
    scope = state.get("search_scope") or "web"
    node = _agent(stage)
    extras = int(state.get("extra_searches") or 0) + 1
    if not query:
        emit(node, "质疑官未给检索词，跳过补检", phase="extra_search", status="running")
        return {"extra_searches": extras, "extra_text": state.get("extra_text") or ""}

    available, engine = web_search_status()
    if not available:
        emit(node, engine, phase="web_search_skip", status="running")
        return {"extra_searches": extras}

    name, code = state["stock_name"], state["stock_code"]
    if scope == "official":
        full = (
            f"{name} {code} {query} "
            "site:cninfo.com.cn OR site:sse.com.cn OR site:szse.cn OR site:bse.cn"
        )
    else:
        full = f"{name} {code} {query}"
    emit(node, f"按质疑官要求补检：{query}", phase="extra_search", status="running")
    text, used = search_web(full)
    block = f"### 补检（{used or engine} / {scope}）\n查询：{full}\n\n{text}"
    prev = state.get("extra_text") or ""
    merged = (prev + "\n\n" + block).strip() if prev else block
    return {"extra_searches": extras, "extra_text": merged}


def write_node(state: EssenceState) -> dict[str, Any]:
    stage = state.get("stage") or "businesses"
    rnd = int(state.get("round") or 0) + 1
    node = _agent(stage)
    emit(
        node,
        f"起草「{STAGE_TITLE[stage]}」第 {rnd} 稿…",
        phase="llm",
        status="running",
    )
    prompt = build_writer_prompt(
        stage=stage,
        stock_name=state.get("stock_name") or "",
        stock_code=state.get("stock_code") or "",
        data_cutoff=state.get("data_cutoff") or "",
        round_no=rnd,
        official_text=state.get("official_text") or "",
        web_text=state.get("web_text") or "",
        extra_text=state.get("extra_text") or "",
        chapters=state.get("chapters") or {},
        previous_draft=state.get("draft") or "",
        critique_issues=list(state.get("critique_issues") or []),
        critique_fix=state.get("critique_fix") or "",
    )
    draft = _ask(WRITER_SYSTEM, prompt)
    emit(node, f"第 {rnd} 稿已交质疑官", phase="llm_done", status="running")
    return {"round": rnd, "draft": draft}


def critique_node(state: EssenceState) -> dict[str, Any]:
    stage = state.get("stage") or "businesses"
    rnd = int(state.get("round") or 1)
    node = _agent(stage)
    emit(node, f"质疑官复核第 {rnd} 稿…", phase="critique", status="running")
    prompt = build_critic_prompt(
        stage=stage,
        stock_name=state.get("stock_name") or "",
        stock_code=state.get("stock_code") or "",
        round_no=rnd,
        draft=state.get("draft") or "",
        official_text=state.get("official_text") or "",
        web_text=state.get("web_text") or "",
        extra_text=state.get("extra_text") or "",
    )
    raw = _ask(CRITIC_SYSTEM, prompt)
    parsed = apply_hard_rules(
        stage=stage,
        draft=state.get("draft") or "",
        parsed=parse_critic(raw),
    )
    if rnd >= MAX_ROUNDS and parsed["verdict"] != "confirm":
        parsed["verdict"] = "exhausted"
        parsed["issues"] = list(parsed.get("issues") or []) + [f"已达 {MAX_ROUNDS} 轮，按最后一稿收录"]

    log = list(state.get("confirm_log") or [])
    log.append(
        {
            "stage": stage,
            "round": rnd,
            "verdict": parsed["verdict"],
            "issues": parsed.get("issues") or [],
        }
    )
    updates: dict[str, Any] = {
        "critique_verdict": parsed["verdict"],
        "critique_issues": parsed.get("issues") or [],
        "critique_fix": parsed.get("required_fix") or "",
        "search_query": parsed.get("search_query") or "",
        "search_scope": parsed.get("search_scope") or "web",
        "confirm_log": log,
    }

    label = {"confirm": "通过", "revise": "退回重写", "need_evidence": "要求补证据", "exhausted": "轮次用尽"}.get(
        parsed["verdict"], parsed["verdict"]
    )
    issue_hint = (parsed.get("issues") or ["无"])[0]
    emit(node, f"第 {rnd} 轮{label}：{issue_hint}", phase="critique", status="running")
    return updates


def advance_node(state: EssenceState) -> dict[str, Any]:
    stage = state.get("stage") or "businesses"
    chapters = dict(state.get("chapters") or {})
    chapters[stage] = state.get("draft") or ""
    emit(_agent(stage), f"「{STAGE_TITLE[stage]}」已确认", phase="confirm", status="done")
    nxt = next_stage(stage)
    updates: dict[str, Any] = {
        "chapters": chapters,
        "draft": "",
        "extra_text": "",
        "extra_searches": 0,
        "round": 0,
        "critique_verdict": "",
        "critique_issues": [],
        "critique_fix": "",
        "search_query": "",
    }
    if nxt:
        updates["stage"] = nxt
        updates["all_done"] = False
    else:
        updates["all_done"] = True
    return updates


def assemble_node(state: EssenceState) -> dict[str, Any]:
    emit("es_save", "拼装报告…", phase="llm", status="running")
    report = assemble_markdown(state)
    return {"final_report": report}


def save_node(state: EssenceState) -> dict[str, Any]:
    emit("es_save", "写入 Markdown…", phase="save_file", status="running")
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    name = state.get("stock_name") or "公司"
    code = state.get("stock_code") or "000000"
    day = (state.get("data_cutoff") or date.today().isoformat()).replace("-", "")
    path = Path(REPORTS_DIR) / f"{name}_{code}生意本质_{day}.md"
    path.write_text(state.get("final_report") or "", encoding="utf-8")
    emit("es_save", f"已保存 {path.name}", phase="done", status="done")
    return {"report_path": str(path)}
