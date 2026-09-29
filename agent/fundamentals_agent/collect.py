"""采集：只负责把原始数据拉齐，不做解读。"""

from __future__ import annotations

import logging
from datetime import date
from typing import Any

from agent.tools.data_fetcher import _fetch_profile_pack, resolve_company
from agent.tools.financials import fetch_financial_pack, fetch_valuation_pack
from agent.tools.progress import report

logger = logging.getLogger(__name__)


def collect(company: str, stock: dict[str, str] | None = None) -> dict[str, Any]:
    resolved = stock or resolve_company(company)
    code = resolved["code"]
    name = resolved["name"]
    errors: list[str] = []
    sources: list[str] = []

    report("fv_collect", f"采集 {name} 财务与估值原始数据", phase="fetch_data", status="running")

    report("fv_collect", "拉取公司画像与行业…", phase="fetch_section")
    profile, industry, profile_text = _fetch_profile_pack(code, name)
    if "未能" not in profile_text:
        sources.extend(["东方财富盘口", "申万行业"])

    report("fv_collect", "拉取财务报表…", phase="fetch_section")
    fin = fetch_financial_pack(code, name)
    errors.extend(fin.get("errors") or [])
    if fin.get("text"):
        sources.extend(fin.get("sources") or [])

    report("fv_collect", "拉取历史倍数与同业…", phase="fetch_section")
    val = fetch_valuation_pack(code, name, profile, industry)
    pe_items = list(val.get("pe_items") or [])
    if val.get("text"):
        sources.extend(val.get("sources") or [])

    report("fv_collect", "采集完成", phase="fetch_data_done", status="done")
    return {
        "data_cutoff_date": date.today().isoformat(),
        "stock_code": code,
        "stock_name": name,
        "stock_market": resolved.get("market") or "",
        "profile": profile,
        "industry": industry,
        "profile_text": profile_text,
        "annual": list(fin.get("annual") or []),
        "recent": list(fin.get("recent") or []),
        "merged": list(fin.get("merged") or []),
        "fin_sections": dict(fin.get("sections") or {}),
        "fin_text": fin.get("text") or "",
        "pe_items": pe_items,
        "val_sections": dict(val.get("sections") or {}),
        "val_text": val.get("text") or "",
        "sources_used": list(dict.fromkeys(sources)),
        "errors": errors,
    }
