"""同行业「八看」横截面比对：Markdown 表格与自然语言结论（确定性模板）。

只消费 ``compare.py`` 组好的 pack，不重算指标。表格按一看~八看 + 综合分块，
每看一个「指标 × 公司」矩阵（目标公司列标记），并附行业基准与目标落位结论。
"""

from __future__ import annotations

from typing import Any

from company.analysis.competition.registry import view_groups
from company.analysis.financialreport._common import fmt_num, fmt_pct, fmt_x, md_table


def _fmt_value(value: Any, unit: str) -> str:
    if value is None:
        return "—"
    if unit == "pct":
        return fmt_pct(value)
    if unit == "yi":
        return f"{fmt_num(value, 2)}亿"
    if unit == "x":
        return fmt_x(value)
    if unit == "day":
        return f"{fmt_num(value, 0)}天"
    if unit == "num":
        return fmt_num(value, 2)
    return str(value)


def _rank_mark(rank: Any, total: int) -> str:
    if not rank or not rank.get("rank"):
        return ""
    return f"〔{rank['rank']}/{total}〕"


def _score_rank(row: dict[str, Any]) -> int:
    info = (row.get("ranks") or {}).get("score_total")
    return info["rank"] if isinstance(info, dict) and info.get("rank") else 999


def _indicator_table(view: dict[str, Any], total: int) -> str:
    """指标 × 公司矩阵：目标公司列置顶并标记 ★，单元格附排名。"""
    indicators = view.get("indicators") or []
    rows = view.get("rows") or []
    if not indicators or not rows:
        return "（该公司组无可比数值）"

    ordered_rows = sorted(rows, key=lambda r: (not r.get("is_target"), _score_rank(r)))
    header = ["指标"] + [("★ " if r.get("is_target") else "") + r["name"] for r in ordered_rows]
    body: list[list[str]] = []
    for ind in indicators:
        key = ind["key"]
        line = [ind["label"]]
        for r in ordered_rows:
            cell = _fmt_value((r.get("values") or {}).get(key), ind["unit"])
            mark = _rank_mark((r.get("ranks") or {}).get(key), total)
            line.append((cell + mark).strip())
        body.append(line)
    return md_table(header, body)


def _benchmark_table(view: dict[str, Any]) -> str:
    """行业基准：每指标的中位数/均值/区间/分位。"""
    indicators = view.get("indicators") or []
    bench = view.get("benchmark") or {}
    body: list[list[str]] = []
    for ind in indicators:
        key = ind["key"]
        stat = bench.get(key) or {}
        if not stat.get("count"):
            continue
        unit = ind["unit"]
        body.append(
            [
                ind["label"],
                _fmt_value(stat.get("median"), unit),
                _fmt_value(stat.get("mean"), unit),
                f"{_fmt_value(stat.get('p25'), unit)} ~ {_fmt_value(stat.get('p75'), unit)}",
                f"{_fmt_value(stat.get('min'), unit)} ~ {_fmt_value(stat.get('max'), unit)}",
            ]
        )
    if not body:
        return ""
    return md_table(["指标", "中位数", "均值", "四分位区间", "极值区间"], body)


def _view_conclusions(pack: dict[str, Any], view: dict[str, Any]) -> list[str]:
    target = pack.get("target") or {}
    indicators = view.get("indicators") or []
    if not target or not indicators:
        return []
    by_ind = target.get("by_indicator") or {}
    lines: list[str] = []
    for ind in indicators:
        key = ind["key"]
        info = by_ind.get(key)
        if not info or info.get("value") is None:
            continue
        bench = (view.get("benchmark") or {}).get(key) or {}
        med = bench.get("median")
        value = info.get("value")
        unit = ind["unit"]
        better = ind["direction"]
        pos = ""
        if info.get("percentile") is not None and better != "neutral":
            pos = f"分位 {info['percentile']:.0f}%"
        vs = ""
        if med is not None and isinstance(value, (int, float)):
            arrow = "高于" if value > med else ("低于" if value < med else "持平")
            vs = f"{arrow}行业中位数 {_fmt_value(med, unit)}"
        if pos or vs:
            lines.append(f"- {info['label']}：{_fmt_value(value, unit)}，{vs}{('，' + pos) if pos else ''}。")
    return lines


def _target_summary(pack: dict[str, Any]) -> list[str]:
    target = pack.get("target") or {}
    if not target:
        return ["- 目标公司未在样本内或缺少数据。"]
    lines = []
    score_rank = target.get("score_rank")
    of = target.get("of")
    if score_rank and of:
        lines.append(
            f"- 综合评分 {target.get('score_total')}，在本行业 {of} 家可比公司中排名第 {score_rank}。"
            if target.get("score_total") is not None
            else f"- 综合评分缺失，样本 {of} 家。"
        )
    strengths = target.get("strengths") or []
    weaknesses = target.get("weaknesses") or []
    if strengths:
        lines.append(f"- 相对优势（分位 ≥70%）：{'；'.join(strengths[:6])}。")
    if weaknesses:
        lines.append(f"- 相对短板（分位 ≤30%）：{'；'.join(weaknesses[:6])}。")
    if not strengths and not weaknesses:
        lines.append("- 各指标大多处于行业中游，未见极端优/劣势。")
    return lines


def render_text(pack: dict[str, Any]) -> str:
    """把 pack 渲染成完整 Markdown。"""
    meta = pack.get("industry") or {}
    label = pack.get("report_type_label") or ""
    title_industry = f"{meta.get('l1_name', '')}/{meta.get('l2_name', '')}/{meta.get('l3_name', '')}".strip("/")
    total = pack.get("universe", {}).get("used") or 0

    parts: list[str] = [f"# 张新民「八看」· 同行业对比（{title_industry or meta.get('l3_code', '')}）", ""]
    parts.append(
        f"> 口径：{label}；基准期：{pack.get('latest_period') or '—'}；"
        f"样本：{total} 家可比公司（行业共 {pack.get('universe', {}).get('total', 0)} 家）。"
    )
    for flag in pack.get("flags") or []:
        parts.append(f">\n> ⚠ {flag}")
    parts.append("")

    parts.append("## 目标公司定位")
    parts.extend(_target_summary(pack))
    parts.append("")

    excluded = pack.get("universe", {}).get("excluded") or []
    if excluded:
        items = "；".join(f"{e['name']}({e['code']})：{e['reason']}" for e in excluded[:20])
        parts.append(f"**已剔除**：{items}")
        parts.append("")

    for view in pack.get("by_view") or []:
        parts.append(f"## {view.get('name')}")
        parts.append("")
        parts.append(_indicator_table(view, total))
        parts.append("")
        bench_table = _benchmark_table(view)
        if bench_table:
            parts.append("**行业基准**：")
            parts.append("")
            parts.append(bench_table)
            parts.append("")
        dispersion = view.get("dispersion") or {}
        if dispersion:
            high = [
                f"{ind['label']}（分化{d['level']}）"
                for ind in view.get("indicators") or []
                for d in [dispersion.get(ind["key"]) or {}]
                if d.get("level") in {"高", "中"}
            ]
            if high:
                parts.append(f"**行业分化提示**：{'、'.join(high)} 的离散度偏高，排名参考价值有限。")
                parts.append("")
        concl = _view_conclusions(pack, view)
        if concl:
            parts.append("**目标公司在本看的落位**：")
            parts.extend(concl)
            parts.append("")

    return "\n".join(parts)
