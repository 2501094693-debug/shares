"""估值分析规则引擎：四路 × 三情景，数字全部在此算出。

历史倍数窗口默认近 10 年 P25 / P50 / P75。
综合中性锚：历史 / 财报 / 收入因素 三路中性市值的中位数；
巴菲特中性只作安全边际下限，不拉高锚。
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

HISTORY_YEARS = 10
PESS_PCT = 25
MID_PCT = 50
OPT_PCT = 75
CAGR_CAP = 0.15
FUND_PESS_EARN_HAIRCUT = 0.80
DRIVER_PESS_REV = -0.15
BUFFETT_REQ = {"悲观": 0.12, "中性": 0.10, "乐观": 0.08}
BUFFETT_MOS = {"悲观": 0.70, "中性": 0.80, "乐观": 1.00}
FINANCIAL_MARKERS = ("银行", "保险", "证券", "多元金融")

SCENARIOS = ("悲观", "中性", "乐观")
PATH_ORDER = ("history", "fundamentals", "buffett", "drivers")
PATH_LABELS = {
    "history": "历史倍数",
    "fundamentals": "财报正常化",
    "buffett": "巴菲特",
    "drivers": "收入关键因素",
}


def _to_float(value: Any) -> float | None:
    if value is None or value == "" or value == "—":
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        if value != value:  # NaN
            return None
        return float(value)
    text = str(value).strip().replace(",", "").replace("%", "").replace("股", "")
    text = text.replace("倍", "").replace("x", "").replace("X", "")
    if not text or text in {"None", "nan"}:
        return None
    multiplier = 1.0
    if text.endswith("万亿"):
        multiplier = 1e12
        text = text[:-2]
    elif text.endswith("亿"):
        multiplier = 1e8
        text = text[:-1]
    elif text.endswith("万"):
        multiplier = 1e4
        text = text[:-1]
    try:
        return float(text) * multiplier
    except ValueError:
        return None


def _parse_day(value: Any) -> date | None:
    text = str(value or "")[:10]
    if len(text) < 10:
        return None
    try:
        return datetime.strptime(text, "%Y-%m-%d").date()
    except ValueError:
        return None


def percentile(vals: list[float], pct: float) -> float | None:
    xs = sorted(v for v in vals if v is not None and v == v)
    if not xs:
        return None
    if len(xs) == 1:
        return xs[0]
    rank = (len(xs) - 1) * (pct / 100.0)
    lo = int(rank)
    hi = min(lo + 1, len(xs) - 1)
    frac = rank - lo
    return xs[lo] * (1.0 - frac) + xs[hi] * frac


def median(vals: list[float | None]) -> float | None:
    xs = sorted(v for v in vals if v is not None)
    if not xs:
        return None
    mid = len(xs) // 2
    if len(xs) % 2:
        return xs[mid]
    return (xs[mid - 1] + xs[mid]) / 2.0


def cagr(first: float | None, last: float | None, years: float) -> float | None:
    if first is None or last is None or first <= 0 or last <= 0 or years <= 0:
        return None
    return (last / first) ** (1.0 / years) - 1.0


def fmt_yi(value: float | None) -> str:
    if value is None:
        return "—"
    sign = "-" if value < 0 else ""
    abs_n = abs(value)
    if abs_n >= 1e8:
        text = f"{abs_n / 1e8:.2f}".rstrip("0").rstrip(".")
        return f"{sign}{text}亿"
    if abs_n >= 1e4:
        text = f"{abs_n / 1e4:.2f}".rstrip("0").rstrip(".")
        return f"{sign}{text}万"
    text = f"{abs_n:.2f}".rstrip("0").rstrip(".")
    return f"{sign}{text}"


def fmt_num(value: float | None, digits: int = 2) -> str:
    if value is None:
        return "—"
    text = f"{value:.{digits}f}".rstrip("0").rstrip(".")
    return text if text else "0"


def fmt_pct(value: float | None, *, ratio: bool = False) -> str:
    if value is None:
        return "—"
    number = value * 100 if ratio else value
    return f"{number:.1f}%"


def fmt_mult(value: float | None) -> str:
    text = fmt_num(value, 2)
    return "—" if text == "—" else f"{text}x"


def _md_table(headers: list[str], rows: list[list[str]]) -> str:
    if not rows:
        return "（无数据）"
    lines = [
        "| " + " | ".join(headers) + " |",
        "|" + "|".join("---" for _ in headers) + "|",
    ]
    for row in rows:
        lines.append("| " + " | ".join(row) + " |")
    return "\n".join(lines)


def _scenario(
    name: str,
    *,
    mcap: float | None,
    shares: float | None,
    price: float | None,
    formula: str,
    na: str | None = None,
) -> dict[str, Any]:
    implied_price = (mcap / shares) if mcap is not None and shares else None
    upside = None
    if implied_price is not None and price:
        upside = implied_price / price - 1.0
    return {
        "name": name,
        "mcap": mcap,
        "price": implied_price,
        "upside": upside,
        "formula": formula,
        "na": na,
    }


def _empty_scenarios(reason: str) -> list[dict[str, Any]]:
    return [
        _scenario(name, mcap=None, shares=None, price=None, formula=reason, na=reason)
        for name in SCENARIOS
    ]


def _industry_text(industry: dict[str, Any] | None, stock: dict[str, Any] | None) -> str:
    industry = industry or {}
    stock = stock or {}
    parts = [
        industry.get("l1_name") or stock.get("l1_name") or "",
        industry.get("l2_name") or stock.get("l2_name") or "",
        industry.get("name") or industry.get("l3_name") or stock.get("l3_name") or "",
    ]
    return " ".join(str(p) for p in parts if p)


def is_financial(industry: dict[str, Any] | None, stock: dict[str, Any] | None) -> bool:
    blob = _industry_text(industry, stock)
    return any(marker in blob for marker in FINANCIAL_MARKERS)


def _filter_history(items: list[dict[str, Any]], years: int = HISTORY_YEARS) -> list[dict[str, Any]]:
    rows: list[tuple[date, dict[str, Any]]] = []
    for item in items or []:
        day = _parse_day(item.get("time") or item.get("date"))
        if day is None:
            continue
        rows.append((day, item))
    if not rows:
        return []
    latest = max(day for day, _ in rows)
    try:
        cutoff = latest.replace(year=latest.year - years)
    except ValueError:
        cutoff = latest - timedelta(days=365 * years + years // 4)
    return [item for day, item in rows if day >= cutoff]


def series_stats(items: list[dict[str, Any]], field: str) -> dict[str, Any]:
    vals: list[float] = []
    for item in items:
        number = _to_float(item.get(field))
        if number is not None and number > 0:
            vals.append(number)
    p25 = percentile(vals, PESS_PCT)
    p50 = percentile(vals, MID_PCT)
    p75 = percentile(vals, OPT_PCT)
    latest = _to_float(items[-1].get(field)) if items else None
    rank = None
    if latest is not None and latest > 0 and vals:
        rank = sum(1 for v in vals if v <= latest) / len(vals)
    span_days = None
    if items:
        first = _parse_day(items[0].get("time"))
        last = _parse_day(items[-1].get("time"))
        if first and last:
            span_days = abs((last - first).days)
    return {
        "count": len(vals),
        "p25": p25,
        "p50": p50,
        "p75": p75,
        "latest": latest if latest and latest > 0 else None,
        "rank": rank,
        "span_years": (span_days / 365.25) if span_days else 0.0,
        "short_sample": bool(span_days is not None and span_days < 365 * 3),
    }


def _mcap_from_profile(stock: dict[str, Any]) -> float | None:
    raw = stock.get("_mcap_raw")
    parsed = _to_float(raw)
    if parsed is not None:
        return parsed
    # 东财盘口 total_market_cap 带「亿」；market_cap 常是无单位的亿元数字。
    labeled = stock.get("total_market_cap")
    parsed = _to_float(labeled)
    if parsed is not None:
        return parsed
    bare = stock.get("market_cap")
    parsed = _to_float(bare)
    if parsed is None:
        return None
    text = str(bare).strip()
    if "亿" in text or "万" in text:
        return parsed
    if parsed < 1e6:
        return parsed * 1e8
    return parsed


def _profile_snapshot(stock: dict[str, Any]) -> dict[str, Any]:
    price = _to_float(stock.get("_price_raw") or stock.get("price"))
    mcap = _mcap_from_profile(stock)
    pe = _to_float(stock.get("pe_ttm"))
    pb = _to_float(stock.get("pb"))
    ps = _to_float(stock.get("ps_ttm"))
    shares = _to_float(
        stock.get("total_share")
        or stock.get("TOTAL_SHARE")
        or stock.get("total_shares")
    )
    if shares is None and mcap and price:
        shares = mcap / price
    if mcap is None and shares and price:
        mcap = shares * price
    ni_ttm = (mcap / pe) if mcap and pe and pe > 0 else None
    sales_ttm = (mcap / ps) if mcap and ps and ps > 0 else None
    book = (mcap / pb) if mcap and pb and pb > 0 else None
    return {
        "price": price,
        "mcap": mcap,
        "shares": shares,
        "pe_ttm": pe if pe and pe > 0 else None,
        "pb": pb if pb and pb > 0 else None,
        "ps_ttm": ps if ps and ps > 0 else None,
        "ni_ttm": ni_ttm if ni_ttm and ni_ttm > 0 else None,
        "sales_ttm": sales_ttm if sales_ttm and sales_ttm > 0 else None,
        "book": book if book and book > 0 else None,
    }


def _choose_primary(
    *,
    pe_ok: bool,
    financial: bool,
    business_type: str,
    ps_ok: bool,
    pb_ok: bool,
) -> str:
    if financial and pb_ok:
        return "PB"
    if business_type == "糟糕":
        if ps_ok:
            return "PS_TTM"
        if pb_ok:
            return "PB"
        return "PS_TTM"
    if pe_ok:
        return "PE_TTM"
    if ps_ok:
        return "PS_TTM"
    return "PB"


def _annual_rows(buffett: dict[str, Any]) -> list[dict[str, Any]]:
    metrics = (buffett or {}).get("metrics") or {}
    rows = list(metrics.get("annual_periods") or [])
    if len(rows) >= 2:
        return rows
    return list(metrics.get("periods") or [])


def _normalized_earnings(rows: list[dict[str, Any]], n: int = 5) -> dict[str, Any]:
    window = rows[:n]
    deducts = [_to_float(r.get("deduct")) for r in window]
    nis = [_to_float(r.get("a")) for r in window]
    fcfs = [_to_float(r.get("fcf")) for r in window]
    revenues = [_to_float(r.get("revenue")) for r in window]
    margins = []
    for row in window:
        ni = _to_float(row.get("deduct")) or _to_float(row.get("a"))
        rev = _to_float(row.get("revenue"))
        if ni is not None and rev and rev > 0:
            margins.append(ni / rev)
    earn_pool = [v for v in deducts if v is not None] or [v for v in nis if v is not None]
    fcf_pool = [v for v in fcfs if v is not None]
    years = max(len(window) - 1, 1)
    rev_cagr = cagr(revenues[-1] if revenues else None, revenues[0] if revenues else None, years) if len(revenues) >= 2 else None
    ni_first = next((v for v in reversed(nis) if v is not None), None)
    ni_last = next((v for v in nis if v is not None), None)
    ni_cagr = cagr(ni_first, ni_last, years) if ni_first and ni_last else None
    worst = min(earn_pool) if earn_pool else None
    return {
        "normalized_ni": median(earn_pool),
        "normalized_fcf": median(fcf_pool) if fcf_pool else None,
        "worst_ni": worst,
        "rev_cagr": rev_cagr,
        "ni_cagr": ni_cagr,
        "margin_p25": percentile(margins, PESS_PCT),
        "margin_p50": percentile(margins, MID_PCT),
        "margin_p75": percentile(margins, OPT_PCT),
        "window": len(window),
        "fcf_negative": bool(fcf_pool) and all(v is not None and v < 0 for v in fcf_pool),
    }


def _history_path(
    snap: dict[str, Any],
    stats: dict[str, dict[str, Any]],
    *,
    primary: str,
    pe_ok: bool,
) -> dict[str, Any]:
    shares = snap.get("shares")
    price = snap.get("price")
    notes: list[str] = []
    scenarios = _empty_scenarios("缺少有效倍数或基本面锚点")
    field_map = {
        "PE_TTM": ("pe_ttm", snap.get("ni_ttm"), "TTM净利润"),
        "PB": ("pb", snap.get("book"), "净资产"),
        "PS_TTM": ("ps_ttm", snap.get("sales_ttm"), "TTM营收"),
    }
    key, anchor, anchor_name = field_map[primary]
    series = stats.get(key) or {}
    if primary == "PE_TTM" and not pe_ok:
        notes.append("TTM 亏损或 PE 无效，历史 PE 路整列不适用")
        return {
            "label": PATH_LABELS["history"],
            "primary": primary,
            "scenarios": _empty_scenarios("PE 不适用"),
            "notes": notes,
            "weight": 0.0,
        }
    if not anchor or not series.get("p50"):
        notes.append(f"{primary} 缺少锚点或近10年分位")
        return {
            "label": PATH_LABELS["history"],
            "primary": primary,
            "scenarios": scenarios,
            "notes": notes,
            "weight": 0.0,
        }
    built = []
    for name, pct_key in (("悲观", "p25"), ("中性", "p50"), ("乐观", "p75")):
        multiple = series.get(pct_key)
        mcap = anchor * multiple if multiple else None
        built.append(
            _scenario(
                name,
                mcap=mcap,
                shares=shares,
                price=price,
                formula=f"{anchor_name} {fmt_yi(anchor)} × {primary} {pct_key.upper()} {fmt_mult(multiple)}",
            )
        )
    if series.get("short_sample"):
        notes.append("历史样本不足 3 年，本路在综合锚中降权")
    notes.append("本路假设基本面维持现状，只让市场倍数沿近10年分位滑动")
    weight = 0.0 if series.get("short_sample") else 1.0
    return {
        "label": PATH_LABELS["history"],
        "primary": primary,
        "scenarios": built,
        "notes": notes,
        "weight": weight,
        "stats": series,
        "anchor": anchor,
        "anchor_name": anchor_name,
    }


def _fundamentals_path(
    snap: dict[str, Any],
    stats: dict[str, dict[str, Any]],
    earned: dict[str, Any],
    *,
    primary: str,
    financial: bool,
) -> dict[str, Any]:
    shares = snap.get("shares")
    price = snap.get("price")
    notes: list[str] = []
    if financial and snap.get("book") and (stats.get("pb") or {}).get("p50"):
        book = snap["book"]
        pb = stats["pb"]
        built = []
        for name, pct_key, haircut in (
            ("悲观", "p25", 0.85),
            ("中性", "p50", 1.0),
            ("乐观", "p75", 1.05),
        ):
            multiple = pb.get(pct_key)
            mcap = book * haircut * multiple if multiple else None
            built.append(
                _scenario(
                    name,
                    mcap=mcap,
                    shares=shares,
                    price=price,
                    formula=f"净资产 {fmt_yi(book)} × {haircut:g} × PB {pct_key.upper()} {fmt_mult(multiple)}",
                )
            )
        notes.append("金融股改用 PB × 净资产，不用正常化净利润")
        return {
            "label": PATH_LABELS["fundamentals"],
            "primary": "PB",
            "scenarios": built,
            "notes": notes,
            "weight": 1.0,
            "earned": earned,
        }

    ni = earned.get("normalized_ni")
    if ni is None or ni <= 0:
        notes.append("正常化盈利无效（扣非/净利中位数非正）")
        return {
            "label": PATH_LABELS["fundamentals"],
            "primary": primary,
            "scenarios": _empty_scenarios("正常化盈利无效"),
            "notes": notes,
            "weight": 0.0,
            "earned": earned,
        }

    field = {"PE_TTM": "pe_ttm", "PB": "pb", "PS_TTM": "ps_ttm"}.get(primary, "pe_ttm")
    series = stats.get(field) or {}
    if not series.get("p50"):
        field = "ps_ttm" if (stats.get("ps_ttm") or {}).get("p50") else "pb"
        series = stats.get(field) or {}
        primary = {"ps_ttm": "PS_TTM", "pb": "PB"}.get(field, primary)
    if not series.get("p50"):
        notes.append("缺少可用退出倍数")
        return {
            "label": PATH_LABELS["fundamentals"],
            "primary": primary,
            "scenarios": _empty_scenarios("缺少退出倍数"),
            "notes": notes,
            "weight": 0.0,
            "earned": earned,
        }

    pess_earn = earned.get("worst_ni")
    if pess_earn is None or pess_earn <= 0:
        pess_earn = ni * FUND_PESS_EARN_HAIRCUT
    growth = earned.get("rev_cagr")
    if growth is None:
        growth = 0.0
    growth = max(min(growth, CAGR_CAP), 0.0)
    opt_earn = ni * (1.0 + growth)
    mapping = {
        "悲观": (pess_earn, series.get("p25"), "正常化盈利悲观"),
        "中性": (ni, series.get("p50"), "正常化盈利（扣非中位数）"),
        "乐观": (opt_earn, series.get("p75"), f"正常化盈利×(1+CAGR封顶{CAGR_CAP:.0%})"),
    }
    built = []
    for name in SCENARIOS:
        earn, multiple, label = mapping[name]
        mcap = earn * multiple if earn is not None and multiple else None
        built.append(
            _scenario(
                name,
                mcap=mcap,
                shares=shares,
                price=price,
                formula=f"{label} {fmt_yi(earn)} × {primary} {fmt_mult(multiple)}",
            )
        )
    if earned.get("fcf_negative"):
        notes.append("近窗自由现金流持续为负，本路只用利润口径，FCF 不作价")
    notes.append("退出倍数仍用近10年历史分位，盈利已按扣非中位数正常化")
    return {
        "label": PATH_LABELS["fundamentals"],
        "primary": primary,
        "scenarios": built,
        "notes": notes,
        "weight": 1.0,
        "earned": earned,
    }


def _buffett_path(
    snap: dict[str, Any],
    buffett: dict[str, Any],
    *,
    understood: bool,
) -> dict[str, Any]:
    shares = snap.get("shares")
    price = snap.get("price")
    metrics = (buffett or {}).get("metrics") or {}
    latest = metrics.get("latest") or {}
    business_type = (buffett or {}).get("business_type") or metrics.get("business_type") or "未知"
    upper = _to_float(latest.get("oe_upper"))
    lower = _to_float(latest.get("oe_lower")) if latest.get("da_disclosed") else None
    fcf = _to_float(latest.get("fcf"))
    notes: list[str] = []
    mid_oe = None
    if upper is not None and lower is not None:
        mid_oe = (upper + lower) / 2.0
    elif upper is not None:
        mid_oe = upper * 0.85
        notes.append("所有者盈余下沿未披露，中性用上沿×0.85，悲观改 OCF−capex")
    pess_oe = lower if lower is not None else fcf
    if pess_oe is None:
        notes.append("悲观所有者盈余数据不足，不得用上沿冒充下沿")
    opt_oe = upper
    if business_type in {"伟大", "优秀"} and opt_oe is not None:
        opt_oe = opt_oe * (1.05 ** 2)
        notes.append("伟大/优秀允许乐观盈余按两年 5% 增长")
    mapping = {
        "悲观": (pess_oe, BUFFETT_REQ["悲观"], BUFFETT_MOS["悲观"]),
        "中性": (mid_oe, BUFFETT_REQ["中性"], BUFFETT_MOS["中性"]),
        "乐观": (opt_oe, BUFFETT_REQ["乐观"], BUFFETT_MOS["乐观"] if business_type == "伟大" else BUFFETT_MOS["中性"]),
    }
    built = []
    for name in SCENARIOS:
        oe, req, mos = mapping[name]
        na = None
        mcap = None
        formula = f"所有者盈余 {fmt_yi(oe)} / {req:.0%} × 安全边际 {mos:.0%}"
        if name == "悲观" and lower is None and fcf is None:
            na = "下沿未披露"
            formula = na
        elif name == "乐观" and not understood:
            na = "看不懂，乐观不采用"
            formula = na
        elif name == "乐观" and business_type in {"平庸", "糟糕"} and mid_oe is not None:
            # 先算中性，乐观封顶在后面处理
            pass
        if na is None and oe is not None and oe > 0:
            mcap = oe / req * mos
        built.append(_scenario(name, mcap=mcap, shares=shares, price=price, formula=formula, na=na))

    mid_mcap = built[1].get("mcap")
    opt = built[2]
    if business_type in {"平庸", "糟糕"} and mid_mcap is not None and opt.get("mcap") is not None:
        if opt["mcap"] > mid_mcap:
            opt["mcap"] = mid_mcap
            opt["price"] = (mid_mcap / shares) if shares else None
            opt["upside"] = (opt["price"] / price - 1.0) if opt["price"] and price else None
            opt["formula"] += "；平庸/糟糕乐观不得高于中性"
            notes.append("平庸/糟糕：乐观封顶为中性")
    if not understood:
        notes.append("能力圈未确认，乐观作废；综合不得「值得进一步研究」")
    notes.append(f"生意类型（规则引擎，禁止改写）：{business_type}")
    weight = 0.0 if all(s.get("mcap") is None for s in built) else 1.0
    return {
        "label": PATH_LABELS["buffett"],
        "primary": "所有者盈余资本化",
        "scenarios": built,
        "notes": notes,
        "weight": weight,
        "business_type": business_type,
        "understood": understood,
    }


def _drivers_path(
    snap: dict[str, Any],
    stats: dict[str, dict[str, Any]],
    earned: dict[str, Any],
    *,
    primary: str,
) -> dict[str, Any]:
    shares = snap.get("shares")
    price = snap.get("price")
    sales = snap.get("sales_ttm")
    notes = [
        "因素尚未由模型点名时，用营收冲击 × 净利率分位作占位；弹性说不清的因素不得进入乘法",
        "退出倍数固定用中性分位，避免与历史倍数路重复放大乐观/悲观",
    ]
    if not sales or sales <= 0:
        return {
            "label": PATH_LABELS["drivers"],
            "primary": primary,
            "scenarios": _empty_scenarios("缺少 TTM 营收"),
            "notes": notes + ["缺少 TTM 营收"],
            "weight": 0.0,
        }
    growth = earned.get("rev_cagr") or 0.0
    opt_shock = max(min(growth, CAGR_CAP), 0.0)
    pess_shock = min(DRIVER_PESS_REV, growth if growth is not None and growth < 0 else DRIVER_PESS_REV)
    margins = {
        "悲观": earned.get("margin_p25"),
        "中性": earned.get("margin_p50"),
        "乐观": earned.get("margin_p75"),
    }
    shocks = {"悲观": pess_shock, "中性": 0.0, "乐观": opt_shock}
    pe_mid = (stats.get("pe_ttm") or {}).get("p50")
    ps_mid = (stats.get("ps_ttm") or {}).get("p50")
    use_ps = primary == "PS_TTM" or not pe_mid
    built = []
    for name in SCENARIOS:
        rev = sales * (1.0 + shocks[name])
        margin = margins.get(name)
        if use_ps or margin is None:
            multiple = ps_mid
            mcap = rev * multiple if multiple else None
            formula = f"营收 {fmt_yi(rev)}（冲击 {fmt_pct(shocks[name], ratio=True)}）× PS中性 {fmt_mult(multiple)}"
        else:
            profit = rev * margin
            mcap = profit * pe_mid if pe_mid else None
            formula = (
                f"营收 {fmt_yi(rev)} × 净利率 {fmt_pct(margin, ratio=True)} "
                f"× PE中性 {fmt_mult(pe_mid)}"
            )
        built.append(_scenario(name, mcap=mcap, shares=shares, price=price, formula=formula))
    weight = 1.0 if any(s.get("mcap") for s in built) else 0.0
    return {
        "label": PATH_LABELS["drivers"],
        "primary": "PS_TTM" if use_ps else "PE_TTM",
        "scenarios": built,
        "notes": notes,
        "weight": weight,
        "shocks": shocks,
        "margins": margins,
    }


def _path_mid(path: dict[str, Any]) -> float | None:
    for row in path.get("scenarios") or []:
        if row.get("name") == "中性":
            return row.get("mcap")
    return None


def _path_price(path: dict[str, Any], name: str) -> float | None:
    for row in path.get("scenarios") or []:
        if row.get("name") == name:
            return row.get("price")
    return None


def _composite(
    paths: dict[str, dict[str, Any]],
    snap: dict[str, Any],
    *,
    business_type: str,
    understood: bool,
) -> dict[str, Any]:
    price = snap.get("price")
    shares = snap.get("shares")
    market_mids = []
    for key in ("history", "fundamentals", "drivers"):
        path = paths.get(key) or {}
        if path.get("weight", 1) <= 0:
            continue
        mid = _path_mid(path)
        if mid is not None:
            market_mids.append(mid)
    anchor = median(market_mids)
    buffett_mid = _path_mid(paths.get("buffett") or {})
    mos_floor = buffett_mid
    notes = [
        "综合中性锚 = 历史/财报/收入因素三路中性市值的中位数，贴近历史定价带",
        "巴菲特中性只作安全边际下限，不拉高锚",
    ]
    if not market_mids:
        anchor = buffett_mid
        notes.append("三路市场定价均缺，临时用巴菲特中性")
    stance = "观望"
    valid_prices = []
    for key in PATH_ORDER:
        path = paths.get(key) or {}
        pess = _path_price(path, "悲观")
        opt = _path_price(path, "乐观")
        if pess is not None and opt is not None:
            valid_prices.append((pess, opt))
    above_opt = 0
    below_pess = 0
    if price:
        for pess, opt in valid_prices:
            if price > opt:
                above_opt += 1
            if price < pess:
                below_pess += 1
    majority = max(1, (len(valid_prices) + 1) // 2)
    if above_opt >= majority and valid_prices:
        stance = "回避" if above_opt >= max(2, majority) else "观望"
    elif (
        below_pess >= majority
        and business_type not in {"糟糕"}
        and understood
        and price
        and (mos_floor is None or shares is None or price <= mos_floor / shares)
    ):
        stance = "值得进一步研究"
    elif below_pess >= majority and price and mos_floor and shares and price > mos_floor / shares:
        notes.append("现价低于多数悲观带，但仍高于巴菲特安全边际下限，维持观望")
    elif not understood:
        notes.append("看不懂：综合不得「值得进一步研究」")
        stance = "观望"

    invalidation = "利润含金量恶化、收入关键因素方向证伪、或所有者盈余下沿持续为负时，本表作废"
    return {
        "anchor_mid_mcap": anchor,
        "anchor_mid_price": (anchor / shares) if anchor and shares else None,
        "mos_floor_mcap": mos_floor,
        "mos_floor_price": (mos_floor / shares) if mos_floor and shares else None,
        "stance": stance,
        "notes": notes,
        "invalidation": invalidation,
        "market_mid_count": len(market_mids),
    }


def _overview_table(paths: dict[str, dict[str, Any]], snap: dict[str, Any], composite: dict[str, Any]) -> str:
    headers = ["路径", "悲观市值", "中性市值", "乐观市值", "中性股价", "相对现价"]
    rows = []
    for key in PATH_ORDER:
        path = paths[key]
        by_name = {s["name"]: s for s in path.get("scenarios") or []}
        mid = by_name.get("中性") or {}
        rows.append(
            [
                path.get("label") or key,
                fmt_yi((by_name.get("悲观") or {}).get("mcap")),
                fmt_yi(mid.get("mcap")),
                fmt_yi((by_name.get("乐观") or {}).get("mcap")),
                fmt_num(mid.get("price")),
                fmt_pct(mid.get("upside"), ratio=True),
            ]
        )
    rows.append(
        [
            "综合锚（三路中性中位数）",
            "—",
            fmt_yi(composite.get("anchor_mid_mcap")),
            "—",
            fmt_num(composite.get("anchor_mid_price")),
            fmt_pct(
                (composite["anchor_mid_price"] / snap["price"] - 1.0)
                if composite.get("anchor_mid_price") and snap.get("price")
                else None,
                ratio=True,
            ),
        ]
    )
    rows.append(
        [
            "巴菲特安全边际下限",
            "—",
            fmt_yi(composite.get("mos_floor_mcap")),
            "—",
            fmt_num(composite.get("mos_floor_price")),
            fmt_pct(
                (composite["mos_floor_price"] / snap["price"] - 1.0)
                if composite.get("mos_floor_price") and snap.get("price")
                else None,
                ratio=True,
            ),
        ]
    )
    return _md_table(headers, rows)


def _path_table(path: dict[str, Any]) -> str:
    rows = []
    for row in path.get("scenarios") or []:
        rows.append(
            [
                row.get("name") or "",
                fmt_yi(row.get("mcap")),
                fmt_num(row.get("price")),
                fmt_pct(row.get("upside"), ratio=True),
                row.get("na") or row.get("formula") or "",
            ]
        )
    return _md_table(["情景", "隐含市值", "隐含股价", "相对现价", "计算公式"], rows)


def _stats_table(stats: dict[str, dict[str, Any]]) -> str:
    labels = {"pe_ttm": "PE_TTM", "pb": "PB", "ps_ttm": "PS_TTM"}
    rows = []
    for key, label in labels.items():
        series = stats.get(key) or {}
        rows.append(
            [
                label,
                str(series.get("count") or 0),
                fmt_num(series.get("span_years"), 1),
                fmt_mult(series.get("p25")),
                fmt_mult(series.get("p50")),
                fmt_mult(series.get("p75")),
                fmt_mult(series.get("latest")),
                fmt_pct(series.get("rank"), ratio=True),
            ]
        )
    return _md_table(
        ["序列", "有效点", "年数", "P25", "P50", "P75", "最新", "现处分位"],
        rows,
    )


def history_window_years(stats: dict[str, dict[str, Any]] | None) -> float:
    years = 0.0
    for series in (stats or {}).values():
        span = _to_float((series or {}).get("span_years"))
        if span and span > years:
            years = span
    return years


def history_window_label(stats: dict[str, dict[str, Any]] | None) -> str:
    years = history_window_years(stats)
    if years <= 0:
        return f"近{HISTORY_YEARS}年"
    if years >= HISTORY_YEARS - 0.5:
        return f"近{HISTORY_YEARS}年"
    return f"近{fmt_num(years, 1)}年（源数据不足{HISTORY_YEARS}年）"


def run_valuation(
    stock: dict[str, Any] | None = None,
    pe_items: list[dict[str, Any]] | None = None,
    buffett: dict[str, Any] | None = None,
    industry: dict[str, Any] | None = None,
    *,
    understood: bool = True,
) -> dict[str, Any]:
    stock = stock or {}
    buffett = buffett or {}
    snap = _profile_snapshot(stock)
    history_items = _filter_history(list(pe_items or []))
    history_items.sort(key=lambda item: str(item.get("time") or ""))
    stats = {
        "pe_ttm": series_stats(history_items, "pe_ttm"),
        "pb": series_stats(history_items, "pb"),
        "ps_ttm": series_stats(history_items, "ps_ttm"),
    }
    pe_ok = bool(snap.get("pe_ttm") and snap.get("ni_ttm"))
    financial = is_financial(industry, stock)
    business_type = buffett.get("business_type") or (buffett.get("metrics") or {}).get("business_type") or "未知"
    primary = _choose_primary(
        pe_ok=pe_ok,
        financial=financial,
        business_type=business_type,
        ps_ok=bool(snap.get("ps_ttm") and snap.get("sales_ttm")),
        pb_ok=bool(snap.get("pb") and snap.get("book")),
    )
    earned = _normalized_earnings(_annual_rows(buffett))
    paths = {
        "history": _history_path(snap, stats, primary=primary, pe_ok=pe_ok),
        "fundamentals": _fundamentals_path(snap, stats, earned, primary=primary, financial=financial),
        "buffett": _buffett_path(snap, buffett, understood=understood),
        "drivers": _drivers_path(snap, stats, earned, primary=primary),
    }
    composite = _composite(paths, snap, business_type=business_type, understood=understood)
    window_label = history_window_label(stats)
    tables = {
        "overview": _overview_table(paths, snap, composite),
        "history": _path_table(paths["history"]),
        "fundamentals": _path_table(paths["fundamentals"]),
        "buffett": _path_table(paths["buffett"]),
        "drivers": _path_table(paths["drivers"]),
        "percentiles": _stats_table(stats),
    }
    header = [
        f"- 现价 {fmt_num(snap.get('price'))} · 市值 {fmt_yi(snap.get('mcap'))} · 股本 {fmt_num(snap.get('shares'), 0)}",
        f"- 生意类型 {business_type} · 主倍数 {primary} · 金融股 {'是' if financial else '否'}",
        f"- 历史窗口{window_label}，分位 P{PESS_PCT}/P{MID_PCT}/P{OPT_PCT}",
        f"- 综合态度 **{composite.get('stance')}**（非买卖点）",
    ]
    notes = []
    for key in PATH_ORDER:
        notes.extend(f"- {PATH_LABELS[key]}：{n}" for n in (paths[key].get("notes") or []))
    notes.extend(f"- 综合：{n}" for n in (composite.get("notes") or []))
    text = "\n".join(
        [
            "### 规则引擎预计算",
            *header,
            "",
            "#### 总览",
            tables["overview"],
            "",
            f"#### {window_label}分位",
            tables["percentiles"],
            "",
            "#### 历史倍数",
            tables["history"],
            "",
            "#### 财报正常化",
            tables["fundamentals"],
            "",
            "#### 巴菲特",
            tables["buffett"],
            "",
            "#### 收入关键因素",
            tables["drivers"],
            "",
            *notes,
        ]
    )
    return {
        "snap": snap,
        "primary": primary,
        "financial": financial,
        "business_type": business_type,
        "pe_ok": pe_ok,
        "stats": stats,
        "earned": earned,
        "paths": paths,
        "composite": composite,
        "tables": tables,
        "text": text,
        "history_count": len(history_items),
        "history_window_years": history_window_years(stats),
        "history_window_label": window_label,
        "understood": understood,
    }
