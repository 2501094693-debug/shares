"""同花顺 F10「分红融资」页：直接解析派现总额。

同花顺分红页 ``http://basic.10jqka.com.cn/{code}/bonus.html`` 的分红表直接给出
每次分红的 **「AH分红总额」**（A 股 + H 股，含特别分红），这是东财
``RPT_SHAREBONUS_DET`` 缺失的那部分。例如药明康德 2025 年三项：
年度 47.12 亿 + 中期 10.33 亿 + 特别分红 10.11 亿 ≈ 67.55 亿。

金额统一为**元**。同花顺金额按「亿 / 万」展示、保留 2 位小数，
故本模块数值为同花顺口径的近似值（非精确到分）。
"""

from __future__ import annotations

import re
from typing import Any

from core.codes import normalize_code
from core.http import browser_get

_BONUS_URL = "http://basic.10jqka.com.cn/{code}/bonus.html"
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    "Referer": "http://basic.10jqka.com.cn/",
}

_IMPLEMENTED_KEYS = ("实施",)
_PLANNED_KEYS = ("预案", "预披露", "意向", "董事会", "股东大会")

# 表头名称 → 字段键（按子串匹配，兼容 A / AH 不同列名）
_COLUMNS = (
    ("report_period", ("报告期",)),
    ("board_date", ("董事会日期",)),
    ("shareholder_date", ("股东大会",)),
    ("impl_date", ("实施公告",)),
    ("plan", ("分红方案",)),
    ("record_date", ("股权登记",)),
    ("ex_date", ("除权除息",)),
    ("total_amount", ("分红总额",)),
    ("progress", ("方案进度", "进度")),
    ("payout_ratio", ("股利支付率", "支付率")),
    ("dividend_yield", ("分红率", "股息率")),
)


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", text or "")).replace("&nbsp;", " ").strip()


def _date(text: str) -> str:
    text = (text or "").strip()
    return "" if text in ("--", "-", "") else text[:10]


def _amount(text: str) -> float | None:
    """「47.12亿」→ 元；「--」→ None。"""
    raw = (text or "").strip().replace(",", "")
    if raw in ("", "--", "-"):
        return None
    mult = 1.0
    if raw.endswith("亿"):
        mult, raw = 1e8, raw[:-1]
    elif raw.endswith("万"):
        mult, raw = 1e4, raw[:-1]
    try:
        return round(float(raw) * mult, 2)
    except ValueError:
        return None


def _ratio(text: str) -> float | None:
    raw = (text or "").strip().replace("%", "")
    if raw in ("", "--", "-"):
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def _status(progress: str) -> str:
    text = progress or ""
    if any(key in text for key in _IMPLEMENTED_KEYS):
        return "implemented"
    if any(key in text for key in _PLANNED_KEYS):
        return "planned"
    return "other"


def _year_of(report_period: str) -> str:
    match = re.search(r"(\d{4})", report_period or "")
    return match.group(1) if match else ""


def _name_from_title(html: str) -> str:
    match = re.search(r"<title>\s*(.*?)\(\d{6}\)", html)
    return match.group(1).strip() if match else ""


def _find_table(html: str) -> str | None:
    for match in re.finditer(r"<table[^>]*>(.*?)</table>", html, re.S):
        inner = match.group(1)
        if "分红方案说明" in inner and "方案进度" in inner:
            return match.group(0)
    return None


def _map_headers(header_cells: list[str]) -> dict[str, int]:
    mapping: dict[str, int] = {}
    for index, cell in enumerate(header_cells):
        for key, needles in _COLUMNS:
            if key in mapping:
                continue
            if any(needle in cell for needle in needles):
                mapping[key] = index
                break
    return mapping


def _cell(cells: list[str], mapping: dict[str, int], key: str) -> str:
    idx = mapping.get(key)
    if idx is None or idx >= len(cells):
        return ""
    return cells[idx]


def parse_bonus_html(html: str) -> dict[str, Any]:
    """解析同花顺分红页 → 结构化数据（金额为元）。"""
    out: dict[str, Any] = {
        "name": _name_from_title(html),
        "cumulative": {},
        "detail": [],
        "cash_by_year": [],
    }

    # 累计分红：「该股自上市以来累计分红 11 次，累计分红金额为 203.09 亿元，
    #          其中A股分红173.61 亿元，港股分红29.48 亿元。」
    m = re.search(r"累计分红\s*<strong>(\d+)</strong>\s*次.*?累计分红金额为\s*<strong>([\d.]+)</strong>\s*亿元", html, re.S)
    if m:
        out["cumulative"]["count"] = int(m.group(1))
        out["cumulative"]["total"] = round(float(m.group(2)) * 1e8, 2)
    m = re.search(r"A股分红<strong>([\d.]+)</strong>\s*亿元，?\s*港股分红<strong>([\d.]+)</strong>", html, re.S)
    if m:
        out["cumulative"]["a_total"] = round(float(m.group(1)) * 1e8, 2)
        out["cumulative"]["h_total"] = round(float(m.group(2)) * 1e8, 2)

    table = _find_table(html)
    if not table:
        return out

    rows = re.findall(r"<tr[^>]*>(.*?)</tr>", table, re.S)
    if not rows:
        return out

    header_cells = [_clean(c) for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", rows[0], re.S)]
    mapping = _map_headers(header_cells)

    for row in rows[1:]:
        cells = [_clean(c) for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row, re.S)]
        if not cells:
            continue
        report_period = _cell(cells, mapping, "report_period")
        if not report_period:
            continue
        progress = _cell(cells, mapping, "progress")
        amount = _amount(_cell(cells, mapping, "total_amount"))
        out["detail"].append(
            {
                "report_period": report_period,
                "year": _year_of(report_period),
                "board_date": _date(_cell(cells, mapping, "board_date")),
                "shareholder_date": _date(_cell(cells, mapping, "shareholder_date")),
                "impl_date": _date(_cell(cells, mapping, "impl_date")),
                "plan": _cell(cells, mapping, "plan"),
                "record_date": _date(_cell(cells, mapping, "record_date")),
                "ex_date": _date(_cell(cells, mapping, "ex_date")),
                "total_amount": amount,
                "progress": progress,
                "status": _status(progress),
                "payout_ratio": _ratio(_cell(cells, mapping, "payout_ratio")),
                "dividend_yield": _ratio(_cell(cells, mapping, "dividend_yield")),
            }
        )

    out["cash_by_year"] = _cash_by_year(out["detail"])
    return out


def _cash_by_year(detail: list[dict[str, Any]]) -> list[dict[str, Any]]:
    buckets: dict[str, dict[str, Any]] = {}
    for item in detail:
        year = item.get("year") or ""
        if not year:
            continue
        bucket = buckets.setdefault(year, {"year": year, "total_amount": 0.0, "periods": 0})
        amount = item.get("total_amount")
        if item.get("status") == "implemented" and amount is not None:
            bucket["total_amount"] += float(amount)
            bucket["periods"] += 1
    for bucket in buckets.values():
        bucket["total_amount"] = round(bucket["total_amount"], 2)
    return [buckets[key] for key in sorted(buckets, reverse=True)]


def fetch_ths_bonus(code: str) -> dict[str, Any]:
    """拉取并解析同花顺分红页；失败返回空结构。"""
    norm = normalize_code(code)
    if not norm:
        return {"code": "", "name": "", "cumulative": {}, "detail": [], "cash_by_year": []}
    try:
        resp = browser_get(_BONUS_URL.format(code=norm), headers=_HEADERS, timeout=20)
        resp.raise_for_status()
        html = resp.content.decode("gbk", errors="ignore")
    except Exception:  # noqa: BLE001
        return {"code": norm, "name": "", "cumulative": {}, "detail": [], "cash_by_year": []}

    data = parse_bonus_html(html)
    data["code"] = norm
    data["source"] = "ths"
    return data
