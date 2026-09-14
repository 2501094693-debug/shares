"""财务规则引擎公共工具。"""

from __future__ import annotations

from typing import Any


def to_float(value: Any) -> float | None:
    if value in (None, "", "-", "--"):
        return None
    try:
        return float(str(value).replace(",", "").replace("%", "").strip())
    except (TypeError, ValueError):
        return None


def pick(row: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in row and row[key] not in (None, "", "-", "--"):
            return row[key]
    return None


def fmt_yi(value: Any) -> str:
    n = to_float(value)
    if n is None:
        return "—"
    sign = "-" if n < 0 else ""
    abs_n = abs(n)
    if abs_n >= 1e8:
        text = f"{abs_n / 1e8:.2f}".rstrip("0").rstrip(".")
        return f"{sign}{text}亿"
    if abs_n >= 1e4:
        text = f"{abs_n / 1e4:.2f}".rstrip("0").rstrip(".")
        return f"{sign}{text}万"
    return f"{sign}{abs_n:.2f}".rstrip("0").rstrip(".")


def fmt_pct(value: Any, digits: int = 2) -> str:
    n = to_float(value)
    if n is None:
        return "—"
    return f"{n:.{digits}f}%"


def fmt_x(value: Any) -> str:
    n = to_float(value)
    if n is None:
        return "—"
    return f"{n:.2f}x"


def fmt_num(value: Any, digits: int = 2) -> str:
    n = to_float(value)
    if n is None:
        return "—"
    text = f"{n:.{digits}f}".rstrip("0").rstrip(".")
    return text if text else "0"


def yoy(curr: Any, prev: Any) -> float | None:
    c, p = to_float(curr), to_float(prev)
    if c is None or p is None or p == 0:
        return None
    return (c - p) / abs(p) * 100


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


def period_label(row: dict[str, Any]) -> str:
    return str(row.get("PERIOD_LABEL") or row.get("REPORT_DATE") or "—")
