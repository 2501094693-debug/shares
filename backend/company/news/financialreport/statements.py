"""东财财务报表拉取与按报告期合并。"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import Any

from company.news.financialreport._common import (
    BALANCE_REPORT,
    CASH_REPORT,
    INCOME_REPORT,
    LICO_REPORT,
    MAIN_REPORT,
    STATEMENT_REPORTS,
    dedupe_periods,
    em_get,
    index_by_date,
    is_annual,
    period_label,
)
from core.codes import normalize_code


def merge_statements(
    main_rows: list[dict[str, Any]],
    income_rows: list[dict[str, Any]],
    balance_rows: list[dict[str, Any]],
    cash_rows: list[dict[str, Any]],
    lico_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    main_map = index_by_date(dedupe_periods(main_rows))
    income_map = index_by_date(dedupe_periods(income_rows))
    balance_map = index_by_date(dedupe_periods(balance_rows))
    cash_map = index_by_date(dedupe_periods(cash_rows))
    lico_map = index_by_date(dedupe_periods(lico_rows))
    dates = sorted(
        set(main_map) | set(income_map) | set(balance_map) | set(cash_map) | set(lico_map),
        reverse=True,
    )
    merged: list[dict[str, Any]] = []
    for day in dates:
        row: dict[str, Any] = {"REPORT_DATE": day}
        for pack in (
            lico_map.get(day) or {},
            cash_map.get(day) or {},
            balance_map.get(day) or {},
            income_map.get(day) or {},
            main_map.get(day) or {},
        ):
            row.update(pack)
        row["REPORT_DATE"] = day
        row["PERIOD_LABEL"] = period_label(day, str(row.get("REPORT_DATE_NAME") or ""))
        merged.append(row)
    return merged


def annual_rows(rows: list[dict[str, Any]], limit: int = 5) -> list[dict[str, Any]]:
    return [r for r in rows if is_annual(str(r.get("REPORT_DATE") or ""))][:limit]


def recent_rows(rows: list[dict[str, Any]], limit: int = 5) -> list[dict[str, Any]]:
    return rows[:limit]


def fetch_statement(code: str, kind: str, *, page_size: int = 24) -> list[dict[str, Any]]:
    report = STATEMENT_REPORTS.get((kind or "").strip().lower())
    if not report:
        raise ValueError(f"未知报表类型: {kind}")
    return em_get(report, code, page_size=page_size)


def fetch_all_statements(code: str, *, page_size: int = 24) -> dict[str, Any]:
    """并行拉取五类报表并合并。"""
    norm = normalize_code(code)
    if not norm:
        raise ValueError("无效股票代码")

    with ThreadPoolExecutor(max_workers=5) as pool:
        fut_main = pool.submit(em_get, MAIN_REPORT, code, page_size=page_size)
        fut_income = pool.submit(em_get, INCOME_REPORT, code, page_size=page_size)
        fut_balance = pool.submit(em_get, BALANCE_REPORT, code, page_size=page_size)
        fut_cash = pool.submit(em_get, CASH_REPORT, code, page_size=page_size)
        fut_lico = pool.submit(em_get, LICO_REPORT, code, page_size=page_size)
        main_rows = fut_main.result()
        income_rows = fut_income.result()
        balance_rows = fut_balance.result()
        cash_rows = fut_cash.result()
        lico_rows = fut_lico.result()

    merged = merge_statements(main_rows, income_rows, balance_rows, cash_rows, lico_rows)
    return {
        "code": norm,
        "source": "eastmoney" if merged else "",
        "statements": {
            "main": dedupe_periods(main_rows),
            "income": dedupe_periods(income_rows),
            "balance": dedupe_periods(balance_rows),
            "cashflow": dedupe_periods(cash_rows),
            "lico": dedupe_periods(lico_rows),
        },
        "merged": merged,
        "annual": annual_rows(merged, 5),
        "recent": recent_rows(merged, 5),
        "count": len(merged),
    }
