"""从东方财富拉取财务报表与估值原始数据，格式化为解读上下文。"""

from __future__ import annotations

import logging
from datetime import date
from typing import Any

from agent.config import BACKEND_ROOT

logger = logging.getLogger(__name__)


def _median(vals: list[float]) -> float:
    """本地中位数，避免 ``import statistics`` 被 ``company.statistics`` 挡住。"""
    xs = sorted(vals)
    n = len(xs)
    mid = n // 2
    return xs[mid] if n % 2 else (xs[mid - 1] + xs[mid]) / 2.0


def _backend():
    import sys

    if str(BACKEND_ROOT) not in sys.path:
        sys.path.insert(0, str(BACKEND_ROOT))
    from core.codes import normalize_code, ths_code
    from core.fmt import to_float
    from core.http import get_json

    return {
        "normalize_code": normalize_code,
        "ths_code": ths_code,
        "to_float": to_float,
        "get_json": get_json,
    }


def _fr_backend():
    import sys

    if str(BACKEND_ROOT) not in sys.path:
        sys.path.insert(0, str(BACKEND_ROOT))
    from company.news.financialreport._common import (
        date_str,
        dedupe_periods,
        index_by_date,
        is_annual,
        period_label,
        pick,
    )
    from company.news.financialreport.fetcher import get_financial_report

    return {
        "date_str": date_str,
        "dedupe_periods": dedupe_periods,
        "index_by_date": index_by_date,
        "is_annual": is_annual,
        "period_label": period_label,
        "pick": pick,
        "get_financial_report": get_financial_report,
    }


def _date(value: Any) -> str:
    return _fr_backend()["date_str"](value)


def _period_label(report_date: str, name: str = "") -> str:
    return _fr_backend()["period_label"](report_date, name)


def _is_annual(report_date: str) -> bool:
    return _fr_backend()["is_annual"](report_date)


def _fmt_yi(value: Any) -> str:
    api = _backend()
    number = api["to_float"](value)
    if number is None:
        return "—"
    sign = "-" if number < 0 else ""
    abs_n = abs(number)
    if abs_n >= 1e8:
        text = f"{abs_n / 1e8:.2f}".rstrip("0").rstrip(".")
        return f"{sign}{text}亿"
    if abs_n >= 1e4:
        text = f"{abs_n / 1e4:.2f}".rstrip("0").rstrip(".")
        return f"{sign}{text}万"
    text = f"{abs_n:.2f}".rstrip("0").rstrip(".")
    return f"{sign}{text}"


def _fmt_pct(value: Any) -> str:
    api = _backend()
    number = api["to_float"](value)
    if number is None:
        return "—"
    return f"{number:.2f}%"


def _fmt_num(value: Any, digits: int = 2) -> str:
    api = _backend()
    number = api["to_float"](value)
    if number is None:
        return "—"
    text = f"{number:.{digits}f}".rstrip("0").rstrip(".")
    return text if text else "0"


def _fmt_x(value: Any) -> str:
    text = _fmt_num(value, 2)
    return "—" if text == "—" else f"{text}x"


def _pick(row: dict[str, Any], *keys: str) -> Any:
    return _fr_backend()["pick"](row, *keys)


def _dedupe_periods(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return _fr_backend()["dedupe_periods"](rows)


def _index_by_date(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return _fr_backend()["index_by_date"](rows)


def _md_table(headers: list[str], body_rows: list[list[str]]) -> str:
    if not body_rows:
        return "（无数据）"
    lines = [
        "| " + " | ".join(headers) + " |",
        "|" + "|".join("---" for _ in headers) + "|",
    ]
    for row in body_rows:
        lines.append("| " + " | ".join(row) + " |")
    return "\n".join(lines)


def _revenue(row: dict[str, Any]) -> Any:
    return _pick(row, "TOTALOPERATEREVE", "TOTAL_OPERATE_INCOME", "OPERATE_INCOME_PK")


def _net_profit(row: dict[str, Any]) -> Any:
    return _pick(row, "PARENTNETPROFIT", "PARENT_NETPROFIT")


def _op_profit(row: dict[str, Any]) -> Any:
    return _pick(row, "OPERATE_PROFIT_PK", "OPERATE_PROFIT")


def _gross_profit(row: dict[str, Any]) -> Any:
    return _pick(row, "MLR")


def _ocf(row: dict[str, Any]) -> Any:
    return _pick(row, "NETCASH_OPERATE_PK", "NETCASH_OPERATE")


def _capex(row: dict[str, Any]) -> Any:
    return _pick(row, "CONSTRUCT_LONG_ASSET")


def _fcf(row: dict[str, Any]) -> Any:
    api = _backend()
    direct = api["to_float"](_pick(row, "FCFF_BACK", "FCFF_FORWARD"))
    if direct is not None:
        return direct
    ocf = api["to_float"](_ocf(row))
    capex = api["to_float"](_capex(row))
    if ocf is None:
        return None
    if capex is None:
        return ocf
    return ocf - capex


def _liq_ratio(row: dict[str, Any], *keys: str) -> Any:
    api = _backend()
    number = api["to_float"](_pick(row, *keys))
    if number is None:
        return None
    # 东财部分接口把流动比率写成百分数（558 ≈ 5.58）
    if number > 50:
        return number / 100
    return number


def _op_margin(row: dict[str, Any]) -> Any:
    api = _backend()
    op = api["to_float"](_op_profit(row))
    rev = api["to_float"](_revenue(row))
    if op is not None and rev:
        return op / rev * 100
    return api["to_float"](_pick(row, "OPERATE_PROFIT_RATIO"))


def _roa(row: dict[str, Any]) -> Any:
    api = _backend()
    direct = api["to_float"](_pick(row, "ZZCJLL"))
    if direct is not None:
        return direct
    profit = api["to_float"](_net_profit(row))
    assets = api["to_float"](_pick(row, "TOTAL_ASSETS_PK", "TOTAL_ASSETS"))
    if profit is not None and assets:
        return profit / assets * 100
    return None


def _trend_table(rows: list[dict[str, Any]]) -> str:
    headers = ["报告期", "营业总收入", "同比", "营业利润", "归母净利润", "同比", "扣非净利润"]
    body = []
    for row in rows:
        body.append(
            [
                str(row.get("PERIOD_LABEL") or _period_label(str(row.get("REPORT_DATE") or ""))),
                _fmt_yi(_revenue(row)),
                _fmt_pct(_pick(row, "TOTALOPERATEREVETZ", "TOI_RATIO")),
                _fmt_yi(_op_profit(row)),
                _fmt_yi(_net_profit(row)),
                _fmt_pct(_pick(row, "PARENTNETPROFITTZ", "PARENT_NETPROFIT_RATIO")),
                _fmt_yi(_pick(row, "KCFJCXSYJLR", "DEDUCT_PARENT_NETPROFIT")),
            ]
        )
    return _md_table(headers, body)


def _profitability_table(rows: list[dict[str, Any]]) -> str:
    headers = ["报告期", "毛利率", "净利率", "经营利润率", "ROE", "ROA", "ROIC", "EPS"]
    body = []
    for row in rows:
        body.append(
            [
                str(row.get("PERIOD_LABEL") or ""),
                _fmt_pct(_pick(row, "XSMLL")),
                _fmt_pct(_pick(row, "XSJLL")),
                _fmt_pct(_op_margin(row)),
                _fmt_pct(_pick(row, "ROEJQ", "WEIGHTAVG_ROE")),
                _fmt_pct(_roa(row)),
                _fmt_pct(_pick(row, "ROIC")),
                _fmt_num(_pick(row, "EPSJB", "BASIC_EPS"), 3),
            ]
        )
    return _md_table(headers, body)


def _cashflow_table(rows: list[dict[str, Any]]) -> str:
    headers = ["报告期", "经营现金流", "资本开支", "自由现金流(FCFF)", "经营现金流/净利润", "每股经营现金流"]
    body = []
    api = _backend()
    for row in rows:
        ocf = api["to_float"](_ocf(row))
        profit = api["to_float"](_net_profit(row))
        ratio = (ocf / profit * 100) if ocf is not None and profit else None
        nco_ratio = api["to_float"](_pick(row, "NCO_NETPROFIT"))
        body.append(
            [
                str(row.get("PERIOD_LABEL") or ""),
                _fmt_yi(_ocf(row)),
                _fmt_yi(_capex(row)),
                _fmt_yi(_fcf(row)),
                _fmt_pct(nco_ratio * 100 if nco_ratio is not None and nco_ratio < 5 else nco_ratio)
                if nco_ratio is not None
                else _fmt_pct(ratio),
                _fmt_num(_pick(row, "MGJYXJJE"), 3),
            ]
        )
    return _md_table(headers, body)


def _balance_table(rows: list[dict[str, Any]]) -> str:
    headers = [
        "报告期",
        "货币资金",
        "总资产",
        "总负债",
        "净资产",
        "资产负债率",
        "流动比率",
        "速动比率",
        "短期借款",
        "存货",
        "应收",
    ]
    body = []
    for row in rows:
        body.append(
            [
                str(row.get("PERIOD_LABEL") or ""),
                _fmt_yi(_pick(row, "MONETARYFUNDS")),
                _fmt_yi(_pick(row, "TOTAL_ASSETS_PK", "TOTAL_ASSETS")),
                _fmt_yi(_pick(row, "LIABILITY", "TOTAL_LIABILITIES")),
                _fmt_yi(_pick(row, "TOTAL_EQUITY_PK", "TOTAL_EQUITY")),
                _fmt_pct(_pick(row, "ZCFZL", "DEBT_ASSET_RATIO")),
                _fmt_x(_liq_ratio(row, "LD", "CURRENT_RATIO")),
                _fmt_x(_liq_ratio(row, "SD")),
                _fmt_yi(_pick(row, "SHORT_LOAN")),
                _fmt_yi(_pick(row, "INVENTORY")),
                _fmt_yi(_pick(row, "ACCOUNTS_RECE")),
            ]
        )
    return _md_table(headers, body)


def _income_raw_table(rows: list[dict[str, Any]]) -> str:
    headers = [
        "报告期",
        "营业总收入",
        "营业成本",
        "销售费用",
        "管理费用",
        "财务费用",
        "营业利润",
        "利润总额",
        "所得税",
        "归母净利润",
    ]
    body = []
    for row in rows:
        body.append(
            [
                str(row.get("PERIOD_LABEL") or ""),
                _fmt_yi(_revenue(row)),
                _fmt_yi(_pick(row, "OPERATE_COST", "OPERATE_EXPENSE")),
                _fmt_yi(_pick(row, "SALE_EXPENSE")),
                _fmt_yi(_pick(row, "MANAGE_EXPENSE")),
                _fmt_yi(_pick(row, "FINANCE_EXPENSE")),
                _fmt_yi(_op_profit(row)),
                _fmt_yi(_pick(row, "TOTAL_PROFIT")),
                _fmt_yi(_pick(row, "INCOME_TAX")),
                _fmt_yi(_net_profit(row)),
            ]
        )
    return _md_table(headers, body)


def _cash_raw_table(rows: list[dict[str, Any]]) -> str:
    headers = ["报告期", "销售商品收现", "经营现金流", "投资现金流", "筹资现金流", "购建固定资产", "现金净增加"]
    body = []
    for row in rows:
        body.append(
            [
                str(row.get("PERIOD_LABEL") or ""),
                _fmt_yi(_pick(row, "SALES_SERVICES")),
                _fmt_yi(_ocf(row)),
                _fmt_yi(_pick(row, "NETCASH_INVEST_PK", "NETCASH_INVEST")),
                _fmt_yi(_pick(row, "NETCASH_FINANCE_PK", "NETCASH_FINANCE")),
                _fmt_yi(_capex(row)),
                _fmt_yi(_pick(row, "CCE_ADD")),
            ]
        )
    return _md_table(headers, body)


def _rel_diff(a: Any, b: Any) -> float | None:
    api = _backend()
    x, y = api["to_float"](a), api["to_float"](b)
    if x is None or y is None:
        return None
    denom = max(abs(x), abs(y), 1e-9)
    return abs(x - y) / denom * 100


def _cross_validate(rows: list[dict[str, Any]], income_rows: list[dict[str, Any]], lico_rows: list[dict[str, Any]]) -> str:
    latest = rows[0] if rows else {}
    day = str(latest.get("REPORT_DATE") or "")
    income_map = _index_by_date(_dedupe_periods(income_rows))
    lico_map = _index_by_date(_dedupe_periods(lico_rows))
    income = income_map.get(day) or {}
    lico = lico_map.get(day) or {}

    checks = [
        ("营业总收入", _revenue(latest), _pick(income, "TOTAL_OPERATE_INCOME"), _pick(lico, "TOTAL_OPERATE_INCOME")),
        ("归母净利润", _net_profit(latest), _pick(income, "PARENT_NETPROFIT"), _pick(lico, "PARENT_NETPROFIT")),
        ("营业利润", _op_profit(latest), _pick(income, "OPERATE_PROFIT"), None),
    ]
    body = []
    for label, main_v, income_v, lico_v in checks:
        d1 = _rel_diff(main_v, income_v)
        d2 = _rel_diff(main_v, lico_v)
        flag = "⚠ 偏差>1%" if any(d is not None and d > 1 for d in (d1, d2)) else "通过"
        body.append(
            [
                label,
                _fmt_yi(main_v),
                _fmt_yi(income_v),
                _fmt_yi(lico_v),
                flag,
            ]
        )
    note = f"对比报告期：{_period_label(day, str(latest.get('PERIOD_LABEL') or ''))}。来源：东财主要指标 / 利润表 / 业绩报表。"
    return note + "\n\n" + _md_table(["指标", "主要指标", "利润表", "业绩报表", "校验"], body)


def format_profile_table(stock: dict[str, Any], industry: dict[str, Any]) -> str:
    keys = [
        ("最新价", "price"),
        ("涨跌幅", "change_1d"),
        ("总市值", "total_market_cap"),
        ("市盈率TTM", "pe_ttm"),
        ("市盈率(动)", "pe"),
        ("市盈率(静)", "pe_static"),
        ("市净率", "pb"),
        ("市销率TTM", "ps_ttm"),
        ("ROE", "roe"),
        ("毛利率", "gross_margin"),
        ("净利率", "net_margin"),
        ("每股收益", "eps"),
        ("每股净资产", "bvps"),
        ("总股本", "total_shares"),
        ("股息率", "dividend_yield"),
    ]
    body = []
    seen_labels: set[str] = set()
    for label, key in keys:
        if label in seen_labels:
            continue
        val = stock.get(key)
        if val in (None, "", "-") and key == "change_1d":
            val = stock.get("change_pct")
        if val not in (None, "", "-"):
            body.append([label, str(val)])
            seen_labels.add(label)
    if industry:
        body.append(
            [
                "申万行业",
                " / ".join(
                    x
                    for x in (
                        industry.get("l1_name") or stock.get("l1_name") or "",
                        industry.get("l2_name") or stock.get("l2_name") or "",
                        industry.get("name") or stock.get("l3_name") or "",
                    )
                    if x
                )
                or "—",
            ]
        )
    return _md_table(["指标", "数值"], body)


def _pe_summary(items: list[dict[str, Any]]) -> str:
    if not items:
        return "（未能获取历史估值序列）"

    def _stats(field: str) -> str:
        vals = []
        api = _backend()
        for item in items:
            n = api["to_float"](item.get(field))
            if n is not None and n > 0:
                vals.append(n)
        if not vals:
            return "—"
        return (
            f"中位 {_fmt_num(_median(vals))} / "
            f"最低 {_fmt_num(min(vals))} / "
            f"最高 {_fmt_num(max(vals))}"
        )

    by_year: dict[str, list[dict[str, Any]]] = {}
    for item in items:
        year = str(item.get("time") or "")[:4]
        if year:
            by_year.setdefault(year, []).append(item)

    year_rows = []
    api = _backend()
    for year in sorted(by_year, reverse=True)[:6]:
        rows = by_year[year]
        pe_vals = [api["to_float"](r.get("pe_ttm")) for r in rows]
        pb_vals = [api["to_float"](r.get("pb")) for r in rows]
        ps_vals = [api["to_float"](r.get("ps_ttm")) for r in rows]
        pe_vals = [v for v in pe_vals if v and v > 0]
        pb_vals = [v for v in pb_vals if v and v > 0]
        ps_vals = [v for v in ps_vals if v and v > 0]
        year_rows.append(
            [
                year,
                _fmt_num(_median(pe_vals)) if pe_vals else "—",
                _fmt_num(_median(pb_vals)) if pb_vals else "—",
                _fmt_num(_median(ps_vals)) if ps_vals else "—",
            ]
        )

    latest = items[-1]
    latest_line = (
        f"最近交易日 {latest.get('time', '')}：收盘 {_fmt_num(latest.get('close'))}，"
        f"PE_TTM {_fmt_num(latest.get('pe_ttm'))}，"
        f"PB {_fmt_num(latest.get('pb'))}，"
        f"PS_TTM {_fmt_num(latest.get('ps_ttm'))}"
    )
    return (
        f"{latest_line}\n\n"
        f"全样本（约 {len(items)} 个交易日）：\n"
        f"- PE_TTM：{_stats('pe_ttm')}\n"
        f"- PB：{_stats('pb')}\n"
        f"- PS_TTM：{_stats('ps_ttm')}\n\n"
        + _md_table(["年份", "PE_TTM中位", "PB中位", "PS_TTM中位"], year_rows)
    )


def _peer_table(code: str, name: str) -> str:
    try:
        import sys

        if str(BACKEND_ROOT) not in sys.path:
            sys.path.insert(0, str(BACKEND_ROOT))
        from industry.service import service as industry
    except Exception as exc:  # noqa: BLE001
        return f"（未能加载行业成分股：{exc}）"

    try:
        industry.stocks.ensure_populated()
        hit = industry.stocks.get_by_code(code)
        if not hit:
            return "（索引中未找到该公司，无法做同业对比）"
        l3_code = str(hit.get("l3_code") or "").strip()
        l3_name = str(hit.get("l3_name") or "")
        if not l3_code:
            return "（缺少申万三级行业代码，无法做同业对比）"
        pack = industry.get_constituents(l3_code, force_refresh=False, update_index=False)
        stocks = [s for s in (pack.get("stocks") or []) if isinstance(s, dict)]
    except Exception as exc:  # noqa: BLE001
        logger.warning("同业对比失败 %s: %s", code, exc)
        return f"（同业对比失败：{exc}）"

    api = _backend()
    self_code = api["normalize_code"](code)
    peers = []
    for stock in stocks:
        scode = api["normalize_code"](str(stock.get("code") or ""))
        if not scode or scode == self_code:
            continue
        mcap = api["to_float"](stock.get("market_cap"))
        peers.append((mcap or 0, stock))
    peers.sort(key=lambda x: x[0], reverse=True)
    top = [s for _, s in peers[:8]]

    body = [
        [
            name,
            code,
            str(hit.get("pe_ttm") or hit.get("pe") or "—"),
            str(hit.get("pb") or "—"),
            str(hit.get("roe") or "—"),
            str(hit.get("market_cap") or "—"),
            "本公司",
        ]
    ]
    for stock in top:
        body.append(
            [
                str(stock.get("name") or ""),
                str(stock.get("code") or ""),
                str(stock.get("pe_ttm") or stock.get("pe") or "—"),
                str(stock.get("pb") or "—"),
                str(stock.get("roe") or "—"),
                str(stock.get("market_cap") or "—"),
                "同业",
            ]
        )
    header = f"申万三级行业：{l3_name or l3_code}（成分股 {len(stocks)} 家，下表为市值靠前的对照）\n\n"
    return header + _md_table(["公司", "代码", "PE", "PB", "ROE", "市值", "标记"], body)


def _valuation_helpers(stock: dict[str, Any], annual: list[dict[str, Any]], pe_items: list[dict[str, Any]]) -> str:
    api = _backend()
    price = api["to_float"](stock.get("price") or stock.get("_price_raw"))
    pe = api["to_float"](stock.get("pe_ttm"))
    pb = api["to_float"](stock.get("pb"))
    ps = api["to_float"](stock.get("ps_ttm"))
    mcap = api["to_float"](stock.get("_mcap_raw"))
    if mcap is None:
        cap_text = str(stock.get("market_cap") or "")
        cap_n = api["to_float"](cap_text.replace("亿", ""))
        if cap_n is not None:
            mcap = cap_n * 1e8
    eps = api["to_float"](stock.get("eps"))
    if (eps is None or eps <= 0) and price and pe and pe > 0:
        eps = price / pe

    latest_annual = annual[0] if annual else {}
    fcf = api["to_float"](_fcf(latest_annual)) if latest_annual else None
    shares = api["to_float"](_pick(latest_annual, "TOTAL_SHARE", "A_FREE_SHARE")) if latest_annual else None
    fcf_ps = (fcf / shares) if fcf is not None and shares else None

    cash = api["to_float"](_pick(latest_annual, "MONETARYFUNDS")) if latest_annual else None
    liab = api["to_float"](_pick(latest_annual, "LIABILITY", "TOTAL_LIABILITIES")) if latest_annual else None
    ev = None
    if mcap is not None:
        ev = mcap + (liab or 0) - (cash or 0)

    pe_vals = [api["to_float"](x.get("pe_ttm")) for x in pe_items]
    pe_vals = [v for v in pe_vals if v and v > 0]
    pe_med = _median(pe_vals) if pe_vals else None

    iv_pe = (eps * pe_med) if eps and pe_med else None
    iv_fcf_10 = (fcf_ps * 10) if fcf_ps else None
    iv_fcf_15 = (fcf_ps * 15) if fcf_ps else None
    fcf_yield = (fcf / mcap * 100) if fcf is not None and mcap else None
    earn_yield = (100 / pe) if pe and pe > 0 else None

    def _mos(iv: Any) -> str:
        if iv is None or not price:
            return "—"
        return _fmt_pct((iv - price) / iv * 100)

    lines = [
        "| 估算项 | 数值 | 口径 |",
        "|--------|------|------|",
        f"| 当前股价 | {_fmt_num(price)} | 东财盘口 |",
        f"| 总市值 | {_fmt_yi(mcap)} | 股价×总股本 |",
        f"| EV（粗算） | {_fmt_yi(ev)} | 市值+总负债-货币资金 |",
        f"| PE_TTM | {_fmt_num(pe)} | 盘口 |",
        f"| PB | {_fmt_num(pb)} | 盘口 |",
        f"| PS_TTM | {_fmt_num(ps)} | 盘口 |",
        f"| 盈利收益率 | {_fmt_pct(earn_yield)} | 1/PE_TTM |",
        f"| FCF Yield | {_fmt_pct(fcf_yield)} | 最近年报FCF/市值 |",
        f"| 历史PE中位 | {_fmt_num(pe_med)} | 东财日频估值序列 |",
        f"| 内在价值A | {_fmt_num(iv_pe)} | EPS×历史PE中位 |",
        f"| 安全边际A | {_mos(iv_pe)} | (IV-股价)/IV |",
        f"| 内在价值B | {_fmt_num(iv_fcf_10)} | 每股FCF×10 |",
        f"| 内在价值C | {_fmt_num(iv_fcf_15)} | 每股FCF×15 |",
        f"| 安全边际B | {_mos(iv_fcf_10)} | 对应FCF×10 |",
    ]
    lines.append("")
    lines.append(
        "以上为程序预计算的参考区间，不是最终投资结论。"
        "解读时须说明假设，并与历史估值、同业对照后给出巴菲特式安全边际判断。"
    )
    return "\n".join(lines)


def fetch_financial_pack(code: str, name: str) -> dict[str, Any]:
    """拉取并格式化财务/估值原始数据包。"""
    pack = _fr_backend()["get_financial_report"](code, scope="all", limit=24)
    statements = pack.get("statements") or {}
    main_rows = statements.get("main") or []
    income_rows = statements.get("income") or []
    lico_rows = statements.get("lico") or []
    merged = pack.get("merged") or []
    annual = pack.get("annual") or []
    recent = pack.get("recent") or []
    today = date.today().isoformat()

    sections: dict[str, str] = {}
    errors: list[str] = []
    if not merged:
        errors.append("未能获取东方财富财务报表")
        return {
            "sections": sections,
            "text": "（未能获取财务报表原始数据）",
            "sources": [],
            "errors": errors,
            "annual": [],
            "recent": [],
            "merged": [],
        }

    note = (
        f"> 数据截止 {today}。金额单位已折算；利润表/现金流量表为**报告期累计数**"
        f"（中报=上半年，三季报=前三季度，年报=全年），不是单季度。\n"
        f"> 来源：东方财富 F10 主要指标 / 利润表 / 资产负债表 / 现金流量表 / 业绩报表。\n"
    )
    sections["近3-5年年报趋势（原始数据）"] = _trend_table(annual)
    sections["近一年各报告期利润表（原始科目）"] = _income_raw_table(recent)
    sections["盈利能力指标（原始数据）"] = _profitability_table(annual or recent)
    sections["现金流（原始数据）"] = (
        _cashflow_table(annual or recent)
        + "\n\n> 自由现金流优先取东财 `FCFF_BACK`；缺省时用经营现金流 − 购建固定资产。"
    )
    sections["近一年现金流量表（原始科目）"] = _cash_raw_table(recent)
    sections["资产负债表健康度（原始数据）"] = _balance_table(annual[:5] or recent)
    sections["数据交叉验证"] = _cross_validate(merged, income_rows, lico_rows)

    parts = [note]
    for title, body in sections.items():
        parts.append(f"### {title}\n{body}")
    return {
        "sections": sections,
        "text": "\n\n".join(parts),
        "sources": ["东方财富 F10 财务报表", "东方财富业绩报表"],
        "errors": errors,
        "annual": annual,
        "recent": recent,
        "merged": merged,
    }


def fetch_valuation_pack(code: str, name: str, stock: dict[str, Any], industry: dict[str, Any]) -> dict[str, Any]:
    """盘口估值 + 历史分位 + 同业对比 + 安全边际预计算。"""
    pe_items: list[dict[str, Any]] = []
    try:
        import sys

        if str(BACKEND_ROOT) not in sys.path:
            sys.path.insert(0, str(BACKEND_ROOT))
        from company.statistics.pe_history import fetch_pe_history

        pack = fetch_pe_history(code, limit=1200)
        pe_items = list(pack.get("items") or []) if isinstance(pack, dict) else []
    except Exception as exc:  # noqa: BLE001
        logger.warning("历史估值失败 %s: %s", code, exc)

    sections = {
        "当前估值与盘口（原始数据）": format_profile_table(stock, industry),
        "历史估值（东财日频，原始序列摘要）": _pe_summary(pe_items),
        "同业估值对比（申万三级）": _peer_table(code, name),
    }
    return {
        "sections": sections,
        "pe_items": pe_items,
        "sources": ["东方财富盘口", "东财估值分析明细", "申万行业成分股"],
        "text": "\n\n".join(f"### {title}\n{body}" for title, body in sections.items()),
    }


def build_valuation_helpers(stock: dict[str, Any], annual: list[dict[str, Any]], pe_items: list[dict[str, Any]]) -> str:
    return _valuation_helpers(stock, annual, pe_items)
