"""公告结果的轻量处理（可扩展）。

设计原则：
- 检索方式由 search_method 形式化生成；
- 检索结果按「维度 → 子查询」分组展示，同一公告可出现在多个子查询下；
- 组内仅做轻量去重 + 时间倒序；
- 以后要加正文摘要、打分等，优先改本模块。
"""
from __future__ import annotations

from typing import Any


PROCESS_NOTE = (
    "结果按子查询分组；组内按公告 id（否则标题+日期）去重，"
    "再按发布时间倒序。同一公告命中多条规则时，会在对应分组各出现一次。"
)


def _sort_key(item: dict[str, Any]) -> tuple:
    ms = item.get("published_ms")
    if isinstance(ms, int):
        return (0, -ms)
    return (1, str(item.get("published_at") or ""))


def _dedup_key(hit: dict[str, Any]) -> str:
    key = str(hit.get("dedup_key") or "")
    if key:
        return key
    aid = str(hit.get("announcement_id") or "").strip()
    if aid:
        return f"id:{aid}"
    return f"tp:{hit.get('title') or ''}|{hit.get('published_at') or ''}"


def _public_item(hit: dict[str, Any]) -> dict[str, Any]:
    return {
        "dedup_key": _dedup_key(hit),
        "title": hit.get("title") or "",
        "published_at": hit.get("published_at") or "",
        "published_ms": hit.get("published_ms"),
        "url": hit.get("url") or "",
        "adjunct_url": hit.get("adjunct_url") or "",
        "category_cn": hit.get("category_cn") or "",
        "source": hit.get("source") or "巨潮资讯",
        "query_id": hit.get("query_id") or "",
        "query_title": hit.get("query_title") or "",
        "matched_by": hit.get("matched_by") or "",
        "matched_terms": list(hit.get("matched_terms") or []),
    }


def dedupe_hits(raw_hits: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """单组内去重，按发布时间倒序。"""
    buckets: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for hit in raw_hits:
        key = _dedup_key(hit)
        if key not in buckets:
            buckets[key] = _public_item(hit)
            order.append(key)
            continue
        bucket = buckets[key]
        for field in ("title", "published_at", "url", "adjunct_url", "category_cn", "source", "query_title"):
            if not bucket.get(field) and hit.get(field):
                bucket[field] = hit.get(field)
        if bucket.get("published_ms") is None and hit.get("published_ms") is not None:
            bucket["published_ms"] = hit.get("published_ms")
    items = [buckets[k] for k in order]
    items.sort(key=_sort_key)
    return items


def build_result_groups(
    query_packs: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """按子查询分组：每组带 symbol/label 与组内去重后的 items。"""
    groups: list[dict[str, Any]] = []
    for pack in query_packs:
        meta = pack.get("meta") or {}
        items = dedupe_hits(pack.get("hits") or [])
        groups.append(
            {
                "qid": meta.get("qid") or "",
                "symbol": meta.get("symbol") or "",
                "index": meta.get("index") or len(groups) + 1,
                "label": meta.get("title") or "",
                "ok": bool(meta.get("ok")),
                "raw_count": int(meta.get("raw_count") or 0),
                "count": len(items),
                "items": items,
            }
        )
    return groups
