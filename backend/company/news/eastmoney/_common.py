"""东财新闻接口共用：JSON/JSONP、日期、去标签、关键词解析。"""

from __future__ import annotations

import html
import json
import logging
import re
import sys
import time
from datetime import date, datetime, timedelta, timezone
from typing import Any, Iterable
from urllib.parse import quote

from core.codes import normalize_code, safe_str
from core.http import browser_get

logger = logging.getLogger(__name__)

TZ_CN = timezone(timedelta(hours=8))
REQUEST_PAUSE_SEC = 0.25
SOURCE = "eastmoney"

_HTML_TAG_RE = re.compile(r"<[^>]+>")
_TIME_RE = re.compile(r"(\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2})")
_MS_TAIL_RE = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})[:.]\d+")
_CN_TIME_RE = re.compile(r"(\d{4})年(\d{1,2})月(\d{1,2})日\s*(\d{1,2}):(\d{2})")


def req_trace() -> str:
    return str(int(time.time() * 1000))


def search_page_url(keyword: str = "") -> str:
    kw = safe_str(keyword)
    if kw:
        return f"https://so.eastmoney.com/news/s?keyword={quote(kw)}"
    return "https://so.eastmoney.com/news/s"


def article_url(code_or_url: str) -> str:
    """文章 ID 或任意东财链接 → 正文页。"""
    raw = safe_str(code_or_url)
    if not raw:
        return ""
    if raw.lower().startswith("http://") or raw.lower().startswith("https://"):
        return raw.replace("http://", "https://", 1)
    digits = re.sub(r"\D", "", raw)
    if len(digits) >= 15:
        return f"https://finance.eastmoney.com/a/{digits}.html"
    return raw


def notice_page_url(code: str, art_code: str) -> str:
    stock = normalize_code(code) or safe_str(code)
    art = safe_str(art_code)
    if not stock or not art:
        return ""
    return f"https://data.eastmoney.com/notices/detail/{stock}/{art}.html"


def f10_page_url(code: str) -> str:
    from core.codes import em_code

    em = em_code(code) or safe_str(code).upper()
    if not em:
        return "https://emweb.securities.eastmoney.com/PC_HSF10/NewsBulletin/Index"
    return (
        "https://emweb.securities.eastmoney.com/PC_HSF10/NewsBulletin/Index"
        f"?type=web&code={em}"
    )


def jsonp_callback() -> str:
    ts = req_trace()
    return f"jQuery3510_{ts}"


def parse_jsonp(text: str) -> Any:
    raw = safe_str(text).lstrip()
    if not raw:
        return {}
    if raw[0] in "{[":
        return json.loads(raw)
    start = raw.find("(")
    end = raw.rfind(")")
    if start < 0 or end <= start:
        return json.loads(raw)
    return json.loads(raw[start + 1 : end])


def get_payload(
    url: str,
    *,
    params: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout: int = 25,
) -> Any:
    """GET 后解析 JSON 或 JSONP。"""
    resp = browser_get(url, params=params, headers=headers or {}, timeout=timeout)
    resp.raise_for_status()
    payload = parse_jsonp(resp.text)
    return payload if payload is not None else {}


def headers_for(referer: str, *, origin: str = "") -> dict[str, str]:
    hdrs = {
        "Referer": referer,
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    }
    if origin:
        hdrs["Origin"] = origin
    return hdrs


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


def strip_em(text: str) -> str:
    return re.sub(r"</?em[^>]*>", "", safe_str(text), flags=re.IGNORECASE)


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
    """毫秒时间戳、带尾毫秒的东财时间、普通 datetime 都收成 ``YYYY-MM-DD HH:MM:SS``。"""
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
    m = _MS_TAIL_RE.match(text)
    if m:
        return m.group(1)
    m = _CN_TIME_RE.search(text)
    if m:
        y, mo, d, h, mi = (int(x) for x in m.groups())
        return f"{y:04d}-{mo:02d}-{d:02d} {h:02d}:{mi:02d}:00"
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


def dedupe(items: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for item in items:
        url = safe_str(item.get("url")).lower()
        art = safe_str(item.get("article_id") or item.get("art_code"))
        title = safe_str(item.get("title"))
        day = safe_str(item.get("published_at"))[:10]
        key = art or url or f"{title}|{day}"
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def resolve_keyword(code_or_name: str) -> dict[str, str]:
    """代码优先解析成简称；失败则原样当关键词。"""
    raw = safe_str(code_or_name)
    code = normalize_code(raw)
    name = ""
    if raw:
        try:
            from company.news.cninfo import resolve_org

            org = resolve_org(raw)
        except Exception as exc:  # noqa: BLE001
            logger.info("解析公司简称失败 %s: %s", raw, exc)
            org = None
        if org:
            code = safe_str(org.get("code")) or code
            name = safe_str(org.get("name"))
    keyword = name or (raw if not code or raw != code else code)
    return {"code": code, "name": name, "keyword": keyword}


def relevant(item: dict[str, Any], *, code: str = "", name: str = "", keyword: str = "") -> bool:
    blob = f"{item.get('title', '')} {item.get('summary', '')}"
    tokens = [t for t in (name, keyword) if t and len(t) >= 2]
    if code and len(code) >= 6:
        tokens.append(code)
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
    extra = [safe_str(pack.get("code")), safe_str(pack.get("name"))]
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
        origin = row.get("media_name") or row.get("category") or ""
        origin_bit = f" [{origin}]" if origin else ""
        cli_print(f"  [{i}] {day}{origin_bit} {row.get('title')}")
        if row.get("url"):
            cli_print(f"       {row['url']}")
