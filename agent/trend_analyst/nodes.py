"""趋势分析智能体 — 节点（仅资金动向 + 分时成交）。"""

from __future__ import annotations

import logging
import re
from datetime import date
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from agent.config import OPENAI_API_KEY, REPORTS_DIR
from agent.tools.data_fetcher import resolve_company
from agent.tools.progress import report as emit_progress
from agent.tools.trend_data import build_trend_pack
from agent.trend_analyst.prompts import SYSTEM, build_synthesis_prompt
from agent.trend_analyst.rules import analyze_fund, analyze_ticks, build_verdict
from agent.trend_analyst.state import TrendState
from agent.utils.llm import get_llm

logger = logging.getLogger(__name__)


def init_company(state: TrendState) -> dict:
    company = (state.get("company") or "").strip()
    emit_progress("tr_init", f"正在解析 {company}…", phase="resolve", status="running")
    stock = resolve_company(company)
    emit_progress("tr_init", f"已解析：{stock['name']} ({stock['code']})", phase="done", status="done")
    return {
        "data_cutoff_date": date.today().isoformat(),
        "stock_code": stock["code"],
        "stock_name": stock["name"],
        "stock_market": stock["market"],
        "day": (state.get("day") or "").strip(),
        "fund_limit": int(state.get("fund_limit") or 60),
        "minute_klt": int(state.get("minute_klt") or 5),
        "min_deal_amount": float(state.get("min_deal_amount") or 300_000),
        "skip_llm": bool(state.get("skip_llm") or False),
        "force": bool(state.get("force") or False),
        "errors": [],
        "sources_used": [],
    }


def fetch_pack(state: TrendState) -> dict:
    code = state.get("stock_code") or ""
    emit_progress("tr_fetch", f"拉取 {code} 资金流 / 分钟资金 / 分时 / 大单…", phase="fetch_data", status="running")
    pack = build_trend_pack(
        code,
        day=state.get("day") or "",
        fund_limit=int(state.get("fund_limit") or 60),
        minute_klt=int(state.get("minute_klt") or 5),
        min_deal_amount=float(state.get("min_deal_amount") or 300_000),
        force=bool(state.get("force")),
    )
    sources = list(pack.get("sources_used") or [])
    errors = list(pack.get("errors") or [])
    emit_progress(
        "tr_fetch",
        f"已用数据源 {', '.join(sources) or '无'}" + (f"；问题 {len(errors)}" if errors else ""),
        phase="fetch_data_done",
        status="done",
    )
    return {
        "pack": pack,
        "day": pack.get("day") or state.get("day") or "",
        "sources_used": sources,
        "errors": errors,
    }


def analyze_main(state: TrendState) -> dict:
    emit_progress("tr_main", "统计资金动向…", phase="analyze", status="running")
    main = analyze_fund(state.get("pack") or {})
    emit_progress("tr_main", f"主力标签：{main.get('label')}", phase="done", status="done")
    return {"main_force": main}


def analyze_retail_node(state: TrendState) -> dict:
    emit_progress("tr_retail", "统计分时成交…", phase="analyze", status="running")
    retail = analyze_ticks(state.get("pack") or {}, state.get("main_force"))
    emit_progress(
        "tr_retail",
        f"分时小单 {retail.get('activity')} · {retail.get('stance')}",
        phase="done",
        status="done",
    )
    return {"retail": retail}


def _fmt_yi(value: Any) -> str:
    if value is None:
        return "—"
    return f"{value} 亿"


def _fmt_pct(value: Any) -> str:
    if value is None:
        return "—"
    try:
        return f"{float(value):.0%}"
    except (TypeError, ValueError):
        return str(value)


def _fmt_num(value: Any, suffix: str = "") -> str:
    if value is None or value == "":
        return "—"
    return f"{value}{suffix}"


def _fmt_align(value: Any) -> str:
    if value is True:
        return "同向"
    if value is False:
        return "背离"
    return "—"


_SESSION_CN = {
    "auction": "集合竞价",
    "open30": "开盘30分钟",
    "morning": "午前连续",
    "afternoon": "午后前段",
    "late": "午后中段",
    "close30": "尾盘30分钟",
    "other": "其他",
}


def _stats_section(state: TrendState) -> str:
    """确定性数据罗列：资金动向 + 分时成交。"""
    fund = state.get("main_force") or {}
    ticks = state.get("retail") or {}
    windows = fund.get("windows") if isinstance(fund.get("windows"), dict) else {}
    streak = fund.get("streak") if isinstance(fund.get("streak"), dict) else {}
    snap = fund.get("snapshot") if isinstance(fund.get("snapshot"), dict) else {}
    minute = fund.get("minute") if isinstance(fund.get("minute"), dict) else {}
    session_yi = minute.get("session_main_yi") if isinstance(minute.get("session_main_yi"), dict) else {}
    quad = fund.get("quad") if isinstance(fund.get("quad"), dict) else {}
    lot = ticks.get("small_lot_threshold") or 50

    lines: list[str] = [
        "## 数据统计",
        "",
        "### 一、资金动向",
        "",
        "#### 1.1 五档日序摘要",
        "",
        f"- 规则标签：{fund.get('label') or '—'}",
        f"- 资金日线样本：{fund.get('daily_bars') or 0} 日",
        f"- 主力连续：{streak.get('direction') or 'flat'} · {streak.get('days') or 0} 日",
        f"- 近20日主力方向翻转：{fund.get('flip_count_20d') or 0} 次",
        f"- 近20日主力与小单同向率：{_fmt_pct(fund.get('main_small_align_20d'))}",
        f"- 近10日超大单与主力同向率：{_fmt_pct(fund.get('super_main_align_10d'))}",
        "",
        "| 窗口 | 主力 | 超大单 | 大单 | 中单 | 小单 |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for key in ("1", "3", "5", "10", "20"):
        w = windows.get(key) or {}
        lines.append(
            f"| 近{key}日 | {_fmt_yi(w.get('main_yi'))} | {_fmt_yi(w.get('super_yi'))} | "
            f"{_fmt_yi(w.get('big_yi'))} | {_fmt_yi(w.get('mid_yi'))} | {_fmt_yi(w.get('small_yi'))} |"
        )

    lines.extend(["", "#### 1.2 近10日明细", ""])
    recent = fund.get("recent_10d") or []
    if recent:
        lines.extend(
            [
                "| 日期 | 主力 | 超大单 | 大单 | 中单 | 小单 | 主力净占比 |",
                "| --- | --- | --- | --- | --- | --- | --- |",
            ]
        )
        for row in recent:
            pct = row.get("main_net_pct")
            pct_s = f"{pct}%" if pct is not None else "—"
            lines.append(
                f"| {row.get('time') or '—'} | {_fmt_yi(row.get('main_yi'))} | "
                f"{_fmt_yi(row.get('super_yi'))} | {_fmt_yi(row.get('big_yi'))} | "
                f"{_fmt_yi(row.get('mid_yi'))} | {_fmt_yi(row.get('small_yi'))} | {pct_s} |"
            )
    else:
        lines.append("- （无日序列）")

    lines.extend(
        [
            "",
            "#### 1.3 当日快照",
            "",
            f"- 主力 {_fmt_yi(snap.get('main_yi'))}（占比 {_fmt_num(snap.get('main_net_pct'), '%')}）",
            f"- 超大单 {_fmt_yi(snap.get('super_yi'))} · 大单 {_fmt_yi(snap.get('big_yi'))} · "
            f"中单 {_fmt_yi(snap.get('mid_yi'))} · 小单 {_fmt_yi(snap.get('small_yi'))}",
            f"- 超大单与主力：{_fmt_align(fund.get('super_align_main'))}",
            "",
            "#### 1.4 分钟资金（按时段）",
            "",
        ]
    )
    if minute.get("bars"):
        lines.append(
            f"- 分钟样本 {minute.get('bars')} 根 · "
            f"{'累计差分' if minute.get('cumulative_like') else '点值求和'} · "
            f"尾盘占全日绝对净额 {_fmt_pct(minute.get('close30_share_of_abs'))}"
        )
        for key in ("open30", "morning", "afternoon", "late", "close30"):
            if key in session_yi:
                lines.append(f"- {_SESSION_CN.get(key, key)}：{_fmt_yi(session_yi.get(key))}")
    else:
        lines.append("- （无分钟资金）")

    lines.extend(
        [
            "",
            "#### 1.5 大单四象限",
            "",
            f"- 样本：{fund.get('big_deal_count') or 0} 笔",
            f"- 主动买 {_fmt_yi(fund.get('active_buy_yi'))} · 主动卖 {_fmt_yi(fund.get('active_sell_yi'))} · "
            f"主动买占比 {_fmt_pct(fund.get('active_buy_share'))}",
            f"- 被动买 {_fmt_yi(fund.get('passive_buy_yi'))} · 被动卖 {_fmt_yi(fund.get('passive_sell_yi'))}",
            "",
        ]
    )
    if quad:
        lines.extend(
            [
                "| 象限 | 笔数 | 金额 |",
                "| --- | --- | --- |",
            ]
        )
        labels = {
            "active_buy": "主动买",
            "active_sell": "主动卖",
            "passive_buy": "被动买",
            "passive_sell": "被动卖",
        }
        for k, cn in labels.items():
            q = quad.get(k) or {}
            lines.append(f"| {cn} | {q.get('count') or 0} | {_fmt_yi(q.get('amount_yi'))} |")

    deal_sess = fund.get("deal_sessions") or {}
    if deal_sess:
        lines.extend(["", "#### 1.5b 大单按时段（主动）", ""])
        for key, cn in _SESSION_CN.items():
            ds = deal_sess.get(key)
            if not ds:
                continue
            lines.append(
                f"- {cn}：主动买 {_fmt_yi(ds.get('active_buy_yi'))} · "
                f"主动卖 {_fmt_yi(ds.get('active_sell_yi'))}"
            )

    top = fund.get("top_events") or []
    lines.extend(["", "#### 1.6 Top 大单事件", ""])
    if top:
        lines.extend(
            [
                "| 时间 | 方向 | 金额 | 事件 |",
                "| --- | --- | --- | --- |",
            ]
        )
        for ev in top[:8]:
            side = f"{ev.get('aggressor') or ''}{ev.get('side') or ''}".strip() or "—"
            lines.append(
                f"| {ev.get('time') or '—'} | {side} | {_fmt_yi(ev.get('amount_yi'))} | "
                f"{ev.get('event_name') or '—'} |"
            )
    else:
        lines.append("- （无大单事件）")

    lines.extend(
        [
            "",
            "### 二、分时成交",
            "",
            "#### 2.1 总量与买卖结构",
            "",
            f"- 分时笔数 {ticks.get('tick_count') or 0}"
            f"（买 {ticks.get('buy_count') or 0} / 卖 {ticks.get('sell_count') or 0} / "
            f"竞价 {ticks.get('auction_count') or 0} / mid {ticks.get('mid_count') or 0}）",
            f"- 买占比（笔） {_fmt_pct(ticks.get('buy_share'))} · "
            f"买占比（量） {_fmt_pct(ticks.get('buy_vol_share'))}",
            f"- 买量 {_fmt_num(ticks.get('buy_vol_lots'), ' 手')} · "
            f"卖量 {_fmt_num(ticks.get('sell_vol_lots'), ' 手')} · "
            f"竞价量 {_fmt_num(ticks.get('auction_vol_lots'), ' 手')}",
            f"- 买额 {_fmt_yi(ticks.get('buy_amount_yi'))} · 卖额 {_fmt_yi(ticks.get('sell_amount_yi'))}",
            f"- 昨收 {_fmt_num(ticks.get('pre_price'))} · 最新 {_fmt_num(ticks.get('last_price'))}"
            f"（{ticks.get('last_time') or '—'}）· 相对昨收 {_fmt_num(ticks.get('pct_vs_pre'), '%')}",
            "",
            "#### 2.2 手数档位分布",
            "",
        ]
    )
    lots = ticks.get("lot_buckets") or []
    if lots:
        lines.extend(
            [
                "| 档位 | 笔数 | 买占比 | 净买量(手) | 估成交额 |",
                "| --- | --- | --- | --- | --- |",
            ]
        )
        for row in lots:
            lines.append(
                f"| {row.get('bucket')} | {row.get('trades') or 0} | "
                f"{_fmt_pct(row.get('buy_share'))} | {_fmt_num(row.get('net_vol_lots'))} | "
                f"{_fmt_yi(row.get('amount_yi'))} |"
            )
    else:
        lines.append("- （无档位样本）")

    lines.extend(["", "#### 2.3 时间分布", ""])
    sessions = ticks.get("sessions") or []
    if sessions:
        lines.extend(
            [
                "| 时段 | 笔数 | 买占比 | 量(手) | 小单笔 | 小单买占比 |",
                "| --- | --- | --- | --- | --- | --- |",
            ]
        )
        for row in sessions:
            cn = _SESSION_CN.get(str(row.get("session")), row.get("session"))
            lines.append(
                f"| {cn} | {row.get('trades') or 0} | {_fmt_pct(row.get('buy_share'))} | "
                f"{_fmt_num(row.get('vol_lots'))} | {row.get('small_trades') or 0} | "
                f"{_fmt_pct(row.get('small_buy_share'))} |"
            )
        peak = ticks.get("peak_session") or {}
        if peak:
            lines.append(
                f"- 成交最密集时段：{_SESSION_CN.get(str(peak.get('session')), peak.get('session'))}"
                f"（{peak.get('trades') or 0} 笔）"
            )
    else:
        lines.append("- （无时段样本）")

    lines.extend(
        [
            "",
            "#### 2.4 小单 / 散户代理",
            "",
            f"- 活跃度：{ticks.get('activity') or '—'} · 动向：{ticks.get('stance') or '—'} · "
            f"相对主力：{ticks.get('relation_to_main') or '—'}",
            f"- 小单（≤{lot} 手）：{ticks.get('small_trade_count') or 0} 笔"
            f"（买 {ticks.get('small_buy_count') or 0} / 卖 {ticks.get('small_sell_count') or 0}）· "
            f"买占比 {_fmt_pct(ticks.get('small_buy_share'))} · "
            f"量 {_fmt_num(ticks.get('small_volume_lots'), ' 手')}",
            f"- 触及价位簇 {ticks.get('price_bucket_count') or 0} · "
            f"代理分 {_fmt_num(ticks.get('retail_proxy_score'))}",
            f"- 小单净额：近1日 {_fmt_yi(ticks.get('small_net_1d_yi'))} · "
            f"近5日 {_fmt_yi(ticks.get('small_net_5d_yi'))}",
            f"- 说明：{ticks.get('note') or '散户数量为小单活跃度代理，非真实持仓人数'}",
            "",
            "#### 2.5 资金 × 分时交叉",
            "",
        ]
    )
    cross = ticks.get("cross_evidence") or []
    if cross:
        lines.extend(f"- {x}" for x in cross)
    else:
        lines.append("- （无显著交叉证据）")
    lines.append("")
    return "\n".join(lines)


def _template_narrative(state: TrendState) -> str:
    fund = state.get("main_force") or {}
    ticks = state.get("retail") or {}
    verdict = state.get("verdict") or {}

    fund_ev = "；".join(str(x) for x in (fund.get("evidence") or [])[:2]) or "证据不足"
    tick_ev = "；".join(str(x) for x in (ticks.get("evidence") or [])[:2]) or "样本有限"

    lines = [
        "### 综合结论",
        "",
        f"{verdict.get('headline') or '结论待定'}（倾向：{verdict.get('lean')}，"
        f"置信度 {verdict.get('confidence')}）。"
        f"失效观察：{verdict.get('invalidation') or '—'}。",
        "",
        "### 资金动向解读",
        "",
        f"标签 **{fund.get('label')}**。"
        f"近5日主力净额 {_fmt_yi(fund.get('main_net_5d_yi'))}，"
        f"大单主动买占比 {_fmt_pct(fund.get('active_buy_share'))}。"
        f"{fund_ev}。",
        "",
        "### 分时成交解读",
        "",
        f"小单活跃度 **{ticks.get('activity')}**，动向 **{ticks.get('stance')}**，"
        f"相对主力：{ticks.get('relation_to_main')}。"
        f"{tick_ev}。"
        f"{ticks.get('note') or ''}",
        "",
        "### 博弈含义与失效观察",
        "",
        f"关系：**{verdict.get('relation') or ticks.get('relation_to_main') or '—'}**。"
        f"{verdict.get('invalidation') or '以主力近5日净额与大单主动买占比为主观察锚'}。",
    ]
    return "\n".join(lines)


def _normalize_analysis(text: str) -> str:
    """把分析段里的二级标题降为三级，避免与「数据统计」同级抢戏。"""
    body = (text or "").strip()
    if not body:
        return body
    body = re.sub(r"^##\s*分析解读\s*\n+", "", body)
    lines_out: list[str] = []
    for line in body.splitlines():
        if re.match(r"^##\s+", line) and not re.match(r"^###\s+", line):
            lines_out.append("#" + line)
        else:
            lines_out.append(line)
    return "\n".join(lines_out).strip()


def synthesize(state: TrendState) -> dict:
    emit_progress("tr_synth", "生成综合结论…", phase="llm", status="running")
    fund = state.get("main_force") or {}
    ticks = state.get("retail") or {}
    verdict = build_verdict(fund, ticks)

    fallback = _template_narrative({**state, "verdict": verdict})
    narrative = fallback
    if not state.get("skip_llm") and OPENAI_API_KEY:
        try:
            llm = get_llm()
            prompt = build_synthesis_prompt(
                state.get("stock_name") or "",
                state.get("stock_code") or "",
                state.get("day") or state.get("data_cutoff_date") or "",
                fund,
                ticks,
                verdict,
            )
            resp = llm.invoke([SystemMessage(content=SYSTEM), HumanMessage(content=prompt)])
            text = getattr(resp, "content", None)
            if isinstance(text, str) and len(text.strip()) > 80:
                narrative = _normalize_analysis(text)
        except Exception as exc:  # noqa: BLE001
            logger.warning("趋势解读 LLM 失败: %s", exc)
            narrative = fallback

    errors = state.get("errors") or []
    stats = _stats_section({**state, "verdict": verdict, "main_force": fund, "retail": ticks})
    analysis = _normalize_analysis(narrative)
    lines = [
        f"# {state.get('stock_name') or ''}（{state.get('stock_code') or ''}）趋势分析",
        "",
        f"- 数据日：{state.get('day') or state.get('data_cutoff_date') or ''}",
        f"- 规则结论：{verdict.get('lean')} · 置信度 {verdict.get('confidence')}",
        f"- 主力：{verdict.get('main_label')} · 散户：{verdict.get('retail_stance')}"
        f"（活跃度 {verdict.get('retail_activity')}）· 关系：{verdict.get('relation')}",
        "",
        stats,
        "## 分析解读",
        "",
        analysis,
        "",
    ]
    if errors:
        lines.extend(["## 采集问题", ""])
        lines.extend(f"- {e}" for e in errors)
        lines.append("")
    lines.extend(
        [
            "## 限制",
            "",
            "- 仅使用资金流与分时成交；不含日线形态、均线或量比",
            "- 主力净额来自东财分档资金流，存在口径与滞后",
            "- 散户数量为小单活跃度代理，不是账户数或持仓人数",
            "- 大单来自同花顺 HQ，失败时仅用资金流序列",
            "- 不做买卖建议；短线推断可能被隔夜消息推翻",
            "",
        ]
    )
    report = "\n".join(lines)
    emit_progress("tr_synth", "结论完成", phase="llm_done", status="done")
    return {"verdict": verdict, "narrative": narrative, "report": report}


def save_report(state: TrendState) -> dict:
    company = state.get("company") or ""
    cutoff = (state.get("data_cutoff_date") or date.today().isoformat()).replace("-", "")
    safe_name = re.sub(r"[^\w\u4e00-\u9fff-]", "_", state.get("stock_name") or company)
    code = state.get("stock_code") or ""
    stem = f"{safe_name}_{code}" if code and code not in safe_name else safe_name
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    path = REPORTS_DIR / f"{stem}趋势分析_{cutoff}.md"
    emit_progress("tr_save", "正在保存报告…", phase="save_file", status="running")
    path.write_text(state.get("report") or "", encoding="utf-8")
    emit_progress("tr_save", f"已保存至 {path.name}", phase="done", status="done")
    return {"report_path": str(path)}
