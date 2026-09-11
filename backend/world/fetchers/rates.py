"""央行 / 政策利率历史。"""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Any

from core.http import browser_get, get_json

from world.catalog import RATES

_JIN10_URL = "https://datacenter-api.jin10.com/reports/list_v2"
_JIN10_HEADERS = {
    "x-app-id": "rU6QIu7JHe2gOUeR",
    "x-version": "1.0.0",
    "Origin": "https://datacenter.jin10.com",
    "Referer": "https://datacenter.jin10.com/",
}
_BOK_URL = (
    "https://www.bok.or.kr/portal/singl/baseRate/list.do"
    "?dataSeCd=01&menuNo=200068"
)
_LPR_URL = "https://datacenter-web.eastmoney.com/api/data/v1/get"
_HIBOR_FILTER = (
    '(MARKET_CODE="005")(CURRENCY_CODE="HKD")(INDICATOR_ID="203")'
)


def _num(raw: Any) -> float | None:
    if raw is None or raw == "":
        return None
    try:
        return round(float(raw), 4)
    except (TypeError, ValueError):
        return None


def _fetch_jin10(attr_id: str, *, limit: int) -> list[dict[str, Any]]:
    rows: list[list[Any]] = []
    max_date = ""
    while len(rows) < limit:
        params = {
            "max_date": max_date,
            "category": "ec",
            "attr_id": attr_id,
            "_": str(int(datetime.now().timestamp() * 1000)),
        }
        vals = (
            get_json(_JIN10_URL, params=params, headers=_JIN10_HEADERS, timeout=12)
            .get("data", {})
            .get("values")
            or []
        )
        if not vals:
            break
        rows.extend(vals)
        last = vals[-1][0]
        try:
            max_date = (
                datetime.strptime(str(last), "%Y-%m-%d").date() - timedelta(days=1)
            ).isoformat()
        except ValueError:
            break
        if len(vals) < 20:
            break

    out: list[dict[str, Any]] = []
    for item in rows[:limit]:
        if not item or len(item) < 4:
            continue
        out.append(
            {
                "date": str(item[0]),
                "value": _num(item[1]),
                "forecast": _num(item[2]),
                "previous": _num(item[3]),
            }
        )
    return out


def _fetch_bok(*, limit: int) -> list[dict[str, Any]]:
    html = browser_get(_BOK_URL, timeout=20).text
    match = re.search(r"var\s+chartObj2_s\s*=\s*(\[\[.*?\]\])", html, re.S)
    if not match:
        return []
    raw = match.group(1)
    pairs = re.findall(
        r'\[\s*"([^"]+)"\s*,\s*([0-9.]+)\s*\]',
        raw,
    )
    rows: list[dict[str, Any]] = []
    for date_raw, value in pairs:
        date = date_raw.strip().replace("/", "-").split()[0]
        rows.append(
            {
                "date": date,
                "value": _num(value),
                "forecast": None,
                "previous": None,
            }
        )
    rows.reverse()
    return rows[:limit]


def _fetch_lpr(*, limit: int) -> list[dict[str, Any]]:
    params = {
        "reportName": "RPTA_WEB_RATE",
        "columns": "TRADE_DATE,LPR1Y,LPR5Y,RATE_1,RATE_2",
        "sortColumns": "TRADE_DATE",
        "sortTypes": "-1",
        "pageNumber": "1",
        "pageSize": str(limit),
        "source": "WEB",
        "client": "WEB",
    }
    rows = (get_json(_LPR_URL, params=params, timeout=15).get("result") or {}).get(
        "data"
    ) or []
    out: list[dict[str, Any]] = []
    for row in rows:
        date = str(row.get("TRADE_DATE") or "")[:10]
        out.append(
            {
                "date": date,
                "value": _num(row.get("LPR1Y")),
                "lpr_5y": _num(row.get("LPR5Y")),
                "forecast": None,
                "previous": None,
            }
        )
    return out


def _fetch_hibor(*, limit: int) -> list[dict[str, Any]]:
    params = {
        "reportName": "RPT_IMP_INTRESTRATEN",
        "columns": "REPORT_DATE,IR_RATE,CHANGE_RATE",
        "filter": _HIBOR_FILTER,
        "pageNumber": "1",
        "pageSize": str(limit),
        "sortTypes": "-1",
        "sortColumns": "REPORT_DATE",
        "source": "WEB",
        "client": "WEB",
    }
    rows = (get_json(_LPR_URL, params=params, timeout=12).get("result") or {}).get(
        "data"
    ) or []
    out: list[dict[str, Any]] = []
    for row in rows:
        out.append(
            {
                "date": str(row.get("REPORT_DATE") or "")[:10],
                "value": _num(row.get("IR_RATE")),
                "change_bp": _num(row.get("CHANGE_RATE")),
                "forecast": None,
                "previous": None,
            }
        )
    return out


def fetch_rate_series(region: str, *, limit: int = 36) -> dict[str, Any]:
    cfg = RATES[region]
    source = cfg["source"]
    if source == "jin10":
        history = _fetch_jin10(str(cfg["attr_id"]), limit=limit)
    elif source == "bok":
        history = _fetch_bok(limit=limit)
    elif source == "lpr":
        history = _fetch_lpr(limit=limit)
    elif source == "hibor":
        history = _fetch_hibor(limit=limit)
    else:
        raise ValueError(f"未知利率数据源: {source}")

    latest = history[0] if history else {}
    return {
        "region": region,
        "name": cfg["name"],
        "label": cfg["label"],
        "source": source,
        "latest": latest,
        "history": history,
    }


def fetch_rates(*, limit: int = 36, regions: list[str] | None = None) -> dict[str, Any]:
    keys = regions or list(RATES.keys())
    items = [fetch_rate_series(region, limit=limit) for region in keys]
    return {"items": items}
