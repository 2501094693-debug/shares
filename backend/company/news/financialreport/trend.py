"""上市以来主要财务数据走势（年报口径，东方财富）。

复用 :mod:`company.news.financialreport._common` 的报表定义与请求工具，
分页拉全五类报表后按报告期合并，只保留年报（12-31）并按时间正序返回，
供前端走势图直接消费。
"""

from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from company.news.financialreport._common import (
    _EM_HEADERS,
    _EM_URLS,
    LICO_REPORT,
    STATEMENT_REPORTS,
    dedupe_periods,
    pick,
)
from company.news.financialreport.statements import merge_statements
from core.cache import TtlCache
from core.codes import normalize_code, ths_code
from core.http import get_json

logger = logging.getLogger(__name__)

_TTL = 6 * 3600
_cache = TtlCache(_TTL)

#: 缓存键版本：v2 为“按年分组、年内分季度”结构。
_TREND_CACHE_KEY = "trend:v2:f10:{code}"

_PAGE_SIZE = 100
_MAX_PAGES = 6

#: 走势指标：id / 展示名 / 候选字段（按优先级）/ 数值种类
TREND_FIELDS: list[dict[str, Any]] = [
    {
        "id": "revenue",
        "label": "营业收入",
        "keys": ["TOTALOPERATEREVE", "OPERATE_INCOME", "TOTAL_OPERATE_INCOME", "OPERATE_INCOME_PK"],
        "kind": "money",
    },
    {
        "id": "parent_profit",
        "label": "归母净利润",
        "keys": ["PARENTNETPROFIT", "PARENT_NETPROFIT"],
        "kind": "money",
    },
    {
        "id": "operate_cash",
        "label": "经营现金流",
        "keys": ["NETCASH_OPERATE", "NETCASH_OPERATE_PK"],
        "kind": "money",
    },
    {
        "id": "invest_cash",
        "label": "投资现金流",
        "keys": ["NETCASH_INVEST", "NETCASH_INVEST_PK"],
        "kind": "money",
    },
    {
        "id": "total_assets",
        "label": "资产总计",
        "keys": ["TOTAL_ASSETS", "TOTAL_ASSETS_PK"],
        "kind": "money",
    },
    {
        "id": "equity",
        "label": "净资产",
        "keys": ["TOTAL_EQUITY", "HOLDER_EQUITY", "TOTAL_EQUITY_PK"],
        "kind": "money",
    },
    {
        "id": "eps",
        "label": "每股收益",
        "keys": ["BASIC_EPS", "BASIC_EPS_PK", "DILUTED_EPS"],
        "kind": "number",
    },
    {
        "id": "roe",
        "label": "净资产收益率",
        "keys": ["ROE", "ROE_PK", "WEIGHTED_ROE", "ROEDILUTED"],
        "kind": "percent",
    },
]


def _num(value: Any) -> float | None:
    if value in (None, "", "-", "--"):
        return None
    try:
        num = float(value)
    except (TypeError, ValueError):
        return None
    return num


def _fetch_report_all(report_name: str, code: str) -> list[dict[str, Any]]:
    """分页拉全某张报表（新→旧），最多 ``_MAX_PAGES`` 页。"""
    stock = normalize_code(code)
    secu = ths_code(code)
    if not stock:
        return []
    filters = [f'(SECUCODE="{secu}")'] if secu else []
    filters.append(f'(SECURITY_CODE="{stock}")')
    sort_col = "REPORTDATE" if report_name == LICO_REPORT else "REPORT_DATE"

    out: list[dict[str, Any]] = []
    for page in range(1, _MAX_PAGES + 1):
        got_page = False
        for url in _EM_URLS:
            for flt in filters:
                params = {
                    "reportName": report_name,
                    "columns": "ALL",
                    "filter": flt,
                    "pageNumber": str(page),
                    "pageSize": str(_PAGE_SIZE),
                    "sortTypes": "-1",
                    "sortColumns": sort_col,
                    "source": "HSF10" if "securities" in url else "WEB",
                    "client": "PC" if "securities" in url else "WEB",
                }
                try:
                    payload = get_json(url, params=params, headers=_EM_HEADERS, timeout=20) or {}
                except Exception as exc:  # noqa: BLE001
                    logger.warning("东财 %s 第%s页拉取失败 %s: %s", report_name, page, code, exc)
                    continue
                result = payload.get("result") if isinstance(payload.get("result"), dict) else {}
                data = result.get("data") or []
                rows = [row for row in data if isinstance(row, dict)]
                if rows:
                    out.extend(rows)
                    got_page = True
                    break
            if got_page:
                break
        if not got_page:
            break
        if len(out) >= page * _PAGE_SIZE and page < _MAX_PAGES:
            continue
        if len(out) < page * _PAGE_SIZE:
            break
    return out


def fetch_trend_rows(code: str) -> list[dict[str, Any]]:
    """拉全报表 → 合并 → 全报告期时间正序（含季报，供按年分季度用）。"""
    norm = normalize_code(code)
    if not norm:
        raise ValueError("无效股票代码")
    with ThreadPoolExecutor(max_workers=5) as pool:
        futs = {name: pool.submit(_fetch_report_all, report, code) for name, report in STATEMENT_REPORTS.items()}
        packs = {name: fut.result() for name, fut in futs.items()}
    merged = merge_statements(
        packs.get("main") or [],
        packs.get("income") or [],
        packs.get("balance") or [],
        packs.get("cashflow") or [],
        packs.get("lico") or [],
    )
    rows = dedupe_periods(merged)
    rows.sort(key=lambda r: str(r.get("REPORT_DATE") or ""))
    return rows


_QUARTERS = ("Q1", "Q2", "Q3", "Q4")
_Q_MONTH = {"03": "Q1", "06": "Q2", "09": "Q3", "12": "Q4"}


def _blank_quarter(q: str) -> dict[str, Any]:
    entry: dict[str, Any] = {"q": q, "report_date": "", "has_data": False}
    for field in TREND_FIELDS:
        entry[field["id"]] = None
        entry[f'{field["id"]}_cum'] = None
        entry[f'{field["id"]}_yoy'] = None
    return entry


def build_trend(code: str, *, force: bool = False) -> dict[str, Any]:
    norm = normalize_code(code)
    if not norm:
        raise ValueError("无效股票代码")
    cache_key = _TREND_CACHE_KEY.format(code=norm)
    now = time.time()
    if not force:
        hit = _cache.get(cache_key)
        if hit is not None:
            return hit

    rows = fetch_trend_rows(code)
    by_year: dict[str, dict[str, dict[str, Any]]] = {}
    for row in rows:
        day = str(row.get("REPORT_DATE") or "")[:10]
        if len(day) < 10:
            continue
        year, month = day[:4], day[5:7]
        q = _Q_MONTH.get(month)
        if not year.isdigit() or not q:
            continue
        by_year.setdefault(year, {})[q] = row

    items: list[dict[str, Any]] = []
    prev_single: dict[str, dict[str, float | None]] = {}
    for year in sorted(by_year):
        qrows = by_year[year]
        prev_cum: dict[str, float] = {}
        quarters: list[dict[str, Any]] = []
        for q in _QUARTERS:
            row = qrows.get(q)
            if row is None:
                quarters.append(_blank_quarter(q))
                continue
            entry: dict[str, Any] = {
                "q": q,
                "report_date": str(row.get("REPORT_DATE") or "")[:10],
                "has_data": True,
            }
            for field in TREND_FIELDS:
                fid = field["id"]
                cum = _num(pick(row, *field["keys"]))
                entry[f"{fid}_cum"] = cum
                if field["kind"] == "money":
                    base = prev_cum.get(fid)
                    single = (cum - base) if (cum is not None and base is not None) else cum
                    entry[fid] = single
                    if cum is not None:
                        prev_cum[fid] = cum
                else:
                    entry[fid] = cum
                cur = entry[fid]
                last = (prev_single.get(fid) or {}).get(q)
                if cur is not None and last not in (None, 0):
                    try:
                        entry[f"{fid}_yoy"] = round((cur - last) / abs(last) * 100, 2)  # type: ignore[operator]
                    except (TypeError, ZeroDivisionError):
                        entry[f"{fid}_yoy"] = None
                else:
                    entry[f"{fid}_yoy"] = None
            quarters.append(entry)
        for field in TREND_FIELDS:
            fid = field["id"]
            prev_single[fid] = {e["q"]: e[fid] for e in quarters}
        items.append({"year": year, "quarters": quarters})

    data = {
        "code": norm,
        "source": "eastmoney" if items else "",
        "count": len(items),
        "start_year": items[0]["year"] if items else "",
        "end_year": items[-1]["year"] if items else "",
        "fields": [
            {"id": f["id"], "label": f["label"], "kind": f["kind"]} for f in TREND_FIELDS
        ],
        "quarters": list(_QUARTERS),
        "items": items,
    }
    if items:
        _cache.put(cache_key, data, cached_at=now)
    return data
