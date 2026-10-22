"""风险事件数据结构"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from .taxonomy import RiskLevel, RiskType


@dataclass(slots=True)
class RiskEvent:
    event_id: str
    code: str
    name: str
    org_id: str
    title: str
    published_at: str
    published_ms: int | None
    url: str
    adjunct_url: str
    category_cn: str
    source: str
    risk_type: RiskType
    risk_level: RiskLevel
    query_id: str
    query_title: str
    matched_by: str  # category/keyword/tab
    matched_terms: list[str]
    dedup_key: str
    raw: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _dedup_key(item: dict[str, Any]) -> str:
    aid = str(item.get("announcement_id") or "").strip()
    if aid:
        return f"id:{aid}"
    title = str(item.get("title") or "").strip()
    pub = str(item.get("published_at") or "").strip()
    return f"tp:{title}|{pub}"


def build_event(
    code: str,
    name: str,
    org_id: str,
    item: dict[str, Any],
    risk_type: RiskType,
    risk_level: RiskLevel,
    query_id: str,
    query_title: str,
    matched_by: str,
    matched_terms: list[str] | None = None,
) -> RiskEvent:
    aid = str(item.get("announcement_id") or "").strip()
    event_id = f"{code}:{aid}" if aid else f"{code}:{_dedup_key(item)}"
    return RiskEvent(
        event_id=event_id,
        code=code or str(item.get("code") or ""),
        name=name or str(item.get("name") or ""),
        org_id=org_id or str(item.get("org_id") or ""),
        title=str(item.get("title") or ""),
        published_at=str(item.get("published_at") or ""),
        published_ms=item.get("published_ms"),
        url=str(item.get("url") or ""),
        adjunct_url=str(item.get("adjunct_url") or ""),
        category_cn=str(item.get("category") or ""),
        source=str(item.get("source") or "巨潮资讯"),
        risk_type=risk_type,
        risk_level=risk_level,
        query_id=query_id,
        query_title=query_title,
        matched_by=matched_by,
        matched_terms=list(matched_terms or []),
        dedup_key=_dedup_key(item),
        raw=item,
    )
