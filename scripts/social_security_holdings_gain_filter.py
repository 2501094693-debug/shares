"""从「社保养老增持」分组筛出「期间最大涨幅」不超过阈值的股票，写入新分组。

流程：

1. 读取「我的」分组（默认 ``社保养老增持``）里的全部股票；
2. 逐只取**最新股东报告期**（``fetch_top_holders`` 返回的最新 ``report_date``）；
3. 取该报告期当日（非交易日取最近的前一交易日）的收盘价作为基准；
4. 取基准日之后到现在的全部日线，找出期间最高价（默认用最高价 ``high``，
   可切到收盘价 ``close``），并把当前实时价也纳入比较；
5. 期间最大涨幅 ``期间最高价 / 基准收盘价 - 1 <= --max-gain``（默认 10%）的
   股票写入目标分组（默认 ``社保养老增持_期间涨幅不超10%``），并逐条打印
   每只股票的处理结果；
6. 日志会额外对比**上一报告期**，逐条列出哪些「社保/养老」股东加仓、加了多少
   （新进十大股东也会标注）。

用法（项目根目录）::

    .venv\\Scripts\\python.exe scripts/social_security_holdings_gain_filter.py
    .venv\\Scripts\\python.exe scripts/social_security_holdings_gain_filter.py --max-gain 10
    .venv\\Scripts\\python.exe scripts/social_security_holdings_gain_filter.py --price-field close
    .venv\\Scripts\\python.exe scripts/social_security_holdings_gain_filter.py --dry-run
    .venv\\Scripts\\python.exe scripts/social_security_holdings_gain_filter.py \\
        --source-group 社保养老增持 --target-group 社保养老增持_期间涨幅不超10% \\
        --workers 8 --no-replace

说明：
- ``--price-field high``（默认）按期间最高价判断，能捕捉盘中冲高；
  ``--price-field close`` 只看每日收盘价。
- ``--adjust`` 默认 ``none``（不复权），与实时现价同一口径；改成 ``qfq`` 会
  使用前复权价格，遇到除权除息时口径会与现价不一致。
- 目标分组默认写入前清空（``--no-replace`` 可改为只追加）。
- ``--dry-run`` 只打印，不写分组。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

_SCRIPT = Path(__file__).resolve()
_ROOT = _SCRIPT.parents[1]
_BACKEND = _ROOT / "backend"
for path in (_BACKEND, _ROOT):
    text = str(path)
    if text not in sys.path:
        sys.path.insert(0, text)

from company.line.fetcher import fetch_kline  # noqa: E402
from company.statistics.holdings.holders import fetch_top_holders  # noqa: E402
from company.statistics.quote.live.fetcher import fetch_live_quote  # noqa: E402
from company.statistics.quote.live.sources import fetch_realtime_quotes  # noqa: E402
from core.codes import normalize_code, safe_str  # noqa: E402
from core.fmt import fmt_pct, fmt_price, fmt_shares, to_float  # noqa: E402
from mine.service import service as mine_service  # noqa: E402

_print_lock = threading.Lock()

DEFAULT_SOURCE_GROUP = "社保养老增持"
DEFAULT_TARGET_GROUP = "社保养老增持_期间涨幅不超10%"
DEFAULT_WORKERS = 8
DEFAULT_MAX_GAIN = 10.0
DEFAULT_ADJUST = "none"
DEFAULT_PRICE_FIELD = "high"
DEFAULT_SCOPE = "holders"
DEFAULT_KEYWORDS = ("社保", "养老")
MAX_STOCKS_PER_GROUP = 1000  # 与 mine.service 上限一致

_SKIP_LABELS = {
    "no_holder": "无股东数据",
    "no_report": "无最新报告期",
    "no_close": "报告期收盘价缺失",
    "no_price": "期间价格缺失",
    "gain_over": "期间最大涨幅超阈值",
    "error": "处理异常",
}


def _configure_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except Exception:  # noqa: BLE001
                pass


def _log(message: str) -> None:
    with _print_lock:
        print(message, flush=True)


def _chunks(items: list[str], size: int) -> list[list[str]]:
    return [items[i : i + size] for i in range(0, len(items), size)]


def _shift_day(day: str, days: int) -> str:
    try:
        base = datetime.strptime(day[:10], "%Y-%m-%d")
    except ValueError:
        return day
    return (base + timedelta(days=days)).strftime("%Y-%m-%d")


def _load_group_stocks(group_name: str) -> tuple[dict[str, Any], list[dict[str, str]]]:
    """按名称找到「我的」分组，返回 (分组信息, 股票列表)。"""
    listed = mine_service.list_groups().get("groups") or []
    target = None
    for group in listed:
        if safe_str(group.get("name")) == group_name:
            target = group
            break
    if target is None:
        names = "、".join(safe_str(g.get("name")) for g in listed) or "（无）"
        raise KeyError(f"分组不存在：{group_name}；现有分组：{names}")

    detail = mine_service.get_group(safe_str(target.get("id")))
    stocks: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in detail.get("stocks") or []:
        if not isinstance(item, dict):
            continue
        code = normalize_code(safe_str(item.get("code")))
        if not code or code in seen:
            continue
        seen.add(code)
        stocks.append({"code": code, "name": safe_str(item.get("name"))})
    return detail, stocks


def _fetch_prices(codes: list[str], *, workers: int) -> dict[str, dict[str, Any]]:
    """批量拉实时价；批量接口缺失的再用单票接口兜底。"""
    out: dict[str, dict[str, Any]] = {}
    for chunk in _chunks(codes, 60):
        try:
            rows = fetch_realtime_quotes(chunk)
        except Exception as exc:  # noqa: BLE001
            _log(f"  ! 批量行情失败（{len(chunk)} 只）：{exc}")
            rows = {}
        if isinstance(rows, dict):
            out.update(rows)

    missing = [
        code
        for code in codes
        if to_float((out.get(code) or {}).get("price")) is None
    ]
    if not missing:
        return out

    def one(code: str) -> tuple[str, dict[str, Any]]:
        try:
            quote = fetch_live_quote(code, force=True)
        except Exception:  # noqa: BLE001
            quote = {}
        return code, quote if isinstance(quote, dict) else {}

    with ThreadPoolExecutor(max_workers=max(1, min(workers, len(missing)))) as pool:
        for code, quote in pool.map(one, missing):
            if to_float(quote.get("price")) is not None:
                out[code] = quote
    return out


def _parse_keywords(raw: str) -> tuple[str, ...]:
    parts = [p.strip() for p in re.split(r"[,，\s;；|]+", safe_str(raw)) if p.strip()]
    return tuple(parts) or DEFAULT_KEYWORDS


def _match_keyword(name: str, keywords: tuple[str, ...]) -> bool:
    text = safe_str(name)
    return bool(text) and any(k in text for k in keywords)


def _shares_map(items: list[dict[str, Any]]) -> dict[str, float]:
    """股东名称 → 持股数；同名保留较大值（个别源会拆多行）。"""
    out: dict[str, float] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        name = safe_str(item.get("name"))
        shares = to_float(item.get("shares"))
        if not name or shares is None:
            continue
        if name in out and out[name] >= shares:
            continue
        out[name] = shares
    return out


def _holder_increases(
    cur_items: list[dict[str, Any]],
    prev_items: list[dict[str, Any]],
    keywords: tuple[str, ...],
) -> list[dict[str, Any]]:
    """对比上一报告期，找出「社保/养老」股东中持股数量增加的那些。"""
    prev_map = _shares_map(prev_items)
    out: list[dict[str, Any]] = []
    for item in cur_items:
        if not isinstance(item, dict):
            continue
        holder = safe_str(item.get("name"))
        if not _match_keyword(holder, keywords):
            continue
        cur_sh = to_float(item.get("shares"))
        if cur_sh is None:
            continue
        prev_sh = prev_map.get(holder, 0.0)
        if cur_sh > prev_sh:
            out.append(
                {
                    "holder": holder,
                    "cur_shares": cur_sh,
                    "prev_shares": prev_sh,
                    "delta": cur_sh - prev_sh,
                    "is_new": holder not in prev_map,
                    "ratio_fmt": safe_str(item.get("ratio_fmt")),
                }
            )
    out.sort(key=lambda h: -float(h.get("delta") or 0.0))
    return out


def _period_stats(
    code: str,
    target_day: str,
    *,
    adjust: str,
    price_field: str,
) -> dict[str, Any] | None:
    """基准收盘价 + 基准日之后到现在的期间最高价。

    ``price_field`` 取 ``high``（最高价，默认）或 ``close``（收盘价）。
    """
    target = target_day[:10]
    try:
        datetime.strptime(target, "%Y-%m-%d")
    except ValueError:
        return None

    beg = _shift_day(target, -40).replace("-", "")
    end = datetime.now().strftime("%Y%m%d")
    pack = fetch_kline(code, period="day", adjust=adjust, beg=beg, end=end, limit=800)
    bars = [b for b in (pack.get("items") or []) if isinstance(b, dict)]
    bars.sort(key=lambda b: str(b.get("time") or ""))

    base: dict[str, Any] | None = None
    for bar in bars:
        day = str(bar.get("time") or "")[:10]
        if not day:
            continue
        if day <= target:
            base = bar
        else:
            break
    if base is None:
        return None

    base_day = str(base.get("time") or "")[:10]
    base_close = to_float(base.get("close"))

    peak_price: float | None = None
    peak_day = ""
    for bar in bars:
        day = str(bar.get("time") or "")[:10]
        if not day or day <= base_day:
            continue
        value = to_float(bar.get(price_field))
        if value is None:
            value = to_float(bar.get("close"))
        if value is None:
            continue
        if peak_price is None or value > peak_price:
            peak_price = value
            peak_day = day

    return {
        "base_close": base_close,
        "base_day": base_day,
        "peak_price": peak_price,
        "peak_day": peak_day,
    }


def _analyze(
    stock: dict[str, str],
    *,
    prices: dict[str, dict[str, Any]],
    max_gain: float,
    adjust: str,
    price_field: str,
    scope: str,
    keywords: tuple[str, ...],
    force: bool,
) -> dict[str, Any]:
    """单只股票：最新报告期收盘价 → 期间最高价 的涨幅判定。"""
    code = stock["code"]
    row: dict[str, Any] = {"code": code, "name": stock.get("name") or ""}

    try:
        holders = fetch_top_holders(code, scope=scope, force=force)
    except Exception as exc:  # noqa: BLE001
        return {**row, "skipped": "no_holder", "detail": str(exc)[:120]}

    row["name"] = safe_str(holders.get("name")) or row["name"]
    report_date = safe_str(holders.get("report_date"))
    if not report_date:
        return {**row, "skipped": "no_report"}

    cur_items = [it for it in (holders.get("items") or []) if isinstance(it, dict)]
    dates = [safe_str(d) for d in (holders.get("report_dates") or []) if safe_str(d)]
    prev_date = dates[1] if len(dates) > 1 else ""

    holder_increases: list[dict[str, Any]] = []
    if prev_date:
        try:
            prev = fetch_top_holders(
                code,
                report_date=prev_date,
                scope=scope,
                force=force,
            )
            holder_increases = _holder_increases(
                cur_items,
                [it for it in (prev.get("items") or []) if isinstance(it, dict)],
                keywords,
            )
        except Exception:  # noqa: BLE001
            holder_increases = []

    base_info: dict[str, Any] = {
        "report_date": report_date,
        "prev_report_date": prev_date,
        "holder_increases": holder_increases,
        "holder_count": sum(
            1 for it in cur_items if _match_keyword(it.get("name"), keywords)
        ),
    }

    try:
        stats = _period_stats(
            code,
            report_date,
            adjust=adjust,
            price_field=price_field,
        )
    except Exception as exc:  # noqa: BLE001
        return {**row, **base_info, "skipped": "no_close", "detail": str(exc)[:120]}
    if stats is None:
        return {**row, **base_info, "skipped": "no_close"}

    close = stats.get("base_close")
    close_day = safe_str(stats.get("base_day"))
    peak_price = stats.get("peak_price")
    peak_day = safe_str(stats.get("peak_day"))

    quote = prices.get(code) or {}
    price = to_float(quote.get("price"))
    if price is not None and price > 0 and (peak_price is None or price > peak_price):
        peak_price = price
        peak_day = datetime.now().strftime("%Y-%m-%d")

    info: dict[str, Any] = {
        **base_info,
        "close_date": close_day,
        "close": close,
        "price": price,
        "peak_price": peak_price,
        "peak_day": peak_day,
    }
    if close is None or close <= 0:
        return {**row, **info, "skipped": "no_close"}
    if peak_price is None or peak_price <= 0:
        return {**row, **info, "skipped": "no_price"}

    max_gain_pct = (peak_price / close - 1.0) * 100.0
    info["max_gain_pct"] = max_gain_pct
    if price is not None and price > 0:
        info["current_gain_pct"] = (price / close - 1.0) * 100.0
    if max_gain_pct > max_gain + 1e-9:
        return {**row, **info, "skipped": "gain_over"}
    return {**row, **info, "matched": True}


def _holder_increase_text(row: dict[str, Any]) -> str:
    """把社保/养老加仓明细拼成一行文本。"""
    increases = [h for h in (row.get("holder_increases") or []) if isinstance(h, dict)]
    if not increases:
        return "无"
    parts: list[str] = []
    for item in increases:
        holder = safe_str(item.get("holder"))
        if item.get("is_new"):
            parts.append(f"{holder} {fmt_shares(item.get('cur_shares'))}(新进)")
        else:
            parts.append(
                f"{holder} {fmt_shares(item.get('prev_shares'))}→"
                f"{fmt_shares(item.get('cur_shares'))}"
                f"(+{fmt_shares(item.get('delta'))})"
            )
    return "；".join(parts)


def _print_holder_detail(row: dict[str, Any]) -> None:
    """逐条打印社保/养老股东的加仓明细（对比上一报告期）。"""
    prev_date = safe_str(row.get("prev_report_date"))
    report_date = safe_str(row.get("report_date")) or "-"
    indent = " " * 17 + "└ "
    text = _holder_increase_text(row)

    if text != "无":
        _log(f"{indent}社保/养老加仓（{prev_date or '-'}→{report_date}）：{text}")
    elif prev_date:
        _log(f"{indent}社保/养老加仓（{prev_date}→{report_date}）：无")
    else:
        _log(f"{indent}社保/养老加仓：无上一报告期数据")


def _print_row(
    row: dict[str, Any],
    *,
    index: int,
    total: int,
    max_gain: float,
) -> None:
    code = safe_str(row.get("code"))
    name = (safe_str(row.get("name")) or "")[:8]
    prefix = f"  [{index:>4}/{total}]"

    report_date = safe_str(row.get("report_date")) or "-"
    close = row.get("close")
    close_day = safe_str(row.get("close_date")) or "-"
    peak = row.get("peak_price")
    peak_day = safe_str(row.get("peak_day")) or "-"
    max_gain_pct = row.get("max_gain_pct")
    price = row.get("price")
    current_gain = row.get("current_gain_pct")

    period_text = (
        f"报告期 {report_date} · 基准收盘 {fmt_price(close) or '-'}@{close_day} · "
        f"期间最高 {fmt_price(peak) or '-'}@{peak_day} · "
        f"最大涨幅 {fmt_pct(max_gain_pct) or '-'}"
    )
    price_text = f"现价 {fmt_price(price) or '-'}"
    if current_gain is not None:
        price_text += f"（{fmt_pct(current_gain)}）"

    if row.get("skipped"):
        reason = _SKIP_LABELS.get(safe_str(row.get("skipped")), safe_str(row.get("skipped")))
        if safe_str(row.get("skipped")) == "gain_over":
            reason = f"{reason} >{max_gain:g}%"
        detail = safe_str(row.get("detail"))
        _log(
            f"{prefix}    {code} {name:<8} · {period_text} · {price_text} "
            f"跳过({reason}{': ' + detail if detail else ''})"
        )
        _print_holder_detail(row)
        return

    _log(
        f"{prefix} ★  {code} {name:<8} · {period_text} · {price_text} "
        f"命中(≤{max_gain:g}%)"
    )
    _print_holder_detail(row)


def _scan(
    stocks: list[dict[str, str]],
    *,
    prices: dict[str, dict[str, Any]],
    max_gain: float,
    adjust: str,
    price_field: str,
    scope: str,
    keywords: tuple[str, ...],
    force: bool,
    workers: int,
) -> list[dict[str, Any]]:
    total = len(stocks)
    hits: list[dict[str, Any]] = []
    skipped = 0
    t0 = time.time()

    def one(stock: dict[str, str]) -> dict[str, Any]:
        try:
            return _analyze(
                stock,
                prices=prices,
                max_gain=max_gain,
                adjust=adjust,
                price_field=price_field,
                scope=scope,
                keywords=keywords,
                force=force,
            )
        except Exception as exc:  # noqa: BLE001
            return {
                "code": stock["code"],
                "name": stock.get("name") or "",
                "skipped": "error",
                "detail": str(exc)[:120],
            }

    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        for index, row in enumerate(pool.map(one, stocks), start=1):
            _print_row(row, index=index, total=total, max_gain=max_gain)
            if row.get("matched"):
                hits.append(row)
            else:
                skipped += 1
            if index % 20 == 0 or index == total:
                _log(
                    f"  -- 进度 {index}/{total} · 命中 {len(hits)} · 跳过 {skipped} "
                    f"· {time.time() - t0:.0f}s --"
                )
    return hits


def _ensure_group(name: str) -> dict[str, Any]:
    listed = mine_service.list_groups().get("groups") or []
    for group in listed:
        if safe_str(group.get("name")) == name:
            return mine_service.get_group(safe_str(group.get("id")))
    return mine_service.create_group(name)


def _clear_group(group_id: str) -> int:
    group = mine_service.get_group(group_id)
    codes = [
        normalize_code(safe_str(s.get("code")))
        for s in (group.get("stocks") or [])
        if isinstance(s, dict)
    ]
    codes = [c for c in codes if c]
    if not codes:
        return 0
    result = mine_service.remove_stocks(group_id, codes)
    return len(result.get("removed") or [])


def _add_to_group(group_id: str, hits: list[dict[str, Any]]) -> dict[str, Any]:
    if len(hits) > MAX_STOCKS_PER_GROUP:
        _log(
            f"  警告：命中 {len(hits)} 只超过分组上限 {MAX_STOCKS_PER_GROUP}，"
            f"截断保留前 {MAX_STOCKS_PER_GROUP} 只"
        )
        hits = hits[:MAX_STOCKS_PER_GROUP]
    codes = [safe_str(row.get("code")) for row in hits if safe_str(row.get("code"))]
    names = {
        safe_str(row.get("code")): safe_str(row.get("name"))
        for row in hits
        if safe_str(row.get("code"))
    }
    if not codes:
        return {"added": [], "skipped": [], "group": mine_service.get_group(group_id)}
    return mine_service.add_stocks(group_id, codes, names=names)


def _write_group(
    hits: list[dict[str, Any]],
    *,
    group_name: str,
    replace: bool,
) -> dict[str, Any] | None:
    if not hits:
        _log(f"分组「{group_name}」无命中，跳过写入")
        return None
    group = _ensure_group(group_name)
    gid = safe_str(group.get("id"))
    if replace:
        removed = _clear_group(gid)
        if removed:
            _log(f"分组「{group_name}」已清空 {removed} 只")
    result = _add_to_group(gid, hits)
    final = result.get("group") or group
    _log(
        f"分组「{final.get('name')}」({final.get('id')}) "
        f"现有 {final.get('count')} 只 · 新加 {len(result.get('added') or [])} "
        f"· 已存在跳过 {len(result.get('skipped') or [])}"
    )
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="社保养老增持分组 → 报告期收盘价之后的期间最大涨幅不超过阈值的股票 → 写入新分组",
    )
    parser.add_argument(
        "--source-group",
        default=DEFAULT_SOURCE_GROUP,
        help=f"来源分组名（默认 {DEFAULT_SOURCE_GROUP}）",
    )
    parser.add_argument(
        "--target-group",
        default=DEFAULT_TARGET_GROUP,
        help=f"写入的新分组名（默认 {DEFAULT_TARGET_GROUP}）",
    )
    parser.add_argument(
        "--max-gain",
        type=float,
        default=DEFAULT_MAX_GAIN,
        help=f"期间最大涨幅上限（百分数，默认 {DEFAULT_MAX_GAIN:g}）",
    )
    parser.add_argument(
        "--price-field",
        default=DEFAULT_PRICE_FIELD,
        choices=("high", "close"),
        help="期间最高价的取法：high 最高价（默认，含盘中冲高） | close 收盘价",
    )
    parser.add_argument(
        "--adjust",
        default=DEFAULT_ADJUST,
        choices=("none", "qfq"),
        help="价格复权口径：none 不复权（默认，与现价一致） | qfq 前复权",
    )
    parser.add_argument(
        "--scope",
        default=DEFAULT_SCOPE,
        choices=("holders", "free"),
        help="股东口径：holders 十大股东（默认） | free 十大流通股东",
    )
    parser.add_argument(
        "--keywords",
        default=",".join(DEFAULT_KEYWORDS),
        help=f"识别社保/养老股东的关键词，逗号分隔（默认 {'/'.join(DEFAULT_KEYWORDS)}）",
    )
    parser.add_argument("--workers", type=int, default=DEFAULT_WORKERS, help="并发数")
    parser.add_argument("--limit", type=int, default=0, help="最多处理多少只（0=不限制，调试用）")
    parser.add_argument("--force", action="store_true", help="强制刷新十大股东缓存（更慢）")
    parser.add_argument(
        "--replace",
        dest="replace",
        action="store_true",
        default=True,
        help="写入前清空目标分组（默认开启）",
    )
    parser.add_argument(
        "--no-replace",
        dest="replace",
        action="store_false",
        help="不清空，只追加未在组内的股票",
    )
    parser.add_argument("--dry-run", action="store_true", help="只打印结果，不写入分组")
    parser.add_argument("--json", action="store_true", help="输出 JSON")
    parser.add_argument("--out", default="", help="写入结果 JSON 文件路径；空=不写文件")
    return parser


def main(argv: list[str] | None = None) -> int:
    _configure_stdio()
    args = build_parser().parse_args(argv)
    started = time.time()

    source_group = safe_str(args.source_group) or DEFAULT_SOURCE_GROUP
    target_group = safe_str(args.target_group) or DEFAULT_TARGET_GROUP
    max_gain = float(args.max_gain)
    adjust = safe_str(args.adjust) or DEFAULT_ADJUST
    price_field = safe_str(args.price_field) or DEFAULT_PRICE_FIELD
    scope = safe_str(args.scope) or DEFAULT_SCOPE
    keywords = _parse_keywords(args.keywords)

    if args.replace and not args.dry_run and source_group == target_group:
        _log("ERROR: 来源分组与目标分组同名，清空会删掉来源股票；请换 --target-group")
        return 1

    try:
        source, stocks = _load_group_stocks(source_group)
    except Exception as exc:  # noqa: BLE001
        _log(f"ERROR: 读取来源分组失败：{exc}")
        return 1

    _log(
        f"来源分组「{safe_str(source.get('name'))}」({safe_str(source.get('id'))}) "
        f"共 {len(stocks)} 只"
    )
    if args.limit and args.limit > 0:
        stocks = stocks[: int(args.limit)]
        _log(f"截断为前 {len(stocks)} 只")
    if not stocks:
        _log("来源分组没有股票")
        return 1

    _log(
        f"开始处理 · 期间最大涨幅阈值 ≤{max_gain:g}% · 取价={price_field} · "
        f"复权={adjust} · 股东口径={scope} · 关键词={'/'.join(keywords)} · "
        f"workers={args.workers} · force={bool(args.force)}"
        + (" · dry-run" if args.dry_run else "")
        + ("" if args.dry_run else f" · replace={bool(args.replace)}")
    )

    _log(f"拉取 {len(stocks)} 只实时现价…")
    prices = _fetch_prices([s["code"] for s in stocks], workers=int(args.workers))
    _log(f"实时现价到手 {len(prices)} 只")

    hits = _scan(
        stocks,
        prices=prices,
        max_gain=max_gain,
        adjust=adjust,
        price_field=price_field,
        scope=scope,
        keywords=keywords,
        force=bool(args.force),
        workers=int(args.workers),
    )
    hits.sort(
        key=lambda r: (
            float(r.get("max_gain_pct") or 0.0),
            safe_str(r.get("code")),
        )
    )

    elapsed = time.time() - started
    _log("")
    _log(
        f"=== 命中 {len(hits)} 只（报告期收盘 → 期间最高 最大涨幅 "
        f"≤{max_gain:g}%，取价={price_field}）==="
    )
    for index, row in enumerate(hits, start=1):
        current_gain = row.get("current_gain_pct")
        current_gain_s = fmt_pct(current_gain) if current_gain is not None else "-"
        _log(
            f"{index:>4}  {safe_str(row.get('code'))} "
            f"{(safe_str(row.get('name')) or '')[:8]:<8}  "
            f"报告期 {row.get('report_date')}  基准收盘 "
            f"{fmt_price(row.get('close'))}@{row.get('close_date')}  "
            f"期间最高 {fmt_price(row.get('peak_price'))}@{row.get('peak_day')}  "
            f"最大涨幅 {fmt_pct(row.get('max_gain_pct'))}  "
            f"现价 {fmt_price(row.get('price'))}（{current_gain_s}）"
        )
        _log(
            f"      └ 社保/养老加仓"
            f"（{safe_str(row.get('prev_report_date')) or '-'}→{row.get('report_date')}）："
            f"{_holder_increase_text(row)}"
        )
    _log(f"\n处理完成（耗时 {elapsed:.1f}s）：{len(stocks)} 只中命中 {len(hits)} 只")

    mine_meta: dict[str, Any] = {
        "source_group": source_group,
        "target_group": target_group,
        "replace": bool(args.replace),
        "dry_run": bool(args.dry_run),
        "written": False,
    }

    if args.dry_run:
        _log(f"[dry-run] 跳过写入分组「{target_group}」（本会写入 {len(hits)} 只）")
    else:
        try:
            result = _write_group(hits, group_name=target_group, replace=bool(args.replace))
            if result is not None:
                final = result.get("group") or {}
                mine_meta["written"] = True
                mine_meta["group_id"] = safe_str(final.get("id"))
                mine_meta["count"] = final.get("count")
                mine_meta["added"] = len(result.get("added") or [])
                mine_meta["skipped"] = len(result.get("skipped") or [])
        except Exception as exc:  # noqa: BLE001
            _log(f"ERROR: 写入分组失败: {exc}")
            return 1

    payload = {
        "meta": {
            "source_group": source_group,
            "target_group": target_group,
            "max_gain_pct": max_gain,
            "price_field": price_field,
            "adjust": adjust,
            "scope": scope,
            "keywords": list(keywords),
            "candidates": len(stocks),
            "matched": len(hits),
            "elapsed_sec": round(elapsed, 1),
            "rule": (
                "期间最高价（high/close，含现价） / 最新股东报告期当日收盘价 - 1 "
                "<= max_gain_pct"
            ),
            "mine": mine_meta,
        },
        "items": hits,
    }

    if args.out.strip():
        out_path = Path(args.out.strip())
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        _log(f"已写入 {out_path}")

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
