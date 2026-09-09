"""公告 PDF：下载、缓存、抽文字、截取经营相关章节。

优先巨潮 static CDN；上交所 CDN 走其带校验的下载器。
年报只抽前若干页里的经营讨论 / 主营业务，避免把整本财务附注塞进模型。
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
import sys
import time
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse

from config import BACKEND_ROOT, PROJECT_ROOT

logger = logging.getLogger(__name__)

if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

PDF_CACHE_DIR = Path(os.getenv("PDF_CACHE_DIR", str(PROJECT_ROOT / "cache" / "pdfs")))
PDF_MAX_PAGES = 90
PDF_ANNUAL_CHARS = 18000
PDF_PERIODIC_CHARS = 8000
PDF_NOTICE_CHARS = 3500
PDF_TOTAL_CHARS = 40000
DOWNLOAD_PAUSE_SEC = 0.35

_SKIP_TITLES = ("摘要", "英文", "取消", "XBRL", "已取消", "已于", "上网文件")
_NOTICE_SKIP = ("停牌", "复牌", "权益分派实施", "股东大会决议", "独立董事", "持股变动")

_KEEP_MARKERS: tuple[tuple[str, int], ...] = (
    ("管理层讨论与分析", 14000),
    ("经营情况讨论与分析", 12000),
    ("经营情况的讨论与分析", 12000),
    ("报告期内公司从事的业务情况", 8000),
    ("报告期内主营业务", 10000),
    ("主营业务分析", 9000),
    ("主营业务", 8000),
    ("公司从事的主要业务", 6000),
    ("主要业务", 5000),
    ("核心竞争力", 4000),
    ("主要会计数据和财务指标", 3500),
    ("主要财务指标", 3000),
    ("分行业、分产品", 6000),
    ("分行业、分地区", 6000),
    ("营业收入情况", 5000),
    ("主要销售客户", 3000),
    ("主要客户", 3000),
    ("研发投入", 2500),
)

_PRIMARY_MARKERS = {
    "管理层讨论与分析",
    "经营情况讨论与分析",
    "经营情况的讨论与分析",
    "报告期内公司从事的业务情况",
    "报告期内主营业务",
    "主营业务分析",
}

_RISK_KEEP_MARKERS: tuple[tuple[str, int], ...] = (
    ("公司治理", 8000),
    ("风险因素", 10000),
    ("可能面对的风险", 10000),
    ("重要事项", 8000),
    ("股份变动及股东情况", 6000),
    ("股东和实际控制人情况", 6000),
    ("董事、监事、高级管理人员情况", 8000),
    ("董事、监事和高级管理人员情况", 8000),
    ("关联交易", 6000),
    ("内部控制", 5000),
    ("会计师事务所", 3000),
    ("管理层讨论与分析", 8000),
    ("经营情况讨论与分析", 6000),
)

ProgressCb = Callable[[str], None]


def _source_rank(item: dict[str, Any]) -> int:
    url = (item.get("url") or "").lower()
    source = str(item.get("source") or item.get("channel") or "").lower()
    if "static.cninfo.com.cn" in url:
        return 0
    if "cninfo" in url or "巨潮" in source or source == "cninfo":
        return 1
    return 2


def prefer_cninfo_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """去重时保留巨潮 PDF 链接（比交易所 CDN 更容易下到）。"""
    unique: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for item in items:
        title = (item.get("title") or "").strip()
        pub = str(item.get("published_at") or item.get("date") or "")[:10]
        key = f"{title}|{pub}"
        if not title:
            continue
        prev = unique.get(key)
        if prev is None:
            unique[key] = item
            order.append(key)
        elif _source_rank(item) < _source_rank(prev):
            unique[key] = item
    return [unique[k] for k in order]


def is_skip_title(title: str, *, extra: tuple[str, ...] = ()) -> bool:
    blob = title or ""
    return any(token in blob for token in _SKIP_TITLES + extra)


def pick_latest_full_report(items: list[dict[str, Any]]) -> dict[str, Any] | None:
    ranked = prefer_cninfo_items(items)
    for item in ranked:
        if not item.get("url"):
            continue
        if is_skip_title(item.get("title") or ""):
            continue
        return item
    for item in ranked:
        title = item.get("title") or ""
        if item.get("url") and "取消" not in title and "英文" not in title:
            return item
    return None


def pick_notice_pdfs(
    items: list[dict[str, Any]],
    *,
    already: list[dict[str, Any]],
    limit: int = 5,
) -> list[dict[str, Any]]:
    taken_urls = {(row.get("url") or "") for row in already}
    taken_titles = {(row.get("title") or "").strip() for row in already}
    out: list[dict[str, Any]] = []
    for item in prefer_cninfo_items(items):
        title = (item.get("title") or "").strip()
        url = item.get("url") or ""
        if not url or url in taken_urls or title in taken_titles:
            continue
        if is_skip_title(title, extra=_NOTICE_SKIP):
            continue
        out.append(item)
        taken_urls.add(url)
        if len(out) >= limit:
            break
    return out


def _cache_stem(url: str) -> str:
    return hashlib.sha1(url.encode("utf-8")).hexdigest()[:16]


def cache_pdf_path(code: str, url: str) -> Path:
    return PDF_CACHE_DIR / (code or "unknown") / f"{_cache_stem(url)}.pdf"


def _text_cache_path(pdf_path: Path) -> Path:
    return pdf_path.with_suffix(".txt")


def _is_real_pdf(path: Path) -> bool:
    try:
        return path.is_file() and path.stat().st_size > 1024 and path.read_bytes()[:4] == b"%PDF"
    except OSError:
        return False


def _download_to(url: str, dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    host = (urlparse(url).netloc or "").lower()
    if "sse.com.cn" in host or "sseinfo.com" in host:
        from company.news.official.exchange.sse import download_pdf as sse_download

        return sse_download(url, dest)
    if "szse.cn" in host:
        from company.news.official.exchange.szse import download_pdf as szse_download

        return szse_download(url, dest)
    if "bse.cn" in host:
        from company.news.official.exchange.bse import download_pdf as bse_download

        return bse_download(url, dest)
    from company.news.official.cninfo.request import download_pdf as cninfo_download

    return cninfo_download(url, dest)


def ensure_pdf(url: str, code: str) -> Path:
    dest = cache_pdf_path(code, url)
    if _is_real_pdf(dest):
        return dest
    if dest.exists():
        dest.unlink(missing_ok=True)
    path = _download_to(url, dest)
    if not _is_real_pdf(path):
        path.unlink(missing_ok=True)
        raise RuntimeError(f"下载结果不是 PDF: {url}")
    return path


def _normalize_pdf_text(text: str) -> str:
    text = text.replace("\u3000", " ").replace("\xa0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"(?<=[\u4e00-\u9fff])\s+(?=[\u4e00-\u9fff])", "", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def extract_pdf_text(path: Path, *, max_pages: int = PDF_MAX_PAGES) -> str:
    cached = _text_cache_path(path)
    if cached.is_file() and cached.stat().st_mtime >= path.stat().st_mtime:
        return cached.read_text(encoding="utf-8")

    text = ""
    try:
        import pymupdf

        doc = pymupdf.open(path)
        try:
            pages = min(len(doc), max_pages)
            parts = [doc[i].get_text("text") or "" for i in range(pages)]
            text = "\n".join(parts)
        finally:
            doc.close()
    except Exception as exc:
        logger.info("PyMuPDF 抽取失败，改用 pypdf: %s", exc)
        try:
            from pypdf import PdfReader

            reader = PdfReader(str(path))
            pages = min(len(reader.pages), max_pages)
            text = "\n".join((reader.pages[i].extract_text() or "") for i in range(pages))
        except Exception as fallback_exc:
            raise RuntimeError(f"无法抽取 PDF 文字: {path.name} ({fallback_exc})") from fallback_exc

    text = _normalize_pdf_text(text)
    if not text:
        raise RuntimeError(f"PDF 无可抽取文字（可能是扫描件）: {path.name}")
    cached.write_text(text, encoding="utf-8")
    return text


def _find_marker(text: str, marker: str) -> int:
    """跳过目录里「标题……页码」那种命中，定位正文。"""
    start = 0
    while True:
        idx = text.find(marker, start)
        if idx < 0:
            return -1
        after = text[idx + len(marker) : idx + len(marker) + 120]
        prev = text[max(0, idx - 1) : idx]
        if prev in '"“「『《':
            start = idx + len(marker)
            continue
        if re.search(r"[.．…·]{6,}", after) or re.search(r"-{8,}", after):
            start = idx + len(marker)
            continue
        return idx


def slice_risk_text(text: str, *, budget: int) -> str:
    """截取公司治理、风险因素、关联交易等章节。"""
    if not text:
        return ""
    hits: list[tuple[int, int, str, int]] = []
    for marker, width in _RISK_KEEP_MARKERS:
        idx = _find_marker(text, marker)
        if idx < 0:
            continue
        start = max(0, idx - 20)
        end = min(len(text), idx + width)
        hits.append((0, start, end, marker))
    if not hits:
        return text[:budget]

    hits.sort(key=lambda row: row[1])
    merged: list[tuple[int, int, list[str]]] = []
    for _pri, start, end, marker in hits:
        if merged and start <= merged[-1][1] + 80:
            prev_start, prev_end, names = merged[-1]
            if marker not in names:
                names.append(marker)
            merged[-1] = (prev_start, max(prev_end, end), names)
        else:
            merged.append((start, end, [marker]))

    chunks: list[str] = []
    used = 0
    for start, end, names in merged:
        piece = text[start:end].strip()
        if len(piece) < 40:
            continue
        label = "、".join(names[:3])
        block = f"【{label}】\n{piece}"
        remain = budget - used
        if remain <= 200:
            break
        if len(block) > remain:
            block = block[:remain] + "\n…（已截断）"
        chunks.append(block)
        used += len(block)
        if used >= budget:
            break
    return "\n\n".join(chunks)[:budget] if chunks else text[:budget]


def slice_business_text(text: str, *, budget: int) -> str:
    """截取经营讨论、主营业务、收入结构等章节。"""
    if not text:
        return ""
    hits: list[tuple[int, int, str, int]] = []
    for marker, width in _KEEP_MARKERS:
        idx = _find_marker(text, marker)
        if idx < 0:
            continue
        priority = 0 if marker in _PRIMARY_MARKERS else 1
        start = max(0, idx - 20)
        end = min(len(text), idx + width)
        hits.append((priority, start, end, marker))
    if not hits:
        return text[:budget]

    hits.sort(key=lambda row: (row[0], row[1]))
    merged: list[tuple[int, int, int, list[str]]] = []
    for priority, start, end, marker in hits:
        if merged and start <= merged[-1][1] + 80 and priority == merged[-1][2]:
            prev_start, prev_end, prev_pri, names = merged[-1]
            if marker not in names:
                names.append(marker)
            merged[-1] = (prev_start, max(prev_end, end), prev_pri, names)
        else:
            merged.append((start, end, priority, [marker]))

    chunks: list[str] = []
    used = 0
    for start, end, _pri, names in merged:
        piece = text[start:end].strip()
        if len(piece) < 40:
            continue
        label = "、".join(names[:3])
        block = f"【{label}】\n{piece}"
        remain = budget - used
        if remain <= 200:
            break
        if len(block) > remain:
            block = block[:remain] + "\n…（已截断）"
        chunks.append(block)
        used += len(block)
        if used >= budget:
            break
    return "\n\n".join(chunks)[:budget] if chunks else text[:budget]


def _char_budget(title: str) -> int:
    title = title or ""
    if "年度报告" in title and "摘要" not in title:
        return PDF_ANNUAL_CHARS
    if "半年度" in title or "半年报" in title:
        return PDF_PERIODIC_CHARS
    if "季度" in title or "季报" in title:
        return PDF_PERIODIC_CHARS
    return PDF_NOTICE_CHARS


def ingest_risk_notice_pdfs(
    items: list[dict[str, Any]],
    *,
    code: str,
    progress: ProgressCb | None = None,
) -> str:
    """下载并抽取一批公告 PDF，保留治理/风险相关章节。"""
    if not items:
        return ""

    blocks: list[str] = []
    used = 0
    ok = 0
    for item in items:
        if used >= PDF_TOTAL_CHARS:
            break
        title = (item.get("title") or "无标题").strip()
        url = item.get("url") or ""
        pub = str(item.get("published_at") or item.get("date") or "")[:10]
        source = item.get("source") or item.get("channel") or ""
        if progress:
            progress(f"下载 PDF：{title}")
        if not url:
            blocks.append(f"#### {title}\n（无 PDF 链接）")
            continue
        try:
            path = ensure_pdf(url, code)
            raw = extract_pdf_text(path)
            budget = min(_char_budget(title), PDF_TOTAL_CHARS - used)
            body = slice_risk_text(raw, budget=budget)
            ok += 1
            used += len(body)
            blocks.append(
                f"#### {title}（{pub}）\n"
                f"来源: {source} | 链接: {url}\n\n"
                f"{body}"
            )
        except Exception as exc:
            logger.warning("公告 PDF 失败 %s: %s", title, exc)
            blocks.append(
                f"#### {title}（{pub}）\n"
                f"来源: {source} | 链接: {url}\n"
                f"（未能抽取正文：{exc}）"
            )
        time.sleep(DOWNLOAD_PAUSE_SEC)

    header = (
        f"### 公告 PDF 正文（已尝试 {len(items)} 份，成功抽出 {ok} 份；"
        "仅保留公司治理 / 风险因素 / 关联交易等章节）\n"
    )
    return header + "\n\n".join(blocks)


def ingest_notice_pdfs(
    items: list[dict[str, Any]],
    *,
    code: str,
    progress: ProgressCb | None = None,
) -> str:
    """下载并抽取一批公告 PDF，返回可直接写入 prompt 的正文。"""
    if not items:
        return ""

    blocks: list[str] = []
    used = 0
    ok = 0
    for item in items:
        if used >= PDF_TOTAL_CHARS:
            break
        title = (item.get("title") or "无标题").strip()
        url = item.get("url") or ""
        pub = str(item.get("published_at") or item.get("date") or "")[:10]
        source = item.get("source") or item.get("channel") or ""
        if progress:
            progress(f"下载 PDF：{title}")
        if not url:
            blocks.append(f"#### {title}\n（无 PDF 链接）")
            continue
        try:
            path = ensure_pdf(url, code)
            raw = extract_pdf_text(path)
            budget = min(_char_budget(title), PDF_TOTAL_CHARS - used)
            body = slice_business_text(raw, budget=budget)
            ok += 1
            used += len(body)
            blocks.append(
                f"#### {title}（{pub}）\n"
                f"来源: {source} | 链接: {url}\n\n"
                f"{body}"
            )
        except Exception as exc:
            logger.warning("公告 PDF 失败 %s: %s", title, exc)
            blocks.append(
                f"#### {title}（{pub}）\n"
                f"来源: {source} | 链接: {url}\n"
                f"（未能抽取正文：{exc}）"
            )
        time.sleep(DOWNLOAD_PAUSE_SEC)

    header = (
        f"### 公告 PDF 正文（已尝试 {len(items)} 份，成功抽出 {ok} 份；"
        "仅保留经营讨论 / 主营业务 / 收入结构等章节）\n"
    )
    return header + "\n\n".join(blocks)
