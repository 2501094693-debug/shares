"""统一结果字典构造。"""

from __future__ import annotations

from typing import Any

from .http_util import safe_str


def make_item(
    *,
    title: str,
    published_at: str = "",
    url: str = "",
    source: str,
    channel: str,
    kind: str,
    summary: str = "",
    why: str = "",
    code: str = "",
    name: str = "",
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    item: dict[str, Any] = {
        "title": safe_str(title),
        "summary": safe_str(summary),
        "source": safe_str(source),
        "channel": safe_str(channel),  # sse / szse / bse / cninfo / regulatory
        "url": safe_str(url),
        "published_at": safe_str(published_at),
        "kind": safe_str(kind),  # notice / inquiry / penalty / regulatory
        "why": safe_str(why),
        "code": safe_str(code),
        "name": safe_str(name),
    }
    if extra:
        item.update(extra)
    return item
