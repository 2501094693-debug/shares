"""定期报告 PDF：拉取字节，并渲染成页面图片供前端阅读展示。"""

from __future__ import annotations

import re
import threading
import time
from io import BytesIO
from urllib.parse import urlparse

try:
    import pypdfium2 as pdfium
except ImportError as exc:  # pragma: no cover
    raise ImportError("缺少依赖 pypdfium2，请执行: pip install pypdfium2") from exc

try:
    from PIL import Image  # noqa: F401  # pypdfium2.to_pil 需要 Pillow
except ImportError as exc:  # pragma: no cover
    raise ImportError("缺少依赖 Pillow，请执行: pip install Pillow") from exc

from core.codes import safe_str
from core.http import get_bytes

# pypdfium2 / PDFium 全库非线程安全；前端会并发拉多页，必须串行化。
_PDFIUM_LOCK = threading.Lock()

_ALLOWED_HOSTS = frozenset(
    {
        "static.cninfo.com.cn",
        "www.cninfo.com.cn",
        "static.sse.com.cn",
        "www.sse.com.cn",
        "disc.static.szse.cn",
        "www.szse.cn",
        "www.bse.cn",
        "www.neeq.com.cn",
    }
)

_TTL_SEC = 1800
_MAX_PDF = 16
_MAX_PAGE = 96
_pdf_cache: dict[str, tuple[float, bytes]] = {}
_page_cache: dict[str, tuple[float, bytes]] = {}


def referer_for(url: str) -> str:
    host = (urlparse(url).hostname or "").lower()
    if "cninfo" in host:
        return "https://www.cninfo.com.cn/"
    if "sse.com" in host:
        return "https://www.sse.com.cn/"
    if "szse" in host:
        return "https://www.szse.cn/"
    if "bse" in host or "neeq" in host:
        return "https://www.bse.cn/"
    return "https://www.cninfo.com.cn/"


def assert_allowed_pdf_url(url: str) -> str:
    raw = safe_str(url)
    parsed = urlparse(raw)
    host = (parsed.hostname or "").lower()
    if parsed.scheme not in {"http", "https"} or host not in _ALLOWED_HOSTS:
        raise ValueError("不支持的 PDF 地址")
    if not raw.lower().endswith(".pdf") and ".pdf" not in (parsed.path or "").lower():
        raise ValueError("不是 PDF 地址")
    return raw


def _cache_get(store: dict[str, tuple[float, bytes]], key: str) -> bytes | None:
    hit = store.get(key)
    if not hit:
        return None
    stamped, data = hit
    if time.time() - stamped >= _TTL_SEC:
        store.pop(key, None)
        return None
    return data


def _cache_put(
    store: dict[str, tuple[float, bytes]],
    key: str,
    data: bytes,
    *,
    limit: int,
) -> None:
    if len(store) >= limit:
        oldest = min(store.items(), key=lambda kv: kv[1][0])[0]
        store.pop(oldest, None)
    store[key] = (time.time(), data)


def _normalize_pdf_bytes(data: bytes) -> bytes:
    """去掉前导垃圾，并做基础完整性检查。"""
    if not data:
        raise ValueError("PDF 为空")
    start = data.find(b"%PDF")
    if start < 0:
        raise ValueError("返回内容不是 PDF")
    if start > 0:
        data = data[start:]
    # 截断下载常见：有文件头但没有 trailer
    if b"%%EOF" not in data:
        raise ValueError("PDF 下载不完整，请重试")
    return data


def fetch_pdf_bytes(url: str, *, force: bool = False) -> bytes:
    safe = assert_allowed_pdf_url(url)
    if not force:
        cached = _cache_get(_pdf_cache, safe)
        if cached is not None:
            return cached
    data = _normalize_pdf_bytes(
        get_bytes(
            safe,
            headers={"Referer": referer_for(safe)},
            timeout=90,
        )
    )
    _cache_put(_pdf_cache, safe, data, limit=_MAX_PDF)
    return data


def _pdfium_error_message(exc: BaseException) -> str:
    text = str(exc) or type(exc).__name__
    if "Data format error" in text or "Failed to load document" in text:
        return "PDF 无法打开（文件损坏或下载不完整），请刷新重试"
    return f"PDF 处理失败: {text}"


# 定期报告章节标题：第一节 / 第1章 / 第十篇 …
_CHAPTER_TITLE_RE = re.compile(
    r"^第[一二三四五六七八九十百千零〇两\d]+[章节篇部]"
)
# 正文目录行：标题 + 引导点/空白 + 页码
_TOC_LINE_RE = re.compile(
    r"^(?P<title>第[一二三四五六七八九十百千零〇两\d]+[章节篇部]\s*.+?)"
    r"\s*[\.．…·•‧、\-\s]{2,}\s*"
    r"(?P<page>\d+)\s*$"
)
_TOC_LINE_LOOSE_RE = re.compile(
    r"^(?P<title>第[一二三四五六七八九十百千零〇两\d]+[章节篇部]\s*\S.*?)"
    r"\s+(?P<page>\d{1,4})\s*$"
)
_TOC_HEADING_RE = re.compile(r"^目\s*录$|^CONTENTS$|^Table of Contents$", re.I)
_MAX_OUTLINE = 120
_TEXT_TOC_SCAN_PAGES = 20


def _page_text(doc: "pdfium.PdfDocument", index: int) -> str:
    page = doc[index]
    textpage = page.get_textpage()
    try:
        return textpage.get_text_bounded() or ""
    finally:
        textpage.close()


def _normalize_toc_title(title: str) -> str:
    text = re.sub(r"\s+", " ", safe_str(title)).strip(" .\t")
    # 「第一节 释义」保留空格；去掉标题里残留引导点
    text = re.sub(r"[\.．…·•‧]{2,}", "", text).strip()
    return text


def _bookmark_outline(doc: "pdfium.PdfDocument") -> list[dict[str, object]]:
    """提取 PDF 书签目录；兼容 pypdfium2 v4（PdfOutlineItem）与更新版（PdfBookmark）。"""
    items: list[dict[str, object]] = []
    try:
        toc_iter = doc.get_toc()
    except Exception:  # noqa: BLE001
        return items
    try:
        for bm in toc_iter:
            if hasattr(bm, "title"):
                title = safe_str(getattr(bm, "title", "") or "")
                page_index = getattr(bm, "page_index", None)
                level = int(getattr(bm, "level", 0) or 0)
            else:
                title = safe_str(bm.get_title() if hasattr(bm, "get_title") else "")
                level = int(getattr(bm, "level", 0) or 0)
                dest = bm.get_dest() if hasattr(bm, "get_dest") else None
                page_index = dest.get_index() if dest is not None else None
            if not title:
                continue
            page = int(page_index) + 1 if page_index is not None else None
            items.append({"title": title, "page": page, "level": max(0, level)})
    except Exception:  # noqa: BLE001
        return items
    return items


def _filter_chapter_bookmarks(
    items: list[dict[str, object]],
) -> list[dict[str, object]]:
    """从嘈杂书签中抽出「第X节/章」级章节（常见于沪深定期报告）。"""
    out: list[dict[str, object]] = []
    seen: set[tuple[str, int | None]] = set()
    for row in items:
        title = _normalize_toc_title(str(row.get("title") or ""))
        compact = title.replace(" ", "")
        if not _CHAPTER_TITLE_RE.match(compact):
            continue
        page = row.get("page")
        page_n = int(page) if page is not None else None
        key = (compact, page_n)
        if key in seen:
            continue
        seen.add(key)
        out.append({"title": title, "page": page_n, "level": 0})
    return out


def _parse_toc_lines(
    lines: list[str],
    *,
    total_pages: int,
) -> list[dict[str, object]]:
    items: list[dict[str, object]] = []
    for raw in lines:
        line = re.sub(r"\s+", " ", raw.replace("\u00a0", " ")).strip()
        if not line or _TOC_HEADING_RE.match(line):
            continue
        if line.startswith(("备查文件", "释义项")):
            break
        m = _TOC_LINE_RE.match(line) or _TOC_LINE_LOOSE_RE.match(line)
        if not m:
            # 已开始收集后遇到非目录行则结束，避免吃进正文
            if items:
                break
            continue
        title = _normalize_toc_title(m.group("title"))
        page = int(m.group("page"))
        if page < 1 or (total_pages and page > total_pages + 5):
            continue
        if total_pages and page > total_pages:
            page = min(page, total_pages)
        items.append({"title": title, "page": page, "level": 0})
    return items


def _text_toc(doc: "pdfium.PdfDocument") -> list[dict[str, object]]:
    """从正文「目录」页解析章节（无 PDF 书签时的主要来源，如深市半年报）。"""
    total = len(doc)
    scan = min(_TEXT_TOC_SCAN_PAGES, total)
    collected: list[dict[str, object]] = []
    for i in range(scan):
        text = _page_text(doc, i)
        lines = [ln.strip() for ln in text.replace("\r", "\n").split("\n") if ln.strip()]
        heading_at = next(
            (idx for idx, ln in enumerate(lines[:20]) if _TOC_HEADING_RE.match(ln)),
            None,
        )
        if heading_at is None:
            continue
        chunk = _parse_toc_lines(lines[heading_at + 1 :], total_pages=total)
        if len(chunk) >= 3:
            return chunk
        if len(chunk) > len(collected):
            collected = chunk
        # 目录可能跨页：继续吃下一页纯目录行
        if chunk and i + 1 < scan:
            more = _parse_toc_lines(
                [
                    ln.strip()
                    for ln in _page_text(doc, i + 1).replace("\r", "\n").split("\n")
                    if ln.strip()
                ],
                total_pages=total,
            )
            merged = chunk + more
            if len(merged) >= 3:
                return merged
    return collected


def _pdf_outline(doc: "pdfium.PdfDocument") -> list[dict[str, object]]:
    """解析目录：优先正文目录页，其次过滤后的书签，最后原始书签。"""
    text_items = _text_toc(doc)
    if len(text_items) >= 3:
        return text_items[:_MAX_OUTLINE]

    bookmarks = _bookmark_outline(doc)
    chapters = _filter_chapter_bookmarks(bookmarks)
    if len(chapters) >= 3:
        return chapters[:_MAX_OUTLINE]

    if text_items:
        return text_items[:_MAX_OUTLINE]

    # 书签过多时只保留顶层，避免「重要提示」逐条刷屏
    if len(bookmarks) > _MAX_OUTLINE:
        top = [row for row in bookmarks if int(row.get("level") or 0) == 0]
        if len(top) >= 3:
            return top[:_MAX_OUTLINE]
        return bookmarks[:_MAX_OUTLINE]
    return bookmarks


def pdf_meta(url: str, *, force: bool = False) -> dict[str, object]:
    data = fetch_pdf_bytes(url, force=force)
    with _PDFIUM_LOCK:
        try:
            doc = pdfium.PdfDocument(data)
        except Exception as exc:  # noqa: BLE001
            raise ValueError(_pdfium_error_message(exc)) from exc
        try:
            return {"pages": len(doc), "outline": _pdf_outline(doc)}
        finally:
            doc.close()


# 最高清晰度：3x 栅格 + 无损 PNG（避免 JPEG 压缩糊字）
_DEFAULT_SCALE = 3.0
_MAX_SCALE = 3.0


def render_pdf_page(
    url: str,
    page: int,
    *,
    scale: float = _DEFAULT_SCALE,
    force: bool = False,
) -> bytes:
    """把第 ``page`` 页（从 1 起）渲染成 PNG，方便前端当文档页展示。"""
    safe = assert_allowed_pdf_url(url)
    index = int(page)
    if index < 1:
        raise ValueError("页码从 1 开始")
    scale_n = max(1.0, min(float(scale or _DEFAULT_SCALE), _MAX_SCALE))
    cache_key = f"{safe}|{index}|{scale_n:.2f}|png"
    if not force:
        cached = _cache_get(_page_cache, cache_key)
        if cached is not None:
            return cached

    data = fetch_pdf_bytes(safe, force=force)
    with _PDFIUM_LOCK:
        try:
            doc = pdfium.PdfDocument(data)
        except Exception as exc:  # noqa: BLE001
            raise ValueError(_pdfium_error_message(exc)) from exc
        try:
            total = len(doc)
            if index > total:
                raise ValueError(f"页码超出范围（共 {total} 页）")
            pil = doc[index - 1].render(scale=scale_n).to_pil()
            if pil.mode not in {"RGB", "RGBA"}:
                pil = pil.convert("RGB")
            buf = BytesIO()
            pil.save(buf, format="PNG", optimize=True)
            png = buf.getvalue()
        finally:
            doc.close()

    _cache_put(_page_cache, cache_key, png, limit=_MAX_PAGE)
    return png
