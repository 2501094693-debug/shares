"""Brief：按章节叙述。数字只引用 Ledger/Gauge，禁止模型重算。"""

from __future__ import annotations

import json
import logging
from typing import Any

from agent.config import OPENAI_API_KEY
from agent.fundamentals_agent.fmt import fmt_num, fmt_pct, fmt_yi
from agent.fundamentals_agent.gauge import Gauge
from agent.fundamentals_agent.ledger import Ledger
from agent.utils.llm import get_llm
from langchain_core.messages import HumanMessage, SystemMessage

logger = logging.getLogger(__name__)

SYSTEM = """你是 A 股财务与估值助手。
你只能解释输入 JSON 里已经算好的数字与灯色，禁止改写、重算、发明任何金额、比率、CAGR、内在价值或安全边际。
禁止给出买入/卖出点、仓位或「便宜就该买」。
态度标签只解释含义，不作交易指令。
输出中文，用 ### 小标题，不要大段表格（表已在报告中）。
每章不超过 220 字。"""

SECTIONS = (
    ("trend", "经营趋势", "近3-5年营收、营业利润、归母净利润走势与增速质量"),
    ("profit", "盈利能力", "ROE、ROA、毛利率、经营利润率的中枢与可持续性"),
    ("cash", "现金流", "经营现金流、资本开支、自由现金流与利润含金量"),
    ("balance", "资产负债健康度", "现金储备、负债率、流动/速动与短债压力"),
    ("valuation", "估值对照", "PE/PB/PS 相对历史中位与同业位置"),
    ("mos", "安全边际", "多种内在价值口径相对现价；综合锚与态度"),
)


def _payload(ledger: Ledger, gauge: Gauge, section_key: str) -> dict[str, Any]:
    dim = next((d for d in gauge.dims if d.key == section_key), None)
    base = {
        "snap": {
            "price": ledger.snap.price,
            "mcap": ledger.snap.mcap,
            "pe_ttm": ledger.snap.pe_ttm,
            "pb": ledger.snap.pb,
            "ps_ttm": ledger.snap.ps_ttm,
            "industry": ledger.snap.industry,
        },
        "growth": ledger.growth,
        "quality": ledger.quality,
        "history": {
            k: {
                "median": v.median,
                "low": v.low,
                "high": v.high,
                "latest": v.latest,
                "count": v.count,
            }
            for k, v in ledger.history.items()
        },
        "years": [
            {
                "period": y.period,
                "revenue": y.revenue,
                "op_profit": y.op_profit,
                "net_profit": y.net_profit,
                "gross_margin": y.gross_margin,
                "op_margin": y.op_margin,
                "roe": y.roe,
                "roa": y.roa,
                "ocf": y.ocf,
                "capex": y.capex,
                "fcf": y.fcf,
                "debt_ratio": y.debt_ratio,
                "cash": y.cash,
                "current_ratio": y.current_ratio,
            }
            for y in ledger.years[:5]
        ],
    }
    if dim:
        base["dim"] = {
            "label": dim.label,
            "light": dim.light,
            "score": dim.score,
            "summary": dim.summary,
            "flags": dim.flags,
        }
    if section_key in {"valuation", "mos"}:
        base["intrinsics"] = [
            {
                "method": i.method,
                "value": i.value,
                "mos": i.mos,
                "note": i.note,
            }
            for i in gauge.intrinsics
        ]
        base["anchor_iv"] = gauge.anchor_iv
        base["anchor_mos"] = gauge.anchor_mos
        base["stance"] = gauge.stance
        base["invalidation"] = gauge.invalidation
    return base


def _fallback(section_key: str, ledger: Ledger, gauge: Gauge) -> str:
    dim = next((d for d in gauge.dims if d.key == section_key), None)
    if section_key == "mos":
        return "\n".join(
            [
                "### 综合锚",
                f"可用内在价值口径的中位数为每股 {fmt_num(gauge.anchor_iv)}，"
                f"相对现价 {fmt_num(ledger.snap.price)} 的安全边际为 "
                f"{fmt_pct(gauge.anchor_mos, ratio=True) if gauge.anchor_mos is not None else '—'}。",
                "",
                "### 态度含义",
                f"规则态度为「{gauge.stance}」，仅描述现价相对质量与估值锚的位置，不是买卖建议。",
                "",
                "### 失效条件",
                "；".join(gauge.invalidation[:3]),
            ]
        )
    if dim:
        return "\n".join(
            [
                "### 规则摘要",
                dim.summary,
                "",
                "### 关注点",
                "；".join(dim.flags) if dim.flags else "见上表。",
            ]
        )
    return "（本节无规则摘要）"


def _ask(prompt: str, fallback: str) -> str:
    if not OPENAI_API_KEY:
        return fallback
    try:
        llm = get_llm()
        resp = llm.invoke([SystemMessage(content=SYSTEM), HumanMessage(content=prompt)])
        text = getattr(resp, "content", None)
        if isinstance(text, str) and len(text.strip()) > 40:
            return text.strip()
    except Exception as exc:  # noqa: BLE001
        logger.warning("财务估值叙述 LLM 失败: %s", exc)
    return fallback


def write_section(
    section_key: str,
    title: str,
    focus: str,
    *,
    stock_name: str,
    stock_code: str,
    ledger: Ledger,
    gauge: Gauge,
    skip_llm: bool = False,
) -> str:
    fallback = _fallback(section_key, ledger, gauge)
    if skip_llm:
        return fallback
    payload = _payload(ledger, gauge, section_key)
    prompt = f"""标的：{stock_name}（{stock_code}）
章节：{title}
关注：{focus}

预计算 JSON（禁止改数）：
{json.dumps(payload, ensure_ascii=False, default=str)[:6000]}

请写解读，结构：
### 现象
### 含义
### 需要盯住的变化
"""
    return _ask(prompt, fallback)


def write_all_sections(
    *,
    stock_name: str,
    stock_code: str,
    ledger: Ledger,
    gauge: Gauge,
    skip_llm: bool = False,
) -> dict[str, str]:
    out: dict[str, str] = {}
    for key, title, focus in SECTIONS:
        out[key] = write_section(
            key,
            title,
            focus,
            stock_name=stock_name,
            stock_code=stock_code,
            ledger=ledger,
            gauge=gauge,
            skip_llm=skip_llm,
        )
    return out


def compose_report(
    *,
    stock_name: str,
    stock_code: str,
    cutoff: str,
    ledger: Ledger,
    gauge: Gauge,
    notes: dict[str, str],
    sources: list[str],
    errors: list[str],
) -> str:
    light_map = {"green": "绿", "yellow": "黄", "red": "红", "gray": "灰"}
    dim_line = " · ".join(
        f"{d.label}{light_map.get(d.light, d.light)}" for d in gauge.dims
    )
    lines = [
        f"# {stock_name}（{stock_code}）财务数据、盈利能力与估值",
        "",
        f"- 数据截止：{cutoff}",
        f"- 现价 {fmt_num(ledger.snap.price)} · 市值 {fmt_yi(ledger.snap.mcap)}",
        f"- 行业 {ledger.snap.industry or '—'}",
        f"- PE_TTM {fmt_num(ledger.snap.pe_ttm)} · PB {fmt_num(ledger.snap.pb)} · PS_TTM {fmt_num(ledger.snap.ps_ttm)}",
        f"- 仪表盘：{dim_line}",
        f"- 综合内在价值锚 {fmt_num(gauge.anchor_iv)} · 安全边际 "
        f"{fmt_pct(gauge.anchor_mos, ratio=True) if gauge.anchor_mos is not None else '—'}",
        f"- 规则态度 **{gauge.stance}**（非买卖点）",
        "",
        "## 仪表盘总览",
        "",
        gauge.tables.get("dashboard") or "",
        "",
        ledger.tables.get("growth_summary") or "",
        "",
    ]

    section_tables = {
        "trend": ("一、经营趋势", "trend"),
        "profit": ("二、盈利能力", "profit"),
        "cash": ("三、现金流", "cash"),
        "balance": ("四、资产负债健康度", "balance"),
        "valuation": ("五、估值：历史与同业", None),
        "mos": ("六、安全边际", None),
    }
    for key, (heading, table_key) in section_tables.items():
        lines.extend([f"## {heading}", ""])
        if table_key:
            lines.extend([ledger.tables.get(table_key) or "", ""])
        if key == "valuation":
            lines.extend(
                [
                    ledger.tables.get("profile") or "",
                    "",
                    ledger.tables.get("history") or "",
                    "",
                    ledger.tables.get("peers") or "",
                    "",
                ]
            )
        if key == "mos":
            lines.extend([gauge.tables.get("intrinsic") or "", ""])
        lines.extend([notes.get(key) or "", ""])

    lines.extend(
        [
            "## 七、综合与失效条件",
            "",
            f"质量灯色与估值位置共同指向「{gauge.stance}」。"
            f"综合锚取多种每股内在价值口径的中位数 {fmt_num(gauge.anchor_iv)}。",
            "",
            "作废条件：",
            "",
        ]
    )
    lines.extend(f"- {item}" for item in gauge.invalidation)
    lines.extend(
        [
            "",
            "## 限制",
            "",
            "- 数字由台账与仪表盘规则计算；模型不得改写",
            "- 利润表/现金流为报告期累计口径；年报趋势为主",
            "- EV 为市值+总负债−货币资金的粗算，不作精确企业价值",
            "- 不做买卖点或仓位建议",
            "",
            "## 来源",
            "",
        ]
    )
    lines.extend(f"- {s}" for s in sources)
    if errors:
        lines.extend(["", "## 采集问题", ""])
        lines.extend(f"- {e}" for e in errors)
    lines.append("")
    return "\n".join(lines)
