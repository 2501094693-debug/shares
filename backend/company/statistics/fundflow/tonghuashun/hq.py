"""同花顺 Hexin HQ：个股大单（主动/被动）。

手机「大资金动向」走行情 TCP（hevo / zipversion=3）。本模块通过 HQ 原生库
``big_order_flow`` 按股票查询，不再扫全市场 HTTP。
"""

from __future__ import annotations

import atexit
import ctypes as c
import hashlib
import json
import logging
import os
import random
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from core.codes import detect_market, normalize_code
from core.fmt import to_float

logger = logging.getLogger(__name__)

_TZ = timezone(timedelta(hours=8))
_DLL_NAME = "hexin_hq17.dll"
_RATE_SEC = 0.025
_CONNECT_BUFFER = 32 * 1024
_QUERY_BUFFER = 8 * 1024 * 1024
_CONNECT_ATTEMPTS = 8
_FIELD_TIME = "1"
_FIELD_DIR = "12"
_FIELD_VOLUME = "13"
_FIELD_AMOUNT = "19"
_DIR_MAP = {
    1: ("active", "buy", "主", "特大主动买"),
    -1: ("active", "sell", "主", "特大主动卖"),
    2: ("passive", "buy", "被", "特大被动买"),
    -2: ("passive", "sell", "被", "特大被动卖"),
}
_MAC_SEED = b"thsdk-account-mac-v1\0"


def hq_security(code: str) -> str:
    """HQ 证券代码，如 ``USZA001309`` / ``USHA603259``。"""
    norm = normalize_code(code)
    if not norm:
        return ""
    market = detect_market(norm)
    if market == "szse":
        prefix = "USZA"
    elif market == "bse":
        prefix = "USTM"
    else:
        prefix = "USHA"
    return f"{prefix}{norm}"


def _dll_path() -> Path:
    override = os.getenv("THS_HQ_DLL")
    if override:
        return Path(override).expanduser()
    native = Path(__file__).resolve().parent / "native"
    named = native / _DLL_NAME
    if named.is_file():
        return named
    return native / "hq.dll"


def _mac_for(username: str) -> str:
    digest = hashlib.sha256(_MAC_SEED + username.encode("utf-8")).digest()
    octets = bytearray(digest[:6])
    octets[0] = (octets[0] & 0xFC) | 0x02
    return ":".join(f"{value:02x}" for value in octets)


def _guest_pool() -> list[tuple[str, str, str]]:
    try:
        from thsdk._temporary_accounts import _TEMPORARY_ACCOUNT_ITEMS, _TEMPORARY_ACCOUNT_PREFIX
    except Exception:  # noqa: BLE001
        return []
    return [
        (f"{_TEMPORARY_ACCOUNT_PREFIX}{suffix}", password, mac)
        for suffix, password, mac in _TEMPORARY_ACCOUNT_ITEMS
    ]


def _credential_candidates() -> list[tuple[str, str, str]]:
    username = os.getenv("THS_USERNAME")
    password = os.getenv("THS_PASSWORD")
    if username and password:
        mac = os.getenv("THS_MAC") or _mac_for(username)
        return [(username, password, mac)]
    guests = _guest_pool()
    if not guests:
        raise RuntimeError("未配置 THS_USERNAME/THS_PASSWORD，且无法获取临时行情账号")
    random.shuffle(guests)
    return guests


def _field(row: dict[str, Any], key: str) -> Any:
    if key in row:
        return row.get(key)
    try:
        return row.get(int(key))
    except (TypeError, ValueError):
        return None


class HexinHqClient:
    """进程内单例：连接一次，按股票拉大单。"""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._lib: Any | None = None
        self._connected = False
        self._last_call = 0.0

    def _load(self) -> Any:
        if self._lib is not None:
            return self._lib
        path = _dll_path()
        if not path.is_file():
            raise FileNotFoundError(f"未找到 HQ 组件: {path}")
        lib = c.CDLL(str(path))
        lib.Call.argtypes = [c.c_char_p, c.c_char_p, c.c_int]
        lib.Call.restype = c.c_int
        self._lib = lib
        return lib

    def _throttle(self) -> None:
        gap = _RATE_SEC - (time.monotonic() - self._last_call)
        if gap > 0:
            time.sleep(gap)

    def _invoke(self, method: str, params: dict[str, Any] | None, buffer_size: int) -> dict[str, Any]:
        lib = self._load()
        self._throttle()
        payload = json.dumps({"method": method, "params": params or {}}, ensure_ascii=False).encode("utf-8")
        out = c.create_string_buffer(buffer_size)
        status = lib.Call(payload, out, buffer_size)
        self._last_call = time.monotonic()
        raw = out.value.decode("utf-8", "replace") if out.value else ""
        try:
            body = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            body = {"err_info": raw or "invalid json", "payload": {}}
        if not isinstance(body, dict):
            body = {"err_info": str(body), "payload": {}}
        if status != 0 and not body.get("err_info"):
            body["err_info"] = f"hq status {status}"
        return body

    def connect(self) -> None:
        with self._lock:
            if self._connected:
                return
            self._load()
            last_err = "主行情连接失败"
            for username, password, mac in _credential_candidates()[:_CONNECT_ATTEMPTS]:
                body = self._invoke(
                    "connect",
                    {"username": username, "password": password, "mac": mac},
                    _CONNECT_BUFFER,
                )
                err = str(body.get("err_info") or "")
                if not err:
                    self._connected = True
                    return
                last_err = err
                logger.info("ths hq connect skip %s: %s", username, err)
                self._invoke("disconnect", {}, 4096)
                time.sleep(0.2)
            raise RuntimeError(last_err)

    def close(self) -> None:
        with self._lock:
            if not self._connected:
                return
            try:
                self._invoke("disconnect", {}, 4096)
            except Exception:  # noqa: BLE001
                logger.info("ths hq disconnect skip", exc_info=True)
            self._connected = False

    def _ensure(self) -> None:
        if not self._connected:
            self.connect()

    def big_order_flow(self, code: str) -> list[dict[str, Any]]:
        security = hq_security(code)
        if not security:
            return []
        with self._lock:
            self._ensure()
            body = self._invoke("big_order_flow", {"code": security}, _QUERY_BUFFER)
            err = str(body.get("err_info") or "")
            if "请先连接" in err:
                self._connected = False
                self._ensure()
                body = self._invoke("big_order_flow", {"code": security}, _QUERY_BUFFER)
                err = str(body.get("err_info") or "")
            if err:
                raise RuntimeError(err)
            payload = body.get("payload") if isinstance(body.get("payload"), dict) else body
            rows = payload.get("result") if isinstance(payload, dict) else None
            return [row for row in rows or [] if isinstance(row, dict)]


_client = HexinHqClient()
atexit.register(_client.close)


def fetch_hq_big_orders(code: str) -> list[dict[str, Any]]:
    """返回该股当日 HQ 大单（主/被、手数、金额），未做金额门槛过滤。"""
    norm = normalize_code(code)
    if not norm:
        return []
    items: list[dict[str, Any]] = []
    for row in _client.big_order_flow(norm):
        parsed = _parse_row(row, code=norm)
        if parsed:
            items.append(parsed)
    return items


def _parse_row(row: dict[str, Any], *, code: str) -> dict[str, Any] | None:
    ts = to_float(_field(row, _FIELD_TIME))
    direction = int(to_float(_field(row, _FIELD_DIR)) or 0)
    volume = to_float(_field(row, _FIELD_VOLUME))
    amount = to_float(_field(row, _FIELD_AMOUNT))
    kind = _DIR_MAP.get(direction)
    if ts is None or kind is None or volume is None or volume <= 0 or amount is None:
        return None
    aggressor, side, label, event_name = kind
    stamp = datetime.fromtimestamp(int(ts), _TZ).strftime("%H:%M:%S")
    price = round(amount / volume, 2)
    lots = round(volume / 100.0, 2)
    return {
        "time": stamp,
        "code": code,
        "name": "",
        "price": price,
        "volume": volume,
        "volume_lots": lots,
        "amount": round(amount, 2),
        "side": side,
        "side_label": "买盘" if side == "buy" else "卖盘",
        "aggressor": aggressor,
        "aggressor_label": label,
        "event_name": event_name,
        "event_id": f"{int(ts)}|{direction}|{int(volume)}",
    }
