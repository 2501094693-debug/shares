"""最近 N 个交易日：相对指数偏离选出 Top 股票（默认不考虑前低交易间隔）。

偏离口径（复用 ``company.analysis.line.compare``）：
  - 四项涨跌幅 → 选区样本标准差 σ → zdif = rs/σs − rb/σb
  - 同涨/同跌权重 1，反向涨跌权重 1.5
  - 按因子权重汇总 |zdif|×权重（与 compare 的 deviation 一致）

默认只按偏离分百分位排名取 Top；``--w-gap > 0`` 时可再加权前低间隔。
默认排除创业板（300/301）与 ST/*ST。
选出结果默认写入「我的」分组（可改名 / 不清空 / 只预览）。

用法（项目根目录）::

    .venv\\Scripts\\python.exe scripts/index_deviate_extremum.py
    .venv\\Scripts\\python.exe scripts/index_deviate_extremum.py --index 000001 --days 10 --top 20
    .venv\\Scripts\\python.exe scripts/index_deviate_extremum.py --group 指数偏离 --top 30
    .venv\\Scripts\\python.exe scripts/index_deviate_extremum.py --no-replace
    .venv\\Scripts\\python.exe scripts/index_deviate_extremum.py --dry-run
    .venv\\Scripts\\python.exe scripts/index_deviate_extremum.py --codes 600519,000333 --json
    .venv\\Scripts\\python.exe scripts/index_deviate_extremum.py --workers 8
    .venv\\Scripts\\python.exe scripts/index_deviate_extremum.py --w-gap 0.5 --pool 120
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
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

from company.analysis.line.compare.codes import normalize_index_code  # noqa: E402
from company.analysis.line.compare.service import compare_one  # noqa: E402
from company.analysis.line.compare.series import (  # noqa: E402
    factors_of,
    fetch_index_day,
    fetch_stock_day,
    slice_factors,
)
from company.analysis.line.extremum.service import (  # noqa: E402
    analyze_extremum,
    compute_extremum,
)
from core.codes import normalize_code, safe_str  # noqa: E402
from core.fmt import to_float  # noqa: E402
from core.paths import STOCK_INDEX_CACHE  # noqa: E402
from mine.service import service as mine_service  # noqa: E402

_print_lock = threading.Lock()

DEFAULT_INDEX = "000001"
DEFAULT_DAYS = 10
DEFAULT_TOP = 20
DEFAULT_POOL = 100
DEFAULT_WORKERS = 6
DEFAULT_W_DEV = 1.0
DEFAULT_W_GAP = 0.0  # 默认不考虑前低交易间隔
DEFAULT_GROUP = "指数偏离"
MAX_STOCKS_PER_GROUP = 1000  # 与 mine.service 上限一致


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


def _is_chinext(code: str) -> bool:
    return code.startswith(("300", "301"))


def _is_st(name: str) -> bool:
    text = safe_str(name).upper().replace(" ", "")
    return "ST" in text


def _load_index_candidates() -> list[dict[str, str]]:
    if not STOCK_INDEX_CACHE.is_file():
        raise FileNotFoundError(f"缺少股票索引: {STOCK_INDEX_CACHE}")
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
        if not code or code in seen:
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
    _log(f"索引过滤：跳过创业板 {skipped_cyb} · ST {skipped_st} · 剩余 {len(out)}")
    return out


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


def _resolve_window(
    index_code: str,
    *,
    days: int,
    end: str = "",
) -> tuple[str, str, list[str], dict[str, Any], dict[str, dict[str, float | None]]]:
    """取指数最近 ``days`` 个交易日作为对比窗，并预取指数因子。"""
    end_s = (end or "").strip()
    if not end_s:
        end_s = datetime.now().strftime("%Y%m%d")
    # 多取自然日，保证盖住 N 个交易日 + 前收
    pad_days = max(40, int(days) * 3 + 20)
    beg_probe = (
        datetime.strptime("".join(ch for ch in end_s if ch.isdigit())[:8], "%Y%m%d")
        - timedelta(days=pad_days)
    ).strftime("%Y%m%d")

    # 同花顺未登录 / 网络慢时会先重试再回退东财→缓存→腾讯，期间原先无日志
    _log(
        f"  拉取指数日线 {index_code}  {beg_probe}~{end_s}"
        f"（同花顺→东财→缓存→腾讯；未登录或网络慢可能要等几十秒）…"
    )
    t_fetch = time.time()
    idx_pack = fetch_index_day(index_code, beg=beg_probe, end=end_s)
    _log(
        f"  指数日线就绪 · 源={idx_pack.get('source') or '-'} · "
        f"{len(idx_pack.get('items') or [])} 根 · {time.time() - t_fetch:.1f}s"
    )
    items = list(idx_pack.get("items") or [])
    dates_all = sorted(
        {
            str(b.get("time") or "")[:10]
            for b in items
            if str(b.get("time") or "")[:10]
        }
    )
    if len(dates_all) < 2:
        raise ValueError(f"指数 {index_code} 交易日不足")

    # 因子需要前收，有效涨跌幅日比 bar 少一天；用因子日对齐
    fac_all = factors_of(items)
    fac_dates = sorted(fac_all.keys())
    if len(fac_dates) < days:
        raise ValueError(
            f"指数有效交易日仅 {len(fac_dates)} 天，不足 {days} 天"
        )
    window = fac_dates[-days:]
    beg = window[0].replace("-", "")
    end_eff = window[-1].replace("-", "")
    idx_fac = slice_factors(fac_all, beg=beg, end=end_eff)
    return beg, end_eff, window, idx_pack, idx_fac


def _bar_date(bar: dict[str, Any]) -> str:
    return str(bar.get("time") or "")[:10]


def _range_min_low_date(
    bars: list[dict[str, Any]],
    window_dates: set[str],
) -> tuple[str, float] | None:
    """区间内最低价（low）及其所在交易日（并列取最近一日）。"""
    best_date: str | None = None
    best_low: float | None = None
    for bar in bars:
        d = _bar_date(bar)
        if d not in window_dates:
            continue
        low = to_float(bar.get("low"))
        if low is None:
            continue
        if best_low is None or low < best_low or (low == best_low and d > (best_date or "")):
            best_low = low
            best_date = d
    if best_date is None or best_low is None:
        return None
    return best_date, best_low


def _percentile_ranks(values: list[float]) -> list[float]:
    """平均秩百分位，落在 (0, 1]；全相等则全 0.5。"""
    n = len(values)
    if n == 0:
        return []
    indexed = sorted(enumerate(values), key=lambda x: x[1])
    ranks = [0.0] * n
    i = 0
    while i < n:
        j = i
        while j + 1 < n and indexed[j + 1][1] == indexed[i][1]:
            j += 1
        # 1-based average rank → / n
        avg = (i + j + 2) / 2.0
        pct = avg / n
        for k in range(i, j + 1):
            ranks[indexed[k][0]] = pct
        i = j + 1
    # 若全部相同，上面会全是同一百分位；改为 0.5 更中性
    if len(set(values)) == 1:
        return [0.5] * n
    return ranks


def _deviation_for_stock(
    code: str,
    name: str,
    *,
    beg: str,
    end: str,
    window: list[str],
    idx_fac: dict[str, dict[str, float | None]],
    with_gap: bool = False,
) -> dict[str, Any]:
    stock_pack = fetch_stock_day(code, beg=beg, end=end)
    label = safe_str(stock_pack.get("name")) or name
    if _is_st(label):
        return {
            "code": code,
            "name": label,
            "skipped": "st",
            "deviation": None,
        }

    items = list(stock_pack.get("items") or [])
    stock_fac_all = factors_of(items)
    stock_fac = slice_factors(stock_fac_all, beg=beg, end=end)
    dates = sorted(d for d in stock_fac if d in idx_fac)
    if len(dates) < 2:
        return {
            "code": code,
            "name": label,
            "error": f"对齐交易日不足({len(dates)})",
            "deviation": None,
        }

    one = compare_one(stock_fac, idx_fac, dates=dates)
    dev = one.get("deviation") or {}
    total = one.get("total") or {}

    sessions: int | None = None
    gap: int | None = None
    prior_date: str | None = None
    min_date: str | None = None
    min_low: float | None = None
    extremum_complete = True
    if with_gap:
        # 先用已拉到的日线估间隔；不够再第二轮 analyze_extremum 补全
        extremum_complete = False
        min_pack = _range_min_low_date(items, set(window))
        if min_pack is not None:
            min_date, min_low = min_pack
            try:
                ext = compute_extremum(items, min_date)
                low_row = (ext.get("extremum") or {}).get("low") or {}
                if low_row.get("date") is not None:
                    sessions = int(low_row["sessions"])
                    gap = int(low_row["gap"]) if low_row.get("gap") is not None else None
                    prior_date = str(low_row.get("date") or "") or None
                    extremum_complete = True
            except ValueError:
                pass

    return {
        "code": code,
        "name": label,
        "deviation": float(dev.get("value") or 0.0),
        "deviation_level": safe_str(dev.get("level")),
        "strength": float(total.get("value") or 0.0),
        "strength_level": safe_str(total.get("level")),
        "norm_mode": safe_str((one.get("norm") or {}).get("mode")),
        "n_days": len(dates),
        "min_low_date": min_date,
        "min_low": min_low,
        "prior_low_date": prior_date,
        "sessions": sessions,
        "gap": gap,
        "extremum_complete": extremum_complete,
    }


def _enrich_extremum(row: dict[str, Any]) -> dict[str, Any]:
    """对尚未找到前低的股票，翻页拉历史补全 low 前低间隔。"""
    if row.get("extremum_complete") or row.get("min_low_date") is None:
        return row
    if row.get("deviation") is None:
        return row
    code = row["code"]
    min_date = str(row["min_low_date"])
    try:
        pack = analyze_extremum(code, min_date)
    except Exception as exc:  # noqa: BLE001
        row = dict(row)
        row["extremum_error"] = str(exc)
        return row
    low_row = (pack.get("extremum") or {}).get("low") or {}
    out = dict(row)
    if not out.get("name") and pack.get("name"):
        out["name"] = safe_str(pack.get("name"))
    if low_row.get("date") is not None:
        out["prior_low_date"] = str(low_row.get("date") or "") or None
        out["sessions"] = int(low_row["sessions"])
        out["gap"] = int(low_row["gap"]) if low_row.get("gap") is not None else None
        out["prior_low"] = to_float(low_row.get("found_price"))
        out["extremum_complete"] = True
    else:
        # 上市以来未见更低：用已有历史长度作为「极大间隔」代理
        out["sessions"] = out.get("sessions")
        out["extremum_complete"] = True
        out["prior_low_date"] = None
        out["gap"] = None
        out["no_prior_lower"] = True
    return out


def _combine_and_rank(
    rows: list[dict[str, Any]],
    *,
    w_dev: float,
    w_gap: float,
    top: int,
) -> list[dict[str, Any]]:
    usable = [r for r in rows if r.get("deviation") is not None]
    if not usable:
        return []

    use_gap = float(w_gap) > 0
    sessions_vals: list[float] = [0.0] * len(usable)
    if use_gap:
        # 无前低：sessions 记 0；「上市未见更低」给同批最大值，避免被当成 0
        finite_sessions = [
            int(r["sessions"])
            for r in usable
            if r.get("sessions") is not None and not r.get("no_prior_lower")
        ]
        max_sess = max(finite_sessions) if finite_sessions else 0
        sentinel = max_sess + max(20, max_sess // 5 + 1) if max_sess else 252
        sessions_vals = []
        for r in usable:
            if r.get("no_prior_lower"):
                sessions_vals.append(float(sentinel))
            elif r.get("sessions") is None:
                sessions_vals.append(0.0)
            else:
                sessions_vals.append(float(r["sessions"]))

    dev_vals = [float(r["deviation"]) for r in usable]
    dev_ranks = _percentile_ranks(dev_vals)
    gap_ranks = _percentile_ranks(sessions_vals) if use_gap else [0.0] * len(usable)
    w_dev_eff = float(w_dev)
    w_gap_eff = float(w_gap) if use_gap else 0.0
    w_sum = w_dev_eff + w_gap_eff
    if w_sum <= 0:
        w_dev_eff, w_gap_eff, w_sum = 1.0, 0.0, 1.0

    ranked: list[dict[str, Any]] = []
    for i, r in enumerate(usable):
        combined = (w_dev_eff * dev_ranks[i] + w_gap_eff * gap_ranks[i]) / w_sum
        item = dict(r)
        item["sessions_used"] = sessions_vals[i] if use_gap else None
        item["rank_deviation"] = round(dev_ranks[i], 4)
        item["rank_sessions"] = round(gap_ranks[i], 4) if use_gap else None
        item["combined"] = round(combined, 6)
        ranked.append(item)

    ranked.sort(
        key=lambda x: (
            float(x["combined"]),
            float(x["deviation"] or 0),
            float(x.get("sessions_used") or 0),
        ),
        reverse=True,
    )
    for i, item in enumerate(ranked, start=1):
        item["rank"] = i
    return ranked[: max(1, top)]


def _scan_deviation(
    candidates: list[dict[str, str]],
    *,
    beg: str,
    end: str,
    window: list[str],
    idx_fac: dict[str, dict[str, float | None]],
    workers: int,
    with_gap: bool = False,
) -> list[dict[str, Any]]:
    total = len(candidates)
    done = 0
    ok = 0
    failed = 0
    skipped = 0
    results: list[dict[str, Any]] = []
    t0 = time.time()

    def one(item: dict[str, str]) -> dict[str, Any]:
        return _deviation_for_stock(
            item["code"],
            item.get("name") or "",
            beg=beg,
            end=end,
            window=window,
            idx_fac=idx_fac,
            with_gap=with_gap,
        )

    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futures = [pool.submit(one, item) for item in candidates]
        for fut in as_completed(futures):
            done += 1
            try:
                row = fut.result()
            except Exception as exc:  # noqa: BLE001
                failed += 1
                _log(f"  ! 偏离计算失败: {exc}")
                continue
            if row.get("skipped"):
                skipped += 1
                _log(
                    f"  [{done}/{total}] {row.get('code')} "
                    f"跳过({row.get('skipped')})"
                )
            elif row.get("deviation") is None:
                failed += 1
                err = row.get("error") or "无偏离分"
                _log(f"  [{done}/{total}] ! {row.get('code')} {err}")
            else:
                ok += 1
                results.append(row)
                _log_stock_score(
                    row, prefix=f"  [{done}/{total}] ", with_gap=with_gap
                )
            if done % 50 == 0 or done == total:
                elapsed = time.time() - t0
                _log(
                    f"  -- 进度 {done}/{total}  有效 {ok}  "
                    f"失败 {failed}  跳过 {skipped}  "
                    f"{elapsed:.0f}s --"
                )
    return results


def _scan_extremum(
    rows: list[dict[str, Any]],
    *,
    workers: int,
) -> list[dict[str, Any]]:
    need = [r for r in rows if not r.get("extremum_complete")]
    if not need:
        return rows
    _log(f"补全前低间隔：{len(need)} / {len(rows)}")
    by_code = {r["code"]: r for r in rows}
    total = len(need)
    done = 0
    t0 = time.time()

    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futures = {pool.submit(_enrich_extremum, r): r["code"] for r in need}
        for fut in as_completed(futures):
            done += 1
            code = futures[fut]
            try:
                row = fut.result()
                by_code[code] = row
                _log_stock_score(
                    row, prefix=f"  前低[{done}/{total}] ", with_gap=True
                )
            except Exception as exc:  # noqa: BLE001
                _log(f"  ! 前低补全失败 {code}: {exc}")
            if done % 20 == 0 or done == total:
                _log(f"  -- 前低补全进度 {done}/{total}  {time.time() - t0:.0f}s --")

    return [by_code[r["code"]] for r in rows]


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
            f"按综合分保留前 {MAX_STOCKS_PER_GROUP} 只"
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


def _format_sessions(row: dict[str, Any]) -> str:
    sess = row.get("sessions_used")
    if sess is None and row.get("sessions") is not None:
        sess = row.get("sessions")
    if sess is None:
        return "-"
    text = f"{float(sess):.0f}"
    if row.get("no_prior_lower"):
        text = f"{text}+"
    return text


def _log_stock_score(
    row: dict[str, Any],
    *,
    prefix: str = "",
    with_gap: bool = False,
) -> None:
    """打印单只股票当前已有评分（扫描阶段尚无综合分）。"""
    code = safe_str(row.get("code")) or "-"
    name = (safe_str(row.get("name")) or "")[:10]
    dev = row.get("deviation")
    if dev is None:
        return
    level = safe_str(row.get("deviation_level")) or "-"
    strength = float(row.get("strength") or 0)
    head = prefix or "  "
    extra = ""
    if row.get("combined") is not None:
        extra = f" · 综合 {float(row['combined']):.4f}"
    gap_part = ""
    if with_gap:
        sess_s = _format_sessions(row)
        if row.get("sessions") is None and not row.get("no_prior_lower"):
            gap_part = " · 间隔待补全"
        else:
            gap_part = f" · 间隔 {sess_s} 个交易日"
            if row.get("no_prior_lower"):
                gap_part += "（上市未见更低）"
    _log(
        f"{head}{code} {name:<10}  "
        f"偏离 {float(dev):.4f}（{level}）· "
        f"强弱 {strength:.4f}{gap_part}{extra}"
    )


def _print_table(
    rows: list[dict[str, Any]],
    *,
    index_code: str,
    index_name: str,
    beg: str,
    end: str,
    w_dev: float,
    w_gap: float,
) -> None:
    use_gap = float(w_gap) > 0
    _log("")
    weight_s = (
        f"权重 偏离={w_dev} 间隔={w_gap}"
        if use_gap
        else f"仅偏离分（w_dev={w_dev}）"
    )
    _log(
        f"=== Top {len(rows)}  ·  vs {index_code} {index_name}  "
        f"·  {beg[:4]}-{beg[4:6]}-{beg[6:]} ~ "
        f"{end[:4]}-{end[4:6]}-{end[6:]}  "
        f"·  {weight_s}"
    )
    if use_gap:
        _log(
            f"{'名次':>4}  {'代码':<8} {'名称':<10}  "
            f"{'综合':>7}  {'偏离分':>7}  {'偏离程度':<8}  "
            f"{'强弱':>7}  {'间隔交易日':>8}  "
            f"{'偏离排名':>8}  {'间隔排名':>8}  "
            f"{'区间低点日':<12} {'前低日':<12}"
        )
    else:
        _log(
            f"{'名次':>4}  {'代码':<8} {'名称':<10}  "
            f"{'综合':>7}  {'偏离分':>7}  {'偏离程度':<8}  "
            f"{'强弱':>7}  {'偏离排名':>8}"
        )
    for row in rows:
        dev_level = safe_str(row.get("deviation_level")) or "-"
        if use_gap:
            sess_s = _format_sessions(row)
            _log(
                f"{row.get('rank') or 0:4d}  "
                f"{row.get('code') or '':<8} "
                f"{(row.get('name') or '')[:10]:<10}  "
                f"{float(row.get('combined') or 0):7.4f}  "
                f"{float(row.get('deviation') or 0):7.4f}  "
                f"{dev_level:<8}  "
                f"{float(row.get('strength') or 0):7.4f}  "
                f"{sess_s:>8}  "
                f"{float(row.get('rank_deviation') or 0):8.4f}  "
                f"{float(row.get('rank_sessions') or 0):8.4f}  "
                f"{str(row.get('min_low_date') or '-'):<12} "
                f"{str(row.get('prior_low_date') or '-'):<12}"
            )
            _log(
                f"      └ 评分：偏离 {float(row.get('deviation') or 0):.4f}"
                f"（{dev_level}）· "
                f"间隔 {sess_s} 个交易日"
                + (
                    "（上市未见更低）"
                    if row.get("no_prior_lower")
                    else ""
                )
                + f" · 综合 {float(row.get('combined') or 0):.4f}"
            )
        else:
            _log(
                f"{row.get('rank') or 0:4d}  "
                f"{row.get('code') or '':<8} "
                f"{(row.get('name') or '')[:10]:<10}  "
                f"{float(row.get('combined') or 0):7.4f}  "
                f"{float(row.get('deviation') or 0):7.4f}  "
                f"{dev_level:<8}  "
                f"{float(row.get('strength') or 0):7.4f}  "
                f"{float(row.get('rank_deviation') or 0):8.4f}"
            )
            _log(
                f"      └ 评分：偏离 {float(row.get('deviation') or 0):.4f}"
                f"（{dev_level}）· "
                f"综合 {float(row.get('combined') or 0):.4f}"
            )


def main(argv: list[str] | None = None) -> int:
    _configure_stdio()
    p = argparse.ArgumentParser(
        description="最近 N 日相对指数偏离 Top 选股（默认不考虑前低交易间隔）"
    )
    p.add_argument(
        "--index",
        default=DEFAULT_INDEX,
        help=f"对比指数，默认 {DEFAULT_INDEX}（上证指数）",
    )
    p.add_argument(
        "--days",
        type=int,
        default=DEFAULT_DAYS,
        help=f"最近交易日数，默认 {DEFAULT_DAYS}",
    )
    p.add_argument(
        "--top",
        type=int,
        default=DEFAULT_TOP,
        help=f"输出只数，默认 {DEFAULT_TOP}",
    )
    p.add_argument(
        "--pool",
        type=int,
        default=DEFAULT_POOL,
        help=(
            f"仅 --w-gap>0 时有效：按偏离分先取前 N 只再补全前低，默认 {DEFAULT_POOL}；"
            "设为 0 表示全量补全（更慢）"
        ),
    )
    p.add_argument("--workers", type=int, default=DEFAULT_WORKERS, help="并发数")
    p.add_argument("--end", default="", help="结束日 YYYYMMDD / YYYY-MM-DD；空=今天")
    p.add_argument("--codes", default="", help="仅扫描这些代码（逗号分隔），便于试跑")
    p.add_argument(
        "--w-dev",
        type=float,
        default=DEFAULT_W_DEV,
        help=f"偏离排名权重，默认 {DEFAULT_W_DEV}",
    )
    p.add_argument(
        "--w-gap",
        type=float,
        default=DEFAULT_W_GAP,
        help=f"前低间隔排名权重，默认 {DEFAULT_W_GAP}（0=不考虑交易间隔）",
    )
    p.add_argument(
        "--group",
        default=DEFAULT_GROUP,
        help=f"写入「我的」分组名，默认 {DEFAULT_GROUP}",
    )
    p.add_argument(
        "--replace",
        dest="replace",
        action="store_true",
        default=True,
        help="写入前清空目标分组（默认开启）",
    )
    p.add_argument(
        "--no-replace",
        dest="replace",
        action="store_false",
        help="不清空，只追加未在组内的股票",
    )
    p.add_argument("--dry-run", action="store_true", help="只打印结果，不写入分组")
    p.add_argument("--json", action="store_true", help="输出 JSON")
    p.add_argument(
        "--out",
        default="",
        help="写入结果 JSON 文件路径；空=不写文件",
    )
    args = p.parse_args(argv)

    if args.days < 2:
        p.error("--days 至少为 2")
    if args.top < 1:
        p.error("--top 至少为 1")

    try:
        index_code = normalize_index_code(args.index)
    except ValueError as exc:
        _log(f"ERROR: {exc}")
        return 1

    _log(f"解析对比窗口：指数 {index_code} · 最近 {args.days} 个交易日 …")
    try:
        beg, end, window, idx_pack, idx_fac = _resolve_window(
            index_code, days=args.days, end=args.end
        )
    except Exception as exc:  # noqa: BLE001
        _log(f"ERROR: 无法取得指数窗口: {exc}")
        return 1

    index_name = safe_str(idx_pack.get("name")) or index_code
    _log(
        f"窗口 {window[0]} ~ {window[-1]}（{len(window)} 日）  "
        f"指数源={idx_pack.get('source') or ''}"
    )

    if args.codes.strip():
        candidates = _parse_codes(args.codes)
    else:
        candidates = _load_index_candidates()
    if not candidates:
        _log("ERROR: 无候选股票")
        return 1
    _log(f"候选 {len(candidates)} · workers={args.workers}")

    w_dev = float(args.w_dev)
    w_gap = float(args.w_gap)
    with_gap = w_gap > 0
    if with_gap:
        _log(f"综合模式：偏离权重={w_dev} · 前低间隔权重={w_gap}")
    else:
        _log("排序口径：仅偏离分（不考虑前低交易间隔）")

    t0 = time.time()
    scored = _scan_deviation(
        candidates,
        beg=beg,
        end=end,
        window=window,
        idx_fac=idx_fac,
        workers=args.workers,
        with_gap=with_gap,
    )
    if not scored:
        _log("ERROR: 无有效偏离结果")
        return 1

    scored.sort(key=lambda r: float(r.get("deviation") or 0), reverse=True)
    if with_gap:
        pool_n = int(args.pool)
        if pool_n > 0 and len(scored) > pool_n:
            _log(f"按偏离分取前 {pool_n} 只进入前低补全 / 综合排序")
            pool = scored[:pool_n]
        else:
            pool = scored
        pool = _scan_extremum(pool, workers=args.workers)
    else:
        pool = scored

    top_rows = _combine_and_rank(
        pool,
        w_dev=w_dev,
        w_gap=w_gap,
        top=int(args.top),
    )

    elapsed = time.time() - t0
    group_name = safe_str(args.group) or DEFAULT_GROUP
    mine_meta: dict[str, Any] = {
        "group": group_name,
        "replace": bool(args.replace),
        "dry_run": bool(args.dry_run),
        "written": False,
    }

    if args.dry_run:
        _log(f"[dry-run] 跳过写入分组「{group_name}」（本会写入 {len(top_rows)} 只）")
    else:
        try:
            result = _write_mine_group(
                top_rows,
                group_name=group_name,
                replace=bool(args.replace),
            )
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
            "index": index_code,
            "index_name": index_name,
            "beg": f"{beg[:4]}-{beg[4:6]}-{beg[6:]}",
            "end": f"{end[:4]}-{end[4:6]}-{end[6:]}",
            "days": len(window),
            "window": window,
            "candidates": len(candidates),
            "scored": len(scored),
            "pool": len(pool),
            "top": len(top_rows),
            "w_dev": float(args.w_dev),
            "w_gap": float(args.w_gap),
            "elapsed_sec": round(elapsed, 1),
            "exclude": ["创业板(300/301)", "ST"],
            "mine": mine_meta,
            "method": {
                "deviation": "compare.zdif 同向×1 反向×1.5，因子加权 |zdif|",
                "extremum": (
                    "区间最低 low → 前更低日 sessions"
                    if with_gap
                    else "未使用"
                ),
                "combine": (
                    "百分位排名加权"
                    if with_gap
                    else "仅偏离百分位排名"
                ),
            },
        },
        "items": top_rows,
    }

    if args.out.strip():
        out_path = Path(args.out.strip())
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        _log(f"已写入 {out_path}")

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        _print_table(
            top_rows,
            index_code=index_code,
            index_name=index_name,
            beg=beg,
            end=end,
            w_dev=float(args.w_dev),
            w_gap=float(args.w_gap),
        )
        _log(f"\n完成：扫描 {len(scored)} 只 · 输出 {len(top_rows)} 只 · {elapsed:.0f}s")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
