"""Ledger：把报表行压成结构化年报台账与 Markdown 表。"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from agent.fundamentals_agent.fmt import (
    cagr,
    fmt_num,
    fmt_pct,
    fmt_x,
    fmt_yi,
    md_table,
    median,
    to_float,
)
from agent.tools.financials import (
    _balance_table,
    _cashflow_table,
    _capex,
    _fcf,
    _ocf,
    _op_margin,
    _op_profit,
    _pick,
    _profitability_table,
    _revenue,
    _roa,
    _net_profit,
    _trend_table,
    _liq_ratio,
)


@dataclass
class YearPoint:
    period: str
    revenue: float | None = None
    revenue_yoy: float | None = None
    op_profit: float | None = None
    net_profit: float | None = None
    net_profit_yoy: float | None = None
    deduct: float | None = None
    gross_margin: float | None = None
    net_margin: float | None = None
    op_margin: float | None = None
    roe: float | None = None
    roa: float | None = None
    roic: float | None = None
    eps: float | None = None
    ocf: float | None = None
    capex: float | None = None
    fcf: float | None = None
    ocf_ni: float | None = None
    cash: float | None = None
    total_assets: float | None = None
    total_liab: float | None = None
    equity: float | None = None
    debt_ratio: float | None = None
    current_ratio: float | None = None
    quick_ratio: float | None = None
    short_loan: float | None = None


@dataclass
class Snapshot:
    price: float | None = None
    mcap: float | None = None
    pe_ttm: float | None = None
    pb: float | None = None
    ps_ttm: float | None = None
    eps: float | None = None
    shares: float | None = None
    industry: str = ""


@dataclass
class HistoryMult:
    field: str
    count: int = 0
    median: float | None = None
    low: float | None = None
    high: float | None = None
    latest: float | None = None


@dataclass
class Ledger:
    years: list[YearPoint] = field(default_factory=list)
    snap: Snapshot = field(default_factory=Snapshot)
    history: dict[str, HistoryMult] = field(default_factory=dict)
    peer_text: str = ""
    tables: dict[str, str] = field(default_factory=dict)
    growth: dict[str, float | None] = field(default_factory=dict)
    quality: dict[str, float | None] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "years": [asdict(y) for y in self.years],
            "snap": asdict(self.snap),
            "history": {k: asdict(v) for k, v in self.history.items()},
            "peer_text": self.peer_text,
            "tables": self.tables,
            "growth": self.growth,
            "quality": self.quality,
        }


def _period_label(row: dict[str, Any]) -> str:
    return str(row.get("PERIOD_LABEL") or str(row.get("REPORT_DATE") or "")[:10] or "—")


def _ocf_ni(row: dict[str, Any]) -> float | None:
    ocf = to_float(_ocf(row))
    ni = to_float(_net_profit(row))
    nco = to_float(_pick(row, "NCO_NETPROFIT"))
    if nco is not None:
        return nco * 100 if nco < 5 else nco
    if ocf is not None and ni:
        return ocf / ni * 100
    return None


def _year_point(row: dict[str, Any]) -> YearPoint:
    return YearPoint(
        period=_period_label(row),
        revenue=to_float(_revenue(row)),
        revenue_yoy=to_float(_pick(row, "TOTALOPERATEREVETZ", "TOI_RATIO")),
        op_profit=to_float(_op_profit(row)),
        net_profit=to_float(_net_profit(row)),
        net_profit_yoy=to_float(_pick(row, "PARENTNETPROFITTZ", "PARENT_NETPROFIT_RATIO")),
        deduct=to_float(_pick(row, "KCFJCXSYJLR", "DEDUCT_PARENT_NETPROFIT")),
        gross_margin=to_float(_pick(row, "XSMLL")),
        net_margin=to_float(_pick(row, "XSJLL")),
        op_margin=to_float(_op_margin(row)),
        roe=to_float(_pick(row, "ROEJQ", "WEIGHTAVG_ROE")),
        roa=to_float(_roa(row)),
        roic=to_float(_pick(row, "ROIC")),
        eps=to_float(_pick(row, "EPSJB", "BASIC_EPS")),
        ocf=to_float(_ocf(row)),
        capex=to_float(_capex(row)),
        fcf=to_float(_fcf(row)),
        ocf_ni=_ocf_ni(row),
        cash=to_float(_pick(row, "MONETARYFUNDS")),
        total_assets=to_float(_pick(row, "TOTAL_ASSETS_PK", "TOTAL_ASSETS")),
        total_liab=to_float(_pick(row, "LIABILITY", "TOTAL_LIABILITIES")),
        equity=to_float(_pick(row, "TOTAL_EQUITY_PK", "TOTAL_EQUITY")),
        debt_ratio=to_float(_pick(row, "ZCFZL", "DEBT_ASSET_RATIO")),
        current_ratio=to_float(_liq_ratio(row, "LD", "CURRENT_RATIO")),
        quick_ratio=to_float(_liq_ratio(row, "SD")),
        short_loan=to_float(_pick(row, "SHORT_LOAN")),
    )


def _mcap(profile: dict[str, Any]) -> float | None:
    raw = to_float(profile.get("_mcap_raw"))
    if raw is not None:
        return raw
    labeled = to_float(profile.get("total_market_cap"))
    if labeled is not None:
        return labeled
    bare = to_float(profile.get("market_cap"))
    if bare is None:
        return None
    text = str(profile.get("market_cap") or "")
    if "亿" in text or "万" in text:
        return bare
    if bare < 1e6:
        return bare * 1e8
    return bare


def _snapshot(profile: dict[str, Any], industry: dict[str, Any], latest: YearPoint | None) -> Snapshot:
    price = to_float(profile.get("_price_raw") or profile.get("price"))
    mcap = _mcap(profile)
    pe = to_float(profile.get("pe_ttm"))
    pb = to_float(profile.get("pb"))
    ps = to_float(profile.get("ps_ttm"))
    eps = to_float(profile.get("eps"))
    if (eps is None or eps <= 0) and price and pe and pe > 0:
        eps = price / pe
    shares = to_float(profile.get("total_share") or profile.get("total_shares") or profile.get("TOTAL_SHARE"))
    if shares is None and mcap and price:
        shares = mcap / price
    industry_text = " / ".join(
        x
        for x in (
            industry.get("l1_name") or profile.get("l1_name") or "",
            industry.get("l2_name") or profile.get("l2_name") or "",
            industry.get("name") or industry.get("l3_name") or profile.get("l3_name") or "",
        )
        if x
    )
    return Snapshot(
        price=price,
        mcap=mcap,
        pe_ttm=pe if pe and pe > 0 else None,
        pb=pb if pb and pb > 0 else None,
        ps_ttm=ps if ps and ps > 0 else None,
        eps=eps,
        shares=shares,
        industry=industry_text,
    )


def _history_stats(pe_items: list[dict[str, Any]]) -> dict[str, HistoryMult]:
    out: dict[str, HistoryMult] = {}
    for field in ("pe_ttm", "pb", "ps_ttm"):
        vals = [to_float(item.get(field)) for item in pe_items]
        vals = [v for v in vals if v is not None and v > 0]
        latest = to_float(pe_items[-1].get(field)) if pe_items else None
        out[field] = HistoryMult(
            field=field,
            count=len(vals),
            median=median(vals),
            low=min(vals) if vals else None,
            high=max(vals) if vals else None,
            latest=latest if latest and latest > 0 else None,
        )
    return out


def _growth(years: list[YearPoint]) -> dict[str, float | None]:
    window = years[:5]
    if len(window) < 2:
        return {"rev_cagr": None, "ni_cagr": None, "op_cagr": None, "n": len(window)}
    # years[0] = 最近一年
    n = len(window) - 1
    return {
        "rev_cagr": cagr(window[-1].revenue, window[0].revenue, n),
        "ni_cagr": cagr(window[-1].net_profit, window[0].net_profit, n),
        "op_cagr": cagr(window[-1].op_profit, window[0].op_profit, n),
        "n": float(len(window)),
    }


def _quality(years: list[YearPoint]) -> dict[str, float | None]:
    window = years[:5]
    return {
        "roe_med": median([y.roe for y in window]),
        "roa_med": median([y.roa for y in window]),
        "gm_med": median([y.gross_margin for y in window]),
        "opm_med": median([y.op_margin for y in window]),
        "ocf_ni_med": median([y.ocf_ni for y in window]),
        "fcf_med": median([y.fcf for y in window]),
        "debt_latest": window[0].debt_ratio if window else None,
        "cash_latest": window[0].cash if window else None,
        "current_latest": window[0].current_ratio if window else None,
        "quick_latest": window[0].quick_ratio if window else None,
    }


def build_ledger(pack: dict[str, Any]) -> Ledger:
    annual = list(pack.get("annual") or [])[:8]
    years = [_year_point(row) for row in annual]
    snap = _snapshot(pack.get("profile") or {}, pack.get("industry") or {}, years[0] if years else None)
    history = _history_stats(list(pack.get("pe_items") or []))
    tables = {
        "trend": (pack.get("fin_sections") or {}).get("近3-5年年报趋势（原始数据）")
        or _trend_table(annual),
        "profit": (pack.get("fin_sections") or {}).get("盈利能力指标（原始数据）")
        or _profitability_table(annual),
        "cash": (pack.get("fin_sections") or {}).get("现金流（原始数据）")
        or _cashflow_table(annual),
        "balance": (pack.get("fin_sections") or {}).get("资产负债表健康度（原始数据）")
        or _balance_table(annual[:5]),
        "profile": (pack.get("val_sections") or {}).get("当前估值与盘口（原始数据）") or "",
        "history": (pack.get("val_sections") or {}).get("历史估值（东财日频，原始序列摘要）") or "",
        "peers": (pack.get("val_sections") or {}).get("同业估值对比（申万三级）") or "",
    }
    # 补一张精简增长摘要表
    g = _growth(years)
    q = _quality(years)
    tables["growth_summary"] = md_table(
        ["指标", "数值"],
        [
            ["样本年数", fmt_num(g.get("n"), 0)],
            ["营收CAGR", fmt_pct(g.get("rev_cagr"), ratio=True)],
            ["营业利润CAGR", fmt_pct(g.get("op_cagr"), ratio=True)],
            ["归母净利CAGR", fmt_pct(g.get("ni_cagr"), ratio=True)],
            ["ROE中位", fmt_pct(q.get("roe_med"))],
            ["ROA中位", fmt_pct(q.get("roa_med"))],
            ["毛利率中位", fmt_pct(q.get("gm_med"))],
            ["经营利润率中位", fmt_pct(q.get("opm_med"))],
            ["OCF/净利润中位", fmt_pct(q.get("ocf_ni_med"))],
            ["FCF中位", fmt_yi(q.get("fcf_med"))],
            ["最新资产负债率", fmt_pct(q.get("debt_latest"))],
            ["最新货币资金", fmt_yi(q.get("cash_latest"))],
            ["最新流动比率", fmt_x(q.get("current_latest"))],
            ["最新速动比率", fmt_x(q.get("quick_latest"))],
        ],
    )
    return Ledger(
        years=years,
        snap=snap,
        history=history,
        peer_text=tables.get("peers") or "",
        tables=tables,
        growth=g,
        quality=q,
    )
