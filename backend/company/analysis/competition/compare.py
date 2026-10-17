"""同申万三级行业「八看」横截面比对：编排层。

流程：
   resolve_industry → build_universe → fetch_series → build_snapshot
   → build_benchmark / target_position → render → pack

对外入口：``compare_peers(code, industry, report_type, peers, force, view)``。
"""

from __future__ import annotations

import hashlib
import time
from typing import Any

from core.cache import TtlCache

from company.analysis.competition import aggregate, render, universe
from company.analysis.competition.registry import view_groups
from company.analysis.competition.snapshot import build_snapshot
from company.analysis.financialreport._common import (
    normalize_report_type,
    report_type_label,
)

_PACK_TTL = 45 * 60  # 45 分钟
_cache = TtlCache(_PACK_TTL)


def _pack_key(
    l3_code: str, report_type: str, target_code: str, peers: int, latest: str
) -> str:
    raw = f"{l3_code}|{report_type}|{target_code}|{peers}|{latest}"
    return "peers:" + hashlib.md5(raw.encode("utf-8")).hexdigest()


def _build_companies(
    stocks: list[dict[str, Any]],
    series_map: dict[str, list[dict[str, Any]]],
    target_code: str,
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    """把每家序列压成快照，返回 (companies, 剔除项)。"""
    companies: list[dict[str, Any]] = []
    dropped: list[dict[str, str]] = []
    for stock in stocks:
        code = stock["code"]
        series = series_map.get(code) or []
        if not series:
            dropped.append({"code": code, "name": stock.get("name") or code, "reason": "未取到同口径定期报告"})
            continue
        snap = build_snapshot(series)
        if not snap.get("metrics"):
            dropped.append({"code": code, "name": stock.get("name") or code, "reason": "关键科目缺失"})
            continue
        companies.append(
            {
                "code": code,
                "name": stock.get("name") or code,
                "is_target": code == target_code,
                "latest_period": snap.get("latest_period") or "",
                "report_date": snap.get("report_date") or "",
                "strategy_type": snap.get("strategy_type") or "",
                "score_total": snap.get("score_total"),
                "risk_hits": snap.get("risk_hits"),
                "flags": snap.get("flags") or [],
                "metrics": snap.get("metrics") or {},
            }
        )
    return companies, dropped


def _attach_ranks(
    companies: list[dict[str, Any]],
    benchmark: dict[str, Any],
    ranks: dict[str, Any],
) -> None:
    """把 rank/percentile 与相对中位数标记挂回每家公司。"""
    marks = aggregate.mark_vs_median(companies, benchmark)
    for c in companies:
        code = c["code"]
        c["ranks"] = {key: (ranks.get(key) or {}).get(code) for key in ranks}
        c["vs_median"] = marks.get(code) or {}


def _build_by_view(
    companies: list[dict[str, Any]],
    benchmark: dict[str, Any],
    dispersion: dict[str, Any],
) -> list[dict[str, Any]]:
    """按一看~八看 + 综合组织横截面表格数据。"""
    out: list[dict[str, Any]] = []
    for group in view_groups():
        indicators = [
            {
                "key": ind.key,
                "label": ind.label,
                "unit": ind.unit,
                "direction": ind.direction,
            }
            for ind in group.indicators
        ]
        rows = []
        for c in companies:
            values = {ind.key: (c.get("metrics") or {}).get(ind.key) for ind in group.indicators}
            row_ranks = {ind.key: (c.get("ranks") or {}).get(ind.key) for ind in group.indicators}
            rows.append(
                {
                    "code": c["code"],
                    "name": c["name"],
                    "is_target": c.get("is_target", False),
                    "values": values,
                    "ranks": row_ranks,
                }
            )
        out.append(
            {
                "key": group.key,
                "no": group.no,
                "name": group.name,
                "indicators": indicators,
                "rows": rows,
                "benchmark": {ind.key: benchmark.get(ind.key) for ind in group.indicators},
                "dispersion": {
                    ind.key: dispersion.get(ind.key)
                    for ind in group.indicators
                    if ind.key in dispersion
                },
            }
        )
    return out


def compare_peers(
    code: str = "",
    *,
    industry_code: str = "",
    report_type: str = "annual",
    peers: int = 0,
    force: bool = False,
    view: str = "",
) -> dict[str, Any]:
    """对比目标公司与其申万三级行业同行在八看上的位置。

    ``peers<=0`` 取行业全部可比公司；否则按市值取 Top N（目标公司始终保留）。
    ``view`` 留空返回全部；否则只挑出该看。
    """
    rt = normalize_report_type(report_type)
    code = (code or "").strip()
    meta = universe.resolve_industry(code, industry_code)
    l3_code = meta["l3_code"]

    sample = universe.build_universe(
        l3_code,
        target_code=code,
        peers=peers,
        force_refresh=force,
    )
    stocks = sample["stocks"]

    # 先用当前样本估基准期，套缓存（避免重复拉 F10）
    cache_key = _pack_key(l3_code, rt, code, peers, f"{sample['used']}")
    if not force:
        hit = _cache.get(cache_key)
        if hit is not None:
            return _select_view(hit, view)

    series_map = universe.fetch_series(stocks, rt, force=force)
    companies, dropped = _build_companies(stocks, series_map, code)

    if not companies:
        return _empty_pack(meta, rt, code, sample, dropped)

    benchmark, ranks, dispersion = aggregate.build_benchmark(companies)
    _attach_ranks(companies, benchmark, ranks)
    score_rank = aggregate.rank_companies_by_score(companies)
    for c in companies:
        c["score_rank"] = score_rank.get(c["code"])

    target = aggregate.target_position(companies, code, ranks)
    by_view = _build_by_view(companies, benchmark, dispersion)

    latest_period = next((c["latest_period"] for c in companies if c["is_target"]), "")
    if not latest_period:
        latest_period = companies[0].get("latest_period") or ""

    pack: dict[str, Any] = {
        "industry": meta,
        "report_type": rt,
        "report_type_label": report_type_label(rt),
        "latest_period": latest_period,
        "ytd": rt != "annual",
        "flags": _coverage_flags(rt),
        "universe": {
            "total": sample["total"],
            "used": len(companies),
            "limited": bool(peers and peers > 0),
            "peers_limit": peers,
            "excluded": list(sample["excluded"]) + dropped,
        },
        "benchmark": benchmark,
        "dispersion": dispersion,
        "companies": companies,
        "target": target,
        "by_view": by_view,
    }
    pack["text"] = render.render_text(pack)

    _cache.put(cache_key, pack, cached_at=time.time())
    return _select_view(pack, view)


def _coverage_flags(report_type: str) -> list[str]:
    if report_type == "annual":
        return []
    label = report_type_label(report_type)
    return [
        f"本次依据{label}口径：利润表/现金流量表为累计数，不可与年报横比；"
        f"周转天数按累计数估算会偏高。同口径内部对比仍具可比性。"
    ]


def _empty_pack(
    meta: dict[str, Any],
    report_type: str,
    code: str,
    sample: dict[str, Any],
    dropped: list[dict[str, str]],
) -> dict[str, Any]:
    return {
        "industry": meta,
        "report_type": report_type,
        "report_type_label": report_type_label(report_type),
        "latest_period": "",
        "ytd": report_type != "annual",
        "flags": _coverage_flags(report_type) + ["未取到可比样本，无法进行横截面比对"],
        "universe": {
            "total": sample["total"],
            "used": 0,
            "limited": bool(peers and peers > 0),
            "peers_limit": peers,
            "excluded": list(sample["excluded"]) + dropped,
        },
        "benchmark": {},
        "dispersion": {},
        "companies": [],
        "target": {},
        "by_view": [],
        "text": f"（{meta.get('l3_name') or meta.get('l3_code')} 行业未取到可比的{report_type_label(report_type)}数据）",
    }


def _select_view(pack: dict[str, Any], view: str) -> dict[str, Any]:
    key = (view or "").strip().lower()
    if not key:
        return pack
    from company.analysis.competition.registry import view_groups

    valid = [g.key for g in view_groups()] + ["all"]
    if key not in valid:
        raise ValueError(f"view 须为 {'|'.join(valid)}")
    if key == "all":
        return pack
    selected = next((v for v in pack.get("by_view") or [] if v["key"] == key), None)
    if selected is None:
        raise ValueError(f"view {key} 无对应数据")
    result = dict(pack)
    result["selected_view"] = selected
    return result
