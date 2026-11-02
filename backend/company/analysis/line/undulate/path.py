"""由起止日与均值的 σ 坐标判定区间走势。

输入 ``S0 = beg_pct/σ``、``U = mean/σ``、``S1 = end_pct/σ``，
看 ``S0 ? U`` 与 ``U ? S1`` 两条关系（各为 ``<`` / ``=`` / ``>``，共九格）：

- 两等号 → 横盘
- 一等号 → 跟剩余那条不等式：``<`` 上行，``>`` 下行
- 零等号 → 同向为上行/下行，异向为冲高回落 / 探底回升

``|a-b| <= eps`` 视为相等。
"""

from __future__ import annotations

from typing import Any, Literal

Cmp = Literal["<", "=", ">"]
Label = Literal["上行", "下行", "冲高回落", "探底回升", "横盘", "unknown"]

DEFAULT_EPS = 0.1


def _cmp(a: float, b: float, eps: float) -> Cmp:
    if abs(a - b) <= eps:
        return "="
    return "<" if a < b else ">"


def classify_path(
    s0: float | None,
    u: float | None,
    s1: float | None,
    *,
    eps: float = DEFAULT_EPS,
) -> dict[str, Any]:
    """按 ``S0 ∘ U ∘ S1`` 九格规则给出走势标签。

    ``s0`` / ``u`` / ``s1`` 任一缺失记 ``unknown``；``eps < 0`` 抛 ``ValueError``。
    """
    eps_v = float(eps)
    if eps_v < 0:
        raise ValueError(f"eps 不能为负: {eps}")
    if s0 is None or u is None or s1 is None:
        return {
            "label": "unknown",
            "S0": s0,
            "U": u,
            "S1": s1,
            "left": None,
            "right": None,
            "eps": eps_v,
            "reason": "缺少 S0/U/S1",
        }

    s0_v, u_v, s1_v = float(s0), float(u), float(s1)
    left = _cmp(s0_v, u_v, eps_v)
    right = _cmp(u_v, s1_v, eps_v)

    if left == "=" and right == "=":
        label: Label = "横盘"
    elif left == "=" or right == "=":
        # 一等号：只看另一条严格符号
        label = "上行" if (left == "<" or right == "<") else "下行"
    elif left == "<" and right == "<":
        label = "上行"
    elif left == ">" and right == ">":
        label = "下行"
    elif left == "<" and right == ">":
        label = "冲高回落"
    else:
        # left == ">" and right == "<"
        label = "探底回升"

    return {
        "label": label,
        "S0": round(s0_v, 6),
        "U": round(u_v, 6),
        "S1": round(s1_v, 6),
        "left": left,
        "right": right,
        "eps": eps_v,
        "reason": f"S0 {left} U {right} S1",
    }


def path_from_stats(
    row: dict[str, Any],
    *,
    eps: float = DEFAULT_EPS,
) -> dict[str, Any]:
    """从 volatility 单因子 ``stats`` 行取 σ 坐标再分类。

    ``U = mean/std``；``S0``/``S1`` 优先用已有 ``beg_sigma`` / ``end_sigma``。
    ``std`` 无效时无法换算，返回 ``unknown``。
    """
    std = row.get("std")
    mean = row.get("mean")
    if std is None or float(std) <= 0 or mean is None:
        return classify_path(None, None, None, eps=eps)

    std_v = float(std)
    s0 = row.get("beg_sigma")
    s1 = row.get("end_sigma")
    if s0 is None and row.get("beg_pct") is not None:
        s0 = float(row["beg_pct"]) / std_v
    if s1 is None and row.get("end_pct") is not None:
        s1 = float(row["end_pct"]) / std_v
    u = float(mean) / std_v
    return classify_path(
        None if s0 is None else float(s0),
        u,
        None if s1 is None else float(s1),
        eps=eps,
    )
