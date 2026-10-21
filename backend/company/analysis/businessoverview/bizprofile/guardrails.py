"""口径护栏：在渲染前校验取数结果，产出告警清单写入报告尾注。

每条护栏都对应一个**实测踩过**的坑，不是假想风险。护栏不修改任何数据，
只负责**如实披露**口径问题，避免读者把不同口径的数字放在一起比较。

编号与含义：

===== ==========================================================
编号  风险
===== ==========================================================
G1    ``totals.gross_profit_rate`` 不是毛利率，禁止当作毛利率呈现
G2    ``gross_profit_ratio`` 是「毛利占总毛利」，不是毛利率
G3    ``level=2`` 子项与 ``level=1`` 重复计数
G4    ``revenue_yoy`` 可能缺失，缺失不等于 0
G5    最新期可能是半年报/季报累计口径，不可与年度直接横比
G6    分部名称跨期改名，按名匹配会漏配
G7    三个维度的可得期数与最新期不同，不可横向当同口径比较
G9    某维度数据可能严重过期（如分地区只更新到 2010 年）
G10   收入占比合计可能不等于 100%（负占比/抵销行），不强行归一
===== ==========================================================
"""

from __future__ import annotations

from typing import Any

#: 维度键 → 中文标签（告警中标明来源维度）
DIM_TITLE: dict[str, str] = {
    "product": "按产品",
    "industry": "按行业",
    "area": "按地区",
}

GUARDRAIL_IDS: tuple[str, ...] = (
    "G1", "G2", "G3", "G4", "G5", "G6", "G7", "G9", "G10",
)

#: 最新期与「正常最新期」相差多少年即视为该维度数据过期（G9）
STALE_YEARS = 3


def _fmt_pct(value: float | None) -> str:
    return "—" if value is None else f"{value * 100:.2f}%"


def _year_of(date: str) -> int | None:
    try:
        return int(str(date)[:4])
    except (TypeError, ValueError):
        return None


def inspect(
    pack: dict[str, Any],
    *,
    dim: str = "",
    dim_periods: dict[str, int] | None = None,
    dim_latest: dict[str, str] | None = None,
    reference_latest: str = "",
) -> list[dict[str, str]]:
    """检查单个维度的 pack，返回命中的护栏列表。

    每项为 ``{"id", "title", "detail"}``，供报告尾注逐条披露。

    参数
    ----
    pack
        统一格式后的分部 pack（:func:`company.analysis.businessoverview.core.normalize.normalize_pack` 输出）。
    dim
        本 pack 对应的维度键（product/industry/area），用于在告警中标明来源维度。
    dim_periods
        各维度的可得期数，用于 G7。
    dim_latest
        各维度的最新报告期，用于 G7 / G9。
    reference_latest
        作为「最新」的参照报告期（通常取主维度最新期），用于 G9。
    """
    hits: list[dict[str, str]] = []
    # 报告表格只渲染**最新一期**的分部，因此 G3/G4 也只看最新期，
    # 否则会出现「表格里同比齐全，尾注却说缺同比」的自相矛盾。
    periods = pack.get("periods") or []
    latest_segments = (periods[0].get("segments") if periods else None)
    segments = latest_segments if latest_segments is not None else (pack.get("segments") or [])
    latest_period = pack.get("report_date") or ""

    # 告警前缀标明维度，避免多维度命中时无法分辨来源
    tag = f"［{DIM_TITLE.get(dim, dim)}］" if dim else ""

    # G1: totals.gross_profit_rate 口径不是毛利率
    totals = pack.get("totals") or {}
    if "gross_profit_rate" in totals:
        hits.append({
            "id": "G1",
            "title": "已忽略 totals.gross_profit_rate",
            "detail": "该字段口径不是毛利率（实测 600990 为 1.164 而真实毛利率 0.147），"
                      "整体毛利率一律由分部毛利 ÷ 分部收入派生。",
        })

    # G3: 二级子项重复计数
    if any(str(s.get("level") or "1") != "1" for s in segments):
        hits.append({
            "id": "G3",
            "title": f"{tag}存在 level=2 二级子项",
            "detail": "子项与一级分部重复计数，合计口径以 level=1 为准。",
        })

    # G4: 同比缺失
    missing_yoy = [s for s in segments if s.get("revenue_yoy") is None]
    if missing_yoy and segments:
        hits.append({
            "id": "G4",
            "title": f"{tag}{len(missing_yoy)} 个分部缺收入同比",
            "detail": "同比缺失已渲染为「—」，未按 0 处理。",
        })

    # G5: 最新期非年度
    if latest_period and not latest_period.endswith("-12-31"):
        hits.append({
            "id": "G5",
            "title": f"{tag}最新报告期为 {latest_period}",
            "detail": "非 12-31 报告期（半年报/季报累计口径），不可与年度数据直接横比。",
        })

    # G6: 跨期改名（需要全部报告期，故用全量 segments，不受最新期限制）
    by_period: dict[str, list[dict[str, Any]]] = {}
    for s in pack.get("segments") or []:
        by_period.setdefault(s.get("report_date") or "", []).append(s)
    dates = sorted(by_period, reverse=True)
    if len(dates) >= 2:
        cur = {s.get("item_name") for s in by_period[dates[0]]}
        prev = {s.get("item_name") for s in by_period[dates[1]]}
        renamed = len(cur & prev) == 0 and bool(cur) and bool(prev)
        if renamed or (cur - prev) or (prev - cur):
            gone = sorted(x for x in (prev - cur) if x)
            fresh = sorted(x for x in (cur - prev) if x)
            if gone or fresh:
                detail = "跨期存在分部名称变化，按名匹配可能漏配"
                if gone:
                    detail += f"；上期有本期无：{'、'.join(gone[:3])}"
                if fresh:
                    detail += f"；本期新出现：{'、'.join(fresh[:3])}"
                hits.append({"id": "G6", "title": f"{tag}分部名称跨期变化", "detail": detail})

    # G7: 维度间期数不同
    if dim_periods and len(set(dim_periods.values())) > 1:
        hits.append({
            "id": "G7",
            "title": "三个维度可得期数不同",
            "detail": "、".join(
                f"{DIM_TITLE.get(k, k)} {v} 期" for k, v in sorted(dim_periods.items())
            ) + "，不可横向当作同口径比较。",
        })

    # G9: 维度数据过期
    if dim_latest and reference_latest:
        ref_year = _year_of(reference_latest)
        for key, date in sorted(dim_latest.items()):
            year = _year_of(date)
            if ref_year and year and (ref_year - year) >= STALE_YEARS:
                hits.append({
                    "id": "G9",
                    "title": f"{DIM_TITLE.get(key, key)} 维度数据滞后",
                    "detail": f"该维度最新期仅到 {date}，而主维度已到 {reference_latest}，"
                              "横向比较会失真。",
                })

    # G10: 占比合计不等于 1
    total_ratio = pack.get("total_ratio")
    if total_ratio is not None and abs(float(total_ratio) - 1.0) > 1e-4:
        hits.append({
            "id": "G10",
            "title": f"{tag}收入占比合计为 {_fmt_pct(float(total_ratio))}",
            "detail": "存在负占比或抵销行，未强行归一到 100%。",
        })

    return hits


__all__ = ["DIM_TITLE", "GUARDRAIL_IDS", "STALE_YEARS", "inspect"]
