"""按角色定向采集数据：调用 backend/company 接口 + 可选联网搜索。"""

from __future__ import annotations

import logging
import sys
from typing import Any

from config import BACKEND_ROOT, DATA_LOOKBACK_DAYS

logger = logging.getLogger(__name__)

if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


def _import_backend():
    from company.news.query import (
        query_cninfo,
        query_exchange,
        query_market_news,
        query_press,
        query_regulatory,
        query_reports,
        resolve_keywords,
    )
    from company.profile import get_stock_profile
    from company.statistics.pe_history import fetch_pe_history
    from core.codes import detect_market, normalize_code

    return {
        "query_cninfo": query_cninfo,
        "query_exchange": query_exchange,
        "query_market_news": query_market_news,
        "query_press": query_press,
        "query_regulatory": query_regulatory,
        "query_reports": query_reports,
        "resolve_keywords": resolve_keywords,
        "get_stock_profile": get_stock_profile,
        "fetch_pe_history": fetch_pe_history,
        "detect_market": detect_market,
        "normalize_code": normalize_code,
    }


def resolve_company(company: str) -> dict[str, str]:
    api = _import_backend()
    resolved = api["resolve_keywords"](company)
    code = resolved.get("code") or api["normalize_code"](company) or company
    name = resolved.get("name") or ""
    market = api["detect_market"](code) if code else "unknown"
    return {
        "code": code,
        "name": name or company,
        "keyword": resolved.get("keyword") or name or company,
        "market": market,
    }


def _fmt_items(items: list[dict[str, Any]], *, limit: int = 20) -> str:
    if not items:
        return "（无数据）"
    lines = []
    for i, item in enumerate(items[:limit], 1):
        title = item.get("title") or item.get("name") or "无标题"
        pub = str(item.get("published_at") or item.get("date") or "")[:19]
        source = item.get("source") or item.get("channel") or item.get("media_name") or ""
        url = item.get("url") or ""
        summary = (item.get("summary") or item.get("abstract") or "")[:200]
        line = f"{i}. [{pub}] {title}"
        if source:
            line += f" | 来源: {source}"
        if url:
            line += f"\n   链接: {url}"
        if summary:
            line += f"\n   摘要: {summary}"
        lines.append(line)
    return "\n".join(lines)


def _fmt_profile(stock: dict[str, Any], industry: dict[str, Any]) -> str:
    keys = (
        "code", "name", "price", "change_pct", "market_cap", "pe_ttm", "pe_dyn",
        "pb", "ps_ttm", "dividend_yield", "roe", "gross_margin", "net_margin",
        "revenue", "net_profit", "total_shares", "float_shares",
        "l1_name", "l2_name", "l3_name",
    )
    lines = ["| 指标 | 数值 |", "|------|------|"]
    for key in keys:
        val = stock.get(key)
        if val not in (None, "", "-"):
            lines.append(f"| {key} | {val} |")
    if industry:
        lines.append(f"| 行业 | {industry.get('l1_name', '')} / {industry.get('l2_name', '')} / {industry.get('name', '')} |")
    return "\n".join(lines)


def _safe_call(label: str, fn, *args, **kwargs) -> Any:
    try:
        return fn(*args, **kwargs)
    except Exception as exc:
        logger.warning("%s 失败: %s", label, exc)
        return None


def _fetch_profile_section(code: str, name: str) -> tuple[str, list[str]]:
    api = _import_backend()
    pack = _safe_call("公司画像", api["get_stock_profile"], code, name=name)
    if not pack:
        return "（未能获取公司画像）", []
    stock = pack.get("stock") or {}
    industry = pack.get("industry") or {}
    text = f"### 公司画像与盘口\n{_fmt_profile(stock, industry)}"
    return text, ["东方财富/腾讯盘口", "申万行业指数"]


def _fetch_periodic_reports(code: str, name: str, days: int) -> str:
    api = _import_backend()
    blocks: list[str] = []
    for kind, label in (
        ("annual", "年报"),
        ("semi", "半年报"),
        ("q1", "一季报"),
        ("q3", "三季报"),
    ):
        cninfo = _safe_call(
            f"巨潮{label}",
            api["query_cninfo"],
            code,
            category=kind,
            days=days,
            max_pages=4,
            limit=8,
        )
        exchange = _safe_call(
            f"交易所{label}",
            api["query_exchange"],
            code,
            category=kind,
            days=days,
            max_pages=4,
            limit=8,
        )
        items: list[dict[str, Any]] = []
        for pack in (cninfo, exchange):
            if pack and isinstance(pack, dict):
                items.extend(pack.get("items") or [])
        blocks.append(f"#### {label}（{len(items)} 条）\n{_fmt_items(items, limit=8)}")
    return f"### 定期报告公告（{name} {code}，近{days}天）\n" + "\n\n".join(blocks)


def _fetch_market_news(code: str, name: str, days: int) -> str:
    api = _import_backend()
    pack = _safe_call(
        "市场新闻",
        api["query_market_news"],
        code,
        name,
        days=days,
        max_pages=4,
    )
    items = pack if isinstance(pack, list) else (pack.get("items") if isinstance(pack, dict) else [])
    items = items or []
    return f"### 市场新闻（{len(items)} 条）\n{_fmt_items(items, limit=25)}"


def _fetch_press(code: str, name: str, days: int) -> str:
    api = _import_backend()
    pack = _safe_call("七网报道", api["query_press"], code or name, days=days, max_pages=3)
    if not pack or not isinstance(pack, dict):
        return "（未能获取七网报道）"
    items = pack.get("items") or []
    return f"### 七网权威媒体报道（{len(items)} 条）\n{_fmt_items(items, limit=20)}"


def _fetch_reports(code: str, name: str, days: int) -> str:
    api = _import_backend()
    pack = _safe_call("研报", api["query_reports"], code, name, days=days, max_pages=3)
    if not pack:
        return "（未能获取研报）"
    items = pack if isinstance(pack, list) else (pack.get("items") if isinstance(pack, dict) else [])
    items = items or []
    return f"### 研报摘要（{len(items)} 条）\n{_fmt_items(items, limit=15)}"


def _fetch_regulatory(code: str, name: str, days: int) -> str:
    api = _import_backend()
    pack = _safe_call("监管问询", api["query_regulatory"], code, days=days, max_pages=4)
    items = pack if isinstance(pack, list) else (pack.get("items") if isinstance(pack, dict) else [])
    items = items or []
    return f"### 监管问询/处罚（{len(items)} 条）\n{_fmt_items(items, limit=20)}"


def _fetch_pe_history(code: str) -> str:
    api = _import_backend()
    pack = _safe_call("估值历史", api["fetch_pe_history"], code, limit=30)
    if not pack or not isinstance(pack, dict):
        return "（未能获取估值历史）"
    items = pack.get("items") or []
    if not items:
        return "（估值历史为空）"
    recent = items[-10:]
    lines = ["| 日期 | 收盘 | PE_TTM | PB |", "|------|------|--------|-----|"]
    for row in recent:
        lines.append(
            f"| {row.get('time', '')} | {row.get('close', '')} | "
            f"{row.get('pe_ttm', '')} | {row.get('pb', '')} |"
        )
    return f"### 近10日估值序列（东财）\n" + "\n".join(lines)


def _fetch_announcements(code: str, name: str, days: int) -> str:
    api = _import_backend()
    cninfo = _safe_call("巨潮公告", api["query_cninfo"], code, days=days, max_pages=5, limit=30)
    items = cninfo.get("items") if isinstance(cninfo, dict) else []
    items = items or []
    return f"### 近期公告（{len(items)} 条）\n{_fmt_items(items, limit=25)}"


def _run_financial_rigor_checks(stock: dict[str, str]) -> str:
    """从画像数据尝试运行 financial_rigor 验算。"""
    from tools.berkshire_tools import run_financial_rigor

    api = _import_backend()
    profile = _safe_call("画像验算", api["get_stock_profile"], stock["code"], name=stock["name"])
    if not profile:
        return ""
    s = profile.get("stock") or {}
    price = str(s.get("price") or "").replace(",", "").strip()
    pe = str(s.get("pe_ttm") or "").replace(",", "").strip()
    if not price or not pe:
        return ""
    try:
        price_f = float(price)
        pe_f = float(pe)
        if price_f <= 0 or pe_f <= 0:
            return ""
        eps = price_f / pe_f
        val_result = run_financial_rigor(
            "verify-valuation",
            price=price,
            eps=f"{eps:.4f}",
        )
        return f"### 金融严谨性验算（financial_rigor）\n```\n{val_result}\n```"
    except (TypeError, ValueError):
        return ""


def fetch_role_data(
    role: str,
    company: str,
    stock: dict[str, str] | None = None,
    *,
    progress_node: str = "",
    enable_web_search: bool = True,
) -> dict[str, Any]:
    """按分析师角色采集结构化数据，可选联网补充。"""
    from tools.progress import report
    from tools.web_search import is_web_search_available, search_for_role

    resolved = stock or resolve_company(company)
    code = resolved["code"]
    name = resolved["name"]
    keyword = resolved.get("keyword") or name
    days = DATA_LOOKBACK_DAYS
    node = progress_node or role.replace("-", "_")

    sections: dict[str, str] = {}
    sources: list[str] = []
    web_search_used = False
    web_engines: list[str] = []

    report(node, f"采集 {name} 的 {role} 数据", phase="fetch_data", status="running")

    profile_text, profile_sources = _fetch_profile_section(code, name)
    sections["公司画像"] = profile_text
    sources.extend(profile_sources)

    if role == "business-analyst":
        report(node, "拉取定期报告与经营公告…", phase="fetch_section")
        sections["定期报告"] = _fetch_periodic_reports(code, name, days)
        sections["市场新闻"] = _fetch_market_news(code, name, days)
        sections["权威媒体"] = _fetch_press(code, name, days)
        sources.extend(["巨潮资讯", "交易所", "七网披露媒体"])

    elif role == "financial-analyst":
        report(node, "拉取财报与估值数据…", phase="fetch_section")
        sections["定期报告"] = _fetch_periodic_reports(code, name, days)
        sections["估值历史"] = _fetch_pe_history(code)
        rigor = _run_financial_rigor_checks(resolved)
        if rigor:
            sections["金融验算"] = rigor
        sources.extend(["东财 datacenter", "巨潮资讯", "financial_rigor"])

    elif role == "industry-researcher":
        report(node, "拉取行业新闻与研报…", phase="fetch_section")
        sections["市场新闻"] = _fetch_market_news(code, name, days)
        sections["权威媒体"] = _fetch_press(code, name, days)
        sections["研报"] = _fetch_reports(code, name, days)
        sources.extend(["市场新闻聚合", "七网", "同花顺/雪球研报"])

    elif role == "risk-assessor":
        report(node, "拉取监管与治理相关公告…", phase="fetch_section")
        sections["监管问询"] = _fetch_regulatory(code, name, days)
        sections["近期公告"] = _fetch_announcements(code, name, days)
        sections["市场新闻"] = _fetch_market_news(code, name, days)
        sources.extend(["交易所问询", "巨潮公告", "市场新闻"])

    if enable_web_search and is_web_search_available():
        report(node, "联网搜索补充公开信息…", phase="fetch_section")
        web_text, web_engines = search_for_role(role, name, stock_code=code)
        if web_text:
            sections["联网搜索"] = web_text
            web_search_used = True
            sources.append("联网搜索(" + "+".join(web_engines) + ")")

    window_note = (
        f"> **范围**：{name}（{code}）· 近 {days} 天 · "
        f"角色: {role}\n\n"
    )
    text_parts = [window_note]
    for title, body in sections.items():
        if body and "（无数据）" not in body:
            text_parts.append(f"## {title}\n{body}")

    text = "\n\n".join(text_parts) if len(text_parts) > 1 else (
        "（未能获取任何结构化数据，请基于已知信息分析并标注数据缺口）"
    )
    data_available = len(text_parts) > 1

    report(node, f"采集完成：{len(sections)} 类数据", phase="fetch_data", status="running")

    return {
        "code": code,
        "name": name,
        "market": resolved.get("market", ""),
        "sections": sections,
        "text": text,
        "sources_used": sources,
        "data_available": data_available,
        "web_search_used": web_search_used,
        "web_engines": web_engines,
    }
