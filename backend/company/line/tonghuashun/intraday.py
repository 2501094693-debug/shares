"""同花顺分时成交（``single_trend`` 分钟级）。

按交易日拉整段分时（约 240 点/天，含价格 / 均价基准 / 累计量），支持单日与最近
``n`` 个交易日（最多 120 日）。与同花顺 App「分时 / 五日」图同源，免登录，历史可回溯多年。
已收盘交易日的分时会落盘到 ``cache/trend``，再次打开直接复用；当日盘中始终回源。

这里只保留「分时成交」能力；逐笔明细（``single_trace`` 尾盘 500 笔那套）已删除。

    python -m company.line.tonghuashun.intraday 600519
    python -m company.line.tonghuashun.intraday 000338 --days 5
    python -m company.line.tonghuashun.intraday 000338 --day 2026-11-05
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

if __name__ == "__main__" or __package__:
    _BACKEND = Path(__file__).resolve().parents[3]
    if str(_BACKEND) not in sys.path:
        sys.path.insert(0, str(_BACKEND))

from core.cache import TtlCache
from core.codes import normalize_code
from core.fmt import to_float
from core.paths import TREND_CACHE_DIR
from company.line.session import is_cn_session_open, parse_session_day, session_day

logger = logging.getLogger(__name__)

_TZ = timezone(timedelta(hours=8))
_DEFAULT_DAYS = 5
# 多日窗口上限：约半年交易日，够画季度级别分时
_MAX_DAYS = 120
# 按日回源是独立 HTTP 请求，并发拉更快；同花顺偶发 RST 由 retry_conn_reset 兜底
_TREND_WORKERS = 8
_TREND_DISK_VERSION = 1
_TREND_EXECUTOR = ThreadPoolExecutor(
    max_workers=_TREND_WORKERS, thread_name_prefix="ths-trend"
)
# 对外只保留画图要用的列，120 日窗口下响应体能小一半以上
_TREND_KEYS = ("time", "price", "avg_price", "volume", "base_price", "seq")
# 交易日列表按代码缓存：扩窗时只需补分时，不必重复拉日 K
_DAYS_TTL = 10 * 60.0
_days_cache = TtlCache(_DAYS_TTL)


def _recent_days(code: str) -> list[str]:
    """最近交易日（升序，最多 ``_MAX_DAYS`` 日）。"""
    # key 带当前交易日：开盘后旧列表自动失效，不会漏掉当天
    key = f"{code}:{session_day().isoformat()}"
    hit = _days_cache.get(key)
    if hit:
        return hit
    from company.line.fetcher import fetch_kline

    days: list[str] = []
    try:
        pack = fetch_kline(code, period="day", limit=_MAX_DAYS + 5)
        for row in reversed(pack.get("items") or []):
            day = parse_session_day(row.get("time"))
            if day is None:
                continue
            iso = day.isoformat()
            if days and days[-1] == iso:
                continue
            days.append(iso)
            if len(days) >= _MAX_DAYS:
                break
        days.reverse()
    except Exception as exc:  # noqa: BLE001
        logger.info("intraday trade days fetch failed %s: %s", code, exc)
    if not days:
        # 日 K 空时退回日历回推（仅工作日近似）
        cursor = session_day()
        while len(days) < _MAX_DAYS:
            if cursor.weekday() < 5:
                days.append(cursor.isoformat())
            cursor -= timedelta(days=1)
        days.reverse()
    _days_cache.put(key, days)
    return days


def _trade_days(code: str, n: int) -> list[str]:
    """最近 ``n`` 个交易日（升序，``YYYY-MM-DD``）。"""
    want = max(1, min(int(n), _MAX_DAYS))
    return _recent_days(code)[-want:]


def _day_int(iso: str) -> int:
    return int(iso.replace("-", ""))


def _fetch_day_trend(code: str, day: str) -> list[dict[str, Any]]:
    """``single_trend`` 分钟点（与 App 分时 / 五日图同源）。"""
    from company.detail.ths_mobile import fetch_trend

    raw = fetch_trend(code, trade_date=_day_int(day), trade_class="intraday")
    if not isinstance(raw, list) or not raw:
        return []
    quote = raw[0] if isinstance(raw[0], dict) else {}
    fields = [str(x) for x in (quote.get("data_fields") or [])]
    index = {name: pos for pos, name in enumerate(fields)}
    base_price = to_float(quote.get("base_price"))
    out: list[dict[str, Any]] = []
    prev_cum = None
    for seq, row in enumerate(quote.get("value") or []):
        if not isinstance(row, (list, tuple)):
            continue

        def cell(name: str) -> Any:
            pos = index.get(name)
            if pos is None or pos >= len(row):
                return None
            return row[pos]

        stamp_ms = to_float(cell("1"))
        price = to_float(cell("10"))
        if stamp_ms is None or price is None:
            continue
        cum_vol = to_float(cell("13"))
        cum_amt = to_float(cell("19"))
        # 累计量差分 → 本分钟量；首根没有 prev，整段累计即开盘量
        vol_shares = None
        if cum_vol is not None:
            vol_shares = cum_vol if prev_cum is None else cum_vol - prev_cum
            prev_cum = cum_vol
        stamp = datetime.fromtimestamp(stamp_ms / 1000.0, _TZ)
        iso = stamp.strftime("%Y-%m-%d %H:%M:%S")
        if iso[:10] != day:
            continue
        lots = (
            round(vol_shares / 100.0, 2)
            if vol_shares is not None
            else None
        )
        # 分时均价 = 累计额 / 累计量（与 App 五日图橙色均线一致）
        avg_price = None
        if cum_amt is not None and cum_vol is not None and cum_vol > 0:
            avg_price = round(cum_amt / cum_vol, 4)
        out.append(
            {
                "time": iso,
                "stamp": iso[11:],
                "day": day,
                "code": code,
                "price": price,
                "avg_price": avg_price,
                "volume": lots,
                "volume_lots": lots,
                "amount": cum_amt,
                "cum_volume": cum_vol,
                "base_price": base_price,
                "seq": seq,
            }
        )
    return out


def _finalized_day(iso: str) -> bool:
    """已收盘交易日的分时不再变化，可长期落盘复用。"""
    today = session_day().isoformat()
    if iso < today:
        return True
    if iso > today:
        return False
    return not is_cn_session_open()


def _slim_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{key: row.get(key) for key in _TREND_KEYS} for row in rows]


def _trend_cache_path(code: str, iso: str) -> Path:
    TREND_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return TREND_CACHE_DIR / f"{code}_{iso}.json"


def _load_trend_disk(code: str, iso: str) -> list[dict[str, Any]] | None:
    path = _trend_cache_path(code, iso)
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if int(payload.get("version") or 0) != _TREND_DISK_VERSION:
        return None
    rows = payload.get("trends")
    if not isinstance(rows, list) or not rows:
        return None
    return rows


def _save_trend_disk(code: str, iso: str, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    path = _trend_cache_path(code, iso)
    text = json.dumps(
        {
            "version": _TREND_DISK_VERSION,
            "code": code,
            "day": iso,
            "trends": rows,
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )
    tmp = path.with_name(f"{path.name}.{threading.get_ident()}.tmp")
    try:
        tmp.write_text(text, encoding="utf-8")
        tmp.replace(path)
    except OSError as exc:
        logger.info("trend cache write skip %s %s: %s", code, iso, exc)
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass


def _fetch_day_cached(code: str, iso: str) -> tuple[list[dict[str, Any]], str]:
    """单日分时：已收盘日优先读盘，缺失再回源；返回 ``(slim rows, error)``。"""
    finalized = _finalized_day(iso)
    if finalized:
        cached = _load_trend_disk(code, iso)
        if cached:
            return cached, ""
    error = ""
    rows: list[dict[str, Any]] = []
    try:
        rows = _slim_rows(_fetch_day_trend(code, iso))
    except Exception as exc:  # noqa: BLE001
        error = str(exc)
        logger.info("intraday trend skip %s %s: %s", code, iso, exc)
    if rows:
        if finalized:
            _save_trend_disk(code, iso, rows)
        return rows, error
    # 回源失败时退回落盘数据，避免多日窗口里出现整日空洞
    cached = _load_trend_disk(code, iso)
    if cached:
        return cached, error
    return [], error


def fetch_day_trend(code: str, day: str | Any) -> dict[str, Any]:
    """单日分时成交（分钟级）。"""
    norm = normalize_code(code)
    if not norm:
        raise ValueError("无效股票代码")
    parsed = parse_session_day(day)
    if parsed is None:
        raise ValueError(f"无效交易日: {day}")
    iso = parsed.isoformat()
    trends: list[dict[str, Any]] = []
    error = ""
    try:
        trends = _fetch_day_trend(norm, iso)
    except Exception as exc:  # noqa: BLE001
        error = str(exc)
        logger.info("intraday trend skip %s %s: %s", norm, iso, exc)
    return {
        "code": norm,
        "day": iso,
        "source": "ths_mobile:trend" if trends else "",
        "count": len(trends),
        "first": trends[0]["time"] if trends else "",
        "last": trends[-1]["time"] if trends else "",
        "trends": trends,
        "error": error,
    }


def fetch_intraday(code: str, *, days: int = _DEFAULT_DAYS) -> dict[str, Any]:
    """最近 ``days`` 个交易日的分时成交（分钟级，最多 120 日）。"""
    norm = normalize_code(code)
    if not norm:
        raise ValueError("无效股票代码")

    day_list = _trade_days(norm, days)
    fetched: dict[str, tuple[list[dict[str, Any]], str]] = {}
    if day_list:
        futures = {
            _TREND_EXECUTOR.submit(_fetch_day_cached, norm, iso): iso
            for iso in day_list
        }
        for future in as_completed(futures):
            iso = futures[future]
            try:
                fetched[iso] = future.result()
            except Exception as exc:  # noqa: BLE001
                logger.info("intraday day failed %s %s: %s", norm, iso, exc)
                fetched[iso] = ([], str(exc))

    by_day: dict[str, dict[str, Any]] = {}
    all_trends: list[dict[str, Any]] = []
    for iso in day_list:
        trends, error = fetched.get(iso) or ([], "")
        # 分钟点只在顶层 trends 里返回，by_day 仅保留每日摘要，避免响应体翻倍
        by_day[iso] = {
            "day": iso,
            "source": "ths_mobile:trend" if trends else "",
            "count": len(trends),
            "first": trends[0]["time"] if trends else "",
            "last": trends[-1]["time"] if trends else "",
            "error": error,
        }
        all_trends.extend(trends)

    all_trends.sort(key=lambda r: (r["time"], int(r.get("seq") or 0)))
    return {
        "code": norm,
        "days": day_list,
        "source": "tonghuashun",
        "count": len(all_trends),
        "first": all_trends[0]["time"] if all_trends else "",
        "last": all_trends[-1]["time"] if all_trends else "",
        "trends": all_trends,
        "by_day": by_day,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="同花顺分时成交（分钟级）")
    parser.add_argument("code", help="股票代码，如 600519")
    parser.add_argument("--days", type=int, default=_DEFAULT_DAYS, help="交易日数，默认 5，最多 120")
    parser.add_argument("--day", default="", help="只拉单日，如 2026-11-05")
    parser.add_argument("--limit", type=int, default=5, help="预览每段首尾条数，0=全量")
    args = parser.parse_args()

    if args.day:
        pack = fetch_day_trend(args.code, args.day)
    else:
        pack = fetch_intraday(args.code, days=args.days)

    if args.limit == 0:
        print(json.dumps(pack, ensure_ascii=False, indent=2))
        return 0 if pack.get("count") else 1

    items = list(pack.get("trends") or [])
    n = max(0, args.limit)
    summary = {
        "code": pack.get("code"),
        "days": pack.get("days") or [pack.get("day")],
        "source": pack.get("source"),
        "count": pack.get("count"),
        "first": pack.get("first"),
        "last": pack.get("last"),
    }
    if "by_day" in pack:
        summary["by_day"] = {
            day: {
                "count": info.get("count"),
                "first": info.get("first"),
                "last": info.get("last"),
                "error": info.get("error") or None,
            }
            for day, info in (pack.get("by_day") or {}).items()
        }
    else:
        summary["day"] = pack.get("day")
        summary["error"] = pack.get("error") or None
    if n and items:
        summary["preview_head"] = items[:n]
        tail = items[-n:] if len(items) > n else []
        if tail and tail[0] != items[0]:
            summary["preview_tail"] = tail
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if items else 1


if __name__ == "__main__":
    raise SystemExit(main())
