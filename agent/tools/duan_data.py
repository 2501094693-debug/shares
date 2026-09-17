"""段永平看业务数据采集与预处理。"""

from __future__ import annotations

import logging
from typing import Any

from agent.duan_analyst.rules import run_duan_screen
from agent.tools.data_fetcher import (
    _fetch_profile_pack,
    resolve_company,
)
from agent.tools.financials import (
    fetch_segment_data,
    fetch_statement_frames,
    fetch_valuation_pack,
)
from agent.tools.progress import report
from agent.tools.web_search import search_for_duan, web_search_status

logger = logging.getLogger(__name__)


def fetch_duan_data(
    company: str,
    stock: dict[str, str] | None = None,
    *,
    progress_node: str = "dy_fetch",
) -> dict[str, Any]:
    """采集段永平看业务所需数据，并运行长期毛利率/净现金预计算。"""
    resolved = stock or resolve_company(company)
    code = resolved["code"]
    name = resolved["name"]
    node = progress_node
    sections: dict[str, str] = {}
    sources: list[str] = []
    errors: list[str] = []

    report(node, f"采集 {name} 段永平看业务数据", phase="fetch_data", status="running")

    report(node, "正在拉取公司画像与行业归属…", phase="fetch_section")
    profile_stock, industry, profile_text = _fetch_profile_pack(code, name)
    if "未能" not in profile_text:
        sections["公司画像与盘口"] = profile_text
        sources.extend(["东方财富盘口", "申万行业"])

    report(node, "正在拉取最新全量定期报告…", phase="fetch_section")
    fin = fetch_statement_frames(code, limit=60, force=True)
    errors.extend(fin.get("errors") or [])
    annual = fin.get("annual") or []
    recent = fin.get("recent") or []
    merged = fin.get("merged") or []
    if merged:
        sources.append("东方财富 F10 定期报告")
    if not annual and not merged:
        errors.append("未能获取财务报表数据")

    report(node, "正在运行长期毛利率与净现金预计算…", phase="fetch_section")
    duan = run_duan_screen(annual, recent, merged=merged)
    sections["段永平数字预计算"] = duan["text"]
    sources.append("规则引擎预计算")
    for title, table in (duan.get("tables") or {}).items():
        sections[f"段永平_{title}"] = table

    report(node, "正在拉取主营业务分部数据…", phase="fetch_section")
    segment = fetch_segment_data(code)
    if segment.get("text"):
        sections["主营业务构成"] = segment["text"]
        sources.extend(segment.get("sources") or [])

    report(node, "正在拉取估值与同业对比…", phase="fetch_section")
    val = fetch_valuation_pack(code, name, profile_stock, industry)
    if val.get("text"):
        sections["估值与同业"] = val["text"]
        sources.extend(val.get("sources") or [])

    web_context = ""
    web_engines: list[str] = []
    web_used = False
    available, engine_note = web_search_status()
    if available:
        report(node, "正在联网补充用户口碑与文化线索…", phase="web_search")
        try:
            web_context, web_engines = search_for_duan(
                name,
                stock_code=code,
                progress_cb=lambda q: report(node, f"检索：{q}", phase="web_search"),
            )
            web_used = bool(web_context)
            if web_used:
                sections["联网补充"] = web_context
                sources.append(f"联网搜索（{'+'.join(web_engines) or engine_note}）")
        except Exception as exc:  # noqa: BLE001
            logger.warning("段永平看业务联网补充失败 %s: %s", code, exc)
            errors.append(f"联网补充失败：{exc}")
    else:
        report(node, f"跳过联网：{engine_note}", phase="web_search_skip")

    text_parts = [f"## {title}\n{body}" for title, body in sections.items()]
    report(node, "段永平看业务数据采集与预计算完成", phase="fetch_data_done", status="done")
    return {
        "stock": profile_stock or resolved,
        "industry": industry or {},
        "annual": annual,
        "recent": recent,
        "merged": merged,
        "duan": duan,
        "sections": sections,
        "text": "\n\n".join(text_parts),
        "web_context": web_context,
        "web_engines": web_engines,
        "web_search_used": web_used,
        "sources_used": list(dict.fromkeys(item.strip() for item in sources if item and str(item).strip())),
        "errors": errors,
        "data_available": bool(annual or merged),
    }
