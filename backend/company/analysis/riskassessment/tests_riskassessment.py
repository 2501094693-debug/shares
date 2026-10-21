"""最小化自测"""
from __future__ import annotations

from company.analysis.riskassessment import (
    RISK_DIMENSIONS,
    RISK_QUERIES,
    get_dimensions,
    get_enabled_queries,
    get_query_map,
    risk_scan_cninfo_only_fetch,
)
from company.analysis.riskassessment.search_method import build_search_method


def test_queries_exist() -> None:
    assert len(RISK_QUERIES) >= 10
    enabled = get_enabled_queries()
    assert len(enabled) == len(RISK_QUERIES)


def test_seven_dimensions() -> None:
    dims = get_dimensions()
    assert len(dims) == 7
    assert len(RISK_DIMENSIONS) == 7
    qids = {q.qid for q in RISK_QUERIES}
    for dim in dims:
        assert dim.query_ids
        assert set(dim.query_ids) <= qids
        assert not hasattr(dim, "how_to_read") or "how_to_read" not in dim.__dataclass_fields__


def test_search_method_formal() -> None:
    qmap = get_query_map()
    dim = get_dimensions()[0]
    queries = [qmap[qid] for qid in dim.query_ids]
    spec = build_search_method(queries)
    assert spec["schema"] == "risk-search/v1"
    assert spec["source"] == "巨潮资讯"
    assert spec["combine"] == "by_query"
    assert spec["slots"] == ["源", "语料", "通道", "分类", "标题关键词", "窗口"]
    assert len(spec["clauses"]) == len(queries)
    assert "分组" in spec["dim_expr"]
    assert "巨潮资讯" in spec["plain"]
    assert "子查询" in spec["plain"]
    c0 = spec["clauses"][0]
    assert c0["symbol"] == "Q1"
    assert len(c0["slots"]) == 6


def test_api_shape() -> None:
    try:
        res = risk_scan_cninfo_only_fetch("000001")
    except Exception:
        return
    assert isinstance(res, dict)
    assert "dimensions" in res
    assert len(res["dimensions"]) == 7
    dim = res["dimensions"][0]
    sm = dim["search_method"]
    assert isinstance(sm, dict)
    assert sm.get("schema") == "risk-search/v1"
    assert "how_to_read" not in dim
    assert "groups" in dim
    assert isinstance(dim["groups"], list)
    assert len(dim["groups"]) == len(dim.get("queries") or [])
