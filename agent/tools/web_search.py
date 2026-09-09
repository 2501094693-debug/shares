"""联网搜索补充：Tavily（优先）→ 必应国内版 → DuckDuckGo。

官方披露（交易所 / 巨潮 / 七网）仍是业务简述主线；本模块只补充最新财报解读、
行业报告等公开网页，不得覆盖主线事实。
"""

from __future__ import annotations

import logging
from typing import Any, Callable

import requests
from lxml import html

from config import ENABLE_WEB_SEARCH, TAVILY_API_KEY, WEB_SEARCH_MAX_RESULTS

logger = logging.getLogger(__name__)

_BING_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}

BUSINESS_SEARCH_QUERIES: tuple[str, ...] = (
    "最新年报 半年报 季报 商业模式 主营业务 收入结构",
    "行业报告 市场份额 竞争格局",
    "护城河 竞争优势 飞轮 平台效应",
    "客户价值 业务矩阵 协同 产品",
)

COMPETITION_SEARCH_QUERIES: tuple[str, ...] = (
    "行业市场规模 增速 渗透率 2024 2025",
    "竞争格局 市场份额 主要竞争对手",
    "行业报告 产业链 上下游 价值分配",
    "技术变革 政策影响 新进入者 国产替代",
    "细分赛道 竞争策略 龙头 挑战者",
)

RISK_SEARCH_QUERIES: tuple[str, ...] = (
    "监管处罚 问询函 关注函 立案 最新",
    "CEO 董事长 总经理 管理层 访谈 言论 战略",
    "关联交易 股权质押 减持 回购 分红",
    "行业监管政策 反垄断 环保 数据安全 最新",
    "诉讼 仲裁 担保 违规 整改",
    "新业务 亏损 扩张 风险 不确定性",
)


def is_web_search_available() -> bool:
    return web_search_status()[0]


def web_search_status() -> tuple[bool, str]:
    """返回 (是否可用, 原因/引擎)。"""
    if not ENABLE_WEB_SEARCH:
        return False, "ENABLE_WEB_SEARCH 已关闭，请在 .env 设为 true"
    if TAVILY_API_KEY:
        return True, "Tavily"
    return True, "必应国内版（可直接联网；配置 TAVILY_API_KEY 效果更好）"


def _ddg_available() -> bool:
    try:
        from ddgs import DDGS  # noqa: F401

        return True
    except ImportError:
        try:
            from duckduckgo_search import DDGS  # noqa: F401

            return True
        except ImportError:
            return False


def _fmt_results(results: list[dict[str, Any]], *, max_snippet: int = 600) -> str:
    if not results:
        return "（未找到相关搜索结果）"
    lines: list[str] = []
    for i, item in enumerate(results, 1):
        title = item.get("title", "")
        url = item.get("url", "") or item.get("href", "")
        content = (item.get("content") or item.get("body") or "")[:max_snippet]
        lines.append(f"{i}. **{title}**\n   来源: {url}\n   {content}")
    return "\n\n".join(lines)


def _search_tavily(query: str, max_results: int) -> list[dict[str, Any]]:
    from tavily import TavilyClient

    client = TavilyClient(api_key=TAVILY_API_KEY)
    response = client.search(query=query, max_results=max_results, search_depth="advanced")
    return response.get("results", []) or []


def _search_ddg(query: str, max_results: int) -> list[dict[str, Any]]:
    try:
        from ddgs import DDGS
    except ImportError:
        from duckduckgo_search import DDGS

    with DDGS(timeout=20) as ddgs:
        rows = list(ddgs.text(query, max_results=max_results))
    return [
        {
            "title": r.get("title", ""),
            "url": r.get("href", ""),
            "content": r.get("body", ""),
        }
        for r in rows
    ]


def _search_bing_cn(query: str, max_results: int) -> list[dict[str, Any]]:
    """国内可访问的必应网页搜索，作为免 Key 兜底。"""
    resp = requests.get(
        "https://cn.bing.com/search",
        params={"q": query, "setlang": "zh-CN"},
        headers=_BING_HEADERS,
        timeout=20,
    )
    resp.raise_for_status()
    tree = html.fromstring(resp.content)
    results: list[dict[str, Any]] = []
    for item in tree.xpath('//li[contains(@class,"b_algo")]'):
        anchors = item.xpath(".//h2/a")
        if not anchors:
            continue
        title = (anchors[0].text_content() or "").strip()
        url = (anchors[0].get("href") or "").strip()
        if not title or not url:
            continue
        paras = item.xpath(".//p")
        snippet = (paras[0].text_content() or "").strip() if paras else ""
        results.append({"title": title, "url": url, "content": snippet})
        if len(results) >= max_results:
            break
    return results


def search_web(query: str, max_results: int | None = None) -> tuple[str, str]:
    """执行联网搜索，返回 (格式化文本, 引擎名称)。失败时自动换引擎。"""
    if not ENABLE_WEB_SEARCH:
        return "", ""

    limit = max_results or WEB_SEARCH_MAX_RESULTS
    attempts: list[tuple[str, Callable[[str, int], list[dict[str, Any]]]]] = []
    if TAVILY_API_KEY:
        attempts.append(("Tavily", _search_tavily))
    attempts.append(("BingCN", _search_bing_cn))
    if _ddg_available():
        attempts.append(("DuckDuckGo", _search_ddg))

    errors: list[str] = []
    for engine, fn in attempts:
        try:
            results = fn(query, limit)
            if results:
                return _fmt_results(results), engine
            errors.append(f"{engine}: 无结果")
        except Exception as exc:
            logger.warning("联网搜索失败 engine=%s query=%s: %s", engine, query, exc)
            errors.append(f"{engine}: {exc}")
    return f"（联网搜索失败: {'; '.join(errors)}）", ""


def search_company_info(
    company: str,
    query_suffix: str,
    *,
    stock_code: str = "",
    max_results: int | None = None,
) -> tuple[str, str]:
    if not is_web_search_available():
        return "", ""

    code_part = f" {stock_code}" if stock_code else ""
    query = f"{company}{code_part} {query_suffix}".strip()
    return search_web(query, max_results=max_results)


def search_for_business(
    company: str,
    *,
    stock_code: str = "",
    max_results_per_query: int | None = None,
    progress_cb: Callable[[str], None] | None = None,
) -> tuple[str, list[str]]:
    """业务简述专用检索：商业模式、行业报告、护城河、客户价值。"""
    engines: list[str] = []
    blocks: list[str] = []
    per_query = max_results_per_query or max(
        4, WEB_SEARCH_MAX_RESULTS // max(len(BUSINESS_SEARCH_QUERIES), 1)
    )

    for q in BUSINESS_SEARCH_QUERIES:
        if progress_cb:
            progress_cb(q)
        text, engine = search_company_info(
            company,
            q,
            stock_code=stock_code,
            max_results=per_query,
        )
        if text and not text.startswith("（"):
            blocks.append(f"### 检索：{q}\n{text}")
            if engine and engine not in engines:
                engines.append(engine)

    if not blocks:
        return "", engines
    return "\n\n".join(blocks), engines


def search_for_competition(
    company: str,
    *,
    industry_name: str = "",
    stock_code: str = "",
    max_results_per_query: int | None = None,
    progress_cb: Callable[[str], None] | None = None,
) -> tuple[str, list[str]]:
    """行业竞争分析专用检索：市场规模、竞争格局、产业链、行业趋势。"""
    engines: list[str] = []
    blocks: list[str] = []
    per_query = max_results_per_query or max(
        4, WEB_SEARCH_MAX_RESULTS // max(len(COMPETITION_SEARCH_QUERIES), 1)
    )

    industry_part = f"{industry_name} " if industry_name else ""
    for q in COMPETITION_SEARCH_QUERIES:
        if progress_cb:
            progress_cb(q)
        query_suffix = f"{industry_part}{q}".strip()
        text, engine = search_company_info(
            company,
            query_suffix,
            stock_code=stock_code,
            max_results=per_query,
        )
        if text and not text.startswith("（"):
            blocks.append(f"### 检索：{query_suffix}\n{text}")
            if engine and engine not in engines:
                engines.append(engine)

    if not blocks:
        return "", engines
    return "\n\n".join(blocks), engines


def search_for_risk(
    company: str,
    *,
    industry_name: str = "",
    stock_code: str = "",
    max_results_per_query: int | None = None,
    progress_cb: Callable[[str], None] | None = None,
) -> tuple[str, list[str]]:
    """投资风险与管理层质量评估专用检索：监管动态、管理层言论、治理风险。"""
    engines: list[str] = []
    blocks: list[str] = []
    per_query = max_results_per_query or max(
        4, WEB_SEARCH_MAX_RESULTS // max(len(RISK_SEARCH_QUERIES), 1)
    )

    industry_part = f"{industry_name} " if industry_name else ""
    for q in RISK_SEARCH_QUERIES:
        if progress_cb:
            progress_cb(q)
        query_suffix = f"{industry_part}{q}".strip()
        text, engine = search_company_info(
            company,
            query_suffix,
            stock_code=stock_code,
            max_results=per_query,
        )
        if text and not text.startswith("（"):
            blocks.append(f"### 检索：{query_suffix}\n{text}")
            if engine and engine not in engines:
                engines.append(engine)

    if not blocks:
        return "", engines
    return "\n\n".join(blocks), engines
