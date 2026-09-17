"""把已确认章节拼成报告，并写入质疑记录。"""

from __future__ import annotations

from typing import Any

from agent.essence_analyst.stages import STAGE_TITLE


def _log_lines(log: list[dict[str, Any]]) -> str:
    if not log:
        return "（无）"
    rows = ["| 章节 | 轮次 | 裁决 | 问题 |", "|------|------|------|------|"]
    for item in log:
        issues = "；".join(item.get("issues") or []) or "—"
        issues = issues.replace("|", "/")
        rows.append(
            f"| {STAGE_TITLE.get(item.get('stage', ''), item.get('stage', ''))} "
            f"| {item.get('round', '')} "
            f"| {item.get('verdict', '')} "
            f"| {issues} |"
        )
    return "\n".join(rows)


def assemble_markdown(state: dict[str, Any]) -> str:
    chapters = dict(state.get("chapters") or {})
    name = state.get("stock_name") or state.get("company") or ""
    code = state.get("stock_code") or ""
    cutoff = state.get("data_cutoff") or ""
    market = state.get("market") or ""

    exhausted = [
        item
        for item in (state.get("confirm_log") or [])
        if item.get("verdict") == "exhausted"
    ]
    exhausted_note = ""
    if exhausted:
        names = "、".join(STAGE_TITLE.get(item.get("stage", ""), "") for item in exhausted)
        exhausted_note = f"\n> 以下章节在 {len(exhausted)} 处轮次用尽后按最后一稿收录：{names}\n"

    report = f"""# {name}（{code}）生意本质

> 研究日期：{cutoff} · 市场：{market}
> 主线：交易所 / 巨潮 / 七网 / 公告 PDF · 解释与关键因素允许联网非官方 · 冲突以官方为准
> 流程：每章均经起草官撰写、质疑官复核，不通过则重写或补证据。
{exhausted_note}
## 一、{STAGE_TITLE['businesses']}

{chapters.get('businesses') or '（未完成）'}

## 二、{STAGE_TITLE['explain']}

{chapters.get('explain') or '（未完成）'}

## 三、{STAGE_TITLE['factors']}

{chapters.get('factors') or '（未完成）'}

## 附录：质疑与确认记录

{_log_lines(list(state.get('confirm_log') or []))}
"""
    return report.strip() + "\n"
