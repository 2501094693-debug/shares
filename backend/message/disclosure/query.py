"""统一查询入口。"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Iterable, Literal

from .http_util import (
    dedupe,
    default_start,
    detect_market,
    normalize_code,
    sort_key,
    within_range,
)
from .sources_bse import fetch_bse_announcements
from .sources_cninfo import fetch_cninfo_announcements
from .sources_regulatory import fetch_regulatory
from .sources_sse import fetch_sse_announcements
from .sources_szse import fetch_szse_announcements

Channel = Literal["sse", "szse", "bse", "cninfo", "auto"]


def _resolve_channels(code: str, channel: Channel | str) -> list[str]:
    ch = (channel or "auto").lower().strip()
    if ch == "auto":
        market = detect_market(code)
        # auto：本市场官方源 + 巨潮双通道，便于交叉核对
        if market == "sse":
            return ["sse", "cninfo"]
        if market == "szse":
            return ["szse", "cninfo"]
        if market == "bse":
            return ["bse", "cninfo"]
        return ["cninfo"]
    if ch in {"sse", "szse", "bse", "cninfo"}:
        return [ch]
    if ch in {"all", "*"}:
        return ["sse", "szse", "bse", "cninfo"]
    raise ValueError(f"不支持的 channel: {channel}")


def query_announcements(
    code: str,
    *,
    channel: Channel | str = "auto",
    start: datetime | None = None,
    end: datetime | None = None,
    days: int | None = 365,
    max_pages: int = 20,
) -> list[dict[str, Any]]:
    """查询指定公司交易所/巨潮公告。

    channel:
      - auto: 按代码市场选官方源，并附带巨潮
      - sse / szse / bse / cninfo: 单一通道
      - all: 四通道都查（跨市场代码可能部分为空）
    """
    code = normalize_code(code)
    if not code:
        return []

    if start is None and days is not None:
        start = default_start(days)

    channels = _resolve_channels(code, channel)
    collected: list[dict[str, Any]] = []

    for ch in channels:
        if ch == "sse":
            collected.extend(
                fetch_sse_announcements(
                    code, start=start, end=end, max_pages=max_pages
                )
            )
        elif ch == "szse":
            collected.extend(
                fetch_szse_announcements(
                    code, start=start, end=end, max_pages=max_pages
                )
            )
        elif ch == "bse":
            collected.extend(
                fetch_bse_announcements(
                    code, start=start, end=end, max_pages=max_pages
                )
            )
        elif ch == "cninfo":
            collected.extend(
                fetch_cninfo_announcements(
                    code, start=start, end=end, max_pages=max_pages
                )
            )

    filtered = [x for x in collected if within_range(x, start, end)]
    return sorted(dedupe(filtered), key=sort_key)


def query_regulatory(
    code: str,
    *,
    start: datetime | None = None,
    end: datetime | None = None,
    days: int | None = 365 * 2,
    max_pages: int = 20,
) -> list[dict[str, Any]]:
    """查询问询函、监管措施、处罚相关信息披露。"""
    code = normalize_code(code)
    if not code:
        return []
    if start is None and days is not None:
        start = default_start(days)

    items = fetch_regulatory(
        code, start=start, end=end, max_pages=max_pages
    )
    filtered = [x for x in items if within_range(x, start, end)]
    return sorted(dedupe(filtered), key=sort_key)


def query_company_messages(
    code: str,
    *,
    channel: Channel | str = "auto",
    include_regulatory: bool = True,
    start: datetime | None = None,
    end: datetime | None = None,
    days: int | None = 365,
    max_pages: int = 20,
) -> dict[str, Any]:
    """一次返回公告 +（可选）监管信息。"""
    code = normalize_code(code)
    notices = query_announcements(
        code,
        channel=channel,
        start=start,
        end=end,
        days=days,
        max_pages=max_pages,
    )
    regulatory: list[dict[str, Any]] = []
    if include_regulatory:
        regulatory = query_regulatory(
            code,
            start=start,
            end=end,
            days=days if days is not None else 365 * 2,
            max_pages=max_pages,
        )

    return {
        "code": code,
        "market": detect_market(code),
        "channel": channel,
        "notices": notices,
        "regulatory": regulatory,
        "notice_count": len(notices),
        "regulatory_count": len(regulatory),
    }


def query_multi(
    codes: Iterable[str],
    **kwargs: Any,
) -> dict[str, dict[str, Any]]:
    """批量查询。"""
    out: dict[str, dict[str, Any]] = {}
    for raw in codes:
        code = normalize_code(raw)
        if not code:
            continue
        out[code] = query_company_messages(code, **kwargs)
    return out
