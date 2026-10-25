"""按参数批量分析并按结果筛选股票。

流程：单只 -> 跑启用的模块 -> 汇总指标 -> 按 FilterParams 过滤 -> 排序返回。
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import Any

from company.analysis.line.jetton.service import run_symbol as run_jetton_symbol
from analysis.select.params import SelectParams
from analysis.select.price.service import price_position


def analyze_one(symbol: str, params: SelectParams) -> dict[str, Any]:
    """对单只股票跑启用的分析，返回原始结果 + 扁平指标。"""
    params.validate()
    out: dict[str, Any] = {"symbol": symbol, "metrics": {}, "pass": True, "reasons": []}
    if params.price.enabled:
        try:
            r = price_position(symbol, params.price.start, params.price.end, params.price.target, params.price.order)
            res = r.get("result") or {}
            out["price"] = {"result": res, "target": r.get("target"), "N": r.get("N")}
            for k in ("open", "high", "low", "close"):
                if isinstance(res.get(k), dict):
                    out["metrics"][f"price_{k}_pct"] = res[k].get("percent")
        except Exception as exc:  # noqa: BLE001
            out["price_error"] = str(exc)
    if params.jetton.enabled:
        try:
            r = run_jetton_symbol(
                symbol, params.jetton.start, params.jetton.end,
                f_mode=params.jetton.f_mode, k_kind=params.jetton.k_kind,
                seed=params.jetton.seed, base=params.jetton.base, width=params.jetton.width,
            )
            st = r.get("stats") or {}
            out["jetton"] = {"stats": st}
            out["metrics"]["profit_ratio"] = st.get("profit_ratio")
            out["metrics"]["conc70"] = st.get("conc70")
            out["metrics"]["avg_cost"] = st.get("avg_cost")
        except Exception as exc:  # noqa: BLE001
            out["jetton_error"] = str(exc)
    passed, reasons = match_filters(out["metrics"], params)
    out["pass"] = passed
    out["reasons"] = reasons
    return out


def match_filters(metrics: dict[str, Any], params: SelectParams) -> tuple[bool, list[str]]:
    """按 FilterParams 检查扁平指标，返回 (是否通过, 未通过原因)。"""
    f = params.filters
    reasons: list[str] = []

    def _num(v: Any) -> float | None:
        try:
            return float(v) if v is not None else None
        except (TypeError, ValueError):
            return None

    for k, lo in (f.price_percent_min or {}).items():
        v = _num(metrics.get(f"price_{k}_pct"))
        if v is not None and v < float(lo):
            reasons.append(f"{k}分位{v}低于{lo}")
    for k, hi in (f.price_percent_max or {}).items():
        v = _num(metrics.get(f"price_{k}_pct"))
        if v is not None and v > float(hi):
            reasons.append(f"{k}分位{v}高于{hi}")
    pr = _num(metrics.get("profit_ratio"))
    if pr is not None:
        if f.profit_ratio_min is not None and pr < f.profit_ratio_min:
            reasons.append(f"获利盘{pr}低于{f.profit_ratio_min}")
        if f.profit_ratio_max is not None and pr > f.profit_ratio_max:
            reasons.append(f"获利盘{pr}高于{f.profit_ratio_max}")
    c70 = _num(metrics.get("conc70"))
    if c70 is not None and f.conc70_max is not None and c70 > f.conc70_max:
        reasons.append(f"集中度{c70}高于{f.conc70_max}")
    return (not reasons, reasons)


def screen_stocks(symbols: list[str], params: SelectParams | dict) -> dict[str, Any]:
    """批量分析 + 筛选，返回通过/未通过两组。"""
    if isinstance(params, dict):
        params = SelectParams.from_dict(params)
    params.validate()
    symbols = [str(s).strip() for s in (symbols or []) if str(s).strip()]
    workers = max(1, min(int(params.max_workers), 32))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        rows = list(pool.map(lambda s: analyze_one(s, params), symbols))
    passed = [r for r in rows if r.get("pass")]
    failed = [r for r in rows if not r.get("pass")]
    return {
        "params": params.to_dict(),
        "total": len(rows),
        "passed": passed,
        "failed": failed,
        "passed_symbols": [r["symbol"] for r in passed],
    }
