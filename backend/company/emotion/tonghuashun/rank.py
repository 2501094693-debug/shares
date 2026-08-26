"""同花顺个股社区热度：手机讨论页 ``stock_rank``。"""

from __future__ import annotations

import logging
from typing import Any

from core.codes import normalize_code, safe_str

from company.emotion.tonghuashun._common import (
    CHANNEL_RANK,
    SOURCE,
    empty_pack,
    mobile_page_url,
    query_forum_index,
    resolve_keyword,
    to_int,
)

logger = logging.getLogger(__name__)


def fetch_rank(code_or_name: str, *, market: str = "") -> dict[str, Any]:
    """个股讨论热度名次（手机 forum/v2/index 的 stock_rank）。"""
    del market
    resolved = resolve_keyword(code_or_name)
    code = resolved["code"] or normalize_code(code_or_name)
    name = resolved["name"]
    page = mobile_page_url(code)
    if not code:
        return empty_pack(channel=CHANNEL_RANK, error="缺少股票代码", page=page)
    try:
        forum = query_forum_index(code)
    except Exception as exc:  # noqa: BLE001
        logger.warning("同花顺个股热度失败 %s: %s", code, exc)
        return empty_pack(
            code=code,
            name=name,
            keyword=resolved["keyword"],
            channel=CHANNEL_RANK,
            error=str(exc),
            page=page,
        )
    block = forum.get("forum") if isinstance(forum.get("forum"), dict) else {}
    rank = forum.get("stock_rank") if isinstance(forum.get("stock_rank"), dict) else {}
    name = safe_str(block.get("name")) or name
    place = to_int(rank.get("rank"))
    amount = to_int(rank.get("rank_amount"))
    change = to_int(rank.get("rank_change"))
    if not rank:
        item = {
            "code": code,
            "name": name,
            "title": "未返回讨论热度",
            "summary": "未返回讨论热度",
            "url": page,
            "source": SOURCE,
            "channel": CHANNEL_RANK,
            "rank": 0,
            "heat": 0,
            "rank_change": 0,
        }
        return {
            "code": code,
            "name": name,
            "keyword": resolved["keyword"],
            "source": SOURCE,
            "channel": CHANNEL_RANK,
            "count": 1,
            "total": 1,
            "items": [item],
            "page": page,
            "rank": 0,
            "heat": 0,
            "rank_change": 0,
            "title": item["title"],
        }
    title = f"{name} 讨论热度第 {place} / {amount}，变动 {change:+d}" if name else f"第 {place} / {amount}"
    item = {
        "code": code,
        "name": name,
        "title": title,
        "summary": title,
        "url": page,
        "source": SOURCE,
        "channel": CHANNEL_RANK,
        "rank": place,
        "heat": amount,
        "rank_amount": amount,
        "rank_change": change,
        "media_name": "讨论热度",
        "fid": to_int(block.get("fid")),
    }
    return {
        "code": code,
        "name": name,
        "keyword": resolved["keyword"],
        "source": SOURCE,
        "channel": CHANNEL_RANK,
        "count": 1,
        "total": 1,
        "items": [item],
        "page": page,
        "rank": place,
        "heat": amount,
        "rank_amount": amount,
        "rank_change": change,
        "title": title,
        "fid": to_int(block.get("fid")),
    }


def fetch_hot_list(*, page: int = 1, page_size: int = 20) -> dict[str, Any]:
    """全市场榜已去掉（原网页端最热个股）。需要个股代码请用 ``fetch_rank``。"""
    del page, page_size
    return empty_pack(
        channel=CHANNEL_RANK,
        error="同花顺社区只保留手机个股讨论热度，请传 code",
        page=mobile_page_url(),
    )


def query_hot_page(*, code: str = "") -> dict[str, Any]:
    """兼容旧名；实际走手机 forum/v2/index。"""
    if not code:
        return {}
    return query_forum_index(code)
