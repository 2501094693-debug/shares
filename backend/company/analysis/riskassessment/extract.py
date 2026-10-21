"""按七维调用 fetch_announcements，并按子查询分组整理结果。"""
from __future__ import annotations

import logging
from typing import Any

from company.news.official.cninfo.fetch import fetch_announcements

from .events import build_event
from .process import PROCESS_NOTE, build_result_groups
from .search_method import build_clause, build_search_method, describe_query_method
from .taxonomy import (
    RiskDimension,
    RiskQuery,
    get_dimensions,
    get_enabled_queries,
    get_query_map,
)

logger = logging.getLogger(__name__)


def _matched_by(q: RiskQuery) -> str:
    if q.tab and q.tab != "fulltext" and not q.category and not q.keyword:
        return "tab"
    if q.category and not q.keyword:
        return "category"
    if q.keyword and not q.category:
        return "keyword"
    if q.category and q.keyword:
        return "category+keyword"
    return "tab"


class CninfoRiskExtractor:
    def __init__(self, code: str) -> None:
        self.code = code.strip()

    def _run_query(self, q: RiskQuery) -> dict[str, Any]:
        """执行单条查询，返回 query 元数据 + 原始命中。"""
        clause = build_clause(q)
        meta: dict[str, Any] = {
            "qid": q.qid,
            "title": q.title,
            "desc": q.desc,
            "risk_type": q.risk_type,
            "level": q.level,
            "method": describe_query_method(q),
            "expr": clause.get("expr") or "",
            "symbol": clause.get("symbol") or "",
            "filters": clause.get("filters") or [],
            "tab": q.tab,
            "tab_label": clause.get("tab_label") or "",
            "category": list(q.category or []),
            "keyword": q.keyword,
            "keyword_terms": clause.get("keyword_terms") or [],
            "days": q.days,
            "ok": False,
            "raw_count": 0,
            "error": "",
        }
        try:
            res = fetch_announcements(
                self.code,
                tab=q.tab or "fulltext",
                category=q.category,
                keyword=q.keyword or "",
                days=q.days,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("riskassessment query failed qid=%s code=%s: %s", q.qid, self.code, exc)
            meta["error"] = str(exc)
            return {"meta": meta, "hits": [], "name": "", "org_id": ""}

        items = res.get("items") or []
        meta["ok"] = True
        meta["raw_count"] = len(items)
        code_res = res.get("code") or self.code
        name_res = res.get("name") or ""
        org_res = res.get("org_id") or ""
        matched_by = _matched_by(q)

        hits: list[dict[str, Any]] = []
        for item in items:
            ev = build_event(
                code=code_res,
                name=name_res,
                org_id=org_res,
                item=item,
                risk_type=q.risk_type,
                risk_level=q.level,
                query_id=q.qid,
                query_title=q.title,
                matched_by=matched_by,
            )
            d = ev.to_dict()
            d.pop("raw", None)
            hits.append(d)

        return {"meta": meta, "hits": hits, "name": name_res, "org_id": org_res}

    def run_dimensions(self, dimensions: list[RiskDimension] | None = None) -> dict[str, Any]:
        dimensions = dimensions or get_dimensions()
        qmap = get_query_map()
        enabled = {q.qid for q in get_enabled_queries()}

        out_dims: list[dict[str, Any]] = []
        total_raw = 0
        name = ""
        org_id = ""

        for dim in dimensions:
            queries_meta: list[dict[str, Any]] = []
            query_packs: list[dict[str, Any]] = []
            dim_queries: list[RiskQuery] = []

            for qid in dim.query_ids:
                q = qmap.get(qid)
                if not q or qid not in enabled:
                    continue
                dim_queries.append(q)
                pack = self._run_query(q)
                clause = build_clause(q, len(dim_queries))
                pack["meta"]["symbol"] = clause["symbol"]
                pack["meta"]["expr"] = clause["expr"]
                pack["meta"]["index"] = clause["index"]
                queries_meta.append(pack["meta"])
                query_packs.append(pack)
                total_raw += int(pack["meta"].get("raw_count") or 0)
                if not name and pack.get("name"):
                    name = pack["name"]
                if not org_id and pack.get("org_id"):
                    org_id = pack["org_id"]

            groups = build_result_groups(query_packs)
            count = sum(int(g.get("count") or 0) for g in groups)
            out_dims.append(
                {
                    "key": dim.key,
                    "no": dim.no,
                    "name": dim.name,
                    "search_method": build_search_method(dim_queries),
                    "process_note": PROCESS_NOTE,
                    "queries": queries_meta,
                    "groups": groups,
                    "count": count,
                    "raw_count": sum(int(q.get("raw_count") or 0) for q in queries_meta),
                    "ok": all(bool(q.get("ok")) for q in queries_meta) if queries_meta else True,
                }
            )

        hit_dims = sum(1 for d in out_dims if d["count"] > 0)
        return {
            "code": self.code,
            "name": name,
            "org_id": org_id,
            "dimensions": out_dims,
            "stats": {
                "total_items_raw": total_raw,
                "total_items": sum(d["count"] for d in out_dims),
                "dimension_count": len(out_dims),
                "hit_dimensions": hit_dims,
                "queries": [q for d in out_dims for q in d["queries"]],
            },
        }
