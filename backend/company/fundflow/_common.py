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


def _request_hosts(
    hosts: tuple[str, ...],
    path: str,
    *,
    params: dict[str, Any],
    timeout: int | tuple[float, float] = 15,
    label: str,
) -> dict[str, Any]:
    last_error: Exception | None = None
    for host in hosts:
        try:
            payload = get_json(
                f"{host}{path}",
                params=params,
                headers=_HEADERS,
                timeout=timeout,
            )
            if isinstance(payload, dict):
                return payload
            last_error = RuntimeError(f"东财{label}返回非 JSON")
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            logger.info("fundflow %s skip %s: %s", label, host, exc)
    raise RuntimeError(f"东财{label}失败: {last_error}")


def request_his(path: str, *, params: dict[str, Any], timeout: int | tuple[float, float] = 15) -> dict[str, Any]:
    return _request_hosts(_HIS_HOSTS, path, params=params, timeout=timeout, label="历史资金流")


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
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    cap = max(1, min(int(limit or 120), 10000))
    params: dict[str, Any] = {
        "secid": secid,
        "klt": str(klt),
        "lmt": str(cap),
        "fields1": _FIELDS1,
        "fields2": fields2,
        "ut": _UT,
    }
    path = "/api/qt/stock/fflow/daykline/get" if use_his else "/api/qt/stock/fflow/kline/get"
    request_fn = request_his if use_his else request_push2
    items: list[dict[str, Any]] = []
    meta = {"code": "", "name": ""}
    for attempt in range(5):
        try:
            payload = request_fn(path, params=params)
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
    if len(items) > cap:
        items = items[-cap:]
    return items, meta
