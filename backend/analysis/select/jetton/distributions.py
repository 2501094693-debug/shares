"""每日生成器 f(p) 与卖出比例 k(p) 的默认选项。"""
from __future__ import annotations
import numpy as np

def _sigmoid(x):
    return 1.0 / (1.0 + np.exp(-np.clip(np.asarray(x, float), -30, 30)))

def shape_weights(row: dict, centers: np.ndarray, mode: str = "triangle", sigma: float = 0.015) -> np.ndarray:
    lo, hi, o, c = float(row["low"]), float(row["high"]), float(row["open"]), float(row["close"])
    w = np.zeros_like(centers, dtype=float)
    if hi <= lo:
        w[int(np.clip(np.searchsorted(centers, c), 0, len(centers) - 1))] = 1.0
        return w
    m = (centers >= lo) & (centers <= hi)
    if mode == "uniform":
        w[m] = 1.0
    elif mode == "close_gauss":
        s = sigma * c
        w[m] = np.exp(-(centers[m] - c) ** 2 / (2 * s * s))
    elif mode == "skew":
        A = (o + c + hi + lo) / 4.0 + 0.25 * np.sign(c - o) * (hi - lo)
        w[m] = np.maximum(0, 1 - np.abs(centers[m] - A) / (hi - lo))
    else:
        A = (o + c + hi + lo) / 4.0
        w[m] = np.maximum(0, 1 - np.abs(centers[m] - A) / (hi - lo))
    s = w.sum()
    return w / s if s > 0 else w

def build_k(centers: np.ndarray, A: float, kind: str = "flat", base: float = 0.05,
            width: float = 0.02, peak: float | None = None) -> np.ndarray:
    if kind == "take_profit":
        return np.clip(base * 2 * _sigmoid((A - centers) / (width * A)), 0, 1)
    if kind == "stop_loss":
        return np.clip(base * 2 * _sigmoid((centers - A) / (width * A)), 0, 1)
    if kind == "nearby":
        g = np.exp(-(centers - A) ** 2 / (2 * (0.03 * A) ** 2))
        return np.clip(base * g / max(float(g.mean()), 1e-12), 0, 1)
    if kind == "resistance":
        p = peak if peak is not None else A * 1.05
        g = np.exp(-(centers - p) ** 2 / (2 * (0.02 * A) ** 2))
        return np.clip(base + 4 * base * g, 0, 1)
    return np.full_like(centers, base, dtype=float)

F_MODES = ("triangle", "uniform", "close_gauss", "skew")
K_KINDS = ("flat", "take_profit", "stop_loss", "nearby", "resistance")
