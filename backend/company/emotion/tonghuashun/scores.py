"""同花顺个股社区快照：手机讨论页的讨论热度名次。"""

from __future__ import annotations

from typing import Any

from company.emotion.tonghuashun._common import CHANNEL_SCORES, SOURCE, mobile_page_url
from company.emotion.tonghuashun.rank import fetch_rank


def query_scores(code: str) -> dict[str, Any]:
    """个股讨论热度快照。"""
    return fetch_rank(code)


def fetch_scores(code_or_name: str) -> dict[str, Any]:
    pack = fetch_rank(code_or_name)
    out = dict(pack)
    out["channel"] = CHANNEL_SCORES
    out["source"] = SOURCE
    item = (pack.get("items") or [None])[0] if pack.get("items") else None
    if isinstance(item, dict):
        row = dict(item)
        row["channel"] = CHANNEL_SCORES
        out["items"] = [row]
        out["title"] = row.get("title") or pack.get("title") or ""
    out["page"] = pack.get("page") or mobile_page_url(str(pack.get("code") or ""))
    return out
