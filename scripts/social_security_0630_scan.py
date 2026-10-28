"""6.30 前十大股东「社保加仓 + 股价回落」扫描，并统计 6.30 之后的最高价涨幅。

扫描范围：全 A 股（默认排除创业板 300/301 与 ST/*ST/退市）。

对每只股票：

1. 取 **2026-06-30** 的前十大股东（``scope=holders``）；
2. 找出 6.30 前十大股东里名称包含「社保」的股东；
3. 取 6.30 **之前最近一次**公布的前十大股东报告期，按股东名称对齐持股数量；
4. 若某个「社保」股东在 6.30 的持股数量比上一次**增加**（新进前十大也视为增加）；
5. 且 **6.30 收盘价 < 上一次报告期所在交易日的收盘价**（股价回落）；
6. 则该股命中，并统计 **6.30 之后到今天的最高价** 相对 6.30 收盘价的涨幅；
7. 命中股票写入「我的」分组（默认组名「社保0630加仓_股价回落」）。

价格口径默认不复权（``--adjust none``，与现价同一口径），可按需改成前复权。

用法（项目根目录）::

    .venv\\Scripts\\python.exe scripts/social_security_0630_scan.py
    .venv\\Scripts\\python.exe scripts/social_security_0630_scan.py --workers 8
    .venv\\Scripts\\python.exe scripts/social_security_0630_scan.py --codes 600519,000333 --dry-run
    .venv\\Scripts\\python.exe scripts/social_security_0630_scan.py --report-date 2026-06-30
    .venv\\Scripts\\python.exe scripts/social_security_0630_scan.py --group 社保0630 --no-replace
    .venv\\Scripts\\python.exe scripts/social_security_0630_scan.py --keywords 社保,养老 --max-scan 300

说明：

- 股票池优先读 ``backend/cache/stocks_index.json``；若该文件不存在，会自动改用
  东财全市场列表（``market.sw.em_stock_flow.fetch_stock_flows``）兜底。
- ``--scope free`` 可改为对比十大流通股东。
- 网络 / 接口异常、6.30 无十大股东、无社保股东、社保未加仓、6.30 收盘未回落、
  6.30 当日停牌无行情的股票都会打印跳过原因。
- 写入分组默认先清空目标分组；``--no-replace`` 改为只追加。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta
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
from company.statistics.quote.live.sources import fetch_realtime_quotes  # noqa: E402
from core.codes import normalize_code, safe_str  # noqa: E402
from core.fmt import fmt_pct, fmt_price, fmt_shares, to_float  # noqa: E402
from core.paths import STOCK_INDEX_CACHE  # noqa: E402
from mine.service import service as mine_service  # noqa: E402

_print_lock = threading.Lock()

DEFAULT_GROUP = "社保0630加仓_股价回落"
DEFAULT_WORKERS = 6
DEFAULT_KEYWORDS = ("社保",)
DEFAULT_SCOPE = "holders"
DEFAULT_ADJUST = "none"
DEFAULT_PRICE_FIELD = "high"
MAX_STOCKS_PER_GROUP = 1000  # 与 mine.service 上限一致

_SKIP_LABELS = {
    "st": "ST/退市",
    "no_0630": "6.30无十大股东数据",
    "no_holder": "6.30十大股东无社保",
    "no_prev": "无上一报告期",
    "no_prev_data": "上一报告期数据缺失",
    "no_increase": "社保股东未加仓",
    "no_price": "收盘价缺失",
    "target_missing": "6.30当日无行情",
    "price_up": "6.30收盘未低于上期",
    "no_peak": "6.30后无行情",
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


def _default_report_date() -> str:
    """最近一个已经过去的 6 月 30 日。"""
    today = date.today()
    candidate = date(today.year, 6, 30)
    if candidate > today:
        candidate = date(today.year - 1, 6, 30)
    return candidate.isoformat()


def _is_chinext(code: str) -> bool:
    return code.startswith(("300", "301"))


def _is_st(name: str) -> bool:
    text = safe_str(name).upper().replace(" ", "")
    return "ST" in text or "退" in text


def _is_a_share(code: str) -> bool:
    """只保留 A 股常见板块前缀，排除 B 股 200/900 等。"""
    return code.startswith(("60", "68", "00", "30", "8", "4", "92"))


def _parse_keywords(raw: str) -> tuple[str, ...]:
    parts = [p.strip() for p in re.split(r"[,，\s;；|]+", safe_str(raw)) if p.strip()]
    return tuple(parts) or DEFAULT_KEYWORDS


def _match_keyword(name: str, keywords: tuple[str, ...]) -> bool:
    text = safe_str(name)
    return bool(text) and any(k in text for k in keywords)


def _load_index_candidates() -> list[dict[str, str]]:
    payload = json.loads(STOCK_INDEX_CACHE.read_text(encoding="utf-8"))
    rows = payload.get("stocks") if isinstance(payload, dict) else payload
    if not isinstance(rows, list):
        raise ValueError("stocks_index.json 格式异常")

    out: list[dict[str, str]] = []
    seen: set[str] = set()
    skipped_cyb = 0
    skipped_st = 0
    for row in rows:
        if not isinstance(row, dict):
            continue
        code = normalize_code(safe_str(row.get("code")))
        name = safe_str(row.get("name"))
        if not code or code in seen or not _is_a_share(code):
            continue
        if _is_chinext(code):
            skipped_cyb += 1
            continue
        if _is_st(name):
            skipped_st += 1
            continue
        seen.add(code)
        out.append({"code": code, "name": name})

    out.sort(key=lambda item: item["code"])
    _log(f"股票索引：跳过创业板 {skipped_cyb} · ST {skipped_st} · 剩余 {len(out)}")
    return out


def _load_em_candidates() -> list[dict[str, str]]:
    from market.sw.em_stock_flow import fetch_stock_flows

    _log("未找到股票索引，改用东财全市场列表（可能需要几十秒）…")
    flows = fetch_stock_flows()
    out: list[dict[str, str]] = []
    seen: set[str] = set()
    skipped_cyb = 0
    skipped_st = 0
    for code_raw, row in (flows or {}).items():
        if not isinstance(row, dict):
            continue
        code = normalize_code(safe_str(row.get("code") or code_raw))
        name = safe_str(row.get("name"))
        if not code or code in seen or not _is_a_share(code):
            continue
        if _is_chinext(code):
            skipped_cyb += 1
            continue
        if _is_st(name):
            skipped_st += 1
            continue
        seen.add(code)
        out.append({"code": code, "name": name})
    out.sort(key=lambda item: item["code"])
    _log(f"东财全市场：跳过创业板 {skipped_cyb} · ST {skipped_st} · 剩余 {len(out)}")
    return out


def _load_universe() -> list[dict[str, str]]:
    if STOCK_INDEX_CACHE.is_file():
        return _load_index_candidates()
    return _load_em_candidates()


def _parse_codes(raw: str) -> list[dict[str, str]]:
    parts = re.split(r"[,，\s;；|]+", safe_str(raw))
    out: list[dict[str, str]] = []
    seen: set[str] = set()
    for part in parts:
        code = normalize_code(part)
        if not code or code in seen:
            continue
        if _is_chinext(code):
            _log(f"  跳过创业板 {code}")
            continue
        seen.add(code)
        out.append({"code": code, "name": ""})
    return out


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


def _holder_increases_from_status(
    cur_items: list[dict[str, Any]],
    keywords: tuple[str, ...],
) -> list[dict[str, Any]]:
    """直接用东财「持仓变动 / 股东状态」判断加仓，避免再拉上一报告期。

    东财前十大股东自带 ``change``（较上一报告期变动股数）与 ``status``
    （加仓 / 减仓 / 新进 / 不变）。能判断时优先用它，缺失时由调用方
    回退到「上一报告期股东名单逐名对比」。
    """
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

        status = safe_str(item.get("status"))
        change = to_float(item.get("change"))
        if status in {"减仓", "减持", "不变"}:
            continue

        if status == "新进":
            out.append(
                {
                    "holder": holder,
                    "cur_shares": cur_sh,
                    "prev_shares": 0.0,
                    "delta": cur_sh,
                    "is_new": True,
                    "ratio_fmt": safe_str(item.get("ratio_fmt")),
                }
            )
            continue

        if status in {"加仓", "增持"} or (not status and change is not None and change > 0):
            delta = change if change is not None and change > 0 else None
            out.append(
                {
                    "holder": holder,
                    "cur_shares": cur_sh,
                    "prev_shares": (cur_sh - delta) if delta is not None else None,
                    "delta": delta,
                    "is_new": False,
                    "ratio_fmt": safe_str(item.get("ratio_fmt")),
                }
            )

    out.sort(key=lambda h: -float(h.get("delta") or 0.0))
    return out


def _holder_increases(
    cur_items: list[dict[str, Any]],
    prev_items: list[dict[str, Any]],
    keywords: tuple[str, ...],
) -> list[dict[str, Any]]:
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
        if cur_sh <= prev_sh:
            continue
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


def _quarter_ends_before(target: str, count: int = 8) -> list[str]:
    """target 之前最近的若干季度末，用于 report_dates 缺失时兜底。"""
    try:
        year = int(target[:4])
    except ValueError:
        return []
    out: list[str] = []
    for y in range(year, year - 3, -1):
        for month, day in ((12, 31), (9, 30), (6, 30), (3, 31)):
            text = f"{y:04d}-{month:02d}-{day:02d}"
            if text < target:
                out.append(text)
    out = sorted(set(out), reverse=True)
    return out[:count]


def _price_profile(
    code: str,
    prev_date: str,
    target_date: str,
    *,
    adjust: str,
    price_field: str,
) -> dict[str, Any]:
    """一次拉取 [prev_date, today] 日线，得到上期收盘 / 6.30 收盘 / 6.30 后最高价。"""
    target = target_date[:10]
    prevd = prev_date[:10]
    try:
        beg = (datetime.strptime(prevd, "%Y-%m-%d") - timedelta(days=20)).strftime("%Y%m%d")
    except ValueError:
        beg = prevd.replace("-", "")
    end = datetime.now().strftime("%Y%m%d")

    pack = fetch_kline(
        code,
        period="day",
        adjust=adjust,
        beg=beg,
        end=end,
        limit=1200,
    )
    bars = [b for b in (pack.get("items") or []) if isinstance(b, dict)]
    bars.sort(key=lambda b: str(b.get("time") or ""))

    prev_bar: dict[str, Any] | None = None
    target_bar: dict[str, Any] | None = None
    for bar in bars:
        day = safe_str(bar.get("time"))[:10]
        if not day:
            continue
        if day <= prevd:
            prev_bar = bar
        if day <= target:
            target_bar = bar

    if prev_bar is None:
        return {"error": "prev_close"}
    if target_bar is None:
        return {"error": "target_close"}

    prev_close = to_float(prev_bar.get("close"))
    cur_close = to_float(target_bar.get("close"))
    if prev_close is None or cur_close is None:
        return {"error": "close_none"}

    target_bar_day = safe_str(target_bar.get("time"))[:10]
    peak_price: float | None = None
    peak_day = ""
    current: float | None = None
    current_day = ""
    for bar in bars:
        day = safe_str(bar.get("time"))[:10]
        if not day:
            continue
        if day > target:
            value = to_float(bar.get(price_field))
            if value is None:
                value = to_float(bar.get("close"))
            if value is not None and (peak_price is None or value > peak_price):
                peak_price = value
                peak_day = day
        close = to_float(bar.get("close"))
        if close is not None:
            current = close
            current_day = day

    return {
        "prev_close": prev_close,
        "prev_close_day": safe_str(prev_bar.get("time"))[:10],
        "cur_close": cur_close,
        "cur_close_day": target_bar_day,
        "target_missing": target_bar_day != target,
        "peak_price": peak_price,
        "peak_day": peak_day,
        "current": current,
        "current_day": current_day,
    }


def _analyze(
    code: str,
    name: str,
    *,
    target_date: str,
    scope: str,
    keywords: tuple[str, ...],
    adjust: str,
    price_field: str,
    force: bool,
) -> dict[str, Any]:
    row: dict[str, Any] = {"code": code, "name": name}

    try:
        cur = fetch_top_holders(code, report_date=target_date, scope=scope, force=force)
    except Exception as exc:  # noqa: BLE001
        return {**row, "skipped": "no_0630", "detail": str(exc)[:120]}

    label = safe_str(cur.get("name")) or name
    row["name"] = label
    if _is_st(label):
        return {**row, "skipped": "st"}

    cur_items = [it for it in (cur.get("items") or []) if isinstance(it, dict)]
    if not cur_items:
        return {**row, "skipped": "no_0630"}

    dates = sorted(
        {safe_str(d)[:10] for d in (cur.get("report_dates") or []) if safe_str(d)},
        reverse=True,
    )
    prior = [d for d in dates if d < target_date]

    prev_date = prior[0] if prior else ""
    prev_items: list[dict[str, Any]] = []

    if not prev_date:
        # report_dates 缺失时，用季度末兜底确认一个可用的上一报告期
        for candidate in _quarter_ends_before(target_date):
            try:
                prev_pack = fetch_top_holders(
                    code,
                    report_date=candidate,
                    scope=scope,
                    force=force,
                )
            except Exception:  # noqa: BLE001
                continue
            prev_items = [
                it for it in (prev_pack.get("items") or []) if isinstance(it, dict)
            ]
            if prev_items:
                prev_date = candidate
                break
        if not prev_date or not prev_items:
            return {**row, "report_date": target_date, "skipped": "no_prev"}

    cur_hits = [it for it in cur_items if _match_keyword(it.get("name"), keywords)]
    if not cur_hits:
        return {
            **row,
            "report_date": target_date,
            "prev_report_date": prev_date,
            "skipped": "no_holder",
        }

    # 优先用东财自带的「加仓 / 新进 / 减仓 / 不变」判断，省掉一次上一报告期请求
    increases = _holder_increases_from_status(cur_hits, keywords)
    if not increases:
        if not prev_items:
            try:
                prev_pack = fetch_top_holders(
                    code,
                    report_date=prev_date,
                    scope=scope,
                    force=force,
                )
                prev_items = [
                    it for it in (prev_pack.get("items") or []) if isinstance(it, dict)
                ]
            except Exception as exc:  # noqa: BLE001
                return {
                    **row,
                    "report_date": target_date,
                    "prev_report_date": prev_date,
                    "skipped": "no_prev_data",
                    "detail": str(exc)[:120],
                }
        increases = _holder_increases(cur_hits, prev_items, keywords)

    if not increases:
        return {
            **row,
            "report_date": target_date,
            "prev_report_date": prev_date,
            "holder_count": len(cur_hits),
            "skipped": "no_increase",
        }

    info: dict[str, Any] = {
        "report_date": target_date,
        "prev_report_date": prev_date,
        "holder_count": len(cur_hits),
        "increases": increases,
    }

    try:
        profile = _price_profile(
            code,
            prev_date,
            target_date,
            adjust=adjust,
            price_field=price_field,
        )
    except Exception as exc:  # noqa: BLE001
        return {**row, **info, "skipped": "no_price", "detail": str(exc)[:120]}

    if profile.get("error"):
        return {**row, **info, "skipped": "no_price", "detail": profile["error"]}
    if profile.get("target_missing"):
        return {
            **row,
            **info,
            "prev_close": profile.get("prev_close"),
            "prev_close_day": profile.get("prev_close_day"),
            "cur_close": profile.get("cur_close"),
            "cur_close_day": profile.get("cur_close_day"),
            "skipped": "target_missing",
        }

    prev_close = profile.get("prev_close")
    cur_close = profile.get("cur_close")
    info.update(
        {
            "prev_close": prev_close,
            "prev_close_day": safe_str(profile.get("prev_close_day")),
            "cur_close": cur_close,
            "cur_close_day": safe_str(profile.get("cur_close_day")),
        }
    )

    if prev_close is None or cur_close is None or cur_close <= 0:
        return {**row, **info, "skipped": "no_price"}

    if not (float(prev_close) > float(cur_close)):
        info["price_drop_pct"] = (float(cur_close) / float(prev_close) - 1.0) * 100.0
        return {**row, **info, "skipped": "price_up"}

    peak_price = profile.get("peak_price")
    peak_day = safe_str(profile.get("peak_day"))
    current = profile.get("current")
    info.update(
        {
            "price_drop_pct": (float(cur_close) / float(prev_close) - 1.0) * 100.0,
            "peak_price": peak_price,
            "peak_day": peak_day,
            "current": current,
            "current_day": safe_str(profile.get("current_day")),
        }
    )

    if peak_price is None or float(peak_price) <= 0:
        info["max_gain_pct"] = None
        info["peak_missing"] = True
    else:
        info["max_gain_pct"] = (float(peak_price) / float(cur_close) - 1.0) * 100.0
        info["peak_missing"] = False

    if current is not None and float(current) > 0:
        info["current_gain_pct"] = (float(current) / float(cur_close) - 1.0) * 100.0

    return {**row, **info, "matched": True}


def _holder_increase_text(row: dict[str, Any]) -> str:
    increases = [h for h in (row.get("increases") or []) if isinstance(h, dict)]
    if not increases:
        return "无"
    parts: list[str] = []
    for item in increases:
        holder = safe_str(item.get("holder"))
        ratio = safe_str(item.get("ratio_fmt"))
        ratio_s = f", 占{ratio}" if ratio else ""
        if item.get("is_new"):
            parts.append(
                f"{holder} {fmt_shares(item.get('cur_shares'))}(新进{ratio_s})"
            )
            continue
        delta = to_float(item.get("delta"))
        if delta is None:
            parts.append(
                f"{holder} {fmt_shares(item.get('cur_shares'))}"
                f"(加仓，变动额未披露{ratio_s})"
            )
            continue
        parts.append(
            f"{holder} {fmt_shares(item.get('prev_shares'))}→"
            f"{fmt_shares(item.get('cur_shares'))}"
            f"(+{fmt_shares(delta)}{ratio_s})"
        )
    return "；".join(parts)


def _print_row(
    row: dict[str, Any],
    *,
    index: int,
    total: int,
) -> None:
    code = safe_str(row.get("code"))
    name = (safe_str(row.get("name")) or "")[:10]
    prefix = f"  [{index:>5}/{total}]"
    skipped = safe_str(row.get("skipped"))

    if skipped:
        reason = _SKIP_LABELS.get(skipped, skipped)
        detail = safe_str(row.get("detail"))
        _log(
            f"{prefix}    {code} {name:<10} · 跳过({reason}"
            + (f": {detail}" if detail else "")
            + ")"
        )
        return

    prev_date = safe_str(row.get("prev_report_date"))
    cur_date = safe_str(row.get("report_date"))
    prev_close = fmt_price(row.get("prev_close")) or "-"
    cur_close = fmt_price(row.get("cur_close")) or "-"
    prev_close_day = safe_str(row.get("prev_close_day")) or prev_date
    cur_close_day = safe_str(row.get("cur_close_day")) or cur_date
    drop = row.get("price_drop_pct")
    drop_s = fmt_pct(drop) or "-"
    peak = fmt_price(row.get("peak_price")) or "-"
    peak_day = safe_str(row.get("peak_day")) or "-"
    max_gain = fmt_pct(row.get("max_gain_pct")) or "-"
    current = fmt_price(row.get("current")) or "-"
    current_gain = fmt_pct(row.get("current_gain_pct")) or "-"

    _log(
        f"{prefix} ★  {code} {name:<10} · "
        f"{prev_date}→{cur_date} · "
        f"收盘 {prev_close}@{prev_close_day}→{cur_close}@{cur_close_day}"
        f"（{drop_s}）"
    )
    _log(f"{' ' * 15}└ 社保加仓：{_holder_increase_text(row)}")
    _log(
        f"{' ' * 15}└ 6.30后最高 {peak}@{peak_day} · 最大涨幅 {max_gain}"
        f" · 现价 {current}（{current_gain}）"
    )
    if row.get("peak_missing"):
        _log(f"{' ' * 15}└ 注意：6.30之后暂无日线数据，最高价涨幅未统计")


def _scan(
    candidates: list[dict[str, str]],
    *,
    target_date: str,
    scope: str,
    keywords: tuple[str, ...],
    adjust: str,
    price_field: str,
    force: bool,
    workers: int,
) -> list[dict[str, Any]]:
    total = len(candidates)
    done = 0
    matched: list[dict[str, Any]] = []
    skipped = 0
    failed = 0
    t0 = time.time()

    def one(item: dict[str, str]) -> dict[str, Any]:
        return _analyze(
            item["code"],
            item.get("name") or "",
            target_date=target_date,
            scope=scope,
            keywords=keywords,
            adjust=adjust,
            price_field=price_field,
            force=force,
        )

    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futures = [pool.submit(one, item) for item in candidates]
        for fut in as_completed(futures):
            done += 1
            try:
                row = fut.result()
            except Exception as exc:  # noqa: BLE001
                failed += 1
                _log(f"  [{done}/{total}] ! 任务失败: {exc}")
                continue

            if row.get("matched"):
                matched.append(row)
            elif row.get("skipped"):
                skipped += 1
            else:
                failed += 1
            _print_row(row, index=done, total=total)

            if done % 50 == 0 or done == total:
                _log(
                    f"  -- 进度 {done}/{total} · 命中 {len(matched)} · 跳过 {skipped}"
                    f" · 失败 {failed} · {time.time() - t0:.0f}s --"
                )

    return matched


def _enrich_live_peak(hits: list[dict[str, Any]], *, adjust: str) -> None:
    """用实时价 / 当日最高价补一次 6.30 后最高价（仅不复权口径可比）。"""
    if not hits or adjust != "none":
        return
    codes = [safe_str(row.get("code")) for row in hits if safe_str(row.get("code"))]
    if not codes:
        return
    _log(f"补拉 {len(codes)} 只命中股的实时行情，用现价/今日最高刷新期间最高价…")
    try:
        quotes = fetch_realtime_quotes(codes)
    except Exception as exc:  # noqa: BLE001
        _log(f"  实时行情失败（忽略）：{exc}")
        return
    if not quotes:
        _log("  实时行情为空（忽略）")
        return

    today = date.today().isoformat()
    for row in hits:
        quote = quotes.get(safe_str(row.get("code"))) or {}
        candidates = [
            to_float(quote.get("price")),
            to_float(quote.get("high")),
        ]
        best = max((v for v in candidates if v is not None and v > 0), default=None)
        if best is None:
            continue
        cur_close = to_float(row.get("cur_close"))
        if cur_close is None or cur_close <= 0:
            continue
        peak = to_float(row.get("peak_price"))
        if peak is None or best > peak:
            row["peak_price"] = best
            row["peak_day"] = today
            row["max_gain_pct"] = (best / cur_close - 1.0) * 100.0
            row["peak_missing"] = False

        price = to_float(quote.get("price"))
        if price is not None and price > 0:
            row["current"] = price
            row["current_day"] = today
            row["current_gain_pct"] = (price / cur_close - 1.0) * 100.0


def _print_summary(hits: list[dict[str, Any]], *, target_date: str) -> None:
    _log("")
    _log(f"=== 命中 {len(hits)} 只（社保加仓 + {target_date} 收盘回落）===")
    for index, row in enumerate(hits, start=1):
        code = safe_str(row.get("code"))
        name = (safe_str(row.get("name")) or "")[:10]
        _log(
            f"{index:>4}  {code} {name:<10}  "
            f"{safe_str(row.get('prev_report_date'))}→{safe_str(row.get('report_date'))}  "
            f"收盘 {fmt_price(row.get('prev_close')) or '-'}"
            f"@{safe_str(row.get('prev_close_day')) or '-'}→"
            f"{fmt_price(row.get('cur_close')) or '-'}"
            f"@{safe_str(row.get('cur_close_day')) or '-'}"
            f"（{fmt_pct(row.get('price_drop_pct')) or '-'}）  "
            f"6.30后最高 {fmt_price(row.get('peak_price')) or '-'}"
            f"@{safe_str(row.get('peak_day')) or '-'}  "
            f"最大涨幅 {fmt_pct(row.get('max_gain_pct')) or '-'}  "
            f"现价 {fmt_price(row.get('current')) or '-'}"
            f"（{fmt_pct(row.get('current_gain_pct')) or '-'}）"
        )
        _log(f"      └ 社保加仓：{_holder_increase_text(row)}")


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


def _write_mine_group(
    rows: list[dict[str, Any]],
    *,
    group_name: str,
    replace: bool,
) -> dict[str, Any] | None:
    name = safe_str(group_name) or DEFAULT_GROUP
    if not rows:
        _log(f"分组「{name}」无命中，跳过写入")
        return None
    group = _ensure_group(name)
    gid = safe_str(group.get("id"))
    if replace:
        removed = _clear_group(gid)
        if removed:
            _log(f"分组「{name}」已清空 {removed} 只")
    result = _add_to_group(gid, rows)
    added = result.get("added") or []
    skipped = result.get("skipped") or []
    final = result.get("group") or group
    _log(
        f"分组「{final.get('name')}」({final.get('id')}) "
        f"现有 {final.get('count')} 只 · 新加 {len(added)} · 已存在跳过 {len(skipped)}"
    )
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="6.30 社保加仓 + 股价回落扫描，并统计 6.30 之后最高价涨幅 → 写入「我的」分组",
    )
    parser.add_argument(
        "--report-date",
        default=_default_report_date(),
        help=f"目标报告期（默认最近一个 6.30：{_default_report_date()}）",
    )
    parser.add_argument(
        "--group",
        default=DEFAULT_GROUP,
        help=f"写入分组名（默认 {DEFAULT_GROUP}）",
    )
    parser.add_argument("--workers", type=int, default=DEFAULT_WORKERS, help="并发数")
    parser.add_argument(
        "--scope",
        default=DEFAULT_SCOPE,
        choices=("holders", "free"),
        help="holders 前十大股东（默认） | free 前十大流通股东",
    )
    parser.add_argument(
        "--keywords",
        default=",".join(DEFAULT_KEYWORDS),
        help=f"股东名称关键词，逗号分隔（默认 {'/'.join(DEFAULT_KEYWORDS)}）",
    )
    parser.add_argument(
        "--adjust",
        default=DEFAULT_ADJUST,
        choices=("none", "qfq"),
        help="价格复权口径：none 不复权（默认） | qfq 前复权",
    )
    parser.add_argument(
        "--price-field",
        default=DEFAULT_PRICE_FIELD,
        choices=("high", "close"),
        help="6.30 之后最高价取法：high 最高价（默认） | close 收盘价",
    )
    parser.add_argument(
        "--codes",
        default="",
        help="只扫描这些代码（逗号分隔）；省略则全市场（已滤创业板/ST）",
    )
    parser.add_argument("--max-scan", type=int, default=0, help="最多扫描多少只（0=不限制）")
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

    target_date = safe_str(args.report_date)[:10]
    try:
        datetime.strptime(target_date, "%Y-%m-%d")
    except ValueError:
        _log(f"ERROR: --report-date 需为 YYYY-MM-DD，收到 {target_date!r}")
        return 1

    keywords = _parse_keywords(args.keywords)
    scope = safe_str(args.scope) or DEFAULT_SCOPE
    adjust = safe_str(args.adjust) or DEFAULT_ADJUST
    price_field = safe_str(args.price_field) or DEFAULT_PRICE_FIELD
    group_name = safe_str(args.group) or DEFAULT_GROUP

    if safe_str(args.codes):
        candidates = _parse_codes(args.codes)
        _log(f"候选来自 --codes：{len(candidates)} 只")
    else:
        try:
            candidates = _load_universe()
        except Exception as exc:  # noqa: BLE001
            _log(f"ERROR: 无法取得股票池：{exc}")
            return 1

    if args.max_scan and args.max_scan > 0:
        candidates = candidates[: int(args.max_scan)]
        _log(f"截断为前 {len(candidates)} 只")

    if not candidates:
        _log("没有可扫描的候选股票")
        return 1

    _log(
        f"开始扫描 · 目标报告期={target_date} · 口径={scope} · "
        f"关键词={'/'.join(keywords)} · 复权={adjust} · 取价={price_field} · "
        f"force={bool(args.force)} · workers={args.workers}"
        + (" · dry-run" if args.dry_run else "")
        + ("" if args.dry_run else f" · replace={bool(args.replace)}")
    )

    hits = _scan(
        candidates,
        target_date=target_date,
        scope=scope,
        keywords=keywords,
        adjust=adjust,
        price_field=price_field,
        force=bool(args.force),
        workers=int(args.workers),
    )

    _enrich_live_peak(hits, adjust=adjust)

    # 6.30 后涨幅从高到低；无涨幅的排最后；同幅度按代码升序
    hits.sort(
        key=lambda r: (
            r.get("max_gain_pct") is None,
            -float(r.get("max_gain_pct") or 0.0),
            safe_str(r.get("code")),
        )
    )

    elapsed = time.time() - started
    _print_summary(hits, target_date=target_date)
    _log(f"\n扫描完成（耗时 {elapsed:.1f}s）：命中 {len(hits)} 只")

    mine_meta: dict[str, Any] = {
        "group": group_name,
        "replace": bool(args.replace),
        "dry_run": bool(args.dry_run),
        "written": False,
    }

    if args.dry_run:
        _log(f"[dry-run] 跳过写入分组「{group_name}」（本会写入 {len(hits)} 只）")
    else:
        try:
            result = _write_mine_group(hits, group_name=group_name, replace=bool(args.replace))
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
            "report_date": target_date,
            "scope": scope,
            "keywords": list(keywords),
            "adjust": adjust,
            "price_field": price_field,
            "candidates": len(candidates),
            "matched": len(hits),
            "elapsed_sec": round(elapsed, 1),
            "exclude": ["创业板(300/301)", "ST/退市", "B股"],
            "rule": (
                f"{target_date} 前十大股东中名称含关键词的股东持股数较上一报告期增加，"
                f"且 {target_date} 收盘价 < 上一报告期交易日收盘价；"
                f"统计 {target_date} 之后（{price_field}，{adjust}）最高价相对 "
                f"{target_date} 收盘价的涨幅"
            ),
            "mine": mine_meta,
        },
        "items": hits,
    }

    if args.out.strip():
        out_path = Path(args.out.strip())
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        _log(f"已写入 {out_path}")

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
