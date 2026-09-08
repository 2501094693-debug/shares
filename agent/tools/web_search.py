"""联网搜索：Tavily（优先）+ DuckDuckGo（免 Key 备用）。"""

from __future__ import annotations

import logging
from typing import Any

from config import ENABLE_WEB_SEARCH, TAVILY_API_KEY, WEB_SEARCH_MAX_RESULTS

logger = logging.getLogger(__name__)


def is_web_search_available() -> bool:
    if not ENABLE_WEB_SEARCH:
        return False
    if TAVILY_API_KEY:
        return True
    return _ddg_available()


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


def search_web(query: str, max_results: int | None = None) -> tuple[str, str]:
    """执行联网搜索，返回 (格式化文本, 引擎名称)。"""
    if not ENABLE_WEB_SEARCH:
        return "", ""

    limit = max_results or WEB_SEARCH_MAX_RESULTS
    try:
        if TAVILY_API_KEY:
            results = _search_tavily(query, limit)
            engine = "Tavily"
        elif _ddg_available():
            results = _search_ddg(query, limit)
            engine = "DuckDuckGo"
        else:
            return (
                "（联网搜索未配置：请安装 ddgs，或设置 TAVILY_API_KEY）",
                "",
            )
        return _fmt_results(results), engine
    except Exception as exc:
        logger.warning("联网搜索失败 query=%s: %s", query, exc)
        return f"（联网搜索失败: {exc}）", ""


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


SEARCH_QUERIES: dict[str, list[str]] = {
    "business-analyst": [
        "年报 半年报 商业模式 主营业务 收入结构",
        "护城河 竞争优势 最新新闻",
    ],
    "financial-analyst": [
        "年报 财务 营收 净利润 ROE 现金流",
        "估值 PE PB 盈利预测",
    ],
    "industry-researcher": [
        "行业格局 市场份额 竞争对手",
        "产业政策 行业趋势",
    ],
    "risk-assessor": [
        "监管 问询函 处罚 诉讼",
        "管理层 股东减持 治理 关联交易",
    ],
}


def search_for_role(
    role: str,
    company: str,
    *,
    stock_code: str = "",
    max_results_per_query: int | None = None,
) -> tuple[str, list[str]]:
    queries = SEARCH_QUERIES.get(role, ["最新资讯 财报"])
    engines: list[str] = []
    blocks: list[str] = []
    per_query = max_results_per_query or max(4, WEB_SEARCH_MAX_RESULTS // max(len(queries), 1))

    for q in queries:
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
