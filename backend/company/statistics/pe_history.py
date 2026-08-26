"""个股历史估值：东财估值分析明细 ``RPT_VALUEANALYSIS_DET``。

按交易日给出收盘价、市盈率 TTM、市盈率静（最新年报 PE_LAR）、市净率 MRQ。
动态市盈率没有现成日频表，按东财盘口口径回推：
``收盘价 / (最新已披露报告期 EPS × 年化系数)``。
年化系数：一季报×4、中报×2、三季报×4/3、年报×1。
EPS 用当日总股本去除以归属净利润，与盘口 ``f162`` 对齐。

    python company/statistics/pe_history.py 600519
    python company/statistics/pe_history.py 600519 --limit 10
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path
from typing import Any

_BACKEND = Path(__file__).resolve().parents[2]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from core.cache import TtlCache
from core.codes import normalize_code
from core.fmt import to_float
from core.http import get_json

logger = logging.getLogger(__name__)

PE_TTL = 600
_PAGE_SIZE = 500
_MAX_PAGES = 12
_COLUMNS = (
    "SECURITY_CODE,SECURITY_NAME_ABBR,TRADE_DATE,"
    "CLOSE_PRICE,PE_TTM,PE_LAR,PB_MRQ,PS_TTM,TOTAL_SHARES"
)
_REPORT_COLUMNS = "REPORTDATE,NOTICE_DATE,PARENT_NETPROFIT,QDATE"
_HEADERS = {"Referer": "https://data.eastmoney.com/"}

_cache = TtlCache(PE_TTL)


def _trade_date(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    return text[:10] if len(text) >= 10 else text


def _annualize_factor(report_date: str) -> float | None:
    """把累计报告期利润折成全年：0331×4、0630×2、0930×4/3、1231×1。"""
    day = _trade_date(report_date)
    if len(day) < 7:
        return None
    try:
        month = int(day[5:7])
    except ValueError:
        return None
    if month == 3:
        return 4.0
    if month == 6:
        return 2.0
    if month == 9:
        return 4.0 / 3.0
    if month == 12:
        return 1.0
    return None


def _parse_row(row: dict[str, Any]) -> dict[str, Any] | None:
    if not isinstance(row, dict):
        return None
    time_s = _trade_date(row.get("TRADE_DATE"))
    if not time_s:
        return None
    close = to_float(row.get("CLOSE_PRICE"))
    pe_ttm = to_float(row.get("PE_TTM"))
    pe_static = to_float(row.get("PE_LAR"))
    pb = to_float(row.get("PB_MRQ"))
    if close is None and pe_ttm is None and pe_static is None and pb is None:
        return None
    return {
        "time": time_s,
        "close": close,
        "pe_ttm": pe_ttm,
        "pe_static": pe_static,
        "pe_dyn": None,
        "pb": pb,
        "ps_ttm": to_float(row.get("PS_TTM")),
        "_shares": to_float(row.get("TOTAL_SHARES")),
    }


def _parse_report(row: dict[str, Any]) -> dict[str, Any] | None:
    if not isinstance(row, dict):
        return None
    notice = _trade_date(row.get("NOTICE_DATE"))
    report = _trade_date(row.get("REPORTDATE"))
    profit = to_float(row.get("PARENT_NETPROFIT"))
    factor = _annualize_factor(report)
    if not notice or not report or profit is None or profit <= 0 or not factor:
        return None
    return {"notice": notice, "report": report, "profit": profit, "factor": factor}


def _fetch_page(code: str, page: int, page_size: int) -> dict[str, Any]:
    payload = get_json(
        "https://datacenter-web.eastmoney.com/api/data/v1/get",
        params={
            "reportName": "RPT_VALUEANALYSIS_DET",
            "columns": _COLUMNS,
            "filter": f'(SECURITY_CODE="{code}")',
            "pageNumber": str(page),
            "pageSize": str(page_size),
            "sortColumns": "TRADE_DATE",
            "sortTypes": "-1",
            "source": "WEB",
            "client": "WEB",
        },
        headers=_HEADERS,
        timeout=15,
    )
    return payload if isinstance(payload, dict) else {}


def _fetch_reports(code: str) -> list[dict[str, Any]]:
    """业绩报表：披露日 + 归属净利润，用来回推动态市盈率。"""
    payload = get_json(
        "https://datacenter-web.eastmoney.com/api/data/v1/get",
        params={
            "reportName": "RPT_LICO_FN_CPD",
            "columns": _REPORT_COLUMNS,
            "filter": f'(SECURITY_CODE="{code}")',
            "pageNumber": "1",
            "pageSize": "100",
            "sortColumns": "REPORTDATE",
            "sortTypes": "-1",
            "source": "WEB",
            "client": "WEB",
        },
        headers=_HEADERS,
        timeout=15,
    )
    if not isinstance(payload, dict):
        return []
    rows = (
        ((payload.get("result") or {}) if isinstance(payload.get("result"), dict) else {}).get(
            "data"
        )
        or []
    )
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows:
        parsed = _parse_report(row)
        if not parsed:
            continue
        key = parsed["notice"] + parsed["report"]
        if key in seen:
            continue
        seen.add(key)
        out.append(parsed)
    out.sort(key=lambda r: (r["notice"], r["report"]))
    return out


def _attach_pe_dyn(items: list[dict[str, Any]], reports: list[dict[str, Any]]) -> None:
    """就地写入 ``pe_dyn``。用披露日不晚于交易日的最新报告期年化。"""
    if not items:
        return
    idx = -1
    n_rep = len(reports)
    for item in items:
        day = item.get("time") or ""
        while idx + 1 < n_rep and reports[idx + 1]["notice"] <= day:
            idx += 1
        item["pe_dyn"] = None
        if idx < 0:
            continue
        close = to_float(item.get("close"))
        shares = to_float(item.get("_shares"))
        profit = reports[idx]["profit"]
        factor = reports[idx]["factor"]
        if close is None or shares is None or shares <= 0 or not profit or not factor:
            continue
        annual_eps = (profit / shares) * factor
        if annual_eps <= 0:
            continue
        item["pe_dyn"] = close / annual_eps


def fetch_pe_history(
    code: str,
    *,
    limit: int = 1500,
    force: bool = False,
) -> dict[str, Any]:
    """拉取按日的估值序列。默认最近 ``limit`` 个交易日，时间升序。"""
    code = normalize_code(code)
    if not code:
        raise ValueError("无效股票代码")

    cap = max(1, min(int(limit or 1500), _PAGE_SIZE * _MAX_PAGES))
    cache_key = f"{code}:{cap}:dyn"
    now = time.time()
    if not force:
        hit = _cache.get(cache_key)
        if hit is not None:
            return hit

    raw_rows: list[dict[str, Any]] = []
    name = ""
    pages = 1
    page = 1
    last_exc: Exception | None = None

    while page <= pages and page <= _MAX_PAGES and len(raw_rows) < cap:
        try:
            payload = _fetch_page(code, page, _PAGE_SIZE)
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            logger.info("pe history skip %s page %s: %s", code, page, exc)
            break
        result = payload.get("result") if isinstance(payload.get("result"), dict) else {}
        if page == 1:
            try:
                pages = max(1, int(result.get("pages") or 1))
            except (TypeError, ValueError):
                pages = 1
        data = result.get("data") or []
        if not data:
            break
        if not name:
            first = data[0] if isinstance(data[0], dict) else {}
            name = str(first.get("SECURITY_NAME_ABBR") or "").strip()
        raw_rows.extend(row for row in data if isinstance(row, dict))
        page += 1

    if not raw_rows and last_exc:
        raise last_exc

    items: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in reversed(raw_rows):
        parsed = _parse_row(row)
        if not parsed:
            continue
        day = parsed["time"]
        if day in seen:
            continue
        seen.add(day)
        items.append(parsed)
    if len(items) > cap:
        items = items[-cap:]

    try:
        reports = _fetch_reports(code)
        _attach_pe_dyn(items, reports)
    except Exception as exc:  # noqa: BLE001
        logger.info("pe dyn skip %s: %s", code, exc)

    for item in items:
        item.pop("_shares", None)

    result = {
        "code": code,
        "name": name,
        "source": "eastmoney" if items else "",
        "count": len(items),
        "items": items,
    }
    _cache.put(cache_key, result, cached_at=now)
    return result


def _print_preview(pack: dict[str, Any], n: int) -> None:
    items = list(pack.get("items") or [])
    print(f"{pack.get('code')} {pack.get('name') or ''}  n={len(items)}")
    for row in items[-max(1, n) :]:
        print(
            f"  {row.get('time')}  close={row.get('close')}  "
            f"dyn={row.get('pe_dyn')}  ttm={row.get('pe_ttm')}  "
            f"static={row.get('pe_static')}"
        )


def main() -> int:
    parser = argparse.ArgumentParser(description="拉取东财历史市盈率")
    parser.add_argument("code", nargs="?", default="600519")
    parser.add_argument("--limit", type=int, default=8)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    pack = fetch_pe_history(args.code, limit=max(args.limit, 8), force=True)
    _print_preview(pack, args.limit)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
