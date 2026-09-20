"""三源个股社区采集，供散户情绪智能体使用。"""

from __future__ import annotations

import logging
import sys
from typing import Any

from agent.config import BACKEND_ROOT

logger = logging.getLogger(__name__)

if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


def _empty(source: str, error: str = "") -> dict[str, Any]:
    return {
        "source": source,
        "channel": "company",
        "count": 0,
        "total": 0,
        "items": [],
        "posts": {"items": [], "count": 0, "error": error},
        "scores": {},
        "rank": {},
        "error": error,
    }


def fetch_eastmoney(
    code_or_name: str,
    *,
    days: int = 3,
    max_pages: int = 3,
    with_replies: bool = False,
) -> dict[str, Any]:
    from company.emotion.eastmoney import fetch_company

    return fetch_company(
        code_or_name,
        kind="all",
        sort="time",
        days=days,
        max_pages=max_pages,
        with_replies=with_replies,
        max_reply_posts=5 if with_replies else 0,
    )


def fetch_tonghuashun(
    code_or_name: str,
    *,
    days: int = 3,
    max_pages: int = 3,
    with_replies: bool = False,
) -> dict[str, Any]:
    from company.emotion.tonghuashun import fetch_company

    return fetch_company(
        code_or_name,
        kind="user",
        sort="time",
        days=days,
        max_pages=max_pages,
        with_replies=with_replies,
        max_reply_posts=5 if with_replies else 0,
    )


def fetch_xueqiu(
    code_or_name: str,
    *,
    days: int = 3,
    max_pages: int = 3,
    with_replies: bool = False,
) -> dict[str, Any]:
    from company.emotion.xueqiu import fetch_company

    return fetch_company(
        code_or_name,
        kind="user",
        sort="time",
        days=days,
        max_pages=max_pages,
        with_replies=with_replies,
        max_reply_posts=5 if with_replies else 0,
    )


def safe_fetch(name: str, fn, *args, **kwargs) -> dict[str, Any]:
    try:
        pack = fn(*args, **kwargs)
        if not isinstance(pack, dict):
            return _empty(name, "返回非字典")
        return pack
    except Exception as exc:  # noqa: BLE001
        logger.warning("采集失败 %s: %s", name, exc)
        return _empty(name, str(exc))
