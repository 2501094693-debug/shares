"""自由流通股、自由流通市值。

口径：东财 ``RPT_F10_EH_EQUITY.FREELIQCI_SHARES``（中证自由流通股本），不做本地扣减回退。

自由流通市值 = 现价 × 自由流通股；没有现价时按流通市值等比折算。

    python company/statistics/quote/fetch/free_float.py
    python company/statistics/quote/fetch/free_float.py 000001
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

_BACKEND = Path(__file__).resolve().parents[4]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from core.codes import em_code, normalize_code, safe_str, secid
from core.fmt import fmt_price, fmt_shares, fmt_yi_wan, to_float
from core.http import get_json

_HOSTS = (
    "https://push2delay.eastmoney.com",
    "https://push2.eastmoney.com",
    "https://82.push2.eastmoney.com",
    "https://71.push2.eastmoney.com",
)

_F10_HEADERS = {
    "Accept": "application/json, text/plain, */*",
}

_DC_HEADERS = {"Referer": "https://data.eastmoney.com/"}


def _first_dict(node: Any) -> dict[str, Any]:
    if isinstance(node, list):
        node = node[0] if node else {}
    return node if isinstance(node, dict) else {}


def _end_date(row: dict[str, Any]) -> str:
    return safe_str(row.get("END_DATE"))[:10]


def _push2(code: str) -> dict[str, Any]:
    params = {
        "fltt": "2",
        "invt": "2",
        "fields": "f43,f57,f58,f84,f85,f116,f117,f277",
        "secid": secid(code),
        "ut": "fa5fd1943c7b386f172d6893dbfba10b",
    }
    headers = {"Referer": "https://quote.eastmoney.com/", "Connection": "close"}
    for host in _HOSTS:
        try:
            payload = get_json(
                f"{host}/api/qt/stock/get",
                params=params,
                headers=headers,
                timeout=8,
            ) or {}
        except Exception:  # noqa: BLE001
            continue
        data = payload.get("data")
        if isinstance(data, dict) and data:
            return data
    return {}


def _equity(code: str) -> dict[str, Any]:
    """东财 F10 股本变动，含 ``FREELIQCI_SHARES``（自由流通股本）。"""
    payload = get_json(
        "https://datacenter-web.eastmoney.com/api/data/v1/get",
        params={
            "reportName": "RPT_F10_EH_EQUITY",
            "columns": "ALL",
            "filter": f'(SECURITY_CODE="{code}")',
            "pageNumber": "1",
            "pageSize": "1",
            "sortColumns": "END_DATE",
            "sortTypes": "-1",
            "source": "WEB",
            "client": "WEB",
        },
        headers=_DC_HEADERS,
        timeout=12,
    ) or {}
    rows = (
        ((payload.get("result") or {}) if isinstance(payload.get("result"), dict) else {}).get(
            "data"
        )
        or []
    )
    return rows[0] if rows and isinstance(rows[0], dict) else {}


def _capital(code: str) -> dict[str, Any]:
    em = em_code(code)
    payload = get_json(
        "https://emweb.securities.eastmoney.com/PC_HSF10/CapitalStockStructure/PageAjax",
        params={"code": em},
        headers={
            **_F10_HEADERS,
            "Referer": (
                "https://emweb.securities.eastmoney.com/"
                f"PC_HSF10/CompanySurvey/Index?type=web&code={em}"
            ),
        },
        timeout=15,
    ) or {}
    return _first_dict(payload.get("gbjg"))


def _free_mcap(
    free: float | None,
    price: float | None,
    float_mcap: float | None,
    float_shares: float | None,
) -> float | None:
    if not free or free <= 0:
        return None
    if price is not None:
        return price * free
    if float_mcap is not None and float_shares:
        return float_mcap * (free / float_shares)
    return None


def calc(code: str) -> dict[str, Any]:
    """拉东财自由流通股本 + 现价，算出自由流通股和自由流通市值。"""
    code = normalize_code(code)
    if not code:
        raise ValueError("无效股票代码")

    quote = _push2(code)
    equity = _equity(code)
    capital = {} if equity else _capital(code)

    listed_a = to_float(equity.get("LISTED_A_SHARES")) or to_float(capital.get("LISTED_A_SHARES"))
    unlimited = to_float(equity.get("UNLIMITED_SHARES")) or to_float(capital.get("UNLIMITED_SHARES"))
    float_shares = listed_a or unlimited or to_float(quote.get("f85") or quote.get("f277"))
    total_shares = (
        to_float(equity.get("TOTAL_SHARES"))
        or to_float(capital.get("TOTAL_SHARES"))
        or to_float(quote.get("f84"))
    )
    price = to_float(quote.get("f43"))
    float_mcap = to_float(quote.get("f117"))
    total_mcap = to_float(quote.get("f116"))

    free = to_float(equity.get("FREELIQCI_SHARES"))
    free_mcap = _free_mcap(free, price, float_mcap, float_shares)

    return {
        "code": code,
        "name": safe_str(quote.get("f58")),
        "source": "eastmoney",
        "end_date": _end_date(equity),
        "price": price,
        "price_fmt": fmt_price(price),
        "total_shares": total_shares,
        "total_shares_fmt": fmt_shares(total_shares),
        "listed_a_shares": listed_a,
        "unlimited_shares": unlimited,
        "float_shares": float_shares,
        "float_shares_fmt": fmt_shares(float_shares),
        "float_market_cap": float_mcap,
        "float_market_cap_fmt": fmt_yi_wan(float_mcap, unit_yi=True),
        "total_market_cap": total_mcap,
        "total_market_cap_fmt": fmt_yi_wan(total_mcap, unit_yi=True),
        "free_float_shares": free,
        "free_float_shares_fmt": fmt_shares(free),
        "free_float_market_cap": free_mcap,
        "free_float_market_cap_fmt": fmt_yi_wan(free_mcap, unit_yi=True),
    }


def print_result(data: dict[str, Any]) -> None:
    title = f"{data['code']} {data['name']}".strip()
    print(f"代码 {title}")
    print("口径：东财 FREELIQCI_SHARES（中证自由流通股本）")
    if data["end_date"]:
        print(f"股本报告期 {data['end_date']}")
    print()
    print(f"{'项目':<16}{'数值':<16}原始值")
    print("-" * 64)
    rows = (
        ("现价", data["price_fmt"], data["price"]),
        ("总股本", data["total_shares_fmt"], data["total_shares"]),
        ("流通A股", data["float_shares_fmt"], data["float_shares"]),
        ("自由流通股", data["free_float_shares_fmt"], data["free_float_shares"]),
        ("流通市值", data["float_market_cap_fmt"], data["float_market_cap"]),
        ("总市值", data["total_market_cap_fmt"], data["total_market_cap"]),
        ("自由流通市值", data["free_float_market_cap_fmt"], data["free_float_market_cap"]),
    )
    for label, text, raw in rows:
        raw_text = "" if raw is None else raw
        print(f"{label:<16}{text:<16}{raw_text}")


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass
    try:
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass

    parser = argparse.ArgumentParser(description="计算自由流通股和自由流通市值")
    parser.add_argument("code", nargs="?", default="600990")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    code = normalize_code(args.code)
    try:
        data = calc(code)
    except Exception as exc:  # noqa: BLE001
        print(f"计算失败: {exc}", file=sys.stderr)
        return 1
    if data.get("free_float_shares") is None:
        print(f"未算出自由流通股: {code}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
    else:
        print_result(data)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
