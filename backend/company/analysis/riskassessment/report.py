"""风险报告生成（按七维 · 子查询分组）"""
from __future__ import annotations

import json
from typing import Any


def to_markdown(pack: dict[str, Any]) -> str:
    code = pack.get("code") or ""
    name = pack.get("name") or ""
    stats = pack.get("stats") or {}
    dims = pack.get("dimensions") or []

    lines: list[str] = []
    head = f"{name}（{code}）" if name else code
    lines.append(f"# 巨潮非定期公告风险排查（七维）- {head}")
    lines.append("")
    lines.append(f"- 维度数：{stats.get('dimension_count', len(dims))}")
    lines.append(f"- 有命中维度：{stats.get('hit_dimensions', 0)}")
    lines.append(f"- 分组合计条数：{stats.get('total_items', 0)}")
    lines.append(f"- 原始命中条数：{stats.get('total_items_raw', 0)}")
    lines.append("")

    for dim in dims:
        lines.append(f"## {dim.get('no')}. {dim.get('name')}（{dim.get('count', 0)}）")
        lines.append("")
        lines.append("### 检索方式")
        lines.append("")
        sm = dim.get("search_method")
        if isinstance(sm, dict):
            lines.append("| 编号 | 子查询 | 通道 | 分类 | 标题关键词 | 窗口 |")
            lines.append("|---|---|---|---|---|---|")
            for c in sm.get("clauses") or []:
                cats = "、".join(c.get("category") or []) or "任意"
                kws = "、".join(c.get("keyword_terms") or []) or "任意"
                lines.append(
                    f"| {c.get('symbol')} | {c.get('label')} | {c.get('tab_label') or c.get('tab')} "
                    f"| {cats} | {kws} | 近{c.get('days')}天 |"
                )
        else:
            lines.append(str(sm or ""))
        lines.append("")
        lines.append("### 检索结果")
        lines.append("")
        groups = dim.get("groups") or []
        if not groups:
            lines.append("_本维暂无子查询_")
            lines.append("")
        else:
            for g in groups:
                lines.append(
                    f"#### {g.get('symbol')}. {g.get('label')}（{g.get('count', 0)}）"
                )
                lines.append("")
                items = g.get("items") or []
                if not items:
                    lines.append("_本组无命中_")
                    lines.append("")
                    continue
                for i, e in enumerate(items, 1):
                    title = e.get("title") or "（无标题）"
                    url = e.get("url") or ""
                    if url:
                        lines.append(f"{i}. [{title}]({url})")
                    else:
                        lines.append(f"{i}. {title}")
                    lines.append(
                        f"   - 时间：{e.get('published_at') or '-'} | 分类：{e.get('category_cn') or '-'}"
                    )
                    lines.append("")

    return "\n".join(lines)


def to_json(pack: dict[str, Any]) -> str:
    return json.dumps(pack, ensure_ascii=False, indent=2)
