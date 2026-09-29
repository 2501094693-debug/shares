"""金额 / 比率格式化。"""

from __future__ import annotations

from typing import Any


def to_float(value: Any) -> float | None:
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
    if not text or text in {"None", "nan", "-"}:
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
    return f"{number:.2f}%"


def fmt_x(value: float | None) -> str:
    text = fmt_num(value, 2)
    return "—" if text == "—" else f"{text}x"


def md_table(headers: list[str], rows: list[list[str]]) -> str:
    if not rows:
        return "（无数据）"
    lines = [
        "| " + " | ".join(headers) + " |",
        "|" + "|".join("---" for _ in headers) + "|",
    ]
    for row in rows:
        lines.append("| " + " | ".join(row) + " |")
    return "\n".join(lines)


def cagr(first: float | None, last: float | None, years: float) -> float | None:
    if first is None or last is None or first <= 0 or last <= 0 or years <= 0:
        return None
    return (last / first) ** (1.0 / years) - 1.0


def median(vals: list[float | None]) -> float | None:
    xs = sorted(v for v in vals if v is not None)
    if not xs:
        return None
    mid = len(xs) // 2
    if len(xs) % 2:
        return xs[mid]
    return (xs[mid - 1] + xs[mid]) / 2.0
