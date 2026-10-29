"""同花顺手机端个股日线接口（quotebridge）接入。

手机端 / 网页端看个股日线时按「最近 N 根 + 按年文件」拆包：
- ``https://d.10jqka.com.cn/v6/line/hs_{code}/00/last.js``  最近约 140 根 + 年份索引
- ``https://d.10jqka.com.cn/v6/line/hs_{code}/00/{year}.js`` 该年全部日线

路径里的复权位：``00`` 不复权、``01`` 前复权、``02`` 后复权。筹码成本按
**不复权** 才成立（同花顺前复权是等差口径，早年价格会变成负数，无法作为
成本价）；取最新交易日时三种口径收盘价相同，筹码峰与当前 K 线仍能对齐。

响应是 JSONP：``quotebridge_v6_line_hs_600519_00_2024({...})``；``data`` 为

    日期,开,高,低,收,成交量(股),成交额(元),换手率(%),...

的分号串。成交量是**股**（不是手），换手率是**百分数**（0.168 = 0.168%），
正好是筹码分布推演需要的两个输入。

本模块只负责「取数 + 解析 + 按年落盘缓存」，筹码口径见 ``core.py``。
"""

from __future__ import annotations

import json
import logging
import os
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from core.cache import TtlCache
from core.codes import normalize_code
from core.fmt import to_float
from core.http import get_text
from core.paths import CACHE_DIR

logger = logging.getLogger(__name__)

_BASE = "https://d.10jqka.com.cn"
# 00 不复权 / 01 前复权 / 02 后复权；筹码成本必须用不复权
_ADJUST_FLAG = "00"
_HEADERS = {
    "Referer": "https://m.10jqka.com.cn/",
    "Accept": "*/*",
}
_CHIP_CACHE_DIR = CACHE_DIR / "chip" / "ths"
_YEAR_VERSION = 2
# 当年文件还会随交易日增长；往年文件视为不再变化，永久复用。
_YEAR_TTL_CURRENT = 300.0
_META_TTL = 300.0

_meta_cache = TtlCache(_META_TTL)


def _security(code: str) -> str:
    """THS 行情证券标识：沪深京 A 股统一 ``hs_{6位代码}``。"""
    norm = normalize_code(code)
    if not norm:
        return ""
    return f"hs_{norm}"


def _jsonp(text: str, *, url: str = "") -> dict[str, Any]:
    """剥 ``quotebridge_xxx({...})`` 外壳。"""
    raw = (text or "").strip()
    left, right = raw.find("("), raw.rfind(")")
    if left < 0 or right <= left:
        raise ValueError(f"同花顺返回非 JSONP：{url or raw[:60]}")
    try:
        payload = json.loads(raw[left + 1 : right])
    except json.JSONDecodeError as exc:
        raise ValueError(f"同花顺 JSONP 解析失败：{url}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"同花顺返回结构异常：{url}")
    return payload


def _parse_row(line: str) -> dict[str, Any] | None:
    """解析日线一行。列不足或关键价格缺失返回 None。

    前 8 列为固定口径；后面的扩展列（约 2026-07 起才有）不参与计算。
    """
    parts = str(line).split(",")
    if len(parts) < 8:
        return None
    date = parts[0].strip()
    if len(date) != 8 or not date.isdigit():
        return None
    open_ = to_float(parts[1])
    high = to_float(parts[2])
    low = to_float(parts[3])
    close = to_float(parts[4])
    if close is None or high is None or low is None:
        return None
    volume = to_float(parts[5]) or 0.0
    turnover = to_float(parts[7])
    return {
        "date": f"{date[:4]}-{date[4:6]}-{date[6:8]}",
        "open": open_ if open_ is not None else close,
        "high": high,
        "low": low,
        "close": close,
        # 股；价格为不复权（复权位 00），可直接作为筹码成本
        "volume": float(volume),
        "amount": to_float(parts[6]),
        "turnover": turnover,
}


def _rows_of(payload: dict[str, Any]) -> list[dict[str, Any]]:
    data = payload.get("data")
    if not isinstance(data, str) or not data.strip():
        return []
    rows = [row for chunk in data.split(";") if (row := _parse_row(chunk))]
    rows.sort(key=lambda r: r["date"])
    return rows


def _fetch(kind: str, code: str) -> dict[str, Any]:
    sec = _security(code)
    if not sec:
        raise ValueError("无效股票代码")
    url = f"{_BASE}/v6/line/{sec}/{_ADJUST_FLAG}/{kind}.js"
    text = get_text(url, headers=_HEADERS, timeout=10, retries=2)
    return _jsonp(text, url=url)


def fetch_last(code: str, *, refresh: bool = False) -> dict[str, Any]:
    """最近约 140 根 + 名称/上市日/年份索引。``refresh=True`` 跳过内存缓存。"""
    norm = normalize_code(code)
    if not norm:
        raise ValueError("无效股票代码")
    key = f"last:{norm}"
    if not refresh:
        hit = _meta_cache.get(key)
        if hit is not None:
            return hit

    payload = _fetch("last", norm)
    years: dict[int, int] = {}
    for raw_year, raw_count in (payload.get("year") or {}).items():
        try:
            years[int(raw_year)] = int(raw_count)
        except (TypeError, ValueError):
            continue
    total = payload.get("total")
    try:
        total_n = int(total)
    except (TypeError, ValueError):
        total_n = 0
    out = {
        "code": norm,
        "sec": _security(norm),
        "name": str(payload.get("name") or ""),
        "start": str(payload.get("start") or ""),
        "today": str(payload.get("today") or ""),
        "total": total_n,
        "years": years,
        "items": _rows_of(payload),
    }
    _meta_cache.put(key, out)
    return out


def _year_path(code: str, year: int) -> Path:
    return _CHIP_CACHE_DIR / code / f"{year}.json"


def _load_year_disk(code: str, year: int) -> list[dict[str, Any]] | None:
    path = _year_path(code, year)
    if not path.is_file():
        return None
    current = time.localtime().tm_year
    try:
        age = time.time() - path.stat().st_mtime
    except OSError:
        return None
    if year >= current and age >= _YEAR_TTL_CURRENT:
        return None
    try:
        body = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if int(body.get("version") or 0) != _YEAR_VERSION:
        return None
    rows = body.get("rows")
    if not isinstance(rows, list) or not rows:
        return None
    return [r for r in rows if isinstance(r, dict) and r.get("date")]


def _save_year_disk(code: str, year: int, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    path = _year_path(code, year)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        body = {
            "version": _YEAR_VERSION,
            "code": code,
            "year": year,
            "saved_at": time.time(),
            "rows": rows,
        }
        # 并发请求可能同时写同一年份：tmp 名带 pid/线程，replace 保持原子
        tmp = path.with_suffix(f".{os.getpid()}.{threading.get_ident()}.tmp")
        tmp.write_text(json.dumps(body, ensure_ascii=False), encoding="utf-8")
        tmp.replace(path)
    except OSError as exc:
        logger.info("chip year cache write %s %s failed: %s", code, year, exc)


def fetch_year(
    code: str,
    year: int,
    *,
    refresh: bool = False,
) -> list[dict[str, Any]]:
    """拉取某一年日线（先读磁盘缓存）。"""
    norm = normalize_code(code)
    if not norm:
        raise ValueError("无效股票代码")
    if not refresh:
        cached = _load_year_disk(norm, year)
        if cached is not None:
            return cached
    payload = _fetch(str(year), norm)
    rows = _rows_of(payload)
    _save_year_disk(norm, year, rows)
    return rows


def fetch_daily(
    code: str,
    *,
    end: str = "",
    refresh: bool = False,
    workers: int = 3,
) -> dict[str, Any]:
    """拉取截至 ``end`` 的全部日线（含上市以来历史，供筹码从首日开始累积）。

    参数
    ----
    end
        ``YYYY-MM-DD`` / ``YYYYMMDD``；只决定取到哪一年，不裁剪 ``items``。
    refresh
        跳过磁盘缓存重新拉全部年份。

    返回
    ----
    ``{code, sec, name, start, total, years, items, source}``，
    ``items`` 按日期升序，每项含 ``date/open/high/low/close/volume/turnover``。
    """
    norm = normalize_code(code)
    if not norm:
        raise ValueError("无效股票代码")
    end_year = 9999
    digits = re.sub(r"\D", "", str(end or ""))[:8]
    if len(digits) >= 4:
        try:
            end_year = int(digits[:4])
        except ValueError:
            end_year = 9999

    meta = fetch_last(norm, refresh=refresh)
    years = sorted(y for y in (meta.get("years") or {}) if y <= end_year)
    if not years:
        years = [end_year - 1, end_year] if end_year < 9999 else []

    by_date: dict[str, dict[str, Any]] = {}
    failed: list[int] = []
    if years:
        with ThreadPoolExecutor(max_workers=max(1, min(8, workers))) as pool:
            futs = {
                year: pool.submit(fetch_year, norm, year, refresh=refresh)
                for year in years
            }
            for year, fut in futs.items():
                try:
                    rows = fut.result()
                except Exception as exc:  # noqa: BLE001
                    logger.info("ths chip daily %s %s failed: %s", norm, year, exc)
                    failed.append(year)
                    continue
                for row in rows:
                    by_date[row["date"]] = row

    # 并发被对端掐连接（Windows 10054）时串行补一次；仍失败就整体报错：
    # 缺一整年会把筹码分布推偏，宁可让上层回退到三源 K 线
    for year in list(failed):
        try:
            rows = fetch_year(norm, year, refresh=True)
        except Exception as exc:  # noqa: BLE001
            logger.info("ths chip daily %s %s retry failed: %s", norm, year, exc)
            continue
        failed.remove(year)
        for row in rows:
            by_date[row["date"]] = row
    if failed:
        missing = ",".join(str(year) for year in failed)
        raise ValueError(f"{norm} 同花顺年线缺失 {missing}（对端断连或超时）")

    # last.js 是实时刷新的最近 140 根，覆盖年线文件里可能滞后的同日期数据
    for row in meta.get("items") or []:
        by_date[row["date"]] = row

    items = sorted(by_date.values(), key=lambda r: r["date"])
    if end_year < 9999:
        tail = f"{end_year:04d}-12-31"
        items = [r for r in items if r["date"] <= tail]
    if not items:
        raise ValueError(f"{norm} 同花顺无日线数据（可能退市或代码无效）")

    return {
        "code": norm,
        "sec": meta.get("sec") or _security(norm),
        "name": meta.get("name") or "",
        "start": meta.get("start") or items[0]["date"],
        "total": meta.get("total") or len(items),
        "years": years,
        "items": items,
        "source": "tonghuashun",
    }


def clear_cache(code: str = "") -> None:
    """清内存缓存；传代码时同时删除该股的年线落盘缓存。"""
    _meta_cache.__init__(_META_TTL)
    root = _CHIP_CACHE_DIR if not code else _CHIP_CACHE_DIR / normalize_code(code)
    if not root.is_dir():
        return
    for path in root.rglob("*.json"):
        try:
            path.unlink()
        except OSError:
            pass
