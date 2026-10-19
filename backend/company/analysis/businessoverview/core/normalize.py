"""格式统一层：把不同数据源的原始字段抹平成同一套契约。

本层**只做格式统一**，不做任何数据加工：

  允许做的（格式）
    * 统一字段名（``item_name`` / ``revenue`` / ``revenue_ratio`` / ...）
    * 统一字段集（缺失补 ``None``，多出的源特有字段不外泄）
    * 统一类型（金额/比率一律 ``float``，文本一律 ``str``，缺失一律 ``None``）
    * 统一单位（金额：元；占比与毛利率：0~1 小数；日期：``YYYY-MM-DD``）
    * 统一维度键（``product`` / ``industry`` / ``area`` + 对应中文标签）
    * 统一排序（按报告期降序，同期内按占比降序）

  不允许做的（加工）
    * 不剔除任何行：二级子项、抵销行、小占比业务一律原样保留
    * 不合并、不改名、不分级、不打分、不打标
    * 不生成任何描述文字、不做交叉校验、不推断源里没有的值

因此本模块是**纯函数**的、无状态、无外部依赖（除基础工具），可单测。
"""

from __future__ import annotations

from typing import Any

from core.codes import safe_str

# --------------------------------------------------------------------------
# 常量：字段契约
# --------------------------------------------------------------------------

#: 分部（segment）统一字段集，顺序即输出顺序
SEGMENT_FIELDS: tuple[str, ...] = (
    "code",
    "report_date",
    "dimension",
    "dimension_key",
    "item_name",
    "level",
    "revenue",
    "revenue_ratio",
    "revenue_yoy",
    "cost",
    "cost_ratio",
    "gross_profit",
    "gross_profit_ratio",
    "gross_margin",
    "source",
    "channel",
)

#: 顶层包（pack）统一字段集
PACK_FIELDS: tuple[str, ...] = (
    "code",
    "name",
    "source",
    "source_label",
    "page",
    "error",
    "dimension",
    "dimension_key",
    "report_date",
    "report_dates",
    "all_periods",
    "period_count",
    "segments",
    "periods",
    "total_ratio",
    "totals",
    "scope",
    "reviews",
    "review_dates",
    "main_business",
    "product_type",
    "product_name",
    "product_name_list",
)

#: 维度键 → 中文标签
DIM_BY_KEY: dict[str, str] = {
    "product": "按产品",
    "industry": "按行业",
    "area": "按地区",
}

#: 中文标签 → 维度键（以标签为桥做跨源归一）
DIM_BY_LABEL: dict[str, str] = {v: k for k, v in DIM_BY_KEY.items()}

#: 各源内部维度键 → 统一维度键
_DIM_SOURCE_KEYS: dict[str, str] = {
    # 同花顺
    "product": "product",
    "industry": "industry",
    "area": "area",
    # 数字别名（1/2/3）
    "1": "product",
    "2": "industry",
    "3": "area",
}

#: 金额单位（所有源一致，元）
AMOUNT_UNIT = "元"

#: 比率口径（所有源一致，0~1 小数）
RATIO_SCALE = "0~1"

#: 缺失哨兵（部分接口用 -1e10 表示无数据）
_SENTINEL = -1e10


# --------------------------------------------------------------------------
# 基础类型转换
# --------------------------------------------------------------------------

def to_float(value: Any) -> float | None:
    """宽松转 float；空值 / ``-`` / ``--`` / 哨兵值 / NaN 一律为 ``None``。"""
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        number = float(value)
    else:
        text = safe_str(value).strip()
        if text in ("", "-", "--", "--"):
            return None
        try:
            number = float(text.replace(",", "").replace("%", "").strip())
        except (TypeError, ValueError):
            return None
    if number != number:  # NaN
        return None
    if number <= _SENTINEL:
        return None
    return number


def to_text(value: Any) -> str:
    """转字符串；``None`` / 空值为 ``""``。"""
    return safe_str(value).strip()


def to_date(value: Any) -> str:
    """统一为 ``YYYY-MM-DD``；无法解析时返回 ``""``。"""
    text = safe_str(value).strip()
    if not text:
        return ""
    return text[:10]


def canonical_dim_key(value: Any) -> str:
    """任意源的维度键 / 标签 → 统一维度键（``product``/``industry``/``area``）。

    识别顺序：统一键 → 源内键（``1``/``2``/``3``）→ 中文标签 → 英文别名。
    无法识别返回 ``""``。
    """
    key = safe_str(value).strip().lower()
    if not key:
        return ""
    if key in DIM_BY_KEY:
        return key
    if key in _DIM_SOURCE_KEYS:
        return _DIM_SOURCE_KEYS[key]
    if key in DIM_BY_LABEL:
        return DIM_BY_LABEL[key]
    if key in ("region", "regions"):
        return "area"
    if key in ("产品", "分产品"):
        return "product"
    if key in ("行业", "分行业"):
        return "industry"
    if key in ("地区", "分地区"):
        return "area"
    return ""


def dim_label(dim_key: str) -> str:
    """统一维度键 → 中文标签。"""
    return DIM_BY_KEY.get(dim_key, "")


# --------------------------------------------------------------------------
# 分部（segment）格式统一
# --------------------------------------------------------------------------

def normalize_segment(
    seg: dict[str, Any], *, default_dim_key: str = ""
) -> dict[str, Any]:
    """把一个分部的原始字段统一成 :data:`SEGMENT_FIELDS` 契约。

    源里没有的字段一律 ``None``，**不做任何推断填充**。
    """
    if not isinstance(seg, dict):
        return {f: None for f in SEGMENT_FIELDS}

    dim_key = (
        canonical_dim_key(seg.get("dimension_key"))
        or canonical_dim_key(seg.get("analysis_type"))
        or canonical_dim_key(seg.get("mainop_type"))
        or canonical_dim_key(seg.get("dimension"))
        or canonical_dim_key(default_dim_key)
    )

    out: dict[str, Any] = {
        "code": to_text(seg.get("code")) or None,
        "report_date": to_date(seg.get("report_date")) or None,
        "dimension": dim_label(dim_key) or to_text(seg.get("dimension")) or None,
        "dimension_key": dim_key or None,
        "item_name": to_text(seg.get("item_name")) or None,
        "level": to_text(seg.get("level")) or None,
        "revenue": to_float(seg.get("revenue")),
        "revenue_ratio": to_float(seg.get("revenue_ratio")),
        "revenue_yoy": to_float(seg.get("revenue_yoy")),
        "cost": to_float(seg.get("cost")),
        "cost_ratio": to_float(seg.get("cost_ratio")),
        "gross_profit": to_float(seg.get("gross_profit")),
        "gross_profit_ratio": to_float(seg.get("gross_profit_ratio")),
        "gross_margin": to_float(seg.get("gross_margin")),
        "source": to_text(seg.get("source")) or None,
        "channel": to_text(seg.get("channel")) or None,
    }
    return out


def normalize_segments(
    segments: list[dict[str, Any]], *, default_dim_key: str = ""
) -> list[dict[str, Any]]:
    """批量统一分部；排序：报告期降序 → 同期内占比降序。"""
    items = [
        normalize_segment(seg, default_dim_key=default_dim_key)
        for seg in (segments or [])
        if isinstance(seg, dict)
    ]
    # 报告期降序 → 同期内占比降序（缺失占比排最后）
    items.sort(key=lambda s: (s.get("revenue_ratio") is None, -(s.get("revenue_ratio") or 0.0)))
    by_date: dict[str, list[dict[str, Any]]] = {}
    for seg in items:
        by_date.setdefault(seg.get("report_date") or "", []).append(seg)
    ordered: list[dict[str, Any]] = []
    for date in sorted(by_date, reverse=True):
        ordered.extend(by_date[date])
    return ordered


# --------------------------------------------------------------------------
# 顶层包（pack）格式统一
# --------------------------------------------------------------------------

def _periods_from_segments(
    segments: list[dict[str, Any]], totals: dict[str, Any]
) -> list[dict[str, Any]]:
    """按报告期把分部归组，并汇总该期占比之和与源给的合计数。"""
    by_date: dict[str, list[dict[str, Any]]] = {}
    for seg in segments:
        by_date.setdefault(seg.get("report_date") or "", []).append(seg)

    periods: list[dict[str, Any]] = []
    for date in sorted(by_date, reverse=True):
        items = by_date[date]
        periods.append(
            {
                "report_date": date,
                "count": len(items),
                "total_ratio": sum(s.get("revenue_ratio") or 0.0 for s in items),
                "totals": totals if date == max(by_date) else {},
                "segments": items,
            }
        )
    return periods


def normalize_pack(
    pack: dict[str, Any],
    *,
    source_key: str,
    source_label: str,
    name: str = "",
) -> dict[str, Any]:
    """把任一源的顶层包统一成 :data:`PACK_FIELDS` 契约。

    只做格式统一：字段名、字段集、类型、单位、日期格式、维度键、排序。
    不剔除行、不合并、不派生。
    """
    if not isinstance(pack, dict):
        pack = {}

    dim_key = (
        canonical_dim_key(pack.get("dimension_key"))
        or canonical_dim_key(pack.get("analysis_type"))
        or canonical_dim_key(pack.get("mainop_type"))
        or canonical_dim_key(pack.get("dimension"))
    )

    segments = normalize_segments(
        [s for s in (pack.get("segments") or []) if isinstance(s, dict)],
        default_dim_key=dim_key,
    )

    totals = pack.get("totals") if isinstance(pack.get("totals"), dict) else {}
    periods = _periods_from_segments(segments, totals)

    all_periods = [to_date(d) for d in (pack.get("all_periods") or [])]
    all_periods = [d for d in all_periods if d]

    report_dates = [to_date(d) for d in (pack.get("report_dates") or [])]
    report_dates = [d for d in report_dates if d]

    reviews = [r for r in (pack.get("reviews") or []) if isinstance(r, dict)]
    review_dates = [to_date(d) for d in (pack.get("review_dates") or [])]
    review_dates = [d for d in review_dates if d]
    if not review_dates and reviews:
        review_dates = [
            to_date(r.get("report_date")) for r in reviews if to_date(r.get("report_date"))
        ]

    names = pack.get("product_name_list")
    if not isinstance(names, list):
        names = []

    out: dict[str, Any] = {
        "code": to_text(pack.get("code")) or None,
        "name": to_text(name) or to_text(pack.get("name")) or None,
        "source": to_text(pack.get("source")) or source_key,
        "source_label": source_label,
        "page": to_text(pack.get("page")) or None,
        "error": to_text(pack.get("error")),
        "dimension": dim_label(dim_key) or to_text(pack.get("dimension")) or None,
        "dimension_key": dim_key or None,
        "report_date": to_date(pack.get("report_date")) or (report_dates[0] if report_dates else ""),
        "report_dates": report_dates,
        "all_periods": all_periods,
        "period_count": int(pack.get("period_count") or 0) or len(all_periods),
        "segments": segments,
        "periods": periods,
        # 分部占比之和（源数据直接相加，未做任何调整）。
        # 与 report_date / totals 口径一致：**只取最新期**。
        # 跨期求和会让 N 期得到 N 倍的占比（实测 3 期得 300%），故不可跨期累加。
        "total_ratio": (
            periods[0]["total_ratio"] if periods
            else sum(s.get("revenue_ratio") or 0.0 for s in segments)
        ),
        "totals": totals,
        "scope": to_text(pack.get("scope")),
        "reviews": reviews,
        "review_dates": review_dates,
        "main_business": to_text(pack.get("main_business")),
        "product_type": to_text(pack.get("product_type")),
        "product_name": to_text(pack.get("product_name")),
        "product_name_list": [to_text(n) for n in names if to_text(n)],
    }
    return {f: out.get(f) for f in PACK_FIELDS}


__all__ = [
    "AMOUNT_UNIT",
    "DIM_BY_KEY",
    "DIM_BY_LABEL",
    "PACK_FIELDS",
    "RATIO_SCALE",
    "SEGMENT_FIELDS",
    "canonical_dim_key",
    "dim_label",
    "normalize_pack",
    "normalize_segment",
    "normalize_segments",
    "to_date",
    "to_float",
    "to_text",
]
