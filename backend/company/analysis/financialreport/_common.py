"""张新民「八看」规则引擎公共工具：报告期口径、数字格式化、Markdown 表格。"""

from __future__ import annotations

from typing import Any

# 报告类型 → 中文名（对外统一口径）
REPORT_TYPE_LABELS = {
    "annual": "年报",
    "semi": "半年报",
    "q1": "一季报",
    "q3": "三季报",
}

# 报告日期的月份 → 报告类型
_MONTH_TO_TYPE = {"12": "annual", "06": "semi", "03": "q1", "09": "q3"}

# 允许的入参别名（中英文都接受）
REPORT_TYPE_ALIASES = {
    "annual": "annual", "year": "annual", "yearly": "annual", "a": "annual", "y": "annual",
    "年报": "annual", "年度": "annual",
    "semi": "semi", "half": "semi", "interim": "semi", "halfyear": "semi", "h": "semi",
    "半年报": "semi", "中报": "semi", "半年度": "semi",
    "q1": "q1", "quarter1": "q1", "first": "q1", "1q": "q1",
    "一季报": "q1", "一季度": "q1", "一季": "q1",
    "q3": "q3", "quarter3": "q3", "third": "q3", "3q": "q3",
    "三季报": "q3", "三季度": "q3", "三季": "q3",
}


def normalize_report_type(value: str | None) -> str:
    """把各种写法归一成 ``annual`` / ``semi`` / ``q1`` / ``q3``，默认年报。"""
    key = str(value or "").strip().lower()
    if not key:
        return "annual"
    if key in REPORT_TYPE_ALIASES:
        return REPORT_TYPE_ALIASES[key]
    raise ValueError(
        "report_type 须为 annual(年报) | semi(半年报) | q1(一季报) | q3(三季报)"
    )


def report_type_label(report_type: str) -> str:
    return REPORT_TYPE_LABELS.get(report_type, "")


def to_float(value: Any) -> float | None:
    """宽松转 float；None / 空串 / '-' / '--' / 东财哨兵值都视为缺失。"""
    if value in (None, "", "-", "--"):
        return None
    try:
        number = float(str(value).replace(",", "").replace("%", "").strip())
    except (TypeError, ValueError):
        return None
    if number != number:  # NaN
        return None
    if number <= -1e10:  # 东财「无数据」哨兵
        return None
    return number


def pick(row: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in row and row[key] not in (None, "", "-", "--"):
            return row[key]
    return None


def report_date_of(row: dict[str, Any]) -> str:
    return str(row.get("REPORT_DATE") or row.get("REPORTDATE") or "")[:10]


def report_kind(row: dict[str, Any]) -> str:
    """单条记录的定期报告类型：年报 / 半年报 / 一季报 / 三季报 / 定期报告。"""
    day = report_date_of(row)
    if len(day) >= 7:
        kind = _MONTH_TO_TYPE.get(day[5:7])
        if kind:
            return REPORT_TYPE_LABELS[kind]
    label = str(row.get("PERIOD_LABEL") or "")
    for name in ("三季报", "半年报", "一季报", "年报"):
        if name in label:
            return name
    if "中报" in label:
        return "半年报"
    return "定期报告"


def period_label(row: dict[str, Any]) -> str:
    return str(row.get("PERIOD_LABEL") or report_date_of(row) or "—")


def select_series(
    rows: list[dict[str, Any]] | None,
    report_type: str,
    *,
    limit: int = 8,
) -> list[dict[str, Any]]:
    """按报告类型挑选同口径序列：最新一期 + 同类型历史期（年报对年报、三季报对三季报）。

    ``rows`` 需按报告日倒序排列（东财 F10 天然如此）。
    """
    rt = normalize_report_type(report_type)
    pool = [row for row in (rows or []) if report_date_of(row)]
    same = [row for row in pool if _MONTH_TO_TYPE.get(report_date_of(row)[5:7]) == rt]
    return same[: max(int(limit or 1), 1)]


def yoy(curr: Any, prev: Any) -> float | None:
    c, p = to_float(curr), to_float(prev)
    if c is None or p is None or p == 0:
        return None
    return (c - p) / abs(p) * 100


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
