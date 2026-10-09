"""定期报告：类型识别与报告期键。"""

from __future__ import annotations

import re

from core.codes import safe_str

KIND_LABELS: dict[str, str] = {
    "annual": "年报",
    "semi": "半年报",
    "q1": "一季报",
    "q3": "三季报",
}

KIND_RANK: dict[str, int] = {
    "q1": 1,
    "semi": 2,
    "q3": 3,
    "annual": 4,
}

CNINFO_KINDS = ("annual", "semi", "q1", "q3")

_SUMMARY_MARKERS = ("摘要", "摘要版", "全文摘要")
_ENGLISH_MARKERS = ("英文", "英文版", "english")
_CANCEL_MARKERS = ("已取消", "取消公告")

_YEAR_RE = re.compile(r"(20\d{2})")
_KIND_TITLE_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("q1", ("一季报", "第一季度报告", "第1季度报告", "一季度报告")),
    ("q3", ("三季报", "第三季度报告", "第3季度报告", "三季度报告")),
    ("semi", ("半年度报告", "半年报", "中期报告", "中报")),
    ("annual", ("年度报告", "年报")),
)


def infer_kind(title: str, category: str = "") -> str:
    text = f"{safe_str(title)} {safe_str(category)}"
    for kind, markers in _KIND_TITLE_RULES:
        if any(m in text for m in markers):
            return kind
    return ""


def infer_report_year(title: str, published_at: str = "") -> str:
    years = _YEAR_RE.findall(safe_str(title))
    if years:
        return years[0]
    day = safe_str(published_at)[:10]
    return day[:4] if len(day) >= 4 else ""


def is_summary_title(title: str) -> bool:
    return any(m in safe_str(title) for m in _SUMMARY_MARKERS)


def is_english_title(title: str) -> bool:
    text = safe_str(title).lower()
    return any(m in text for m in _ENGLISH_MARKERS)


def is_cancelled_title(title: str) -> bool:
    return any(m in safe_str(title) for m in _CANCEL_MARKERS)


def period_label(kind: str, year: str) -> str:
    label = KIND_LABELS.get(kind, "")
    if year and label:
        return f"{year}{label}"
    return label or year or ""


def period_key(year: str, kind: str) -> str:
    y = safe_str(year)
    k = safe_str(kind)
    if y and k:
        return f"{y}-{k}"
    return y or k or ""
