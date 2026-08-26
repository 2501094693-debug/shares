"""计算自由流通股、自由流通市值。

口径与盘口编排层一致：流通 A 股 − 持股 ≥5% 的流通股东（剔除港股通）。
自由流通市值 = 现价 × 自由流通股；没有现价时按流通市值等比折算。

    python company/statistics/free_float.py
    python company/statistics/free_float.py 000001
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

_BACKEND = Path(__file__).resolve().parents[2]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from core.codes import em_code, normalize_code, safe_str, secid
from core.fmt import fmt_price, fmt_shares, fmt_yi_wan, to_float
from core.http import get_json

# 港股通持仓不计入「持股 ≥5% 扣除」，以匹配东财自由流通口径
_FREE_FLOAT_SKIP_NAMES = ("香港中央结算", "香港中央結算")

_HOSTS = (
    "https://push2delay.eastmoney.com",
    "https://push2.eastmoney.com",
    "https://82.push2.eastmoney.com",
    "https://71.push2.eastmoney.com",
)

_F10_HEADERS = {
    "Accept": "application/json, text/plain, */*",
}


def _first_dict(node: Any) -> dict[str, Any]:
    if isinstance(node, list):
        node = node[0] if node else {}
    return node if isinstance(node, dict) else {}


def _end_date(row: dict[str, Any]) -> str:
    return safe_str(row.get("END_DATE"))[:10]


def _latest_holders(rows: list[Any]) -> tuple[str, list[dict[str, Any]]]:
    """十大流通股东接口偶发带多期，只取最近报告期，避免重复扣除。"""
    holders = [row for row in rows if isinstance(row, dict)]
    dates = [_end_date(row) for row in holders if _end_date(row)]
    latest = max(dates) if dates else ""
    if latest:
        holders = [row for row in holders if _end_date(row) == latest]
    return latest, holders


def _deduct_shares(
    hold: float | None,
    ratio: float | None,
    float_shares: float | None,
) -> float:
    """大股东扣除股数。

    十大流通股东的 ``HOLD_NUM`` 有时按 A+H 总流通计（如建设银行汇金），
    而自由流通分母用的是流通 A 股。直接相减会得到负数并被夹成 0。
    持股数大于流通 A 股时，改按占流通比折到 A 股口径。
    """
    if hold is None or hold <= 0:
        return 0.0
    if float_shares and hold > float_shares:
        if ratio is not None and ratio > 0:
            return float_shares * (ratio / 100.0)
        return 0.0
    return hold


def _holder_row(row: dict[str, Any]) -> dict[str, Any]:
    name = safe_str(row.get("HOLDER_NAME"))
    hold = to_float(row.get("HOLD_NUM"))
    ratio = to_float(row.get("FREE_HOLDNUM_RATIO"))
    skip = any(token in name for token in _FREE_FLOAT_SKIP_NAMES)
    deduct = (not skip) and ratio is not None and ratio >= 5 and hold is not None
    return {
        "name": name,
        "hold_num": hold,
        "ratio": ratio,
        "skip_hkconnect": skip,
        "deduct": deduct,
        "hold_num_fmt": fmt_shares(hold),
        "ratio_fmt": f"{ratio:.2f}%" if ratio is not None else "",
    }


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


def _shareholders(code: str) -> list[Any]:
    em = em_code(code)
    payload = get_json(
        "https://emweb.securities.eastmoney.com/PC_HSF10/ShareholderResearch/PageAjax",
        params={"code": em},
        headers={
            **_F10_HEADERS,
            "Referer": (
                "https://emweb.securities.eastmoney.com/"
                f"PC_HSF10/ShareholderResearch/Index?type=web&code={em}"
            ),
        },
        timeout=15,
    ) or {}
    rows = payload.get("sdltgd") or []
    return rows if isinstance(rows, list) else []


def calc(code: str) -> dict[str, Any]:
    """拉股本 + 十大流通股东 + 现价，算出自由流通股和自由流通市值。"""
    code = normalize_code(code)
    if not code:
        raise ValueError("无效股票代码")

    quote = _push2(code)
    capital = _capital(code)
    latest, holders_raw = _latest_holders(_shareholders(code))

    listed_a = to_float(capital.get("LISTED_A_SHARES"))
    unlimited = to_float(capital.get("UNLIMITED_SHARES"))
    float_shares = listed_a or unlimited or to_float(quote.get("f85") or quote.get("f277"))
    total_shares = to_float(capital.get("TOTAL_SHARES")) or to_float(quote.get("f84"))
    price = to_float(quote.get("f43"))
    float_mcap = to_float(quote.get("f117"))
    total_mcap = to_float(quote.get("f116"))

    holders = [_holder_row(row) for row in holders_raw]
    deducted = [row for row in holders if row["deduct"]]
    skipped = [row for row in holders if row["skip_hkconnect"]]
    big = sum(
        _deduct_shares(row["hold_num"], row["ratio"], float_shares) for row in deducted
    )
    free = max(float_shares - big, 0) if float_shares is not None else None
    if (not free) and float_shares:
        free = float_shares

    free_mcap = None
    if free and free > 0:
        if price is not None:
            free_mcap = price * free
        elif float_mcap is not None and float_shares:
            free_mcap = float_mcap * (free / float_shares)

    return {
        "code": code,
        "name": safe_str(quote.get("f58")),
        "end_date": latest,
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
        "holders": holders,
        "deducted": deducted,
        "skipped": skipped,
        "big_hold": big,
        "big_hold_fmt": fmt_shares(big),
        "free_float_shares": free,
        "free_float_shares_fmt": fmt_shares(free),
        "free_float_market_cap": free_mcap,
        "free_float_market_cap_fmt": fmt_yi_wan(free_mcap, unit_yi=True),
    }


def print_result(data: dict[str, Any]) -> None:
    title = f"{data['code']} {data['name']}".strip()
    print(f"代码 {title}")
    print("口径：流通A股 − 持股≥5%（剔除港股通）")
    if data["end_date"]:
        print(f"股东报告期 {data['end_date']}")
    print()
    print(f"{'项目':<16}{'数值':<16}原始值")
    print("-" * 64)
    rows = (
        ("现价", data["price_fmt"], data["price"]),
        ("总股本", data["total_shares_fmt"], data["total_shares"]),
        ("流通A股", data["float_shares_fmt"], data["float_shares"]),
        ("≥5%扣除", data["big_hold_fmt"], data["big_hold"]),
        ("自由流通股", data["free_float_shares_fmt"], data["free_float_shares"]),
        ("流通市值", data["float_market_cap_fmt"], data["float_market_cap"]),
        ("总市值", data["total_market_cap_fmt"], data["total_market_cap"]),
        ("自由流通市值", data["free_float_market_cap_fmt"], data["free_float_market_cap"]),
    )
    for label, text, raw in rows:
        raw_text = "" if raw is None else raw
        print(f"{label:<16}{text:<16}{raw_text}")

    print("\n[十大流通股东]")
    print(f"{'操作':<10}{'持股':<14}{'占流通比':<12}股东")
    print("-" * 64)
    for row in data["holders"]:
        if row["deduct"]:
            action = "扣除"
        elif row["skip_hkconnect"]:
            action = "跳过港股通"
        else:
            action = "保留"
        print(f"{action:<10}{row['hold_num_fmt']:<14}{row['ratio_fmt']:<12}{row['name']}")


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
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
