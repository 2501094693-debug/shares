"""东财个股资金流向：请求、解析与字段映射。"""

from __future__ import annotations

import logging
import time
from typing import Any, Callable

from core.http import get_json

logger = logging.getLogger(__name__)

_UT = "b2884a393a59ad64002292a3e90d46a5"
_HEADERS = {
    "Referer": "https://data.eastmoney.com/zjlx/",
    "Accept": "application/json, text/plain, */*",
}

# push2his 才有完整日线；delay / push2 的 daykline 经常只给最新一根。
_HIS_HOSTS = (
    "https://push2his.eastmoney.com",
    "https://push2delay.eastmoney.com",
    "https://push2.eastmoney.com",
)
_PUSH2_HOSTS = (
    "https://push2delay.eastmoney.com",
    "https://push2.eastmoney.com",
    "https://71.push2.eastmoney.com",
    "https://82.push2.eastmoney.com",
)

# f51 日期；f52-f56 主力/小/中/大/超大单净流入；f57-f61 各档净占比
_DAILY_FIELDS2 = "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61"
_MINUTE_FIELDS2 = "f51,f52,f53,f54,f55,f56,f57"
_FIELDS1 = "f1,f2,f3,f7"
_SNAPSHOT_FIELDS = "f62,f184,f66,f69,f72,f75,f78,f81,f84,f87,f14"
_DC_FUNDFLOW_URL = "https://datacenter-web.eastmoney.com/api/data/v1/get"
_DC_FUNDFLOW_REPORT = "RPT_DMSK_TS_FUNDFLOW"
_WAN_YUAN = 10000.0


def _dash_to_none(value: Any) -> Any:
    if value in {"-", "--", ""}:
        return None
    return value


def to_flow_float(value: Any) -> float | None:
    """资金流金额：保留大额负数，不按盘口哨兵值过滤。"""
    value = _dash_to_none(value)
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number:
        return None
    return number


def _float_at(parts: list[str], idx: int) -> float | None:
    if idx >= len(parts):
        return None
    return to_flow_float(parts[idx])


def parse_daily_line(line: str) -> dict[str, Any] | None:
    parts = str(line or "").split(",")
    if len(parts) < 7:
        return None
    time_s = parts[0].strip()
    if not time_s:
        return None
    return {
        "time": time_s,
        "main_net": _float_at(parts, 1),
        "small_net": _float_at(parts, 2),
        "mid_net": _float_at(parts, 3),
        "big_net": _float_at(parts, 4),
        "super_net": _float_at(parts, 5),
        "main_net_pct": _float_at(parts, 6),
        "small_net_pct": _float_at(parts, 7),
        "mid_net_pct": _float_at(parts, 8),
        "big_net_pct": _float_at(parts, 9),
        "super_net_pct": _float_at(parts, 10),
    }


def parse_minute_line(line: str) -> dict[str, Any] | None:
    parts = str(line or "").split(",")
    if len(parts) < 7:
        return None
    time_s = parts[0].strip()
    if not time_s:
        return None
    return {
        "time": time_s,
        "main_net": _float_at(parts, 1),
        "small_net": _float_at(parts, 2),
        "mid_net": _float_at(parts, 3),
        "big_net": _float_at(parts, 4),
        "super_net": _float_at(parts, 5),
        "main_net_pct": _float_at(parts, 6),
    }


def parse_snapshot_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "main_net": to_flow_float(row.get("f62")),
        "main_net_pct": to_flow_float(row.get("f184")),
        "super_net": to_flow_float(row.get("f66")),
        "super_net_pct": to_flow_float(row.get("f69")),
        "big_net": to_flow_float(row.get("f72")),
        "big_net_pct": to_flow_float(row.get("f75")),
        "mid_net": to_flow_float(row.get("f78")),
        "mid_net_pct": to_flow_float(row.get("f81")),
        "small_net": to_flow_float(row.get("f84")),
        "small_net_pct": to_flow_float(row.get("f87")),
    }


def _yuan_from_wan(value: Any) -> float | None:
    number = to_flow_float(value)
    if number is None:
        return None
    return round(number * _WAN_YUAN, 2)


def parse_datacenter_row(row: dict[str, Any]) -> dict[str, Any] | None:
    if not isinstance(row, dict):
        return None
    time_s = str(row.get("TRADE_DATE") or "").strip()[:10]
    if len(time_s) < 10:
        return None
    return {
        "time": time_s,
        "main_net": _yuan_from_wan(row.get("NET_INFLOW")),
        "small_net": _yuan_from_wan(row.get("SMALLDEAL_NET")),
        "mid_net": _yuan_from_wan(row.get("MIDDEAL_NET")),
        "big_net": _yuan_from_wan(row.get("BIGDEAL_NET")),
        "super_net": _yuan_from_wan(row.get("SUPERDEAL_NET")),
        "main_net_pct": to_flow_float(row.get("NET_INFLOW_RATIO")),
        "small_net_pct": to_flow_float(row.get("SMALLDEAL_NET_RATIO")),
        "mid_net_pct": to_flow_float(row.get("MIDDEAL_NET_RATIO")),
        "big_net_pct": to_flow_float(row.get("BIGDEAL_NET_RATIO")),
        "super_net_pct": to_flow_float(row.get("SUPERDEAL_NET_RATIO")),
    }


def _code_from_secid(secid: str) -> str:
    text = str(secid or "").strip()
    if "." in text:
        return text.split(".", 1)[1]
    return text


def fetch_datacenter_daily(code: str, *, limit: int = 120) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """东财数据中心个股资金流历史。金额字段为万元，这里换成元。"""
    cap = max(1, min(int(limit or 120), 500))
    norm = str(code or "").strip()
    meta = {"code": norm, "name": ""}
    if not norm:
        return [], meta
    payload = get_json(
        _DC_FUNDFLOW_URL,
        params={
            "reportName": _DC_FUNDFLOW_REPORT,
            "columns": "ALL",
            "filter": f'(SECURITY_CODE="{norm}")',
            "pageNumber": "1",
            "pageSize": str(cap),
            "sortColumns": "TRADE_DATE",
            "sortTypes": "-1",
            "source": "WEB",
            "client": "WEB",
        },
        headers=_HEADERS,
        timeout=15,
        retries=1,
    )
    result = payload.get("result") if isinstance(payload, dict) else None
    rows = (result or {}).get("data") if isinstance(result, dict) else None
    items: list[dict[str, Any]] = []
    for row in rows or []:
        parsed = parse_datacenter_row(row if isinstance(row, dict) else {})
        if parsed:
            items.append(parsed)
            if not meta["name"]:
                meta["name"] = str(row.get("SECURITY_NAME_ABBR") or "").strip()
            if not meta["code"]:
                meta["code"] = str(row.get("SECURITY_CODE") or "").strip()
    items.sort(key=lambda d: str(d.get("time") or ""))
    if len(items) > cap:
        items = items[-cap:]
    return items, meta


def _klines_count(payload: dict[str, Any]) -> int:
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    klines = data.get("klines")
    return len(klines) if isinstance(klines, list) else 0


def _request_hosts(
    hosts: tuple[str, ...],
    path: str,
    *,
    params: dict[str, Any],
    timeout: int | tuple[float, float] = 15,
    label: str,
    min_klines: int = 0,
) -> dict[str, Any]:
    last_error: Exception | None = None
    best: dict[str, Any] | None = None
    best_n = -1
    for host in hosts:
        try:
            payload = get_json(
                f"{host}{path}",
                params=params,
                headers=_HEADERS,
                timeout=timeout,
            )
            if not isinstance(payload, dict):
                last_error = RuntimeError(f"东财{label}返回非 JSON")
                continue
            n = _klines_count(payload)
            if n > best_n:
                best = payload
                best_n = n
            if min_klines <= 0 or n >= min_klines:
                return payload
            logger.info("fundflow %s skip %s: only %s klines", label, host, n)
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            logger.info("fundflow %s skip %s: %s", label, host, exc)
    if best is not None:
        return best
    raise RuntimeError(f"东财{label}失败: {last_error}")


def request_his(
    path: str,
    *,
    params: dict[str, Any],
    timeout: int | tuple[float, float] = 15,
    min_klines: int = 0,
) -> dict[str, Any]:
    return _request_hosts(
        _HIS_HOSTS,
        path,
        params=params,
        timeout=timeout,
        label="历史资金流",
        min_klines=min_klines,
    )


def request_push2(path: str, *, params: dict[str, Any], timeout: int | tuple[float, float] = 15) -> dict[str, Any]:
    return _request_hosts(_PUSH2_HOSTS, path, params=params, timeout=timeout, label="实时资金流")


def fetch_fflow_klines(
    *,
    secid: str,
    klt: int,
    limit: int,
    fields2: str,
    parser: Callable[[str], dict[str, Any] | None],
    use_his: bool = True,
    code: str = "",
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    cap = max(1, min(int(limit or 120), 10000))
    params: dict[str, Any] = {
        "secid": secid,
        "klt": str(klt),
        "lmt": "0" if use_his else str(cap),
        "fields1": _FIELDS1,
        "fields2": fields2,
        "ut": _UT,
    }
    path = "/api/qt/stock/fflow/daykline/get" if use_his else "/api/qt/stock/fflow/kline/get"
    items: list[dict[str, Any]] = []
    meta = {"code": "", "name": ""}
    for attempt in range(5):
        try:
            if use_his:
                payload = request_his(path, params=params, min_klines=2 if cap > 1 else 0)
            else:
                payload = request_push2(path, params=params)
            data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
            meta = {
                "code": str(data.get("code") or "").strip(),
                "name": str(data.get("name") or "").strip(),
            }
            items = []
            for line in data.get("klines") or []:
                row = parser(str(line))
                if row:
                    items.append(row)
            if items:
                break
        except Exception as exc:  # noqa: BLE001
            logger.info("fundflow klines retry %s/%s: %s", attempt + 1, 5, exc)
        if attempt < 4:
            time.sleep(0.5 * (attempt + 1))
    if use_his and cap > 1 and len(items) <= 1:
        dc_code = (code or meta.get("code") or _code_from_secid(secid)).strip()
        try:
            dc_items, dc_meta = fetch_datacenter_daily(dc_code, limit=cap)
        except Exception as exc:  # noqa: BLE001
            logger.info("fundflow datacenter fallback failed: %s", exc)
            dc_items, dc_meta = [], {}
        if len(dc_items) > len(items):
            logger.info("fundflow datacenter fallback %s: %s bars", dc_code, len(dc_items))
            items = dc_items
            meta = {
                "code": dc_meta.get("code") or meta.get("code") or dc_code,
                "name": dc_meta.get("name") or meta.get("name") or "",
            }
    if len(items) > cap:
        items = items[-cap:]
    return items, meta
