"""同花顺新闻接口共用：请求头、日期、代码解析、去标签。"""

from __future__ import annotations

import html
import json
import logging
import re
import sys
from datetime import date, datetime, timedelta, timezone
from typing import Any, Iterable
from urllib.parse import quote

from core.codes import detect_market, normalize_code, safe_str
from core.http import browser_get

logger = logging.getLogger(__name__)

TZ_CN = timezone(timedelta(hours=8))
REQUEST_PAUSE_SEC = 0.25
SOURCE = "tonghuashun"

NEWS_API = "https://basic.10jqka.com.cn/basicapi/notice/news"
PUB_API = "https://basic.10jqka.com.cn/basicapi/notice/pub"
FLASH_API = "https://news.10jqka.com.cn/tapp/news/push/stock/"
FLASH_PAGE = "https://news.10jqka.com.cn/"
F10_HOST = "https://basic.10jqka.com.cn"

# F10 页 #marketId。92xxxx 北交所是 151，8/4 开头是 145。
_MARKET_BY_PREFIX = (
    ("92", "151"),
    ("8", "145"),
    ("4", "145"),
    ("60", "17"),
    ("68", "17"),
    ("90", "17"),
    ("00", "33"),
    ("30", "33"),
    ("20", "33"),
)
_MARKET_BY_DETECT = {"sse": "17", "szse": "33", "bse": "145"}

_HTML_TAG_RE = re.compile(r"<[^>]+>")
_TIME_RE = re.compile(r"(\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2})")
_MS_TAIL_RE = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})[:.]\d+")
_SEQ_RE = re.compile(r"(?:[cm]|seq=)?(\d{6,})")


def f10_news_url(code: str = "") -> str:
    stock = normalize_code(code) or safe_str(code)
    if stock:
        return f"{F10_HOST}/{stock}/news.html"
    return f"{F10_HOST}/"


def search_page_url(code_or_name: str = "") -> str:
    stock = normalize_code(code_or_name)
    if stock:
        return f10_news_url(stock)
    kw = safe_str(code_or_name)
    if kw:
        return f"https://news.10jqka.com.cn/search.html?keyword={quote(kw)}"
    return FLASH_PAGE


def ths_market(code: str) -> str:
    """F10 公告接口要的 market 号。沪 17 / 深 33 / 北交所 151 或 145。"""
    c = normalize_code(code)
    if not c:
        return ""
    for prefix, mid in _MARKET_BY_PREFIX:
        if c.startswith(prefix):
            return mid
    return _MARKET_BY_DETECT.get(detect_market(c), "17")


def article_url(seq_or_url: str, *, day: str = "") -> str:
    """文章 seq、含日期的路径或完整 URL → 可打开的正文页。"""
    raw = safe_str(seq_or_url)
    if not raw:
        return ""
    if raw.lower().startswith("http://") or raw.lower().startswith("https://"):
        return raw.replace("http://", "https://", 1)
    date_m = re.search(r"(20\d{6})", raw)
    seq_m = re.search(r"c(\d{6,})", raw, re.I) or re.search(r"(\d{6,})", raw)
    seq = seq_m.group(1) if seq_m else ""
    ymd = safe_str(day).replace("-", "")[:8]
    if not ymd and date_m:
        ymd = date_m.group(1)
    if seq and ymd:
        return f"https://stock.10jqka.com.cn/{ymd}/c{seq}.shtml"
    if seq:
        return f"https://news.10jqka.com.cn/m{seq}/"
    return raw


def article_candidates(seq_or_url: str, *, day: str = "") -> list[str]:
    """正文候选地址：完整 URL 优先，否则按 seq 试 PC / 移动 / 分享页。"""
    raw = safe_str(seq_or_url)
    if not raw:
        return []
    if raw.lower().startswith("http://") or raw.lower().startswith("https://"):
        url = raw.replace("http://", "https://", 1)
        out = [url]
        m = re.search(r"(20\d{6}).*?c(\d{6,})", url, re.I)
        if m:
            ymd, seq = m.group(1), m.group(2)
            alt = f"https://stock.10jqka.com.cn/{ymd}/c{seq}.shtml"
            if alt not in out:
                out.append(alt)
            alt = f"https://news.10jqka.com.cn/{ymd}/c{seq}.shtml"
            if alt not in out:
                out.append(alt)
        return out
    date_m = re.search(r"(20\d{6})", raw)
    seq_m = re.search(r"c(\d{6,})", raw, re.I) or _SEQ_RE.search(raw)
    seq = seq_m.group(1) if seq_m else re.sub(r"\D", "", raw)
    if not seq:
        return []
    ymd = safe_str(day).replace("-", "")[:8] or (date_m.group(1) if date_m else "")
    out: list[str] = []
    days = [ymd] if ymd else [
        (date.today() - timedelta(days=i)).strftime("%Y%m%d") for i in range(0, 8)
    ]
    for ymd in days:
        out.extend(
            [
                f"https://stock.10jqka.com.cn/{ymd}/c{seq}.shtml",
                f"https://news.10jqka.com.cn/{ymd}/c{seq}.shtml",
            ]
        )
    out.extend(
        [
            f"https://news.10jqka.com.cn/m{seq}/",
            f"https://news.10jqka.com.cn/tapp/news/share/{seq}/",
        ]
    )
    seen: set[str] = set()
    uniq: list[str] = []
    for url in out:
        if url not in seen:
            seen.add(url)
            uniq.append(url)
    return uniq


def headers_for(referer: str, *, origin: str = "") -> dict[str, str]:
    # 不要带 ``*/*; q=0.01``：部分 basicapi 会把 Accept 解析坏。
    hdrs = {
        "Referer": referer,
        "Accept": "application/json, text/javascript, */*",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "X-Requested-With": "XMLHttpRequest",
    }
    if origin:
        hdrs["Origin"] = origin
    return hdrs


def get_payload(
    url: str,
    *,
    params: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout: int = 25,
) -> Any:
    resp = browser_get(url, params=params, headers=headers or {}, timeout=timeout)
    resp.raise_for_status()
    try:
        payload = resp.json()
    except ValueError:
        text = resp.text.lstrip()
        payload = json.loads(text) if text else {}
    return payload if payload is not None else {}


def decode_html(resp: Any) -> str:
    """F10 页是 GBK，新闻正文页是 UTF-8。"""
    raw = getattr(resp, "content", b"") or b""
    ctype = safe_str(getattr(resp, "headers", {}).get("Content-Type")).lower()
    if "gbk" in ctype or "gb2312" in ctype or "gb18030" in ctype:
        return raw.decode("gb18030", "replace")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("gb18030", "replace")
    if "\ufffd" in text[:400]:
        return raw.decode("gb18030", "replace")
    return text


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
        art = safe_str(item.get("article_id") or item.get("seq") or item.get("guid"))
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
            from company.news.official.cninfo import resolve_org

            org = resolve_org(raw)
        except Exception as exc:  # noqa: BLE001
            logger.info("解析公司简称失败 %s: %s", raw, exc)
            org = None
        if org:
            code = safe_str(org.get("code")) or code
            name = safe_str(org.get("name"))
    keyword = name or (raw if not code or raw != code else code)
    return {"code": code, "name": name, "keyword": keyword, "market": ths_market(code)}


def relevant(item: dict[str, Any], *, code: str = "", name: str = "", keyword: str = "") -> bool:
    blob = f"{item.get('title', '')} {item.get('summary', '')}"
    tokens = [t for t in (name, keyword) if t and len(t) >= 2]
    if code and len(code) >= 6:
        tokens.append(code)
    stocks = item.get("related_stocks") or item.get("stock") or []
    if isinstance(stocks, list):
        for row in stocks:
            if isinstance(row, dict) and code and safe_str(row.get("stockCode")) == code:
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
        origin = row.get("media_name") or row.get("category") or row.get("rating") or ""
        origin_bit = f" [{origin}]" if origin else ""
        cli_print(f"  [{i}] {day}{origin_bit} {row.get('title')}")
        if row.get("url"):
            cli_print(f"       {row['url']}")
        pdf = row.get("pdf_url")
        if pdf:
            cli_print(f"       pdf {pdf}")
