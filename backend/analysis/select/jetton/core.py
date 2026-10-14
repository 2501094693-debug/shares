"""迭代引擎：H = Hold + Add，保证 sum(H) < TOTAL。S_min = Hsum + V - TOTAL。"""
from __future__ import annotations
import numpy as np
from analysis.select.jetton.distributions import build_k, shape_weights

def resolve_tick(rows: list[dict], tick: float | None = None, rel: float = 0.001,
                min_tick: float = 0.01) -> float:
    if tick is not None:
        if tick <= 0:
            raise ValueError("tick 最小价格步长须 > 0")
        return float(tick)
    anchor = float(rows[0].get("close", rows[0]["low"]))
    if anchor <= 0:
        anchor = float(np.median([float(r["close"]) for r in rows]))
    auto = max(min_tick, anchor * rel)
    return float(max(min_tick, round(auto / min_tick) * min_tick))

def make_axis(rows: list[dict], tick: float | None = None, rel: float = 0.001,
              min_tick: float = 0.01):
    tick = resolve_tick(rows, tick, rel, min_tick)
    lo = min(float(r["low"]) for r in rows)
    hi = max(float(r["high"]) for r in rows)
    if hi <= lo:
        hi = lo + tick
    lo = float(np.floor(lo / tick) * tick)
    hi = float(np.ceil(hi / tick) * tick)
    if hi <= lo:
        hi = lo + tick
    edges = np.arange(lo, hi + tick * 0.5, tick, dtype=float)
    edges = np.round(edges, 10)
    if len(edges) < 2:
        edges = np.array([lo, lo + tick], dtype=float)
    return edges, (edges[:-1] + edges[1:]) / 2.0

def _alloc_shape_preserving(w: np.ndarray, cap: np.ndarray, S: float, dt) -> np.ndarray:
    wsum = float(w.sum())
    if wsum <= 0 or S <= 0:
        return np.zeros_like(cap)
    S = min(S, float(cap.sum()))
    alpha = S / wsum
    T = alpha * w
    capped = T >= cap
    if not bool(capped.any()):
        return T.astype(dt, copy=False)
    lo_a, hi_a = alpha, alpha
    while float(np.minimum(hi_a * w, cap).sum()) < S:
        hi_a *= 2.0
        if hi_a > 1e18:
            break
    for _ in range(60):
        mid = (lo_a + hi_a) / 2.0
        if float(np.minimum(mid * w, cap).sum()) < S:
            lo_a = mid
        else:
            hi_a = mid
    return np.minimum(hi_a * w, cap).astype(dt, copy=False)

def settle(H_prev: np.ndarray, V: float, TOTAL: float, f: np.ndarray, k: np.ndarray):
    dt = H_prev.dtype
    fsum = float(f.sum())
    Add = (f / fsum * V).astype(dt, copy=False) if fsum > 0 else np.zeros_like(H_prev)
    kc = np.clip(k, 0, 1)
    S_want = float((H_prev * kc).sum())
    Hsum = float(H_prev.sum())
    S_min = max(0.0, Hsum + V - TOTAL + 1)
    S = float(min(max(S_want, S_min), Hsum))
    w = H_prev * np.maximum(k, 0)
    if S <= 0:
        T = np.zeros_like(H_prev)
    elif float(w.sum()) > 0:
        T = _alloc_shape_preserving(w, H_prev, S, dt)
    elif Hsum > 0:
        T = _alloc_shape_preserving(H_prev, H_prev, S, dt)
    else:
        T = np.zeros_like(H_prev)
    Hold = (H_prev - T).astype(dt, copy=False)
    H = (Hold + Add).astype(dt, copy=False)
    return Hold, Add, T, H, S

def run_jetton(rows: list[dict], TOTAL: float, tick: float | None = None, bins: int | None = None,
               rel: float = 0.001, min_tick: float = 0.01, seed: str = "triangle",
               f_mode: str = "triangle", k_kind: str = "flat",
               base: float = 0.05, width: float = 0.02,
               return_history: bool = False, keep_every: int = 1,
               include_details: bool = False, dtype=np.float32) -> dict:
    if TOTAL <= 0:
        raise ValueError("TOTAL 总股本须 > 0")
    if bins is not None:
        lo0 = min(float(r["low"]) for r in rows)
        hi0 = max(float(r["high"]) for r in rows)
        if hi0 > lo0 and bins > 0:
            tick = max((hi0 - lo0) / bins, 1e-9)
    else:
        tick = resolve_tick(rows, tick, rel, min_tick)
    edges, centers = make_axis(rows, tick)
    H = np.zeros(len(centers), dtype=dtype)
    hist: list[dict] = []
    last_close = float(rows[-1]["close"])
    for t, row in enumerate(rows):
        V = float(row["volume"]) * 100.0
        if V >= TOTAL:
            raise ValueError(f'{row["date"]} 成交 {V:.0f} >= 总股本 {TOTAL:.0f}')
        if t == 0:
            f = shape_weights(row, centers, seed)
            H = (f * V).astype(dtype, copy=False)
            S = 0.0
            Hold, Add, T, k = None, H, np.zeros_like(H), np.zeros_like(H)
        else:
            A = (float(row["open"]) + float(row["high"]) + float(row["low"]) + float(rows[t - 1]["close"])) / 4.0
            up_mask = centers > A
            peak = None
            if up_mask.any() and H[up_mask].max() > 0:
                peak = float(centers[up_mask][int(np.argmax(H[up_mask]))])
            k = build_k(centers, A, k_kind, base, width, peak)
            f = shape_weights(row, centers, f_mode)
            Hold, Add, T, H, S = settle(H, V, TOTAL, f, k)
        if return_history and (keep_every <= 1 or t % keep_every == 0 or t == len(rows) - 1):
            snap: dict = {"date": row["date"], "close": float(row["close"]), "V": V, "S": S}
            snap["H"] = H.copy() if include_details or True else None
            if include_details:
                snap["Hold"] = None if Hold is None else Hold.copy()
                snap["Add"] = Add.copy()
                snap["T"] = T.copy()
                snap["k"] = k.copy()
            hist.append(snap)
    return {"centers": centers, "edges": edges, "TOTAL": TOTAL, "tick": float(tick),
            "H": H, "close": last_close, "history": hist}

def summarize_from_H(H, centers, close: float | None = None) -> dict:
    H = np.asarray(H, dtype=float)
    if close is None:
        close = float(centers[int(np.argmax(H))]) if len(H) else 0.0
    tot = float(H.sum())
    order = np.argsort(centers)
    c, r = np.asarray(centers)[order], H[order] / tot if tot else H[order]
    cum = np.cumsum(r)
    pct = lambda q: float(np.interp(q, cum, c)) if len(c) else 0.0
    denom = pct(0.85) + pct(0.15)
    return {"close": float(close), "total": tot,
            "profit_ratio": float(r[c <= close].sum()) if len(c) else 0.0,
            "avg_cost": float((c * r).sum()) if len(c) else 0.0, "median": pct(0.5),
            "poc": float(c[int(np.argmax(r))]) if len(c) else 0.0,
            "conc70": (pct(0.85) - pct(0.15)) / denom if denom else 0.0}

def summarize(history: list[dict], centers) -> dict:
    if not history:
        raise ValueError("history 为空")
    last = history[-1]
    return summarize_from_H(last["H"], centers, last.get("close"))
