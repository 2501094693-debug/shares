"""HTTP 与通用小工具。"""

from __future__ import annotations

import json
import re
import time
from datetime import date, datetime, timedelta
from typing import Any

import requests

from .constants import REQUEST_TIMEOUT, USER_AGENT

try:
    from curl_cffi import requests as curl_requests
except ImportError:  # pragma: no cover
    curl_requests = None


def http_get(
    url: str,
    *,
    params: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout: int = REQUEST_TIMEOUT,
):
    """GET：优先 curl_cffi（Chrome 指纹），否则 requests。"""
    hdrs = {"User-Agent": USER_AGENT, **(headers or {})}
    if curl_requests is not None:
        return curl_requests.get(
            url,
            params=params,
            headers=hdrs,
            timeout=timeout,
            impersonate="chrome",
        )
    return requests.get(url, params=params, headers=hdrs, timeout=timeout)


def http_post(
    url: str,
    *,
    params: dict[str, Any] | None = None,
    data: Any = None,
    json_body: Any = None,
    headers: dict[str, str] | None = None,
    timeout: int = REQUEST_TIMEOUT,
):
    """POST：优先 curl_cffi。"""
    hdrs = {"User-Agent": USER_AGENT, **(headers or {})}
    if curl_requests is not None:
        return curl_requests.post(
            url,
            params=params,
            data=data,
            json=json_body,
            headers=hdrs,
            timeout=timeout,
            impersonate="chrome",
        )
    return requests.post(
        url,
        params=params,
        data=data,
        json=json_body,
        headers=hdrs,
        timeout=timeout,
    )


def parse_jsonp(text: str) -> Any:
    """解析 callback({...}) / callback([{...}]) 形式的 JSONP。"""
    text = (text or "").strip()
    if not text:
        return None
    start = text.find("(")
    end = text.rfind(")")
    if start < 0 or end <= start:
        # 纯 JSON
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return None
    body = text[start + 1 : end].strip()
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        return None


def safe_str(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value != value:  # NaN
        return ""
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(value, date):
        return value.strftime("%Y-%m-%d")
    return str(value).strip()


def parse_time(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime.combine(value, datetime.min.time())
    if isinstance(value, (int, float)):
        # 巨潮 announcementTime 常为毫秒时间戳
        ts = float(value)
        if ts > 1e12:
            ts /= 1000.0
        if ts > 1e9:
            try:
                return datetime.fromtimestamp(ts)
            except (OverflowError, OSError, ValueError):
                return None

    text = safe_str(value)
    if not text:
        return None
    # 截掉毫秒尾巴：2026-07-17 21:26:22:243
    text = re.sub(r":(\d{3})$", r".\1", text)
    for fmt in (
        "%Y-%m-%d %H:%M:%S.%f",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y/%m/%d %H:%M:%S",
        "%Y/%m/%d %H:%M",
        "%Y-%m-%d",
        "%Y/%m/%d",
        "%Y%m%d",
    ):
        try:
            return datetime.strptime(text[:26], fmt)
        except ValueError:
            continue
    return None


def normalize_code(code: str) -> str:
    code = safe_str(code)
    if not code:
        return ""
    # 允许 600519.SH / sh600519
    code = code.upper().replace("SH", "").replace("SZ", "").replace("BJ", "")
    code = re.sub(r"[^0-9]", "", code)
    return code.zfill(6) if code else ""


def detect_market(code: str) -> str:
    """粗分市场：sse / szse / bse / unknown。"""
    c = normalize_code(code)
    if not c:
        return "unknown"
    if c.startswith(("60", "68", "90")):
        return "sse"
    if c.startswith(("00", "30", "20")):
        return "szse"
    if c.startswith(("8", "4", "92")):
        return "bse"
    return "unknown"


def default_start(days: int = 365) -> datetime:
    return datetime.now() - timedelta(days=max(1, int(days)))


def lookback_start(days: int | None = None, *, years: int = 50) -> datetime:
    """回溯窗口起点；days 为空时约 years 年。"""
    if days is None:
        days = 365 * years + 5
    return datetime.now() - timedelta(days=max(1, int(days)))


def full_lookback_days(*, years: int = 50) -> int:
    return 365 * years + 5


def within_lookback(
    item: dict[str, Any],
    start: datetime,
    *,
    require_time: bool = False,
) -> bool:
    dt = parse_time(item.get("published_at", ""))
    if dt is None:
        return not require_time
    return dt >= start


def within_range(
    item: dict[str, Any],
    start: datetime | None,
    end: datetime | None,
) -> bool:
    dt = parse_time(item.get("published_at"))
    if dt is None:
        return True
    if start is not None and dt < start:
        return False
    if end is not None and dt > end + timedelta(days=1):
        return False
    return True


def strip_em_tags(text: str) -> str:
    return re.sub(r"</?em>", "", text or "", flags=re.IGNORECASE)


def sort_key(item: dict[str, Any]) -> tuple[int, float]:
    dt = parse_time(item.get("published_at"))
    if dt is None:
        return (1, 0.0)
    return (0, -dt.timestamp())


def dedupe(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """按 url 优先、否则 title+date 去重，保序。"""
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for item in items:
        url = safe_str(item.get("url"))
        title = safe_str(item.get("title"))
        day = safe_str(item.get("published_at"))[:10]
        key = url.lower() if url else f"{title}|{day}"
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def extract_href(html: str) -> str:
    """从深交所问询函 ck 字段里抽出 encode-open 路径。"""
    text = safe_str(html)
    if not text:
        return ""
    m = re.search(r"encode-open='([^']+)'", text)
    if m:
        return m.group(1)
    m = re.search(r'href=[\'"]([^\'"]+)[\'"]', text)
    return m.group(1) if m else ""


def sleep_pause(sec: float) -> None:
    if sec > 0:
        time.sleep(sec)
