"""Gauge：规则仪表盘 —— 各维度打灯 + 内在价值/安全边际。"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from agent.fundamentals_agent.fmt import fmt_num, fmt_pct, fmt_yi, md_table, median
from agent.fundamentals_agent.ledger import Ledger


Light = str  # green / yellow / red / gray


@dataclass
class DimScore:
    key: str
    label: str
    light: Light
    score: int  # 0-100
    summary: str
    flags: list[str] = field(default_factory=list)


@dataclass
class Intrinsic:
    method: str
    value: float | None
    mos: float | None  # (IV - price) / IV
    note: str


@dataclass
class Gauge:
    dims: list[DimScore] = field(default_factory=list)
    intrinsics: list[Intrinsic] = field(default_factory=list)
    anchor_iv: float | None = None
    anchor_mos: float | None = None
    stance: str = "观望"
    tables: dict[str, str] = field(default_factory=dict)
    invalidation: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "dims": [asdict(d) for d in self.dims],
            "intrinsics": [asdict(i) for i in self.intrinsics],
            "anchor_iv": self.anchor_iv,
            "anchor_mos": self.anchor_mos,
            "stance": self.stance,
            "tables": self.tables,
            "invalidation": self.invalidation,
        }


def _light(score: int) -> Light:
    if score >= 70:
        return "green"
    if score >= 40:
        return "yellow"
    if score >= 0 and score < 40:
        # 0 分也是红灯（有数据但很差）；缺数据时调用方应直接返回 gray
        return "red"
    return "gray"


def _mos(iv: float | None, price: float | None) -> float | None:
    if iv is None or not price or iv <= 0:
        return None
    return (iv - price) / iv


def _dim_trend(ledger: Ledger) -> DimScore:
    g = ledger.growth
    flags: list[str] = []
    score = 50
    rev = g.get("rev_cagr")
    ni = g.get("ni_cagr")
    op = g.get("op_cagr")
    if rev is None and ni is None:
        return DimScore("trend", "经营趋势", "gray", 0, "年报样本不足，无法判断趋势", ["缺少年报序列"])
    if rev is not None:
        if rev >= 0.10:
            score += 20
            flags.append(f"营收CAGR {fmt_pct(rev, ratio=True)} 偏强")
        elif rev >= 0.03:
            score += 8
            flags.append(f"营收CAGR {fmt_pct(rev, ratio=True)} 温和扩张")
        elif rev >= -0.03:
            flags.append(f"营收基本持平 {fmt_pct(rev, ratio=True)}")
        else:
            score -= 20
            flags.append(f"营收下滑 {fmt_pct(rev, ratio=True)}")
    if ni is not None:
        if ni >= 0.10:
            score += 15
            flags.append(f"净利CAGR {fmt_pct(ni, ratio=True)} 改善")
        elif ni < -0.05:
            score -= 25
            flags.append(f"净利下滑 {fmt_pct(ni, ratio=True)}")
        else:
            flags.append(f"净利CAGR {fmt_pct(ni, ratio=True)}")
    if rev is not None and ni is not None and rev > 0.03 and ni < -0.03:
        score -= 15
        flags.append("增收不增利")
    if op is not None and ni is not None and op > 0.05 and ni < -0.05:
        flags.append("经营利润与归母净利背离，留意非经常项")
    score = max(0, min(100, score))
    summary = "；".join(flags) if flags else "趋势中性"
    return DimScore("trend", "经营趋势", _light(score), score, summary, flags)


def _dim_profit(ledger: Ledger) -> DimScore:
    q = ledger.quality
    years = ledger.years[:5]
    flags: list[str] = []
    score = 45
    roe = q.get("roe_med")
    gm = q.get("gm_med")
    opm = q.get("opm_med")
    roa = q.get("roa_med")
    if roe is None and gm is None:
        return DimScore("profit", "盈利能力", "gray", 0, "缺少盈利能力指标", ["无ROE/毛利率"])
    if roe is not None:
        if roe >= 15:
            score += 25
            flags.append(f"ROE中位 {fmt_pct(roe)} 较高")
        elif roe >= 8:
            score += 10
            flags.append(f"ROE中位 {fmt_pct(roe)} 中等")
        else:
            score -= 20
            flags.append(f"ROE中位 {fmt_pct(roe)} 偏低")
    if gm is not None:
        if gm >= 40:
            score += 10
            flags.append(f"毛利率中位 {fmt_pct(gm)}")
        elif gm < 15:
            score -= 10
            flags.append(f"毛利率中位 {fmt_pct(gm)} 偏薄")
        else:
            flags.append(f"毛利率中位 {fmt_pct(gm)}")
    if opm is not None:
        flags.append(f"经营利润率中位 {fmt_pct(opm)}")
        if opm < 5:
            score -= 8
    if roa is not None:
        flags.append(f"ROA中位 {fmt_pct(roa)}")
    # 毛利率斜率：最近 vs 最早
    if len(years) >= 3 and years[0].gross_margin is not None and years[-1].gross_margin is not None:
        delta = years[0].gross_margin - years[-1].gross_margin
        if delta <= -3:
            score -= 10
            flags.append(f"毛利率下行约 {fmt_pct(delta)}")
        elif delta >= 3:
            score += 8
            flags.append(f"毛利率上行约 {fmt_pct(delta)}")
    score = max(0, min(100, score))
    return DimScore("profit", "盈利能力", _light(score), score, "；".join(flags) or "盈利中性", flags)


def _dim_cash(ledger: Ledger) -> DimScore:
    q = ledger.quality
    years = ledger.years[:5]
    flags: list[str] = []
    score = 50
    ocf_ni = q.get("ocf_ni_med")
    fcf_med = q.get("fcf_med")
    if ocf_ni is None and fcf_med is None and not years:
        return DimScore("cash", "现金流", "gray", 0, "缺少现金流数据", ["无OCF/FCF"])
    if ocf_ni is not None:
        if ocf_ni >= 100:
            score += 20
            flags.append(f"OCF/净利润中位 {fmt_pct(ocf_ni)}，利润现金含量好")
        elif ocf_ni >= 70:
            score += 8
            flags.append(f"OCF/净利润中位 {fmt_pct(ocf_ni)}")
        elif ocf_ni >= 40:
            score -= 10
            flags.append(f"OCF/净利润中位 {fmt_pct(ocf_ni)}，含金量偏弱")
        else:
            score -= 25
            flags.append(f"OCF/净利润中位 {fmt_pct(ocf_ni)}，利润现金支撑弱")
    fcf_vals = [y.fcf for y in years if y.fcf is not None]
    if fcf_vals:
        neg = sum(1 for v in fcf_vals if v < 0)
        if neg == len(fcf_vals):
            score -= 20
            flags.append("近样本年自由现金流持续为负")
        elif neg >= 2:
            score -= 10
            flags.append(f"自由现金流 {neg}/{len(fcf_vals)} 年为负")
        else:
            flags.append(f"FCF中位 {fmt_yi(fcf_med)}")
    latest = years[0] if years else None
    if latest and latest.ocf is not None and latest.ocf < 0:
        score -= 15
        flags.append("最近一年经营现金流为负")
    score = max(0, min(100, score))
    return DimScore("cash", "现金流", _light(score), score, "；".join(flags) or "现金流中性", flags)


def _dim_balance(ledger: Ledger) -> DimScore:
    q = ledger.quality
    years = ledger.years
    flags: list[str] = []
    score = 55
    debt = q.get("debt_latest")
    current = q.get("current_latest")
    quick = q.get("quick_latest")
    cash = q.get("cash_latest")
    if debt is None and current is None:
        return DimScore("balance", "资产负债", "gray", 0, "缺少资产负债表关键指标", ["无负债率/流动性"])
    if debt is not None:
        if debt <= 40:
            score += 15
            flags.append(f"资产负债率 {fmt_pct(debt)} 偏低")
        elif debt <= 60:
            flags.append(f"资产负债率 {fmt_pct(debt)} 适中")
        elif debt <= 75:
            score -= 15
            flags.append(f"资产负债率 {fmt_pct(debt)} 偏高")
        else:
            score -= 30
            flags.append(f"资产负债率 {fmt_pct(debt)} 很高")
    if current is not None:
        if current >= 1.5:
            score += 10
            flags.append(f"流动比率 {fmt_num(current)}x")
        elif current >= 1.0:
            flags.append(f"流动比率 {fmt_num(current)}x 勉强覆盖")
        else:
            score -= 20
            flags.append(f"流动比率 {fmt_num(current)}x，短期偿债承压")
    if quick is not None:
        flags.append(f"速动比率 {fmt_num(quick)}x")
        if quick < 0.8:
            score -= 8
    if cash is not None:
        flags.append(f"货币资金 {fmt_yi(cash)}")
    if years and years[0].short_loan and years[0].cash is not None:
        if years[0].short_loan > (years[0].cash or 0) * 1.2:
            score -= 10
            flags.append("短期借款高于货币资金，关注再融资")
    score = max(0, min(100, score))
    return DimScore("balance", "资产负债", _light(score), score, "；".join(flags) or "资产负债中性", flags)


def _dim_valuation(ledger: Ledger) -> DimScore:
    snap = ledger.snap
    hist = ledger.history
    flags: list[str] = []
    score = 50
    pe = snap.pe_ttm
    pe_med = (hist.get("pe_ttm").median if hist.get("pe_ttm") else None)
    pb = snap.pb
    pb_med = (hist.get("pb").median if hist.get("pb") else None)
    ps = snap.ps_ttm
    ps_med = (hist.get("ps_ttm").median if hist.get("ps_ttm") else None)

    def _vs(label: str, cur: float | None, med: float | None) -> None:
        nonlocal score
        if cur is None or med is None or med <= 0:
            return
        premium = cur / med - 1.0
        if premium <= -0.25:
            score += 20
            flags.append(f"{label} {fmt_num(cur)} 低于历史中位 {fmt_num(med)} 约 {fmt_pct(premium, ratio=True)}")
        elif premium <= 0.10:
            score += 5
            flags.append(f"{label} {fmt_num(cur)} 贴近历史中位 {fmt_num(med)}")
        elif premium <= 0.40:
            score -= 10
            flags.append(f"{label} {fmt_num(cur)} 高于历史中位 {fmt_num(med)} 约 {fmt_pct(premium, ratio=True)}")
        else:
            score -= 25
            flags.append(f"{label} {fmt_num(cur)} 显著高于历史中位 {fmt_num(med)}（+{fmt_pct(premium, ratio=True)}）")

    if pe is None and pb is None and ps is None:
        return DimScore("valuation", "估值位置", "gray", 0, "缺少有效估值倍数", ["PE/PB/PS 无效"])
    _vs("PE_TTM", pe, pe_med)
    _vs("PB", pb, pb_med)
    _vs("PS_TTM", ps, ps_med)
    if pe is None:
        flags.append("PE_TTM 无效（可能亏损），主看 PB/PS")
    score = max(0, min(100, score))
    return DimScore("valuation", "估值位置", _light(score), score, "；".join(flags) or "估值中性", flags)


def _intrinsics(ledger: Ledger) -> list[Intrinsic]:
    snap = ledger.snap
    price = snap.price
    mcap = snap.mcap
    pe_med = (ledger.history.get("pe_ttm").median if ledger.history.get("pe_ttm") else None)
    rows: list[Intrinsic] = []

    # A: EPS × 历史 PE 中位
    iv_a = (snap.eps * pe_med) if snap.eps and pe_med and snap.eps > 0 else None
    rows.append(
        Intrinsic(
            "历史PE锚定",
            iv_a,
            _mos(iv_a, price),
            f"EPS {fmt_num(snap.eps, 3)} × 历史PE中位 {fmt_num(pe_med)}",
        )
    )

    # B/C: 每股 FCF × 10 / 15
    latest = ledger.years[0] if ledger.years else None
    fcf = latest.fcf if latest else None
    shares = snap.shares
    fcf_ps = (fcf / shares) if fcf is not None and shares else None
    iv_b = (fcf_ps * 10) if fcf_ps is not None and fcf_ps > 0 else None
    iv_c = (fcf_ps * 15) if fcf_ps is not None and fcf_ps > 0 else None
    rows.append(
        Intrinsic(
            "FCF×10",
            iv_b,
            _mos(iv_b, price),
            f"每股FCF {fmt_num(fcf_ps, 3)} × 10（最近年报）",
        )
    )
    rows.append(
        Intrinsic(
            "FCF×15",
            iv_c,
            _mos(iv_c, price),
            f"每股FCF {fmt_num(fcf_ps, 3)} × 15（最近年报）",
        )
    )

    # D: 粗略资本化：近3年 FCF 中位 / 10% × 0.75 安全边际 → 每股
    fcf_med = median([y.fcf for y in ledger.years[:3]])
    if fcf_med is not None and fcf_med > 0 and shares:
        equity_val = fcf_med / 0.10 * 0.75
        iv_d = equity_val / shares
        rows.append(
            Intrinsic(
                "FCF资本化(10%,25%折扣)",
                iv_d,
                _mos(iv_d, price),
                f"近3年FCF中位 {fmt_yi(fcf_med)} / 10% × 75% ÷ 股本",
            )
        )
    else:
        rows.append(
            Intrinsic(
                "FCF资本化(10%,25%折扣)",
                None,
                None,
                "FCF 中位非正或缺少股本，本路不适用",
            )
        )

    # E: EV 粗算（信息项，不作股价）
    if mcap is not None and latest:
        liab = latest.total_liab or 0.0
        cash = latest.cash or 0.0
        ev = mcap + liab - cash
        rows.append(
            Intrinsic(
                "EV粗算(信息)",
                None,
                None,
                f"EV≈市值+总负债-货币资金 = {fmt_yi(ev)}（不作每股内在价值）",
            )
        )
    return rows


def _stance(anchor_mos: float | None, dims: list[DimScore]) -> str:
    quality_keys = {"trend", "profit", "cash", "balance"}
    quality = [d for d in dims if d.key in quality_keys and d.light != "gray"]
    reds = sum(1 for d in quality if d.light == "red")
    greens = sum(1 for d in quality if d.light == "green")
    if anchor_mos is None:
        return "观望"
    if reds >= 2 and anchor_mos < 0.15:
        return "回避"
    if anchor_mos >= 0.30 and greens >= 2 and reds == 0:
        return "具备安全边际"
    if anchor_mos >= 0.15 and reds <= 1:
        return "谨慎乐观"
    if anchor_mos < -0.20:
        return "偏贵"
    return "观望"


def run_gauge(ledger: Ledger) -> Gauge:
    dims = [
        _dim_trend(ledger),
        _dim_profit(ledger),
        _dim_cash(ledger),
        _dim_balance(ledger),
        _dim_valuation(ledger),
    ]
    intrinsics = _intrinsics(ledger)
    usable = [i.value for i in intrinsics if i.value is not None and i.method != "EV粗算(信息)"]
    anchor = median(usable)
    price = ledger.snap.price
    mos = _mos(anchor, price)
    stance = _stance(mos, dims)

    light_map = {"green": "绿", "yellow": "黄", "red": "红", "gray": "灰"}
    dash = md_table(
        ["维度", "灯", "分", "摘要"],
        [
            [d.label, light_map.get(d.light, d.light), str(d.score), d.summary]
            for d in dims
        ],
    )
    iv_table = md_table(
        ["方法", "内在价值/股", "安全边际", "口径"],
        [
            [
                i.method,
                fmt_num(i.value),
                fmt_pct(i.mos, ratio=True) if i.mos is not None else "—",
                i.note,
            ]
            for i in intrinsics
        ],
    )
    invalidation = [
        "利润现金含量持续恶化（OCF/净利润显著下行）",
        "毛利率或 ROE 中枢下移被新一轮年报确认",
        "自由现金流连续为负且资本开支无回报",
        "资产负债率或短期偿债指标恶化",
        "估值锚定依赖的盈利/FCF 基数失效",
    ]
    return Gauge(
        dims=dims,
        intrinsics=intrinsics,
        anchor_iv=anchor,
        anchor_mos=mos,
        stance=stance,
        tables={"dashboard": dash, "intrinsic": iv_table},
        invalidation=invalidation,
    )
