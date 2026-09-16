"""Probe Tonghuashun mobile big-capital-movement APIs for 603259."""
from __future__ import annotations

import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

CODE = "603259"
UA = (
    "Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Mobile Safari/537.36 "
    "Hexin_Gphone/11.20.40 (Phone; Android 13; zh)"
)
TARGETS = ["10:28:13", "1255", "2986", "1138", "1700", "1208"]


def fetch(url: str, *, referer: str = "") -> tuple[int, str]:
    headers = {
        "User-Agent": UA,
        "Accept": "application/json, text/html, */*",
        "Referer": referer or f"https://stockpage.10jqka.com.cn/{CODE}/",
    }
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=12) as resp:
            return resp.status, resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace") if exc.fp else ""
        return exc.code, body
    except Exception as exc:
        return -1, str(exc)


def hit(text: str) -> bool:
    return any(t in text for t in TARGETS)


def probe_sp_service() -> None:
    print("=== spService ===")
    paths = [
        "Funds/realFunds",
        "Funds/lineFunds",
        "Funds/bigFunds",
        "Funds/largeFunds",
        "Funds/ddzz",
        "Funds/ddFunds",
        "Funds/bigOrder",
        "Funds/bigOrderList",
        "Funds/largeOrder",
        "Funds/largeOrderList",
        "Funds/ddzzList",
        "Funds/bigDeal",
        "Funds/bigDealList",
        "Funds/capitalMove",
        "Funds/capitalMovement",
        "Funds/largeCapital",
        "Funds/largeCapitalMove",
        "Funds/largeCapitalMovement",
        "Funds/orderList",
        "Funds/tradeList",
        "Funds/bigTrade",
        "Funds/bigTradeList",
        "Funds/ddList",
        "Funds/ddOrder",
        "Funds/ddOrderList",
        "Funds/zjlx",
        "Funds/dd",
        "Funds/ddzj",
        "Funds/ddzjlx",
        "Funds/ddzzFunds",
        "Funds/ddzzFlow",
        "Funds/ddzzOrder",
        "Funds/ddzzOrders",
        "Funds/ddzzListV2",
        "Funds/ddzzListV3",
        "Funds/ddzzDetail",
        "Funds/ddzzDetails",
        "Funds/ddzzData",
        "Funds/ddzzInfo",
        "Funds/ddzzReal",
        "Funds/ddzzRealTime",
        "Funds/ddzzRealFunds",
        "Funds/ddzzRealOrder",
        "Funds/ddzzRealOrders",
        "Funds/ddzzRealList",
        "Funds/ddzzRealData",
        "Funds/ddzzRealInfo",
        "Funds/ddzzRealDetail",
        "Funds/ddzzRealDetails",
        "Funds/ddzzRealFlow",
        "Funds/ddzzRealFundsFlow",
        "Funds/ddzzRealFundsList",
        "Funds/ddzzRealFundsData",
        "Funds/ddzzRealFundsInfo",
        "Funds/ddzzRealFundsDetail",
        "Funds/ddzzRealFundsDetails",
        "Funds/ddzzRealFundsFlowList",
        "Funds/ddzzRealFundsFlowData",
        "Funds/ddzzRealFundsFlowInfo",
        "Funds/ddzzRealFundsFlowDetail",
        "Funds/ddzzRealFundsFlowDetails",
        "Funds/ddzzRealFundsFlowOrder",
        "Funds/ddzzRealFundsFlowOrders",
        "Funds/ddzzRealFundsFlowListV2",
        "Funds/ddzzRealFundsFlowListV3",
        "Funds/ddzzRealFundsFlowListV4",
        "Funds/ddzzRealFundsFlowListV5",
        "Funds/ddzzRealFundsFlowListV6",
        "Funds/ddzzRealFundsFlowListV7",
        "Funds/ddzzRealFundsFlowListV8",
        "Funds/ddzzRealFundsFlowListV9",
        "Funds/ddzzRealFundsFlowListV10",
    ]
    for path in paths:
        url = f"https://stockpage.10jqka.com.cn/spService/{CODE}/{path}"
        status, text = fetch(url)
        if status == 200 and len(text) > 20:
            marker = "HIT" if hit(text) else "ok"
            print(f"{marker:4} {path:40} len={len(text)} {text[:120].replace(chr(10), ' ')}")


def probe_fuyao() -> None:
    print("=== fuyao ===")
    bases = [
        "https://dq.10jqka.com.cn/fuyao/fundflow/stock/v1",
        "https://dq.10jqka.com.cn/fuyao/capital_flow/stock/v1",
        "https://dq.10jqka.com.cn/fuyao/stock_fund/v1",
        "https://dq.10jqka.com.cn/fuyao/stock_fund_flow/v1",
        "https://dq.10jqka.com.cn/fuyao/stock_capital/v1",
        "https://dq.10jqka.com.cn/fuyao/capital_move/v1",
        "https://dq.10jqka.com.cn/fuyao/large_order/v1",
        "https://dq.10jqka.com.cn/fuyao/big_order/v1",
        "https://dq.10jqka.com.cn/fuyao/ddzz/v1",
        "https://dq.10jqka.com.cn/fuyao/stock_capital_flow/v1",
        "https://dq.10jqka.com.cn/fuyao/stock_capital_move/v1",
        "https://dq.10jqka.com.cn/fuyao/stock_large_order/v1",
        "https://dq.10jqka.com.cn/fuyao/stock_big_order/v1",
        "https://dq.10jqka.com.cn/fuyao/stock_ddzz/v1",
        "https://dq.10jqka.com.cn/fuyao/stock_ddzz_flow/v1",
        "https://dq.10jqka.com.cn/fuyao/stock_ddzz_list/v1",
        "https://dq.10jqka.com.cn/fuyao/stock_ddzz_order/v1",
        "https://dq.10jqka.com.cn/fuyao/stock_ddzz_orders/v1",
        "https://dq.10jqka.com.cn/fuyao/stock_ddzz_detail/v1",
        "https://dq.10jqka.com.cn/fuyao/stock_ddzz_details/v1",
        "https://dq.10jqka.com.cn/fuyao/stock_ddzz_real/v1",
        "https://dq.10jqka.com.cn/fuyao/stock_ddzz_realtime/v1",
        "https://dq.10jqka.com.cn/fuyao/stock_ddzz_real_time/v1",
        "https://dq.10jqka.com.cn/fuyao/stock_ddzz_real_funds/v1",
        "https://dq.10jqka.com.cn/fuyao/stock_ddzz_real_funds_flow/v1",
        "https://dq.10jqka.com.cn/fuyao/stock_ddzz_real_funds_list/v1",
        "https://dq.10jqka.com.cn/fuyao/stock_ddzz_real_funds_data/v1",
        "https://dq.10jqka.com.cn/fuyao/stock_ddzz_real_funds_info/v1",
        "https://dq.10jqka.com.cn/fuyao/stock_ddzz_real_funds_detail/v1",
        "https://dq.10jqka.com.cn/fuyao/stock_ddzz_real_funds_details/v1",
        "https://dq.10jqka.com.cn/fuyao/stock_ddzz_real_funds_flow_list/v1",
        "https://dq.10jqka.com.cn/fuyao/stock_ddzz_real_funds_flow_data/v1",
        "https://dq.10jqka.com.cn/fuyao/stock_ddzz_real_funds_flow_info/v1",
        "https://dq.10jqka.com.cn/fuyao/stock_ddzz_real_funds_flow_detail/v1",
        "https://dq.10jqka.com.cn/fuyao/stock_ddzz_real_funds_flow_details/v1",
        "https://dq.10jqka.com.cn/fuyao/stock_ddzz_real_funds_flow_order/v1",
        "https://dq.10jqka.com.cn/fuyao/stock_ddzz_real_funds_flow_orders/v1",
        "https://dq.10jqka.com.cn/fuyao/stock_ddzz_real_funds_flow_list_v2/v1",
        "https://dq.10jqka.com.cn/fuyao/stock_ddzz_real_funds_flow_list_v3/v1",
        "https://dq.10jqka.com.cn/fuyao/stock_ddzz_real_funds_flow_list_v4/v1",
        "https://dq.10jqka.com.cn/fuyao/stock_ddzz_real_funds_flow_list_v5/v1",
        "https://dq.10jqka.com.cn/fuyao/stock_ddzz_real_funds_flow_list_v6/v1",
        "https://dq.10jqka.com.cn/fuyao/stock_ddzz_real_funds_flow_list_v7/v1",
        "https://dq.10jqka.com.cn/fuyao/stock_ddzz_real_funds_flow_list_v8/v1",
        "https://dq.10jqka.com.cn/fuyao/stock_ddzz_real_funds_flow_list_v9/v1",
        "https://dq.10jqka.com.cn/fuyao/stock_ddzz_real_funds_flow_list_v10/v1",
    ]
    suffixes = [
        "get",
        "list",
        "big_order",
        "big_order_list",
        "large_order",
        "large_order_list",
        "ddzz",
        "ddzz_list",
        "capital_move",
        "capital_movement",
        "large_capital_movement",
        "order_list",
        "trade_list",
        "detail",
        "details",
        "real",
        "realtime",
        "real_time",
        "real_funds",
        "real_funds_flow",
        "real_funds_list",
        "real_funds_data",
        "real_funds_info",
        "real_funds_detail",
        "real_funds_details",
        "real_funds_flow_list",
        "real_funds_flow_data",
        "real_funds_flow_info",
        "real_funds_flow_detail",
        "real_funds_flow_details",
        "real_funds_flow_order",
        "real_funds_flow_orders",
        "real_funds_flow_list_v2",
        "real_funds_flow_list_v3",
        "real_funds_flow_list_v4",
        "real_funds_flow_list_v5",
        "real_funds_flow_list_v6",
        "real_funds_flow_list_v7",
        "real_funds_flow_list_v8",
        "real_funds_flow_list_v9",
        "real_funds_flow_list_v10",
    ]
    for base in bases:
        for suf in suffixes:
            url = f"{base}/{suf}?code={CODE}"
            status, text = fetch(url)
            if status == 200 and len(text) > 30 and "404" not in text and "Not Found" not in text:
                marker = "HIT" if hit(text) else "ok"
                print(f"{marker:4} {url} {text[:120].replace(chr(10), ' ')}")


def probe_ddzz_stock_urls() -> None:
    print("=== ddzz stock urls ===")
    urls = [
        f"http://data.10jqka.com.cn/funds/ddzz/stock/{CODE}/field/time/order/desc/ajax/1/free/1/",
        f"http://data.10jqka.com.cn/funds/ddzz/stock/{CODE}/ajax/1/free/1/",
        f"http://data.10jqka.com.cn/funds/ddzz/stock/{CODE}/ajax/1/",
        f"http://data.10jqka.com.cn/funds/ddzz/stock/{CODE}/",
        f"http://data.10jqka.com.cn/funds/ddzz/stock/{CODE}/field/time/order/desc/page/1/ajax/1/free/1/",
        f"http://data.10jqka.com.cn/funds/ddzz/stock/{CODE}/field/time/order/desc/page/2/ajax/1/free/1/",
        f"http://data.10jqka.com.cn/funds/ddzz/stock/{CODE}/field/time/order/desc/page/3/ajax/1/free/1/",
        f"http://data.10jqka.com.cn/funds/ddzz/stock/{CODE}/field/time/order/desc/page/4/ajax/1/free/1/",
        f"http://data.10jqka.com.cn/funds/ddzz/stock/{CODE}/field/time/order/desc/page/5/ajax/1/free/1/",
        f"http://data.10jqka.com.cn/funds/ddzz/stock/{CODE}/field/time/order/desc/page/6/ajax/1/free/1/",
        f"http://data.10jqka.com.cn/funds/ddzz/stock/{CODE}/field/time/order/desc/page/7/ajax/1/free/1/",
        f"http://data.10jqka.com.cn/funds/ddzz/stock/{CODE}/field/time/order/desc/page/8/ajax/1/free/1/",
        f"http://data.10jqka.com.cn/funds/ddzz/stock/{CODE}/field/time/order/desc/page/9/ajax/1/free/1/",
        f"http://data.10jqka.com.cn/funds/ddzz/stock/{CODE}/field/time/order/desc/page/10/ajax/1/free/1/",
        f"http://data.10jqka.com.cn/funds/ddzz/stock/{CODE}/field/time/order/desc/page/11/ajax/1/free/1/",
        f"http://data.10jqka.com.cn/funds/ddzz/stock/{CODE}/field/time/order/desc/page/12/ajax/1/free/1/",
        f"http://data.10jqka.com.cn/funds/ddzz/stock/{CODE}/field/time/order/desc/page/13/ajax/1/free/1/",
        f"http://data.10jqka.com.cn/funds/ddzz/stock/{CODE}/field/time/order/desc/page/14/ajax/1/free/1/",
        f"http://data.10jqka.com.cn/funds/ddzz/stock/{CODE}/field/time/order/desc/page/15/ajax/1/free/1/",
        f"http://data.10jqka.com.cn/funds/ddzz/stock/{CODE}/field/time/order/desc/page/16/ajax/1/free/1/",
        f"http://data.10jqka.com.cn/funds/ddzz/stock/{CODE}/field/time/order/desc/page/17/ajax/1/free/1/",
        f"http://data.10jqka.com.cn/funds/ddzz/stock/{CODE}/field/time/order/desc/page/18/ajax/1/free/1/",
        f"http://data.10jqka.com.cn/funds/ddzz/stock/{CODE}/field/time/order/desc/page/19/ajax/1/free/1/",
        f"http://data.10jqka.com.cn/funds/ddzz/stock/{CODE}/field/time/order/desc/page/20/ajax/1/free/1/",
    ]
    for url in urls:
        status, text = fetch(url, referer=f"http://data.10jqka.com.cn/funds/ddzz/stock/{CODE}/")
        if status != 200:
            print("ERR", status, url)
            continue
        count_603259 = text.count(CODE)
        has_target = hit(text)
        if count_603259 or has_target:
            print(f"HIT code={count_603259} target={has_target} {url}")
            if has_target:
                print(text[:500])


def scan_ddzz_pages_for_code() -> None:
    print("=== scan ddzz pages for 603259 ===")
    try:
        from company.statistics.fundflow.tonghuashun._hexin import make_hexin_v
    except Exception as exc:
        print("hexin import failed:", exc)
        make_hexin_v = lambda: ""

    headers = {
        "User-Agent": UA,
        "Accept": "text/html, */*; q=0.01",
        "Referer": f"http://data.10jqka.com.cn/funds/ddzz/stock/{CODE}/",
        "X-Requested-With": "XMLHttpRequest",
        "hexin-v": make_hexin_v(),
    }

    def page_url(page: int) -> str:
        if page == 1:
            return (
                f"http://data.10jqka.com.cn/funds/ddzz/stock/{CODE}"
                f"/field/time/order/desc/ajax/1/free/1/"
            )
        return (
            f"http://data.10jqka.com.cn/funds/ddzz/stock/{CODE}"
            f"/field/time/order/desc/page/{page}/ajax/1/free/1/"
        )

    found = []
    for page in range(1, 51):
        req = urllib.request.Request(page_url(page), headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                html = resp.read().decode("gbk", "replace")
        except Exception as exc:
            print("page", page, "error", exc)
            break
        if CODE not in html:
            continue
        rows = re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.S)
        for row in rows:
            if CODE not in row:
                continue
            cells = [
                re.sub(r"<[^>]+>", "", cell).strip()
                for cell in re.findall(r"<td[^>]*>(.*?)</td>", row, re.S)
            ]
            if len(cells) >= 6:
                found.append({"page": page, "cells": cells[:9]})
        if len(found) >= 20:
            break
    print("found rows:", len(found))
    for item in found[:15]:
        print(json.dumps(item, ensure_ascii=False))


if __name__ == "__main__":
    probe_sp_service()
    probe_fuyao()
    probe_ddzz_stock_urls()
    scan_ddzz_pages_for_code()
