"""DCF 现金流折现绝对估值引擎。

复用现有能力：
- ``financialreport.engine.compute_bundle`` 的 ``metrics``（FCF/OCF/资本开支/金融性负债/货币资金/营收/净利润）
- ``company.profile.get_stock_profile`` 的当前价、总股本、总市值

全部计算为确定性 Python，不依赖任何模型。输出的是「内在价值区间 + 安全边际」所需的基础量，
不给出买卖建议（建议由安全边际模块结合价格判断）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from core.fmt import to_float

_YI = 1e8
_WAN = 1e4


def _to_raw(value: Any) -> float | None:
    """把东财展示字符串（如 "12.34亿"/"1234万"）或原始数字还原为原始单位数值。

    支持单位后缀：亿、万、股（股本字段常带"股"）。失败返回 None，避免静默用错单位。
    """
    n = to_float(value)
    if n is not None:
        return n
    text = str(value or "").strip().replace(",", "").replace("股", "")
    if not text:
        return None
    mult = 1.0
    if text.endswith("亿"):
        mult = _YI
        text = text[:-1]
    elif text.endswith("万"):
        mult = _WAN
        text = text[:-1]
    base = to_float(text)
    if base is None:
        return None
    return base * mult


def _pct(value: Any) -> float | None:
    """把百分比（如 15.2 或 "15.2%"）转成小数（0.152）。"""
    n = to_float(value)
    if n is None:
        return None
    # 东财部分接口已是百分数（15.2 表示 15.2%），部分已是小数（0.152）；>1 的按百分数处理
    return n / 100.0 if n > 1 else n


@dataclass
class DcfAssumptions:
    """DCF 假设参数。全部可由调用方覆盖；缺省采用保守值。"""

    projection_years: int = 5          # 显性预测期年数
    wacc: float = 0.09                 # 折现率（加权平均资本成本）
    terminal_growth: float = 0.025     # 永续增长率（必须 < wacc）
    first_stage_growth: float | None = None  # 显性期年复合增长率；None 时由营收 CAGR 推导
    safety_discount: float = 0.0       # 额外安全发令（0~1，对内在价值打折）

    def __post_init__(self) -> None:
        if not (0 < self.wacc < 1):
            raise ValueError("wacc 必须在 0~1 之间")
        if not (0 <= self.terminal_growth < self.wacc):
            raise ValueError("terminal_growth 必须满足 0 <= g < wacc")


@dataclass
class DcfResult:
    """DCF 计算结果。单位：金额为元，每股为元/股。"""

    # 核心产出
    intrinsic_value_per_share: float | None = None
    enterprise_value: float | None = None        # 企业价值 EV
    equity_value: float | None = None            # 股权价值 = EV - 净债务
    net_debt: float | None = None                # 净债务 = 有息债 - 货币资金

    # 明细
    fcf_base: float | None = None                # 基期自由现金流
    fcf_projection: list[dict[str, Any]] = field(default_factory=list)  # 每年 FCF 与现值
    terminal_value: float | None = None
    pv_terminal: float | None = None
    pv_explicit: float | None = None

    # 与价格对比
    current_price: float | None = None
    margin_of_safety_pct: float | None = None    # (内在 - 价) / 内在
    upside_downside_pct: float | None = None     # (内在 - 价) / 价

    # 敏感性：(wacc, g) -> 每股内在价值
    sensitivity: list[dict[str, Any]] = field(default_factory=list)

    # 元数据
    assumptions_used: dict[str, Any] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
    revenue_cagr_used: float | None = None


def _latest_series_value(series: list[dict[str, Any]], *keys: str) -> float | None:
    """从年度系列最新一期取首个非空字段。"""
    for row in series or []:
        for key in keys:
            v = to_float(row.get(key))
            if v is not None:
                return v
    return None


def _revenue_cagr(annual_series: list[dict[str, Any]]) -> float | None:
    """按可用的年度营收算复合增长率（首尾两期）。返回小数，失败返回 None。"""
    revenues: list[float] = []
    for row in annual_series or []:
        rev = to_float(
            row.get("TOTALOPERATEREVE")
            or row.get("TOTAL_OPERATE_INCOME")
            or row.get("OPERATE_INCOME_PK")
        )
        if rev is not None and rev > 0:
            revenues.append(rev)
    if len(revenues) < 2:
        return None
    # annual_series 通常按时间降序，最新在前；取首末
    latest, oldest = revenues[0], revenues[-1]
    periods = len(revenues) - 1
    if periods <= 0 or oldest <= 0:
        return None
    cagr = (latest / oldest) ** (1.0 / periods) - 1.0
    return cagr


def _base_fcf(metrics: dict[str, Any]) -> tuple[float | None, list[str]]:
    """确定基期自由现金流。优先 FCFF，其次 OCF - 资本开支，再退到净利润代理。"""
    notes: list[str] = []
    cash = (metrics or {}).get("cash") or {}
    fcf = cash.get("fcf")
    if fcf is not None and fcf > 0:
        return fcf, notes
    if fcf is not None:
        notes.append(f"基期 FCF 为 {fcf:,.0f} 元（≤0），改用经营现金流作为保守代理")
    ocf = cash.get("ocf")
    capex = cash.get("capex") or 0.0
    if ocf is not None:
        derived = ocf - capex
        if derived > 0:
            notes.append("FCF 未直接披露，按 经营现金流 - 资本开支 估算")
            return derived, notes
    profit = (metrics or {}).get("profit") or {}
    net = profit.get("net_profit")
    if net is not None and net > 0:
        notes.append("经营现金流亦不可用，以净利润作极保守的 FCF 代理（高估可能）")
        return net, notes
    return None, notes


def _net_debt(metrics: dict[str, Any]) -> tuple[float | None, list[str]]:
    """净债务 = 有息债务 - 货币资金。失败返回 None。"""
    notes: list[str] = []
    liab = (metrics or {}).get("liabilities") or {}
    assets = (metrics or {}).get("assets") or {}
    debt = liab.get("financial_liabilities")
    if debt is None:
        debt = liab.get("total_liabilities")
        notes.append("未取到金融性负债，以总负债代理计算净债务")
    cash = assets.get("cash")  # MONETARYFUNDS 货币资金
    if debt is None:
        return None, notes
    if cash is None:
        notes.append("未取到货币资金，净债务仅按有息债务计（保守）")
        return debt, notes
    return debt - cash, notes


def _shares_from_profile(profile: dict[str, Any] | None) -> float | None:
    """从盘口画像提取总股本（原始股数）。"""
    if not profile:
        return None
    raw = profile.get("total_shares") or profile.get("share_capital")
    return _to_raw(raw)


def _price_from_profile(profile: dict[str, Any] | None) -> float | None:
    if not profile:
        return None
    return _to_raw(profile.get("price") or profile.get("current_price") or profile.get("latest_price"))


def _market_cap_from_profile(profile: dict[str, Any] | None) -> float | None:
    if not profile:
        return None
    return _to_raw(
        profile.get("total_market_cap")
        or profile.get("market_cap")
        or profile.get("total_market_value")
    )


def _annual_series_from_metrics(metrics: dict[str, Any]) -> list[dict[str, Any]]:
    """metrics 里不直接带系列；此处保留空列表占位，由 engine 注入 annual series。"""
    return []


def dcf_valuate(
    metrics: dict[str, Any],
    *,
    profile: dict[str, Any] | None = None,
    assumptions: DcfAssumptions | None = None,
    annual_series: list[dict[str, Any]] | None = None,
) -> DcfResult:
    """基于自由现金流折现（DCF）估算每股内在价值。

    参数
    ----------
    metrics:
        财报八看 ``compute_bundle`` 产出的 metrics 字典（含 cash/assets/liabilities/profit）。
    profile:
        个股盘口画像，用于取当前价、总股本、总市值。
    assumptions:
        折现假设；缺省用保守值（wacc 9%、永续增长 2.5%、预测 5 年）。
    annual_series:
        年度定期报告序列（最新在前），用于推导营收 CAGR 作为显性期增长率。

    返回
    -------
    DcfResult：每股内在价值、EV/股权价值、现金流明细、安全边际、敏感性矩阵。
    """
    assumptions = assumptions or DcfAssumptions()
    notes: list[str] = []

    # ---------- 1. 基期 FCF ----------
    fcf_base, fcf_notes = _base_fcf(metrics)
    notes.extend(fcf_notes)
    if fcf_base is None:
        return DcfResult(
            notes=notes + ["无法确定基期自由现金流，DCF 无法计算"],
            assumptions_used={
                "projection_years": assumptions.projection_years,
                "wacc": assumptions.wacc,
                "terminal_growth": assumptions.terminal_growth,
            },
        )

    # ---------- 2. 显性期增长率 ----------
    growth = assumptions.first_stage_growth
    if growth is None and annual_series:
        growth = _revenue_cagr(annual_series)
        if growth is not None:
            # 保守截断：过高增长不可持续，上限 20%，下限 -10%
            growth = max(-0.10, min(0.20, growth))
            notes.append(f"显性期增长率取营收 CAGR {growth*100:.1f}%（已截断到 [-10%, 20%]）")
        else:
            notes.append("未取到足够年度营收，显性期增长率暂按 0%（极保守）")
            growth = 0.0
    elif growth is None:
        notes.append("未提供显性期增长率，暂按 0%（极保守）")
        growth = 0.0

    revenue_cagr_used = growth

    # ---------- 3. 股本与净债务 ----------
    total_shares = _shares_from_profile(profile)
    if total_shares is None:
        notes.append("未取到总股本，将只输出企业价值/股权价值总额，不输出每股内在价值")
    net_debt, debt_notes = _net_debt(metrics)
    notes.extend(debt_notes)

    # ---------- 4. 显性期现金流折现 ----------
    projection_years = assumptions.projection_years
    wacc = assumptions.wacc
    g = growth
    projection: list[dict[str, Any]] = []
    pv_explicit = 0.0
    fcf_t = fcf_base
    for year in range(1, projection_years + 1):
        fcf_t = fcf_base * ((1.0 + g) ** year)
        pv = fcf_t / ((1.0 + wacc) ** year)
        pv_explicit += pv
        projection.append(
            {
                "year": year,
                "fcf": round(fcf_t, 2),
                "pv": round(pv, 2),
                "discount_factor": round(1.0 / ((1.0 + wacc) ** year), 6),
            }
        )

    # ---------- 5. 终值（戈登增长模型） ----------
    terminal_growth = assumptions.terminal_growth
    if terminal_growth >= wacc:
        terminal_growth = wacc - 0.005
        notes.append("永续增长率已被下调至低于折现率（避免分母非正）")
    fcf_terminal = fcf_t * (1.0 + terminal_growth)
    terminal_value = fcf_terminal / (wacc - terminal_growth)
    pv_terminal = terminal_value / ((1.0 + wacc) ** projection_years)

    # ---------- 6. 企业价值 / 股权价值 / 每股价值 ----------
    enterprise_value = pv_explicit + pv_terminal
    if net_debt is not None:
        equity_value = enterprise_value - net_debt
    else:
        equity_value = enterprise_value
        notes.append("未取到净债务，股权价值暂等于企业价值")

    intrinsic_per_share: float | None = None
    if total_shares and total_shares > 0:
        intrinsic_per_share = equity_value / total_shares

    # 应用额外安全发令
    if assumptions.safety_discount and intrinsic_per_share is not None:
        intrinsic_per_share = intrinsic_per_share * (1.0 - assumptions.safety_discount)
        notes.append(f"已对每股内在价值打 {assumptions.safety_discount*100:.0f}% 额外安全发令")

    # ---------- 7. 与当前价格对比 ----------
    current_price = _price_from_profile(profile)
    margin_of_safety: float | None = None
    upside_downside: float | None = None
    if intrinsic_per_share is not None and current_price and current_price > 0:
        margin_of_safety = (intrinsic_per_share - current_price) / intrinsic_per_share
        upside_downside = (intrinsic_per_share - current_price) / current_price

    # ---------- 8. 敏感性矩阵（wacc ±1%，g ±0.5%） ----------
    sensitivity: list[dict[str, Any]] = []
    if total_shares and total_shares > 0:
        for w in (round(wacc - 0.01, 3), wacc, round(wacc + 0.01, 3)):
            for tg in (round(terminal_growth - 0.005, 3), terminal_growth, round(terminal_growth + 0.005, 3)):
                if tg >= w:
                    continue
                fcf_n = fcf_base * ((1.0 + g) ** projection_years)
                tv = fcf_n * (1.0 + tg) / (w - tg)
                pv_tv = tv / ((1.0 + w) ** projection_years)
                # 重新算显性期 PV（随 wacc 变化）
                pv_exp = sum(
                    fcf_base * ((1.0 + g) ** yr) / ((1.0 + w) ** yr)
                    for yr in range(1, projection_years + 1)
                )
                ev = pv_exp + pv_tv
                eq = ev - (net_debt if net_debt is not None else 0.0)
                per_share = eq / total_shares
                sensitivity.append(
                    {
                        "wacc": round(w * 100, 2),
                        "terminal_growth": round(tg * 100, 2),
                        "intrinsic_per_share": round(per_share, 2),
                    }
                )

    return DcfResult(
        intrinsic_value_per_share=round(intrinsic_per_share, 2) if intrinsic_per_share is not None else None,
        enterprise_value=round(enterprise_value, 2) if enterprise_value is not None else None,
        equity_value=round(equity_value, 2) if equity_value is not None else None,
        net_debt=round(net_debt, 2) if net_debt is not None else None,
        fcf_base=round(fcf_base, 2),
        fcf_projection=projection,
        terminal_value=round(terminal_value, 2),
        pv_terminal=round(pv_terminal, 2),
        pv_explicit=round(pv_explicit, 2),
        current_price=round(current_price, 2) if current_price is not None else None,
        margin_of_safety_pct=round(margin_of_safety * 100, 2) if margin_of_safety is not None else None,
        upside_downside_pct=round(upside_downside * 100, 2) if upside_downside is not None else None,
        sensitivity=sensitivity,
        assumptions_used={
            "projection_years": projection_years,
            "wacc": round(wacc * 100, 2),
            "terminal_growth": round(terminal_growth * 100, 2),
            "first_stage_growth": round(g * 100, 2),
            "safety_discount": round(assumptions.safety_discount * 100, 2),
            "fcf_base_yi": round(fcf_base / _YI, 2),
        },
        notes=notes,
        revenue_cagr_used=round(revenue_cagr_used * 100, 2) if revenue_cagr_used is not None else None,
    )
