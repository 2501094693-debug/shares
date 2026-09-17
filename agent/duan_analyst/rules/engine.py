"""段永平看业务规则引擎：长期毛利率、净现金流、杠杆 — 只给数字提示，不当最终判决。"""

from __future__ import annotations

import re
import statistics
from typing import Any

from agent.buffett_analyst.rules.engine import period_kind
from agent.comprehensive_analyst.rules._common import (
    fmt_pct,
    fmt_yi,
    md_table,
    period_label,
    pick,
    to_float,
)
from agent.duan_analyst.rules._fields import (
    CAPEX_FIELDS,
    DEBT_RATIO_FIELDS,
    EQUITY_FIELDS,
    GROSS_MARGIN_FIELDS,
    NET_MARGIN_FIELDS,
    NET_PROFIT_FIELDS,
    OCF_FIELDS,
    REVENUE_FIELDS,
    ROE_FIELDS,
    TOTAL_ASSETS_FIELDS,
    TOTAL_LIAB_FIELDS,
)

PASS = "通过"
WEAK = "存疑"
REJECT = "离开"
UNKNOWN = "看不懂"
SKIPPED = "跳过"

CHEAP = "便宜"
FAIR = "还行"
EXPENSIVE = "贵"

ATTITUDE_LEAVE = "离开"
ATTITUDE_WAIT = "等待好价钱"
ATTITUDE_OK = "可以毛估估"
ATTITUDE_UNKNOWN = "看不懂"

HINT_GOOD = "数字上像好生意"
HINT_HARD = "数字上像苦生意"
HINT_OK = "数字上像一般生意"
HINT_THIN = "数据不足"

ANNUAL_LIMIT = 8
STOP_VERDICTS = {REJECT, UNKNOWN}
CONTINUE_VERDICTS = {PASS, WEAK}

FILTER_VERDICT_RE = re.compile(r"过滤器判决[：:]\s*(通过|存疑|离开|看不懂)")
PRICE_VERDICT_RE = re.compile(r"价格判决[：:]\s*(便宜|还行|贵|跳过)")
ATTITUDE_RE = re.compile(r"综合态度[：:]\s*(离开|等待好价钱|可以毛估估|看不懂)")


def _median(values: list[float]) -> float | None:
    clean = [v for v in values if v is not None]
    if not clean:
        return None
    return float(statistics.median(clean))


def _ratio(num: float | None, den: float | None) -> float | None:
    if num is None or den in (None, 0):
        return None
    return num / den * 100


def _debt_ratio(row: dict[str, Any]) -> float | None:
    disclosed = to_float(pick(row, *DEBT_RATIO_FIELDS))
    if disclosed is not None:
        return disclosed
    liab = to_float(pick(row, *TOTAL_LIAB_FIELDS))
    assets = to_float(pick(row, *TOTAL_ASSETS_FIELDS))
    return _ratio(liab, assets)


def _snapshot(row: dict[str, Any]) -> dict[str, Any]:
    revenue = to_float(pick(row, *REVENUE_FIELDS))
    ni = to_float(pick(row, *NET_PROFIT_FIELDS))
    ocf = to_float(pick(row, *OCF_FIELDS))
    capex_raw = to_float(pick(row, *CAPEX_FIELDS))
    capex = abs(capex_raw) if capex_raw is not None else None
    fcf = None if ocf is None or capex is None else ocf - capex
    ocf_ni = _ratio(ocf, ni) if ni not in (None, 0) else None
    return {
        "period": period_label(row),
        "kind": period_kind(row),
        "revenue": revenue,
        "net_profit": ni,
        "ocf": ocf,
        "capex": capex,
        "fcf": fcf,
        "gross_margin": to_float(pick(row, *GROSS_MARGIN_FIELDS)),
        "net_margin": to_float(pick(row, *NET_MARGIN_FIELDS)),
        "roe": to_float(pick(row, *ROE_FIELDS)),
        "debt_ratio": _debt_ratio(row),
        "equity": to_float(pick(row, *EQUITY_FIELDS)),
        "ocf_ni": ocf_ni,
        "capex_sales": _ratio(capex, revenue),
    }


def _annual_rows(
    annual: list[dict[str, Any]] | None,
    merged: list[dict[str, Any]] | None,
    *,
    limit: int = ANNUAL_LIMIT,
) -> list[dict[str, Any]]:
    pool = list(annual or [])
    if not pool:
        pool = [row for row in (merged or []) if period_kind(row) == "年报"]
    return pool[:limit]


def _hint(snaps: list[dict[str, Any]]) -> tuple[str, str, list[str]]:
    flags: list[str] = []
    gm_vals = [s["gross_margin"] for s in snaps if s.get("gross_margin") is not None]
    fcf_vals = [s["fcf"] for s in snaps if s.get("fcf") is not None]
    debt_vals = [s["debt_ratio"] for s in snaps if s.get("debt_ratio") is not None]
    ocf_ni_vals = [s["ocf_ni"] for s in snaps if s.get("ocf_ni") is not None]
    roe_vals = [s["roe"] for s in snaps if s.get("roe") is not None]
    capex_sales_vals = [s["capex_sales"] for s in snaps if s.get("capex_sales") is not None]

    gm_median = _median(gm_vals)
    gm_min = min(gm_vals) if gm_vals else None
    latest = snaps[0] if snaps else {}
    latest_gm = latest.get("gross_margin")
    latest_debt = latest.get("debt_ratio")
    fcf_pos_ratio = (
        sum(1 for v in fcf_vals if v > 0) / len(fcf_vals) if fcf_vals else None
    )
    ocf_ni_median = _median(ocf_ni_vals)
    roe_median = _median(roe_vals)
    capex_sales_median = _median(capex_sales_vals)

    if latest_gm is not None and gm_median is not None and latest_gm < gm_median - 8:
        flags.append(f"毛利率从中位 {gm_median:.1f}% 降到最新 {latest_gm:.1f}%，差异化可能在变薄")
    if gm_median is not None and gm_median < 18:
        flags.append("长期毛利率偏低，产品可替代性可能较高")
    if fcf_pos_ratio is not None and fcf_pos_ratio < 0.5:
        flags.append("自由现金流多年为负，长期净现金不满意")
    if latest_debt is not None and latest_debt >= 70:
        flags.append("资产负债率偏高，段永平不喜欢高负债生意")
    if (
        roe_median is not None
        and roe_median >= 15
        and latest_debt is not None
        and latest_debt >= 70
    ):
        flags.append("ROE 看起来不低，但杠杆不低，先别被回报率骗了")
    if (
        capex_sales_median is not None
        and capex_sales_median >= 15
        and (gm_median is None or gm_median < 25)
        and (fcf_pos_ratio is None or fcf_pos_ratio < 0.5)
    ):
        flags.append("资本开支重、毛利薄、现金弱，更像辛苦生意；重资产本身不是否决项")

    if len(gm_vals) < 3 and len(fcf_vals) < 3:
        return HINT_THIN, "年报样本不足，数字只能当旁证", flags

    hard = False
    if gm_median is not None and gm_median < 12:
        hard = True
    if gm_median is not None and gm_median < 18 and fcf_pos_ratio is not None and fcf_pos_ratio < 0.5:
        hard = True
    if latest_debt is not None and latest_debt >= 75:
        hard = True

    good = (
        gm_median is not None
        and gm_median >= 30
        and gm_min is not None
        and gm_min >= 18
        and fcf_pos_ratio is not None
        and fcf_pos_ratio >= 0.6
        and (latest_debt is None or latest_debt < 65)
    )

    if hard:
        return HINT_HARD, "长期毛利率、净现金或杠杆数字难看，先当苦生意筛一遍", flags
    if good:
        reason = "长期毛利率厚、净现金多数年份为正、杠杆可控"
        if ocf_ni_median is not None:
            reason += f"，经营现金流/净利润中位 {ocf_ni_median:.0f}%"
        return HINT_GOOD, reason, flags
    return HINT_OK, "数字不上不下，生意好不好仍取决于差异化能不能长期维持", flags


def hint_to_fallback_verdict(hint: str) -> str:
    if hint == HINT_HARD:
        return REJECT
    if hint == HINT_GOOD:
        return PASS
    return WEAK


def parse_filter_verdict(text: str, fallback: str = WEAK) -> str:
    match = FILTER_VERDICT_RE.search(text or "")
    return match.group(1) if match else fallback


def parse_price_verdict(text: str, fallback: str = SKIPPED) -> str:
    match = PRICE_VERDICT_RE.search(text or "")
    return match.group(1) if match else fallback


def parse_attitude(text: str, fallback: str) -> str:
    match = ATTITUDE_RE.search(text or "")
    return match.group(1) if match else fallback


def should_continue_after_business(verdict: str) -> bool:
    return verdict in CONTINUE_VERDICTS


def should_continue_after_culture(verdict: str) -> bool:
    return verdict in CONTINUE_VERDICTS


def resolve_final_attitude(business: str, culture: str, price: str) -> str:
    """过滤器是必要条件：后面的章节不得推翻前面的离开/看不懂。"""
    if business == UNKNOWN:
        return ATTITUDE_UNKNOWN
    if business == REJECT:
        return ATTITUDE_LEAVE
    if culture == UNKNOWN:
        return ATTITUDE_UNKNOWN
    if culture == REJECT:
        return ATTITUDE_LEAVE
    if price == EXPENSIVE:
        return ATTITUDE_WAIT
    if price in {CHEAP, FAIR}:
        return ATTITUDE_OK
    return ATTITUDE_WAIT


def _long_term_table(snaps: list[dict[str, Any]]) -> str:
    rows = [
        [
            s["period"],
            fmt_yi(s.get("revenue")),
            fmt_pct(s.get("gross_margin")),
            fmt_pct(s.get("net_margin")),
            fmt_yi(s.get("net_profit")),
            fmt_yi(s.get("ocf")),
            fmt_yi(s.get("fcf")),
            fmt_pct(s.get("ocf_ni")),
            fmt_pct(s.get("roe")),
            fmt_pct(s.get("debt_ratio")),
        ]
        for s in snaps
    ]
    table = md_table(
        [
            "报告期",
            "营收",
            "毛利率",
            "净利率",
            "归母净利润",
            "经营现金流",
            "自由现金流",
            "OCF/净利润",
            "ROE",
            "资产负债率",
        ],
        rows,
    )
    return (
        table
        + "\n\n**计算公式**\n\n"
        + md_table(
            ["指标", "计算公式"],
            [
                ["毛利率", "东财 XSMLL（销售毛利率）"],
                ["自由现金流", "经营现金流 − |购建固定资产等支付的现金|"],
                ["OCF/净利润", "经营现金流 / 归母净利润"],
                ["资产负债率", "优先用披露值 ZCFZL，否则 总负债 / 总资产"],
            ],
        )
    )


def _diagnosis_table(
    hint: str,
    reason: str,
    snaps: list[dict[str, Any]],
    gm_median: float | None,
    fcf_pos_ratio: float | None,
) -> str:
    latest = snaps[0] if snaps else {}
    gm_vals = [s["gross_margin"] for s in snaps if s.get("gross_margin") is not None]
    return md_table(
        ["检查项", "结果"],
        [
            ["数字提示（禁止改写）", hint],
            ["提示依据", reason],
            ["样本期数", str(len(snaps))],
            ["长期毛利率中位", fmt_pct(gm_median)],
            ["长期毛利率最低", fmt_pct(min(gm_vals) if gm_vals else None)],
            ["自由现金流为正的年份占比", fmt_pct((fcf_pos_ratio or 0) * 100 if fcf_pos_ratio is not None else None)],
            ["最新资产负债率", fmt_pct(latest.get("debt_ratio"))],
            ["最新 ROE", fmt_pct(latest.get("roe"))],
        ],
    )


def run_duan_screen(
    annual: list[dict[str, Any]] | None = None,
    recent: list[dict[str, Any]] | None = None,
    *,
    merged: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """预计算长期毛利率、净现金流、杠杆。差异化仍由模型判断。"""
    annual_rows = _annual_rows(annual, merged)
    if not annual_rows and (recent or merged):
        annual_rows = list(recent or merged or [])[:ANNUAL_LIMIT]
    snaps = [_snapshot(row) for row in annual_rows]
    snaps = [s for s in snaps if s.get("period")]
    hint, reason, flags = _hint(snaps)
    gm_vals = [s["gross_margin"] for s in snaps if s.get("gross_margin") is not None]
    fcf_vals = [s["fcf"] for s in snaps if s.get("fcf") is not None]
    fcf_pos_ratio = (
        sum(1 for v in fcf_vals if v > 0) / len(fcf_vals) if fcf_vals else None
    )
    gm_median = _median(gm_vals)
    latest = snaps[0] if snaps else {}

    tables = {
        "long_term": _long_term_table(snaps) if snaps else "（无年报样本）",
        "diagnosis": _diagnosis_table(hint, reason, snaps, gm_median, fcf_pos_ratio),
    }
    coverage = "、".join(s["period"] for s in snaps[:5]) or "无"
    text = "\n".join(
        [
            f"### 数字提示：{hint}",
            f"- 依据：{reason}",
            f"- 年报样本：{coverage}",
            f"- 长期毛利率中位：{fmt_pct(gm_median)}，最低：{fmt_pct(min(gm_vals) if gm_vals else None)}",
            f"- 自由现金流为正的年份：{fmt_pct((fcf_pos_ratio or 0) * 100 if fcf_pos_ratio is not None else None)}",
            f"- 最新资产负债率：{fmt_pct(latest.get('debt_ratio'))}，ROE：{fmt_pct(latest.get('roe'))}",
            "",
            "### 风险警示",
        ]
        + ([f"- {item}" for item in flags] if flags else ["- 暂无重大数字警示"])
        + [
            "",
            "> 数字只回答「长期毛利率、净现金、杠杆」。差异化、用户是否换得走、企业文化，必须另外判断。",
            "> 重资产不等于坏生意；资本开支高但净现金好，不能据此离开。",
        ]
    )
    return {
        "metrics": {
            "latest": latest,
            "snapshots": snaps,
            "gm_median": gm_median,
            "fcf_positive_ratio": fcf_pos_ratio,
            "hint": hint,
            "reason": reason,
        },
        "flags": flags,
        "tables": tables,
        "text": text,
        "numeric_hint": hint,
    }
