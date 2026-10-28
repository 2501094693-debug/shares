"""全市场「社保 / 养老增持 + 股价回落」扫描，命中写入「我的」分组。

扫描范围：全 A 股（默认排除创业板 300/301 与 ST/*ST）。
对每只股票（复用系统现有功能 ``company.statistics.holdings`` 的前十大股东）：

1. 取「本次报告期」（最新）前十大股东，挑出名称含「社保」「养老」的股东；
2. 取「上一次报告期」前十大股东，按股东名称对齐其持股数量；
3. 若某个「社保 / 养老」股东的持股数量较上一次报告期**增加**（新增进十大也视为增加）；
4. 且该股「上一次报告期当日收盘价」> 「本次报告期当日收盘价」（股价回落），

则该股命中，写入「我的」分组（默认组名「社保养老增持」）。

收盘价取报告期当日（非交易日取最近的前一交易日）的前复权收盘价。
扫描过程中实时打印每只股票的处理结果。

用法（项目根目录）::

    .venv\\Scripts\\python.exe scripts/social_security_holdings.py
    .venv\\Scripts\\python.exe scripts/social_security_holdings.py --workers 8
    .venv\\Scripts\\python.exe scripts/social_security_holdings.py --codes 600519,000333 --dry-run
    .venv\\Scripts\\python\\python.exe scripts/social_security_holdings.py --group 社保养老增持 --no-replace
    .venv\\Scripts\\python.exe scripts/social_security_holdings.py --keywords 社保,养老,汇金 --max-scan 300

说明：
- ``--keywords`` 可自定义关键词（默认「社保,养老」）。
- ``--scope`` 可选 ``holders``（十大股东，默认）或 ``free``（十大流通股东）。
- 网络/接口异常、无数据、无社保养老股东、持股未增加、股价未回落的股票都会被跳过并打印原因。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

_SCRIPT = Path(__file__).resolve()
_ROOT = _SCRIPT.parents[1]
_BACKEND = _ROOT / "backend"
for path in (_BACKEND, _ROOT):
    text = str(path)
    if text not in sys.path:
        sys.path.insert(0, text)

from company.analysis.line.compare.series import fetch_stock_day  # noqa: E402
from company.statistics.holdings.holders import fetch_top_holders  # noqa: E402
from core.codes import normalize_code, safe_str  # noqa: E402
from core.fmt import fmt_pct, fmt_shares, to_float  # noqa: E402
from core.paths import STOCK_INDEX_CACHE  # noqa: E402
from mine.service import service as mine_service  # noqa: E402

_print_lock = threading.Lock()

DEFAULT_GROUP = "社保养老增持"
DEFAULT_WORKERS = 6
DEFAULT_KEYWORDS = ("社保", "养老")
DEFAULT_SCOPE = "holders"
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
    """创业板：深交所 300 / 301。"""
    return code.startswith(("300", "301"))


def _is_st(name: str) -> bool:
    text = safe_str(name).upper().replace(" ", "")
    return "ST" in text


def _parse_keywords(raw: str) -> tuple[str, ...]:
    parts = [p.strip() for p in re.split(r"[,，\s;；|]+", safe_str(raw)) if p.strip()]
    return tuple(parts) or DEFAULT_KEYWORDS


def _match_keyword(name: str, keywords: tuple[str, ...]) -> bool:
    text = safe_str(name)
    return bool(text) and any(k in text for k in keywords)


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


def _close_on_or_before(bars: list[dict[str, Any]], target_date: str) -> float | None:
    """在按时间升序的日线里，取 <= target_date 的最近一根收盘价。"""
    best: dict[str, Any] | None = None
    for bar in bars:
        day = str(bar.get("time") or "")[:10]
        if not day:
            continue
        if day <= target_date:
            best = bar
        else:
            break
    if best is None:
        return None
    return to_float(best.get("close"))


def _close_pair(
    code: str, prev_date: str, cur_date: str
) -> tuple[float | None, float | None, str]:
    """取上一次 / 本次报告期当日（或之前最近交易日）的前复权收盘价。"""
    pack = fetch_stock_day(code, beg=prev_date, end=cur_date)
    items = list(pack.get("items") or [])
    items.sort(key=lambda b: str(b.get("time") or ""))
    prev_close = _close_on_or_before(items, prev_date)
    cur_close = _close_on_or_before(items, cur_date)
    return prev_close, cur_close, str(pack.get("source") or "")


def _shares_of(items: list[dict[str, Any]]) -> dict[str, float]:
    """报告期十大股东 → {股东名称: 持股数}；忽略无持股数的记录。"""
    out: dict[str, float] = {}
    for item in items:
        name = safe_str(item.get("name"))
        shares = to_float(item.get("shares"))
        if not name or shares is None:
            continue
        # 同名保留较大值（个别源会拆多行）
        if name in out and out[name] >= shares:
            continue
        out[name] = shares
    return out


def _analyze(
    code: str,
    name: str,
    *,
    scope: str,
    keywords: tuple[str, ...],
    force: bool,
) -> dict[str, Any]:
    """对单只股票做一遍「社保养老增持 + 股价回落」判定。"""
    base = {"code": code, "name": name}

    cur = fetch_top_holders(code, scope=scope, force=force)
    label = safe_str(cur.get("name")) or name
    base["name"] = label
    if _is_st(label):
        return {**base, "skipped": "st"}

    cur_items = list(cur.get("items") or [])
    cur_date = safe_str(cur.get("report_date"))
    dates = [safe_str(d) for d in (cur.get("report_dates") or []) if safe_str(d)]

    cur_hits = [it for it in cur_items if _match_keyword(it.get("name"), keywords)]
    if not cur_hits:
        return {**base, "report_date": cur_date, "skipped": "no_holder"}
    if len(dates) < 2:
        return {**base, "report_date": cur_date, "skipped": "no_prev"}

    prev_date = dates[1]
    prev = fetch_top_holders(code, report_date=prev_date, scope=scope, force=force)
    prev_map = _shares_of(list(prev.get("items") or []))

    increases: list[dict[str, Any]] = []
    for it in cur_hits:
        holder = safe_str(it.get("name"))
        cur_sh = to_float(it.get("shares"))
        if cur_sh is None:
            continue
        prev_sh = prev_map.get(holder, 0.0)
        if cur_sh > prev_sh:
            increases.append(
                {
                    "holder": holder,
                    "cur_shares": cur_sh,
                    "prev_shares": prev_sh,
                    "delta": cur_sh - prev_sh,
                    "is_new": holder not in prev_map,
                    "ratio_fmt": safe_str(it.get("ratio_fmt")),
                }
            )

    info = {
        "report_date": cur_date,
        "prev_report_date": prev_date,
        "holder_count": len(cur_hits),
    }
    if not increases:
        return {**base, **info, "skipped": "no_increase"}

    prev_close, cur_close, source = _close_pair(code, prev_date, cur_date)
    info.update(
        {
            "prev_close": prev_close,
            "cur_close": cur_close,
            "price_source": source,
        }
    )
    if prev_close is None or cur_close is None:
        return {**base, **info, "skipped": "no_price"}

    # 要求：上一次收盘 > 本次收盘（价格回落）
    if not (prev_close > cur_close):
        return {**base, **info, "skipped": "price_up"}

    price_drop_pct = (cur_close / prev_close - 1.0) * 100 if prev_close else None
    return {
        **base,
        **info,
        "matched": True,
        "increases": increases,
        "price_drop_pct": price_drop_pct,
    }


def _scan(
    candidates: list[dict[str, str]],
    *,
    scope: str,
    keywords: tuple[str, ...],
    force: bool,
    workers: int,
) -> list[dict[str, Any]]:
    total = len(candidates)
    done = 0
    matched = 0
    skipped = 0
    failed = 0
    results: list[dict[str, Any]] = []
    t0 = time.time()

    def one(item: dict[str, str]) -> dict[str, Any]:
        return _analyze(
            item["code"],
            item.get("name") or "",
            scope=scope,
            keywords=keywords,
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
                _log(f"  ! 任务失败: {exc}")
                continue

            code = safe_str(row.get("code"))
            name = (safe_str(row.get("name")) or "")[:10]
            if row.get("skipped"):
                skipped += 1
                _log(f"  [{done}/{total}] {code} {name} · 跳过({row['skipped']})")
            elif row.get("matched"):
                matched += 1
                results.append(row)
                _log_hit(row, prefix=f"  [{done}/{total}] ")
            else:
                failed += 1
                _log(f"  [{done}/{total}] ! {code} {name} 无结果")

            if done % 50 == 0 or done == total:
                elapsed = time.time() - t0
                _log(
                    f"  -- 进度 {done}/{total} · 命中 {matched} · 跳过 {skipped} "
                    f"· 失败 {failed} · {elapsed:.0f}s --"
                )

    return results


def _log_hit(row: dict[str, Any], *, prefix: str = "") -> None:
    code = safe_str(row.get("code"))
    name = (safe_str(row.get("name")) or "")[:10]
    prev_close = row.get("prev_close")
    cur_close = row.get("cur_close")
    drop = row.get("price_drop_pct")
    drop_s = fmt_pct(drop) if drop is not None else "-"
    holders = row.get("increases") or []
    holder_s = "；".join(
        f"{h['holder']} {fmt_shares(h['prev_shares'])}→{fmt_shares(h['cur_shares'])}"
        + ("(新进)" if h.get("is_new") else "")
        for h in holders
    )
    _log(
        f"{prefix}★ {code} {name} · "
        f"{row.get('prev_report_date')}→{row.get('report_date')} · "
        f"收盘 {prev_close}→{cur_close}（{drop_s}）· {holder_s}"
    )


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
        description="全市场社保/养老增持 + 股价回落扫描 → 写入「我的」分组",
    )
    parser.add_argument("--group", default=DEFAULT_GROUP, help=f"写入分组名（默认 {DEFAULT_GROUP}）")
    parser.add_argument("--workers", type=int, default=DEFAULT_WORKERS, help="并发数")
    parser.add_argument(
        "--scope",
        default=DEFAULT_SCOPE,
        choices=("holders", "free"),
        help="holders 十大股东（默认） | free 十大流通股东",
    )
    parser.add_argument(
        "--keywords",
        default=",".join(DEFAULT_KEYWORDS),
        help=f"股东名称关键词，逗号分隔（默认 {'/'.join(DEFAULT_KEYWORDS)}）",
    )
    parser.add_argument(
        "--codes",
        default="",
        help="只扫描这些代码（逗号分隔）；省略则从股票索引取全市场（已滤创业板/ST）",
    )
    parser.add_argument("--max-scan", type=int, default=0, help="最多扫描多少只（0=不限制）")
    parser.add_argument("--force", action="store_true", help="强制刷新东财十大股东缓存（更慢）")
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

    keywords = _parse_keywords(args.keywords)
    scope = safe_str(args.scope) or DEFAULT_SCOPE

    if safe_str(args.codes):
        candidates = _parse_codes(args.codes)
        _log(f"候选来自 --codes：{len(candidates)} 只")
    else:
        candidates = _load_index_candidates()
        _log(f"候选来自股票索引（已滤创业板/ST）：{len(candidates)} 只")

    if args.max_scan and args.max_scan > 0:
        candidates = candidates[: int(args.max_scan)]
        _log(f"截断为前 {len(candidates)} 只")

    if not candidates:
        _log("没有可扫描的候选股票")
        return 1

    _log(
        f"开始扫描 · 口径={scope} · 关键词={'/'.join(keywords)} · "
        f"force={bool(args.force)} · workers={args.workers}"
        + (" · dry-run" if args.dry_run else "")
        + ("" if args.dry_run else f" · replace={bool(args.replace)}")
    )

    hits = _scan(
        candidates,
        scope=scope,
        keywords=keywords,
        force=bool(args.force),
        workers=int(args.workers),
    )

    # 命中按回撤幅度降序（跌得多的在前），同幅度按代码升序
    hits.sort(
        key=lambda r: (
            float(r.get("price_drop_pct") or 0.0),
            safe_str(r.get("code")),
        )
    )
    elapsed = time.time() - started

    _log("")
    _log(f"=== 命中 {len(hits)} 只（社保/养老增持 + 股价回落）===")
    for i, row in enumerate(hits, start=1):
        code = safe_str(row.get("code"))
        name = (safe_str(row.get("name")) or "")[:10]
        drop = row.get("price_drop_pct")
        drop_s = fmt_pct(drop) if drop is not None else "-"
        holders = "；".join(
            f"{h['holder']} {fmt_shares(h['prev_shares'])}→{fmt_shares(h['cur_shares'])}"
            + ("(新进)" if h.get("is_new") else "")
            for h in (row.get("increases") or [])
        )
        _log(
            f"{i:4d}  {code} {name:<10}  "
            f"{row.get('prev_report_date')}→{row.get('report_date')}  "
            f"收盘 {row.get('prev_close')}→{row.get('cur_close')}（{drop_s}）  {holders}"
        )
    _log(f"\n扫描完成（耗时 {elapsed:.1f}s）：命中 {len(hits)} 只")

    group_name = safe_str(args.group) or DEFAULT_GROUP
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
            "scope": scope,
            "keywords": list(keywords),
            "candidates": len(candidates),
            "matched": len(hits),
            "elapsed_sec": round(elapsed, 1),
            "exclude": ["创业板(300/301)", "ST"],
            "rule": "上次报告期收盘 > 本次报告期收盘 且 社保/养老股东持股数量增加",
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
