"""同花顺 iFinD 数据接口：登录 + 高频序列 ``THS_HF``。

账号与手机 Level-2 会员不是同一套产品。需要 iFinD **数据接口**账号：

- SDK：安装 ``iFinDPy``，环境变量 ``IFIND_USER`` / ``IFIND_PASSWORD``
- HTTP：超级命令「工具 → refresh_token 查询」，``IFIND_REFRESH_TOKEN``

登录成功码：``0`` 成功，``-201`` 重复登录（可继续取数）。
"""

from __future__ import annotations

import json
import logging
import os
import threading
from pathlib import Path
from typing import Any

import requests

logger = logging.getLogger(__name__)


def _load_dotenv() -> None:
    root = Path(__file__).resolve().parents[4] / ".env"
    if not root.exists():
        return
    try:
        text = root.read_text(encoding="utf-8")
    except OSError:
        return
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


_load_dotenv()

HTTP_TOKEN_URLS = (
    "https://quantapi.51ifind.com/api/v1/get_access_token",
    "https://quantapi.10jqka.com.cn/api/v1/get_access_token",
)
HTTP_HF_URLS = (
    "https://quantapi.51ifind.com/api/v1/high_frequency",
    "https://quantapi.10jqka.com.cn/api/v1/high_frequency",
)

_lock = threading.Lock()
_sdk_ready = False
_access_token = ""


class IFindError(RuntimeError):
    def __init__(self, message: str, *, errorcode: int | None = None) -> None:
        super().__init__(message)
        self.errorcode = errorcode


def _session() -> requests.Session:
    sess = requests.Session()
    sess.trust_env = False
    sess.headers.update({"Content-Type": "application/json"})
    return sess


def _env(*names: str) -> str:
    for name in names:
        value = (os.environ.get(name) or "").strip()
        if value:
            return value
    return ""


def credentials() -> dict[str, str]:
    return {
        "user": _env("IFIND_USER", "IFIND_USERNAME", "IFIND_ACCOUNT"),
        "password": _env("IFIND_PASSWORD", "IFIND_PASSWD"),
        "refresh_token": _env("IFIND_REFRESH_TOKEN", "IFIND_TOKEN"),
    }


def has_credentials() -> bool:
    creds = credentials()
    return bool(creds["user"] and creds["password"]) or bool(creds["refresh_token"])


def _ok(code: Any) -> bool:
    try:
        return int(code) in {0, -201}
    except (TypeError, ValueError):
        return False


def _payload(result: Any) -> dict[str, Any]:
    if result is None:
        return {}
    if isinstance(result, dict):
        return result
    errorcode = getattr(result, "errorcode", None)
    errmsg = getattr(result, "errmsg", "") or ""
    data = getattr(result, "data", None)
    if errorcode is None and hasattr(result, "__getitem__"):
        try:
            errorcode = result[0]
            data = result[1]
        except (IndexError, TypeError, KeyError):
            pass
    out: dict[str, Any] = {
        "errorcode": 0 if errorcode is None else errorcode,
        "errmsg": str(errmsg),
    }
    if isinstance(data, dict):
        out.update(data)
        if "data" not in data:
            out["data"] = data
    else:
        out["data"] = data
    return out


def _raise_if_error(payload: dict[str, Any], *, action: str) -> None:
    code = payload.get("errorcode", 0)
    if _ok(code):
        return
    try:
        err = int(code)
    except (TypeError, ValueError):
        err = None
    msg = str(payload.get("errmsg") or payload.get("errorMsg") or "").strip()
    if not msg:
        msg = f"iFinD {action}失败 errorcode={code}"
    else:
        msg = f"iFinD {action}失败：{msg}（errorcode={code}）"
    raise IFindError(msg, errorcode=err)


def _sdk_login(user: str, password: str) -> None:
    global _sdk_ready
    try:
        from iFinDPy import THS_iFinDLogin
    except ImportError as exc:
        raise IFindError(
            "未安装 iFinDPy。请使用同花顺数据接口安装包，或改配 IFIND_REFRESH_TOKEN 走 HTTP"
        ) from exc
    code = THS_iFinDLogin(user, password)
    if not _ok(code):
        raise IFindError(f"iFinD 登录失败 errorcode={code}", errorcode=int(code) if str(code).lstrip("-").isdigit() else None)
    _sdk_ready = True


def _http_token(refresh_token: str) -> str:
    last_exc: Exception | None = None
    sess = _session()
    for url in HTTP_TOKEN_URLS:
        try:
            resp = sess.post(url, headers={"refresh_token": refresh_token}, timeout=20)
            resp.raise_for_status()
            payload = resp.json()
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            logger.info("iFinD token skip %s: %s", url, exc)
            continue
        if not isinstance(payload, dict):
            continue
        data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
        token = str((data or {}).get("access_token") or "").strip()
        err = payload.get("errorcode", 0)
        if token and _ok(err):
            return token
        _raise_if_error(payload, action="获取 access_token")
    if last_exc:
        raise IFindError(f"iFinD 获取 access_token 失败：{last_exc}") from last_exc
    raise IFindError("iFinD 获取 access_token 失败：响应里没有 token")


def login(*, force: bool = False) -> str:
    """登录。返回 ``sdk`` 或 HTTP access_token。"""
    global _sdk_ready, _access_token
    creds = credentials()
    user, password, refresh = creds["user"], creds["password"], creds["refresh_token"]
    if not user and not refresh:
        raise IFindError(
            "未配置 iFinD 账号。请在 .env 填写 IFIND_USER / IFIND_PASSWORD，"
            "或填写超级命令里的 IFIND_REFRESH_TOKEN"
        )

    with _lock:
        if not force:
            if _sdk_ready:
                return "sdk"
            if _access_token:
                return _access_token
        if user and password:
            try:
                _sdk_login(user, password)
                return "sdk"
            except IFindError:
                if not refresh:
                    raise
                logger.info("iFinD SDK 登录失败，改走 HTTP refresh_token")
        if not refresh:
            raise IFindError("iFinD SDK 不可用，且未配置 IFIND_REFRESH_TOKEN")
        _access_token = _http_token(refresh)
        return _access_token


def _join_indicators(indicators: str | list[str], *, sep: str) -> str:
    if isinstance(indicators, str):
        parts = [p.strip() for p in indicators.replace(";", ",").split(",") if p.strip()]
    else:
        parts = [str(p).strip() for p in indicators if str(p).strip()]
    return sep.join(parts)


def _sdk_hf(
    code: str,
    indicators: str,
    params: str,
    start: str,
    end: str,
) -> dict[str, Any]:
    from iFinDPy import THS_HF

    result = THS_HF(code, indicators, params, start, end, "format:json")
    payload = _payload(result)
    _raise_if_error(payload, action="高频序列")
    return payload


def _http_hf(
    token: str,
    code: str,
    indicators: str,
    params: dict[str, str],
    start: str,
    end: str,
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "codes": code,
        "indicators": indicators,
        "starttime": start,
        "endtime": end,
    }
    if params:
        body["functionpara"] = params
    last_exc: Exception | None = None
    sess = _session()
    headers = {"access_token": token}
    for url in HTTP_HF_URLS:
        try:
            resp = sess.post(url, json=body, headers=headers, timeout=60)
            resp.raise_for_status()
            payload = resp.json()
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            logger.info("iFinD high_frequency skip %s: %s", url, exc)
            continue
        if not isinstance(payload, dict):
            continue
        if payload.get("errorcode") in (-1010, -1302, "-1010", "-1302"):
            refreshed = login(force=True)
            if refreshed == "sdk":
                return _sdk_hf(
                    code,
                    _join_indicators(indicators, sep=";"),
                    ",".join(f"{k}:{v}" for k, v in params.items()),
                    start,
                    end,
                )
            token = refreshed
            headers = {"access_token": token}
            try:
                resp = sess.post(url, json=body, headers=headers, timeout=60)
                resp.raise_for_status()
                payload = resp.json()
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                continue
            if not isinstance(payload, dict):
                continue
        _raise_if_error(payload, action="高频序列")
        return payload
    if last_exc:
        raise IFindError(f"iFinD 高频序列请求失败：{last_exc}") from last_exc
    raise IFindError("iFinD 高频序列请求失败：无有效响应")


def high_frequency(
    code: str,
    indicators: str | list[str],
    *,
    start: str,
    end: str,
    max_points: int = 100000,
    extra_params: dict[str, str] | None = None,
) -> dict[str, Any]:
    """拉一段高频序列。``code`` 必须是 ``600519.SH`` 这种 iFinD 代码。"""
    params = {"MaxPoints": str(int(max_points))}
    if extra_params:
        params.update({str(k): str(v) for k, v in extra_params.items() if v is not None})
    mode = login()
    if mode == "sdk":
        indi = _join_indicators(indicators, sep=";")
        kv = ",".join(f"{k}:{v}" for k, v in params.items())
        return _sdk_hf(code, indi, kv, start, end)
    indi = _join_indicators(indicators, sep=",")
    return _http_hf(mode, code, indi, params, start, end)


def tables(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """把 THS_HF / HTTP 返回拆成按时间对齐的行列表。"""
    if not payload:
        return []
    raw_tables = payload.get("tables")
    if isinstance(raw_tables, list) and raw_tables:
        rows: list[dict[str, Any]] = []
        for block in raw_tables:
            if isinstance(block, dict):
                rows.extend(_rows_from_table(block))
        if rows:
            return rows

    data = payload.get("data")
    if isinstance(data, dict) and isinstance(data.get("tables"), list):
        return tables(data)
    if isinstance(data, list) and data and isinstance(data[0], dict):
        return list(data)
    if data is not None and hasattr(data, "to_dict"):
        try:
            records = data.to_dict(orient="records")
            if isinstance(records, list):
                return [row for row in records if isinstance(row, dict)]
        except Exception:  # noqa: BLE001
            logger.debug("iFinD dataframe to_dict failed", exc_info=True)
    if isinstance(payload.get("errmsg"), str) and "tables" not in payload:
        try:
            nested = json.loads(payload["errmsg"])
            if isinstance(nested, dict):
                return tables(nested)
        except (TypeError, ValueError):
            pass
    return []


def _rows_from_table(block: dict[str, Any]) -> list[dict[str, Any]]:
    table = block.get("table") if isinstance(block.get("table"), dict) else {}
    columns: dict[str, list[Any]] = {}
    for key, value in table.items():
        if isinstance(value, list):
            columns[str(key)] = value
    times = block.get("time")
    if isinstance(times, list) and "time" not in columns:
        columns["time"] = times
    length = max((len(v) for v in columns.values()), default=0)
    if length == 0:
        return []
    thscode = str(block.get("thscode") or block.get("code") or "")
    rows: list[dict[str, Any]] = []
    for i in range(length):
        row: dict[str, Any] = {}
        if thscode:
            row["thscode"] = thscode
        for key, values in columns.items():
            if i < len(values):
                row[key] = values[i]
        rows.append(row)
    return rows
