"""雪球新闻接口共用：Cookie 会话、代码、日期、去标签。

雪球没有文档化的公开新闻 API。所有 XHR 都要带 ``xq_a_token``，
没有就返回 ``error_code=400016``。token 优先读环境变量；否则访问
``/about``（首页会被 WAF 拦）拿匿名 cookie。
"""

from __future__ import annotations

import html
import json
import logging
import os
import re
import sys
import threading
import time
from datetime import date, datetime, timedelta, timezone
from typing import Any, Iterable
from urllib.parse import quote

import requests

from core.codes import em_code, normalize_code, safe_str

logger = logging.getLogger(__name__)

TZ_CN = timezone(timedelta(hours=8))
REQUEST_PAUSE_SEC = 0.4
SOURCE = "xueqiu"

WEB_HOST = "https://xueqiu.com"
API_HOST = "https://api.xueqiu.com"
STOCK_HOST = "https://stock.xueqiu.com"
WARMUP_URLS = (
    f"{WEB_HOST}/about",
    f"{WEB_HOST}/about/faq",
    f"{WEB_HOST}/",
)
COOKIE_KEYS = (
    "xq_a_token",
    "xqat",
    "xq_r_token",
    "xq_id_token",
    "u",
    "cookiesu",
    "acw_tc",
)

TIMELINE_API = f"{API_HOST}/statuses/stock_timeline.json"
TIMELINE_API_FALLBACK = f"{WEB_HOST}/statuses/stock_timeline.json"
SEARCH_API = f"{API_HOST}/query/v1/symbol/search/status.json"
SEARCH_API_FALLBACK = f"{WEB_HOST}/query/v1/symbol/search/status.json"
KEYWORD_SEARCH_API = f"{API_HOST}/query/v1/search/status.json"
FLASH_API = f"{WEB_HOST}/statuses/livenews/list.json"
COLUMN_API = f"{WEB_HOST}/v4/statuses/public_timeline_by_category.json"
SHOW_API = f"{API_HOST}/statuses/show.json"
QUOTE_API = f"{STOCK_HOST}/v5/stock/quote.json"

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/122.0.0.0 Safari/537.36"
)

_HTML_TAG_RE = re.compile(r"<[^>]+>")
_TIME_RE = re.compile(r"(\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2})")
_MS_TAIL_RE = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})[:.]\d+")
_XQ_PREFIX_RE = re.compile(r"^(SH|SZ|BJ)\d{6}$", re.I)
_HK_RE = re.compile(r"^HK\d{1,5}$", re.I)
_TICKER_RE = re.compile(r"^[A-Z]{1,5}$")
_STATUS_ID_RE = re.compile(r"(?:xueqiu\.com)?/(?:S/[^/]+/)?(\d{6,})")

# 个股时间线 source。搜索接口不认「自选股新闻 / 公告 / 研报」。
TIMELINE_SOURCES: dict[str, str] = {
    "news": "自选股新闻",
    "资讯": "自选股新闻",
    "自选股新闻": "自选股新闻",
    "announcement": "公告",
    "notice": "公告",
    "notices": "公告",
    "公告": "公告",
    "report": "研报",
    "reports": "研报",
    "研报": "研报",
}


def stock_page_url(symbol: str = "") -> str:
    sym = xq_symbol(symbol) if symbol else ""
    if sym:
        return f"{WEB_HOST}/S/{sym}"
    return WEB_HOST + "/"


def search_page_url(code_or_name: str = "") -> str:
    stock = xq_symbol(code_or_name)
    if stock:
        return stock_page_url(stock)
    kw = safe_str(code_or_name)
    if kw:
        return f"{WEB_HOST}/k?q={quote(kw)}"
    return WEB_HOST + "/"


def article_url(target_or_url: str) -> str:
    raw = safe_str(target_or_url)
    if not raw:
        return ""
    if raw.lower().startswith("http://") or raw.lower().startswith("https://"):
        return raw.replace("http://", "https://", 1)
    if raw.startswith("/"):
        return WEB_HOST + raw
    if raw.isdigit():
        return f"{WEB_HOST}/{raw}"
    return WEB_HOST + "/" + raw.lstrip("/")


def status_id_of(target_or_url: str) -> str:
    raw = safe_str(target_or_url)
    if raw.isdigit() and len(raw) >= 6:
        return raw
    m = _STATUS_ID_RE.search(raw)
    return m.group(1) if m else ""


def xq_symbol(code: str) -> str:
    """雪球个股代码：A 股 ``SH600519`` / ``SZ000001`` / ``BJ830964``，港股 ``00700``，美股 ticker。"""
    raw = safe_str(code).strip()
    if not raw:
        return ""
    upper = raw.upper().replace(".SS", "").replace(".SZ", "").replace(".HK", "")
    compact = upper.replace(".", "")
    if _XQ_PREFIX_RE.match(compact):
        return compact
    if _HK_RE.match(compact):
        return compact[2:].zfill(5)
    if _TICKER_RE.match(compact) and not compact.isdigit():
        return compact
    digits = re.sub(r"\D", "", raw)
    if compact.startswith("HK") or raw.upper().endswith(".HK"):
        return digits.zfill(5) if digits else ""
    if digits and len(digits) <= 5:
        return digits.zfill(5)
    c = normalize_code(raw)
    if c:
        return em_code(c)
    return compact


def headers_for(referer: str, *, origin: str = "") -> dict[str, str]:
    hdrs = {
        "User-Agent": _UA,
        "Referer": referer or WEB_HOST + "/",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "X-Requested-With": "XMLHttpRequest",
    }
    if origin:
        hdrs["Origin"] = origin
    return hdrs


def _cookie_get(sess: Any, name: str) -> str:
    jar = getattr(sess, "cookies", None)
    if jar is None:
        return ""
    if hasattr(jar, "get_dict"):
        try:
            val = jar.get_dict().get(name)
            if val:
                return str(val)
        except Exception:  # noqa: BLE001
            pass
    try:
        val = jar.get(name)
        if val:
            return str(val)
    except Exception:  # noqa: BLE001
        pass
    try:
        for cookie in jar:
            if getattr(cookie, "name", None) == name:
                return str(getattr(cookie, "value", "") or "")
    except Exception:  # noqa: BLE001
        pass
    return ""


def _cookie_header(sess: Any) -> str:
    parts: list[str] = []
    for name in COOKIE_KEYS:
        val = _cookie_get(sess, name)
        if val:
            parts.append(f"{name}={val}")
    return "; ".join(parts)


def _cookie_set(sess: Any, name: str, value: str) -> None:
    if not name or not value:
        return
    for kwargs in ({"domain": ".xueqiu.com"}, {}, {"domain": "xueqiu.com"}):
        try:
            sess.cookies.set(name, value, **kwargs)
            return
        except Exception:  # noqa: BLE001
            continue
    logger.debug("写入 Cookie %s 失败", name)


def _parse_cookie_header(raw: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for part in safe_str(raw).split(";"):
        if "=" not in part:
            continue
        key, value = part.split("=", 1)
        key = key.strip()
        if key:
            out[key] = value.strip()
    return out


class _Client:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._sess: Any = None
        self._warmed = False

    def set_token(self, token: str, cookies: str = "") -> None:
        with self._lock:
            self._ensure_session()
            for name, value in _parse_cookie_header(cookies).items():
                _cookie_set(self._sess, name, value)
            if token:
                _cookie_set(self._sess, "xq_a_token", safe_str(token))
            self._warmed = bool(_cookie_get(self._sess, "xq_a_token"))

    def token(self) -> str:
        with self._lock:
            return _cookie_get(self._sess, "xq_a_token") if self._sess else ""

    def _ensure_session(self) -> Any:
        if self._sess is not None:
            return self._sess
        try:
            from curl_cffi import requests as curl_requests

            self._sess = curl_requests.Session(impersonate="chrome")
        except ImportError:
            self._sess = requests.Session()
            self._sess.trust_env = False
            self._sess.headers.update({"User-Agent": _UA})
        env_cookies = os.environ.get("XUEQIU_COOKIES") or os.environ.get("XUEQIU_COOKIE") or ""
        env_token = os.environ.get("XUEQIU_TOKEN") or os.environ.get("XQ_A_TOKEN") or ""
        for name, value in _parse_cookie_header(env_cookies).items():
            _cookie_set(self._sess, name, value)
        if env_token:
            _cookie_set(self._sess, "xq_a_token", env_token.strip())
        return self._sess

    def warmup(self, *, force: bool = False) -> str:
        with self._lock:
            sess = self._ensure_session()
            token = _cookie_get(sess, "xq_a_token")
            if token and not force:
                self._warmed = True
                return token
            last_exc: Exception | None = None
            for url in WARMUP_URLS:
                try:
                    sess.get(
                        url,
                        headers=headers_for(WEB_HOST + "/"),
                        timeout=20,
                    )
                except Exception as exc:  # noqa: BLE001
                    last_exc = exc
                    logger.info("雪球预热失败 %s: %s", url, exc)
                    continue
                token = _cookie_get(sess, "xq_a_token")
                if token:
                    break
            if last_exc and not token:
                logger.info("雪球预热失败: %s", last_exc)
            self._warmed = bool(token)
            if not token:
                logger.info("未拿到 xq_a_token，可设置环境变量 XUEQIU_TOKEN")
            return token

    def request(
        self,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        timeout: int = 25,
    ) -> Any:
        self.warmup()
        with self._lock:
            sess = self._ensure_session()
            hdrs = dict(headers or {})
            cookie = hdrs.get("Cookie") or hdrs.get("cookie") or ""
            built = _cookie_header(sess)
            if built and "xq_a_token=" not in cookie:
                hdrs["Cookie"] = f"{cookie}; {built}".strip("; ")
            return sess.get(
                url,
                params=params,
                headers=hdrs,
                timeout=timeout,
            )


_CLIENT = _Client()


def set_token(token: str, cookies: str = "") -> None:
    """手动注入 ``xq_a_token``，或一整段浏览器 Cookie。"""
    _CLIENT.set_token(token, cookies)


def current_token() -> str:
    return _CLIENT.token()


def _xq_error(payload: Any) -> str:
    if not isinstance(payload, dict):
        return ""
    code = payload.get("error_code")
    if code in (None, "", 0, "0"):
        return ""
    desc = safe_str(payload.get("error_description") or payload.get("message"))
    return desc or f"error_code={code}"


def _is_auth_error(payload: Any, status_code: int = 0) -> bool:
    if status_code in {400, 401, 403}:
        return True
    if not isinstance(payload, dict):
        return False
    return safe_str(payload.get("error_code")) in {"400016", "400013"}


def _parse_body(resp: Any) -> Any:
    text = safe_str(getattr(resp, "text", "")).lstrip()
    if not text:
        return {}
    if text.startswith("<") or "访问验证" in text[:200]:
        raise RuntimeError("雪球 WAF 拦截，请设置 XUEQIU_TOKEN 或稍后重试")
    try:
        return json.loads(text)
    except ValueError as exc:
        raise RuntimeError(f"雪球返回非 JSON: {text[:120]}") from exc


def get_payload(
    url: str,
    *,
    params: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout: int = 25,
    fallback: str = "",
) -> Any:
    """GET 并解析 JSON。遇到 400016 会刷新 token 再打一次。"""
    hdrs = headers or headers_for(WEB_HOST + "/", origin=WEB_HOST)
    urls = [url]
    if fallback and fallback != url:
        urls.append(fallback)
    last_exc: Exception | None = None
    for target in urls:
        refreshed = False
        while True:
            try:
                resp = _CLIENT.request(target, params=params, headers=hdrs, timeout=timeout)
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                break
            status = int(getattr(resp, "status_code", 0) or 0)
            try:
                payload = _parse_body(resp)
            except RuntimeError as exc:
                last_exc = exc
                break
            if _is_auth_error(payload, status) and not refreshed:
                logger.info("雪球 token 失效，重新预热后重试")
                _CLIENT.warmup(force=True)
                refreshed = True
                continue
            err = _xq_error(payload)
            if err and status >= 400:
                raise RuntimeError(err)
            if isinstance(payload, dict) and err and not payload.get("list") and not payload.get("items"):
                raise RuntimeError(err)
            return payload if payload is not None else {}
        continue
    if last_exc:
        raise last_exc
    return {}


def get_html(
    url: str,
    *,
    headers: dict[str, str] | None = None,
    timeout: int = 25,
) -> str:
    resp = _CLIENT.request(
        url,
        headers=headers or headers_for(WEB_HOST + "/"),
        timeout=timeout,
    )
    status = int(getattr(resp, "status_code", 0) or 0)
    if status >= 400:
        resp.raise_for_status()
    return safe_str(getattr(resp, "text", ""))


def strip_html(text: str) -> str:
    cleaned = html.unescape(safe_str(text))
    cleaned = _HTML_TAG_RE.sub("", cleaned)
    return (
        cleaned.replace("&nbsp;", " ")
        .replace("\xa0", " ")
        .replace("\u3000", " ")
        .replace("\r\n", " ")
        .replace("\n", " ")
        .strip()
    )


def map_choice(value: str | None, table: dict[str, str], default: str, label: str) -> str:
    key = safe_str(value)
    if not key:
        key = default
    if key in table:
        return table[key]
    mapped = table.get(key.lower())
    if mapped is not None:
        return mapped
    raise ValueError(f"未知 {label}: {value}；可用 {', '.join(sorted(set(table)))}")


def parse_day(value: str | date | datetime | None) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        dt = value if value.tzinfo else value.replace(tzinfo=TZ_CN)
        return dt.astimezone(TZ_CN).date()
    if isinstance(value, date):
        return value
    text = safe_str(value).replace("/", "-").replace("T", " ")
    for fmt, size in (("%Y-%m-%d", 10), ("%Y%m%d", 8)):
        try:
            return datetime.strptime(text[:size], fmt).date()
        except ValueError:
            continue
    return None


def date_range(
    start: str | date | datetime | None,
    end: str | date | datetime | None,
    days: int | None,
) -> tuple[date | None, date | None]:
    end_d = parse_day(end)
    start_d = parse_day(start)
    if start_d is None and days is not None:
        end_d = end_d or date.today()
        start_d = end_d - timedelta(days=max(1, int(days)))
    if start_d and end_d and start_d > end_d:
        start_d, end_d = end_d, start_d
    return start_d, end_d


def fmt_dt(value: Any) -> str:
    if value is None or value == "":
        return ""
    if isinstance(value, datetime):
        dt = value if value.tzinfo else value.replace(tzinfo=TZ_CN)
        return dt.astimezone(TZ_CN).strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(value, (int, float)):
        ts = float(value)
        if ts > 1e12:
            ts /= 1000.0
        if ts <= 0:
            return ""
        try:
            return datetime.fromtimestamp(ts, tz=TZ_CN).strftime("%Y-%m-%d %H:%M:%S")
        except (OverflowError, OSError, ValueError):
            return ""
    text = safe_str(value).replace("T", " ")
    if text.isdigit() and len(text) >= 10:
        try:
            return fmt_dt(int(text[:13] if len(text) >= 13 else text[:10]))
        except ValueError:
            pass
    m = _MS_TAIL_RE.match(text)
    if m:
        return m.group(1)
    m = _TIME_RE.search(text)
    if m:
        return m.group(1).replace("T", " ")
    day = parse_day(text)
    return day.isoformat() + " 00:00:00" if day else text


def in_range(item: dict[str, Any], start_d: date | None, end_d: date | None) -> bool:
    day = parse_day(item.get("published_at"))
    if day is None:
        return True
    if start_d and day < start_d:
        return False
    if end_d and day > end_d:
        return False
    return True


def oldest_day(items: list[dict[str, Any]]) -> date | None:
    days = [parse_day(x.get("published_at")) for x in items]
    days = [d for d in days if d is not None]
    return min(days) if days else None


def dedupe(items: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for item in items:
        url = safe_str(item.get("url")).lower()
        art = safe_str(item.get("article_id") or item.get("status_id"))
        title = safe_str(item.get("title"))
        day = safe_str(item.get("published_at"))[:10]
        key = art or url or f"{title}|{day}"
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def decode_embedded(row: Any) -> dict[str, Any]:
    """分类资讯流的 ``list[i].data`` 是 JSON 字符串。"""
    if isinstance(row, dict):
        data = row.get("data")
        if isinstance(data, dict):
            return data
        if isinstance(data, str) and data.strip().startswith("{"):
            try:
                parsed = json.loads(data)
            except ValueError:
                return row
            return parsed if isinstance(parsed, dict) else row
        return row
    if isinstance(row, str) and row.strip().startswith("{"):
        try:
            parsed = json.loads(row)
        except ValueError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def related_stocks(row: dict[str, Any]) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    seen: set[str] = set()
    blobs: list[Any] = []
    for key in ("stocks", "stock", "symbols", "interesting_symbols"):
        val = row.get(key)
        if isinstance(val, list):
            blobs.extend(val)
        elif isinstance(val, dict):
            blobs.append(val)
        elif isinstance(val, str) and val:
            blobs.append(val)
    for item in blobs:
        code = ""
        name = ""
        if isinstance(item, dict):
            code = xq_symbol(
                safe_str(item.get("symbol") or item.get("code") or item.get("stockCode"))
            )
            name = safe_str(item.get("name") or item.get("stockName"))
        elif isinstance(item, str):
            code = xq_symbol(item)
        key = code or name
        if not key or key in seen:
            continue
        seen.add(key)
        out.append({"symbol": code, "name": name})
    return out


def normalize_status(
    row: dict[str, Any],
    *,
    code: str = "",
    name: str = "",
    channel: str = "news",
    symbol: str = "",
) -> dict[str, Any] | None:
    data = decode_embedded(row) or row
    if not isinstance(data, dict) or not data:
        return None
    title = strip_html(safe_str(data.get("title") or data.get("rawTitle")))
    text = safe_str(data.get("text") or data.get("description") or data.get("text_pre"))
    summary = strip_html(text)
    if not title:
        title = summary[:80]
    if not title and not summary:
        return None
    status_id = safe_str(data.get("id") or data.get("status_id"))
    target = safe_str(data.get("target") or data.get("target_url"))
    url = article_url(target) if target else (article_url(status_id) if status_id else "")
    user = data.get("user") if isinstance(data.get("user"), dict) else {}
    stocks = related_stocks(data)
    if not stocks and symbol:
        stocks = [{"symbol": symbol, "name": name}]
    return {
        "code": code,
        "name": name,
        "symbol": symbol or (stocks[0]["symbol"] if stocks else ""),
        "article_id": status_id,
        "status_id": status_id,
        "title": title,
        "summary": summary[:400],
        "published_at": fmt_dt(data.get("created_at") or data.get("edited_at")),
        "url": url,
        "target": target,
        "source": SOURCE,
        "channel": channel,
        "media_name": safe_str(
            data.get("source") or user.get("screen_name") or data.get("column")
        ),
        "author": safe_str(user.get("screen_name")),
        "user_id": safe_str(user.get("id")),
        "reply_count": data.get("reply_count"),
        "retweet_count": data.get("retweet_count"),
        "like_count": data.get("like_count") or data.get("fav_count"),
        "view_count": data.get("view_count"),
        "related_stocks": stocks,
    }


def query_timeline(
    symbol: str,
    *,
    source: str = "自选股新闻",
    page: int = 1,
    count: int = 10,
) -> dict[str, Any]:
    """个股时间线原始 JSON。``source`` 为中文：自选股新闻 / 公告 / 研报。"""
    payload = get_payload(
        TIMELINE_API,
        params={
            "symbol_id": symbol,
            "symbol": symbol,
            "source": source,
            "count": max(1, min(int(count), 20)),
            "page": max(1, int(page)),
        },
        headers=headers_for(stock_page_url(symbol), origin=WEB_HOST),
        timeout=20,
        fallback=TIMELINE_API_FALLBACK,
    )
    return payload if isinstance(payload, dict) else {}


def query_quote(symbol: str) -> dict[str, Any]:
    payload = get_payload(
        QUOTE_API,
        params={"symbol": symbol, "extend": "detail"},
        headers=headers_for(stock_page_url(symbol), origin=WEB_HOST),
        timeout=15,
    )
    if not isinstance(payload, dict):
        return {}
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    quote = data.get("quote") if isinstance(data.get("quote"), dict) else {}
    return quote if isinstance(quote, dict) else {}


def resolve_timeline_source(source: str | None, default: str = "news") -> str:
    return map_choice(source, TIMELINE_SOURCES, default, "source")


def resolve_keyword(code_or_name: str) -> dict[str, str]:
    """代码优先解析成雪球 symbol；失败则原样当关键词。"""
    raw = safe_str(code_or_name)
    code = normalize_code(raw)
    name = ""
    if raw:
        try:
            from company.news.official.cninfo import resolve_org

            org = resolve_org(raw)
        except Exception as exc:  # noqa: BLE001
            logger.info("解析公司简称失败 %s: %s", raw, exc)
            org = None
        if org:
            code = safe_str(org.get("code")) or code
            name = safe_str(org.get("name"))
    symbol = xq_symbol(code or raw)
    if symbol and not name:
        try:
            quote = query_quote(symbol)
            name = safe_str(quote.get("name"))
            if not code:
                code = normalize_code(safe_str(quote.get("code") or quote.get("symbol")))
        except Exception as exc:  # noqa: BLE001
            logger.debug("雪球行情名失败 %s: %s", symbol, exc)
    keyword = name or (raw if not code or raw != code else code)
    return {"code": code, "name": name, "keyword": keyword, "symbol": symbol}


def relevant(item: dict[str, Any], *, code: str = "", name: str = "", keyword: str = "") -> bool:
    blob = f"{item.get('title', '')} {item.get('summary', '')}"
    tokens = [t for t in (name, keyword) if t and len(t) >= 2]
    if code and len(code) >= 6:
        tokens.append(code)
    symbol = xq_symbol(code)
    for row in item.get("related_stocks") or []:
        if isinstance(row, dict):
            if symbol and safe_str(row.get("symbol")) == symbol:
                return True
            if code and code in safe_str(row.get("symbol")):
                return True
            if name and name in safe_str(row.get("name")):
                return True
    if not tokens:
        return True
    return any(t in blob for t in tokens)


def empty_pack(
    *,
    code: str = "",
    name: str = "",
    keyword: str = "",
    channel: str = "news",
    error: str = "",
    page: str = "",
    **extra: Any,
) -> dict[str, Any]:
    pack = {
        "code": code,
        "name": name,
        "keyword": keyword,
        "source": SOURCE,
        "channel": channel,
        "count": 0,
        "total": 0,
        "items": [],
        "page": page,
    }
    pack.update(extra)
    if error:
        pack["error"] = error
    return pack


def fetch_stock_statuses(
    code_or_name: str,
    *,
    source: str = "自选股新闻",
    channel: str = "news",
    start: str | date | datetime | None = None,
    end: str | date | datetime | None = None,
    days: int | None = 31,
    max_pages: int = 3,
    page_size: int = 10,
    strict: bool = False,
) -> dict[str, Any]:
    """个股时间线翻页：资讯 / 公告 / 研报共用。"""
    resolved = resolve_keyword(code_or_name)
    code = resolved["code"] or normalize_code(code_or_name)
    name = resolved["name"]
    symbol = resolved["symbol"] or xq_symbol(code or code_or_name)
    page_url = stock_page_url(symbol)
    if not symbol:
        return empty_pack(
            code=code,
            name=name,
            keyword=resolved["keyword"],
            channel=channel,
            error="缺少股票代码",
            page=page_url,
            symbol=symbol,
        )

    src = resolve_timeline_source(source, source if source in TIMELINE_SOURCES.values() else "news")
    start_d, end_d = date_range(start, end, days)
    items: list[dict[str, Any]] = []
    total = 0
    page = 1
    limit = max(1, int(max_pages))
    size = max(1, min(int(page_size), 20))
    while page <= limit:
        try:
            payload = query_timeline(symbol, source=src, page=page, count=size)
        except Exception as exc:  # noqa: BLE001
            logger.warning("雪球时间线失败 %s page=%s: %s", symbol, page, exc)
            if page == 1:
                return empty_pack(
                    code=code,
                    name=name,
                    keyword=resolved["keyword"],
                    channel=channel,
                    error=str(exc),
                    page=page_url,
                    symbol=symbol,
                    begin_date=start_d.isoformat() if start_d else "",
                    end_date=end_d.isoformat() if end_d else "",
                )
            break
        rows = payload.get("list") or []
        total = int(payload.get("count") or payload.get("total") or total or 0)
        if not isinstance(rows, list) or not rows:
            break
        page_items: list[dict[str, Any]] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            item = normalize_status(
                row, code=code, name=name, channel=channel, symbol=symbol
            )
            if not item:
                continue
            if strict and not relevant(
                item, code=code, name=name, keyword=resolved["keyword"]
            ):
                continue
            page_items.append(item)
            if in_range(item, start_d, end_d):
                items.append(item)
        if start_d:
            old = oldest_day(page_items)
            if old and old < start_d:
                break
        if len(rows) < size:
            break
        page += 1
        if page <= limit:
            time.sleep(REQUEST_PAUSE_SEC)

    items = dedupe(items)
    return {
        "code": code,
        "name": name,
        "keyword": resolved["keyword"],
        "symbol": symbol,
        "begin_date": start_d.isoformat() if start_d else "",
        "end_date": end_d.isoformat() if end_d else "",
        "source": SOURCE,
        "channel": channel,
        "timeline_source": src,
        "count": len(items),
        "total": total or len(items),
        "items": items,
        "page": page_url,
    }


def cli_print(text: str) -> None:
    try:
        print(text)
    except UnicodeEncodeError:
        enc = getattr(sys.stdout, "encoding", None) or "utf-8"
        print(text.encode(enc, errors="replace").decode(enc, errors="replace"))


def print_items(pack: dict[str, Any], limit: int, as_json: bool) -> None:
    if as_json:
        payload = dict(pack)
        if limit > 0:
            payload["items"] = (pack.get("items") or [])[:limit]
        cli_print(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    items = pack.get("items") or []
    shown = items if limit <= 0 else items[:limit]
    extra = [safe_str(pack.get("code")), safe_str(pack.get("name")), safe_str(pack.get("symbol"))]
    bits = " ".join(p for p in extra if p)
    channel = pack.get("channel") or pack.get("kind") or ""
    cli_print(
        f"{bits}  channel={channel} keyword={pack.get('keyword') or ''} "
        f"{pack.get('begin_date', '')}~{pack.get('end_date', '')} "
        f"count={pack.get('count')}"
        + (f"/{pack.get('total')}" if pack.get("total") else "")
    )
    if pack.get("error"):
        cli_print(f"  error: {pack['error']}")
        return
    if not shown:
        cli_print("  (empty)")
        return
    for i, row in enumerate(shown, 1):
        day = (row.get("published_at") or "")[:19] or (row.get("published_at") or "")[:10]
        origin = row.get("media_name") or row.get("author") or row.get("category") or ""
        origin_bit = f" [{origin}]" if origin else ""
        cli_print(f"  [{i}] {day}{origin_bit} {row.get('title')}")
        if row.get("url"):
            cli_print(f"       {row['url']}")
