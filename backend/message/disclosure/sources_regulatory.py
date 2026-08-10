"""问询函 / 监管措施 / 处罚相关信息披露。"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from .constants import MAX_PAGES, REGULATORY_TITLE_KEYWORDS
from .http_util import detect_market, normalize_code, safe_str
from .sources_cninfo import fetch_cninfo_announcements
from .sources_sse import fetch_sse_inquiries
from .sources_szse import fetch_szse_inquiries


def _is_regulatory_title(title: str) -> bool:
    return any(k in title for k in REGULATORY_TITLE_KEYWORDS)


def _classify_kind(title: str) -> str:
    # 问询类优先，避免标题同时出现「风险提示」等词时误判
    if any(k in title for k in ("问询函", "关注函", "监管函", "警示函", "监管工作函")):
        return "inquiry"
    penalty_keys = (
        "行政处罚",
        "市场禁入",
        "处罚决定",
        "纪律处分",
        "通报批评",
        "公开谴责",
        "监管措施",
        "责令改正",
        "立案告知",
        "立案调查",
        "立案",
    )
    if any(k in title for k in penalty_keys):
        return "penalty"
    return "regulatory"


def fetch_regulatory_from_cninfo(
    code: str,
    *,
    start: datetime | None = None,
    end: datetime | None = None,
    max_pages: int = MAX_PAGES,
) -> list[dict[str, Any]]:
    """从巨潮公告里筛公司披露的问询/处罚相关文件（第一手附件）。"""
    rows = fetch_cninfo_announcements(
        code, start=start, end=end, max_pages=max_pages
    )
    out: list[dict[str, Any]] = []
    for row in rows:
        title = safe_str(row.get("title"))
        if not _is_regulatory_title(title):
            continue
        item = dict(row)
        item["kind"] = _classify_kind(title)
        item["channel"] = "regulatory"
        item["source"] = "巨潮资讯(监管相关披露)"
        item["why"] = item["kind"]
        out.append(item)
    return out


def fetch_regulatory(
    code: str,
    *,
    start: datetime | None = None,
    end: datetime | None = None,
    max_pages: int = MAX_PAGES,
) -> list[dict[str, Any]]:
    """汇总问询与处罚相关信息。

    来源：
    1. 上交所 / 深交所问询函公开接口（按市场）
    2. 巨潮中公司披露的问询函/处罚决定等原文附件
    """
    code = normalize_code(code)
    if not code:
        return []

    items: list[dict[str, Any]] = []
    market = detect_market(code)
    page_cap = min(20, max_pages)

    if market == "sse":
        items.extend(
            fetch_sse_inquiries(
                code, start=start, end=end, max_pages=page_cap
            )
        )
    elif market == "szse":
        items.extend(fetch_szse_inquiries(code, max_pages=page_cap))

    # 沪/深/北：公司在法定渠道披露的「收到问询函/处罚」类公告
    items.extend(
        fetch_regulatory_from_cninfo(
            code, start=start, end=end, max_pages=max_pages
        )
    )
    return items
