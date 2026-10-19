"""主营业务画像：取数编排 + 派生指标。

本模块是 :mod:`company.analysis.businessoverview` 的**派生层**：
只消费它的取数与格式统一结果，不修改其语义，也不改变其「不做二次加工」的承诺。

职责
----
1. **取数** —— 一次请求取全三个维度（按产品/按行业/按地区）+ 一次 SSR 请求取全
   主营介绍与经营评述，共 2 次 HTTP；
2. **格式统一** —— 复用 ``businessoverview.core.normalize``，不自造字段契约；
3. **派生指标** —— 集中度、整体毛利率、占比迁移等**纯计算**，全部可由 pack 复算；
4. **口径护栏** —— 如实披露口径问题，不修改数据。

**不调用任何模型**，全部输出确定性可复现。
"""

from __future__ import annotations

import logging
import re
from collections import Counter
from datetime import date
from typing import Any

from company.analysis.businessoverview.core.normalize import normalize_pack
from company.analysis.businessoverview.core.source import get_source
from company.analysis.businessoverview.tonghuashun.fetcher import (
    ANALYSIS_DIM,
    TYPE_PRIORITY,
    fetch_operate_dimensions,
    fetch_operate_text_blocks,
)
from company.analysis.businessoverview.bizprofile import guardrails

logger = logging.getLogger(__name__)

#: 维度键 → 中文标签（与 businessoverview 的统一键一致）
DIM_LABEL: dict[str, str] = dict(ANALYSIS_DIM)

#: 归一化名称用的标点（跨期匹配时剔除）
_PUNCT_RE = re.compile(r"[\s　()（）·、,，.。:：;；/／\-—_]+")


def _resolve_name(code: str) -> str:
    """用公司画像补简称，失败不阻塞主流程。"""
    try:
        from company.profile import get_stock_profile

        prof = get_stock_profile(code)
        return str((prof.get("stock") or {}).get("name") or "").strip()
    except Exception:
        return ""


def _match_key(name: str) -> str:
    """跨期匹配用的归一名：剔除空白与标点，保留汉字与字母数字。"""
    return _PUNCT_RE.sub("", str(name or "")).lower()


def _level1(segments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """只取一级分部（level=1），避免二级子项重复计数（护栏 G3）。"""
    return [s for s in segments if str(s.get("level") or "1") == "1"]


def _concentration(segments: list[dict[str, Any]]) -> dict[str, float | None]:
    """CR3 与 HHI（按收入占比）。

    占比缺失或非正的行不参与计算。
    """
    ratios = [
        float(s.get("revenue_ratio") or 0.0)
        for s in segments
        if s.get("revenue_ratio") is not None and float(s.get("revenue_ratio") or 0.0) > 0
    ]
    if not ratios:
        return {"cr3": None, "hhi": None}
    ratios.sort(reverse=True)
    return {
        "cr3": round(sum(ratios[:3]), 6),
        "hhi": round(sum(r * r for r in ratios), 6),
    }


def _overall_margin(segments: list[dict[str, Any]]) -> float | None:
    """整体毛利率 = Σ分部毛利 ÷ Σ分部收入。

    **绝不**取 ``totals.gross_profit_rate``（该字段口径不是毛利率，护栏 G1）。
    """
    revenue = sum(float(s.get("revenue") or 0.0) for s in segments)
    gross_profit = sum(float(s.get("gross_profit") or 0.0) for s in segments)
    if not revenue:
        return None
    return gross_profit / revenue


def _migration(
    current: list[dict[str, Any]], previous: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """占比迁移：本期 vs 上期。

    匹配顺序：完全同名 → 归一名相同 → 归一名互相包含。
    匹配不上的记为「本期新出现」/「本期无」，不猜测对应关系（护栏 G6）。
    """
    cur_by_key: dict[str, dict[str, Any]] = {}
    for s in current:
        cur_by_key.setdefault(_match_key(s.get("item_name") or ""), s)

    used: set[str] = set()
    pairs: list[tuple[dict[str, Any] | None, dict[str, Any]]] = []
    for s in previous:
        key = _match_key(s.get("item_name") or "")
        hit = cur_by_key.get(key)
        if hit is None:
            for ckey, cand in cur_by_key.items():
                if ckey and (ckey in key or key in ckey):
                    hit = cand
                    break
        if hit is not None:
            pairs.append((hit, s))
            used.add(_match_key(hit.get("item_name") or ""))
        else:
            pairs.append((None, s))

    rows: list[dict[str, Any]] = []
    for cur, prev in pairs:
        name = (cur or prev).get("item_name") or ""
        cur_ratio = (cur or {}).get("revenue_ratio")
        prev_ratio = (prev or {}).get("revenue_ratio")
        if cur is not None and prev_ratio is not None and cur_ratio is not None:
            status = "匹配"
            delta = (float(cur_ratio) - float(prev_ratio)) * 100
        elif cur is not None:
            status = "本期新出现"
            delta = None
        else:
            status = "本期无"
            delta = None
        rows.append({
            "item_name": name,
            "cur_ratio": cur_ratio,
            "prev_ratio": prev_ratio,
            "cur_revenue": (cur or {}).get("revenue"),
            "prev_revenue": (prev or {}).get("revenue"),
            "revenue_yoy": (cur or {}).get("revenue_yoy"),
            "delta_pp": delta,
            "status": status,
        })

    # 本期新出现但上一轮没遍历到的（名称完全对不上）也补进来
    for s in current:
        key = _match_key(s.get("item_name") or "")
        if key in used:
            continue
        if any(r["item_name"] == (s.get("item_name") or "") for r in rows):
            continue
        rows.append({
            "item_name": s.get("item_name") or "",
            "cur_ratio": s.get("revenue_ratio"),
            "prev_ratio": None,
            "cur_revenue": s.get("revenue"),
            "prev_revenue": None,
            "revenue_yoy": s.get("revenue_yoy"),
            "delta_pp": None,
            "status": "本期新出现",
        })
    return rows


def _classify(segments: list[dict[str, Any]]) -> dict[str, Any]:
    """业务归类（词典派生，规则确定可复现）。

    复用 ``businessoverview.rules.lexicon`` 的静态词典：命中与否完全由
    字符串匹配决定；未命中走 GENERIC 兜底，不做任何模型推断。
    """
    try:
        from company.analysis.businessoverview.rules.lexicon import (
            CATEGORY_MODEL_HINT,
            DEFAULT_BUYERS,
            GENERIC_CATEGORY,
            lookup,
        )
    except Exception:  # noqa: BLE001
        return {"available": False}

    hits: list[dict[str, str]] = []
    unmatched: list[str] = []
    for s in segments:
        name = s.get("item_name") or ""
        hit = lookup(name)
        if hit:
            hits.append({
                "item_name": name,
                "keyword": hit.get("keyword", ""),
                "category": hit.get("category", ""),
                "model": hit.get("model", ""),
                "buyers": hit.get("buyers", ""),
                "product": hit.get("product", ""),
            })
        else:
            unmatched.append(name)

    categories = Counter(h["category"] for h in hits)
    models = Counter(h["model"] for h in hits)
    buyers = Counter(h["buyers"] for h in hits)

    return {
        "available": True,
        "hits": hits,
        "unmatched": unmatched,
        "main_category": categories.most_common(1)[0][0] if categories else GENERIC_CATEGORY,
        "main_model": models.most_common(1)[0][0] if models else "",
        "model_hint": CATEGORY_MODEL_HINT.get(
            models.most_common(1)[0][0] if models else "", ""
        ),
        "main_buyers": buyers.most_common(1)[0][0] if buyers else DEFAULT_BUYERS,
        "category_options": categories.most_common(),
        "generic": not hits,
    }


def _gloss(text: str) -> str:
    """术语白话替换（纯正则，可预期可审计）。"""
    try:
        from company.analysis.businessoverview.rules.glossary import gloss_text

        return gloss_text(text)
    except Exception:  # noqa: BLE001
        return text


def _fetch_all(code: str, *, latest_n: int) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    """取全三维度 + 文本块（共 2 次 HTTP）。

    维度数据走 ``product_index_query``（一次返回三块）；
    主营介绍与经营评述同源于 SSR 页面，合并为一次抓取。
    """
    raw_dims = fetch_operate_dimensions(code, latest_n=latest_n)
    text_blocks = fetch_operate_text_blocks(code)
    return raw_dims, text_blocks


def build_profile(
    company: str,
    *,
    latest_n: int = 3,
    with_text: bool = True,
) -> dict[str, Any]:
    """产出主营业务画像的全部中间数据（不含 Markdown 文本）。

    参数
    ----
    company
        股票代码或名称。
    latest_n
        取最近 N 个报告期，默认 3。
    with_text
        是否抓取主营介绍与董事会经营评述（SSR 页面）。
    """
    code = str(company or "").strip()
    if not code:
        raise ValueError("缺少股票代码或名称")

    source = get_source()
    raw_dims, text_blocks = _fetch_all(code, latest_n=latest_n)

    intro = (text_blocks or {}).get("intro") or {}
    review = (text_blocks or {}).get("review") or {}

    # 统一格式：逐维度归一
    dimensions: dict[str, dict[str, Any]] = {}
    for key in TYPE_PRIORITY:
        raw = raw_dims.get(key)
        if not raw:
            continue
        pack = normalize_pack(
            raw,
            source_key=source.key,
            source_label=source.label,
            name=_resolve_name(code),
        )
        periods = pack.get("periods") or []
        current = _level1(periods[0]["segments"]) if periods else []
        previous = _level1(periods[1]["segments"]) if len(periods) >= 2 else []
        pack["_latest_segments"] = current
        pack["_prev_segments"] = previous
        pack["_concentration"] = _concentration(current)
        pack["_overall_margin"] = _overall_margin(current)
        pack["_migration"] = _migration(current, previous)
        pack["_classification"] = _classify(current)
        dimensions[key] = pack

    if not dimensions:
        raise ValueError(f"未获取到 {code} 的主营构成数据")

    # 主维度：按产品 > 按行业 > 按地区
    primary_key = next((k for k in TYPE_PRIORITY if k in dimensions), "")
    primary = dimensions[primary_key]

    # 文本块挂到主维度 pack 上（字段名沿用 businessoverview 契约）
    if with_text:
        primary["main_business"] = intro.get("main_business") or ""
        primary["product_type"] = intro.get("product_type") or ""
        primary["product_name"] = intro.get("product_name") or ""
        primary["product_name_list"] = intro.get("product_name_list") or []
        primary["scope"] = intro.get("business_scope") or ""
        primary["reviews"] = review.get("items") or []
        primary["review_dates"] = review.get("report_dates") or []

    # 经营评述：取最长的一期（最新 ≠ 最完整，护栏 G8）
    reviews = primary.get("reviews") or []
    picked = max(reviews, key=lambda r: int(r.get("length") or 0)) if reviews else None
    primary["_review_picked"] = picked

    dim_periods = {k: int(d.get("period_count") or 0) for k, d in dimensions.items()}
    dim_latest = {k: (d.get("report_date") or "") for k, d in dimensions.items()}
    reference_latest = dim_latest.get(primary_key) or ""

    hits: list[dict[str, str]] = []
    for key, pack in dimensions.items():
        hits.extend(
            guardrails.inspect(
                pack,
                dim=key,
                dim_periods=dim_periods,
                dim_latest=dim_latest,
                reference_latest=reference_latest,
                review_picked=picked if key == primary_key else None,
                review_total=len(reviews) if key == primary_key else 0,
            )
        )
    # 同一编号可能多维度重复命中，去重（保留首条）
    seen: set[tuple[str, str]] = set()
    unique_hits: list[dict[str, str]] = []
    for hit in hits:
        key = (hit["id"], hit["title"])
        if key in seen:
            continue
        seen.add(key)
        unique_hits.append(hit)

    return {
        "code": code,
        "name": primary.get("name") or _resolve_name(code),
        "source": source.key,
        "source_label": source.label,
        "page": primary.get("page") or "",
        "error": primary.get("error") or "",
        "cutoff_date": date.today().isoformat(),
        "primary": primary_key,
        "primary_label": DIM_LABEL.get(primary_key, ""),
        "dimensions": dimensions,
        "dim_periods": dim_periods,
        "dim_latest": dim_latest,
        "review_picked": picked,
        "review_total": len(reviews),
        "classification": primary.get("_classification") or {"available": False},
        "gloss": _gloss,
        "guardrails": unique_hits,
    }


__all__ = ["DIM_LABEL", "build_profile"]
