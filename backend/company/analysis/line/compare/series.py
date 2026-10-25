"""日线序列拉取与四项涨跌幅计算。

- 个股：``company.line.fetcher.fetch_kline``（前复权日线）
- 指数：``exponent.fetch_kline``，**优先同花顺**，失败再东财 / 磁盘缓存 / 腾讯
"""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from company.analysis.line.compare.codes import FACTORS

logger = logging.getLogger(__name__)

_FETCH_RETRIES = 4

# 与 probe / 既有缓存约定一致：``cache/analysis/index_day/{secid}_day.json``
_INDEX_DAY_CACHE = (
    Path(__file__).resolve().parents[4] / "cache" / "analysis" / "index_day"
)

_TX_SYMBOL: dict[str, str] = {
    "000001": "sh000001",
    "399001": "sz399001",
    "000300": "sh000300",
    "000905": "sh000905",
    "000852": "sh000852",
}


def _norm_date(value: str) -> str:
    return str(value or "")[:10].replace("/", "-")


def _ymd(value: str) -> str:
    text = (value or "").replace("-", "").replace("/", "").strip()
    if not text:
        return ""
    if len(text) == 8 and text.isdigit():
        return text
    raise ValueError(f"日期须为 YYYYMMDD 或 YYYY-MM-DD，收到 {value!r}")


def _iso(value: str) -> str:
    ymd = _ymd(value)
    return f"{ymd[:4]}-{ymd[4:6]}-{ymd[6:8]}"


def _pad_beg(beg: str, *, days: int = 90) -> str:
    """向前多取若干自然日：前收 + 波动标准化所需历史（约 20 个交易日）。"""
    ymd = _ymd(beg)
    dt = datetime.strptime(ymd, "%Y%m%d") - timedelta(days=days)
    return dt.strftime("%Y%m%d")


def _today_ymd() -> str:
    return datetime.now().strftime("%Y%m%d")


def _retry(loader, *, label: str, retries: int = _FETCH_RETRIES) -> dict[str, Any]:
    last: Exception | None = None
    for attempt in range(max(1, retries)):
        try:
            pack = loader()
            if pack.get("items"):
                return pack
            last = ValueError("空 K 线")
        except ValueError:
            raise
        except RuntimeError as exc:
            # 同花顺未登录：立即失败，交给下游回退，不要空等重试
            if "THS_NEED_QRCODE" in str(exc):
                raise
            last = exc
            time.sleep(1.2 + attempt * 1.5)
        except Exception as exc:  # noqa: BLE001
            last = exc
            time.sleep(1.2 + attempt * 1.5)
    raise ValueError(f"行情接口暂时抖动({label})，请稍后重试: {last}")


def _try_index_source(
    *,
    display: str,
    pad: str,
    end_s: str,
    source: str,
    retries: int = _FETCH_RETRIES,
) -> dict[str, Any] | None:
    """尝试某一指数源；失败返回 None（登录缺失等立即放弃该源）。"""
    from exponent import fetch_kline

    try:
        pack = _retry(
            lambda: fetch_kline(
                display,
                source=source,
                period="day",
                beg=pad,
                end=end_s,
                limit=10000,
            ),
            label=f"index:{source}:{display}",
            retries=retries,
        )
        return {
            "code": str(pack.get("code") or display),
            "name": str(pack.get("name") or ""),
            "source": str(pack.get("source") or source),
            "items": list(pack.get("items") or []),
        }
    except RuntimeError as exc:
        logger.info("index source %s skip %s: %s", source, display, exc)
        return None
    except ValueError as exc:
        logger.info("index source %s failed %s: %s", source, display, exc)
        return None


def _filter_range(
    items: list[dict[str, Any]],
    *,
    lo: str,
    hi: str,
    keep_before: int = 1,
) -> list[dict[str, Any]]:
    """保留 [lo, hi]；并多留 lo 之前若干根（前收 / 波动窗）。"""
    if not items:
        return []
    sorted_items = sorted(items, key=lambda b: _norm_date(str(b.get("time") or "")))
    in_range = [
        b
        for b in sorted_items
        if lo <= _norm_date(str(b.get("time") or "")) <= hi
    ]
    if not in_range:
        return []
    first_in = _norm_date(str(in_range[0].get("time") or ""))
    prev = [b for b in sorted_items if _norm_date(str(b.get("time") or "")) < first_in]
    n = max(0, int(keep_before))
    head = prev[-n:] if n and prev else []
    return head + in_range


def _index_meta(code: str) -> dict[str, Any]:
    from exponent.eastmoney.codes import resolve

    return resolve(code)


def _cache_path(secid: str) -> Path:
    return _INDEX_DAY_CACHE / f"{secid}_day.json"


def _load_index_disk(secid: str) -> dict[str, Any] | None:
    path = _cache_path(secid)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict) or not data.get("items"):
        return None
    return data


def _save_index_disk(secid: str, pack: dict[str, Any]) -> None:
    path = _cache_path(secid)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        body = {
            "version": 1,
            "name": pack.get("name") or "",
            "source": pack.get("source") or "",
            "fetched_at": datetime.now().isoformat(timespec="seconds"),
            "count": len(pack.get("items") or []),
            "items": list(pack.get("items") or []),
        }
        path.write_text(json.dumps(body, ensure_ascii=False), encoding="utf-8")
    except OSError as exc:
        logger.info("index day cache write failed %s: %s", secid, exc)


def _fetch_index_tencent(code: str, *, pad: str, end_s: str) -> dict[str, Any]:
    """同花顺/东财都不可用时，用系统腾讯 K 线拉宽基指数。"""
    from company.line.tencent.kline import fetch_line

    sym = _TX_SYMBOL.get(code) or f"sh{code}"
    return fetch_line(sym, period="day", adjust="none", beg=pad, end=end_s, limit=10000)


def _merge_bars_by_date(
    older: list[dict[str, Any]], newer: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    have = {_norm_date(str(b.get("time") or "")) for b in newer}
    head = [
        b
        for b in older
        if (d := _norm_date(str(b.get("time") or ""))) and d not in have
    ]
    return sorted(head + list(newer), key=lambda b: _norm_date(str(b.get("time") or "")))


def fetch_stock_day(code: str, *, beg: str, end: str = "") -> dict[str, Any]:
    """个股日线（系统统一入口，带缓存）。

    腾讯等源单页约 640 根；长区间按 end 往前翻页，直到覆盖 beg（与行情日 K
    loadOlder 同策略），避免股指对比只算出近两年。
    """
    from company.line.fetcher import fetch_kline

    beg_s = _ymd(beg)
    end_s = _ymd(end) or _today_ymd()
    if beg_s > end_s:
        raise ValueError(f"起始日不能晚于结束日: {beg_s} > {end_s}")
    pad = _pad_beg(beg_s)
    lo, hi = _iso(beg_s), _iso(end_s)

    def _page(*, beg_arg: str = "", end_arg: str = "", limit: int = 2000) -> dict[str, Any]:
        return fetch_kline(
            code,
            period="day",
            adjust="qfq",
            beg=beg_arg,
            end=end_arg,
            limit=limit,
        )

    pack = _retry(
        lambda: _page(beg_arg=pad, end_arg=end_s, limit=10000),
        label=f"stock:{code}",
    )
    items = list(pack.get("items") or [])
    source = str(pack.get("source") or "")
    name = str(pack.get("name") or "")

    # 单页未盖住起始日时继续往前翻（最多约 40 页，足够覆盖 A 股上市以来日线）
    for _ in range(40):
        if not items:
            break
        first = _norm_date(str(items[0].get("time") or ""))
        if not first or first <= lo:
            break
        if pack.get("full_history"):
            break
        try:
            end_page = (
                datetime.strptime(first, "%Y-%m-%d") - timedelta(days=1)
            ).strftime("%Y%m%d")
        except ValueError:
            break
        try:
            older_pack = _retry(
                lambda ep=end_page: _page(end_arg=ep, limit=2000),
                label=f"stock-older:{code}:{end_page}",
            )
        except ValueError:
            break
        older_items = [
            b
            for b in (older_pack.get("items") or [])
            if _norm_date(str(b.get("time") or "")) < first
        ]
        if not older_items:
            break
        items = _merge_bars_by_date(older_items, items)
        if older_pack.get("source"):
            source = str(older_pack.get("source") or source)
        if older_pack.get("name") and not name:
            name = str(older_pack.get("name") or "")
        pack = older_pack
        if older_pack.get("full_history"):
            break

    # 保留请求区间前约 40 根，供前收与波动 σ（20 日窗）
    items = _filter_range(items, lo=lo, hi=hi, keep_before=40)
    return {
        "code": str(pack.get("code") or code),
        "name": name or str(pack.get("name") or ""),
        "source": source or str(pack.get("source") or ""),
        "adjust": "qfq",
        "beg": lo,
        "end": hi,
        "items": items,
    }


def _pack_in_range(
    pack: dict[str, Any] | None,
    *,
    lo: str,
    hi: str,
    keep_before: int = 40,
) -> list[dict[str, Any]]:
    """过滤到请求区间；区间内无 bar 则返回空（视为该源未覆盖）。"""
    if not pack:
        return []
    return _filter_range(
        list(pack.get("items") or []), lo=lo, hi=hi, keep_before=keep_before
    )


def fetch_index_day(code: str, *, beg: str, end: str = "") -> dict[str, Any]:
    """指数日线：同花顺优先 → 东财 → 磁盘缓存 → 腾讯。

    某一源若拉到了数据但请求区间内无 bar（例如过期磁盘缓存），会继续试下一源，
    避免空结果挡住腾讯等回退。
    """
    beg_s = _ymd(beg)
    end_s = _ymd(end) or _today_ymd()
    if beg_s > end_s:
        raise ValueError(f"起始日不能晚于结束日: {beg_s} > {end_s}")
    pad = _pad_beg(beg_s)
    lo, hi = _iso(beg_s), _iso(end_s)

    meta = _index_meta(code)
    secid = str(meta.get("secid") or "")
    display = str(meta.get("code") or code)
    name = str(meta.get("name") or "")

    chosen: dict[str, Any] | None = None
    items: list[dict[str, Any]] = []

    for source in ("tonghuashun", "eastmoney"):
        retries = 2 if source == "tonghuashun" else _FETCH_RETRIES
        pack = _try_index_source(
            display=display, pad=pad, end_s=end_s, source=source, retries=retries
        )
        filtered = _pack_in_range(pack, lo=lo, hi=hi)
        if pack is not None and filtered:
            chosen, items = pack, filtered
            break

    if not items:
        disk = _load_index_disk(secid) if secid else None
        if disk and disk.get("items"):
            pack = {
                "code": display,
                "name": str(disk.get("name") or name),
                "source": f"cache:{disk.get('source') or 'disk'}",
                "items": list(disk["items"]),
            }
            filtered = _pack_in_range(pack, lo=lo, hi=hi)
            if filtered:
                chosen, items = pack, filtered

    if not items:
        try:
            tx = _retry(
                lambda: _fetch_index_tencent(display, pad=pad, end_s=end_s),
                label=f"index-tx:{display}",
            )
            pack = {
                "code": display,
                "name": str(tx.get("name") or name),
                "source": "tencent",
                "items": list(tx.get("items") or []),
            }
            filtered = _pack_in_range(pack, lo=lo, hi=hi)
            if filtered:
                chosen, items = pack, filtered
        except ValueError:
            pack = None

    if not items or chosen is None:
        raise ValueError(
            f"指数日线获取失败({display})：同花顺/东财/缓存/腾讯均未覆盖 {lo}~{hi}"
        )

    if not chosen.get("name"):
        chosen["name"] = name
    if chosen.get("items") and not str(chosen.get("source") or "").startswith("cache:"):
        _save_index_disk(secid or display, chosen)

    return {
        "code": str(chosen.get("code") or display),
        "name": str(chosen.get("name") or name),
        "source": str(chosen.get("source") or "tonghuashun"),
        "adjust": "none",
        "beg": lo,
        "end": hi,
        "items": items,
    }


def factors_of(bars: list[dict[str, Any]]) -> dict[str, dict[str, float | None]]:
    """每日相对前收的 open/high/low/close 涨跌幅。

    - open → 开盘涨跌幅
    - high → 最大涨幅
    - low  → 最大跌幅
    - close → 收盘涨跌幅
    """
    out: dict[str, dict[str, float | None]] = {}
    for i, bar in enumerate(bars):
        date = _norm_date(str(bar.get("time") or ""))
        if not date:
            continue
        if i == 0:
            continue
        prev = bars[i - 1].get("close")
        if prev is None or float(prev) == 0:
            continue
        prev_f = float(prev)
        row: dict[str, float | None] = {}
        for key in FACTORS:
            val = bar.get(key)
            row[key] = (float(val) / prev_f - 1.0) if val is not None else None
        out[date] = row
    return out


def slice_factors(
    fac: dict[str, dict[str, float | None]],
    *,
    beg: str,
    end: str = "",
) -> dict[str, dict[str, float | None]]:
    lo = _iso(beg)
    hi = _iso(end) if end else "9999-12-31"
    return {d: fac[d] for d in sorted(fac) if lo <= d <= hi}
