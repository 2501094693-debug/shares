"""数据接入：日线用 company.line.fetcher.fetch_kline，总股本用 quote/fetch/free_float.calc。"""
from __future__ import annotations
from company.line.fetcher import fetch_kline
from company.statistics.quote.fetch.free_float import calc as free_float_calc
from analysis.select.jetton.core import run_jetton, summarize_from_H

def load_daily(symbol: str, start: str, end: str) -> list[dict]:
    s, e = start.replace("-", ""), end.replace("-", "")
    pack = fetch_kline(symbol, period="day", adjust="qfq", limit=10000, beg=s, end=e)
    rows = []
    for b in pack.get("items") or []:
        d = str(b.get("time") or "")[:10]
        if not d or d < start[:10] or d > end[:10]:
            continue
        try:
            rows.append({"date": d, "open": float(b["open"]), "high": float(b["high"]),
                         "low": float(b["low"]), "close": float(b["close"]),
                         "volume": float(b.get("volume") or 0)})
        except (TypeError, ValueError):
            continue
    rows.sort(key=lambda r: r["date"])
    return rows

def load_total(symbol: str, which: str = "free") -> float:
    d = free_float_calc(symbol)
    v = d.get("free_float_shares") if which == "free" else d.get("total_shares")
    if not v:
        v = d.get("float_shares") or d.get("total_shares")
    if not v:
        raise ValueError(f"{symbol} 取不到股本数据")
    return float(v)

def run_symbol(symbol: str, start: str, end: str, TOTAL: float | None = None, **kw) -> dict:
    rows = load_daily(symbol, start, end)
    if not rows:
        raise ValueError(f"{symbol} 在 {start}~{end} 无日线")
    if TOTAL is None:
        TOTAL = load_total(symbol)
    out = run_jetton(rows, TOTAL, **kw)
    out["symbol"] = symbol
    out["stats"] = summarize_from_H(out["H"], out["centers"], out.get("close"))
    out["TOTAL"] = TOTAL
    return out
