"""用公司详情「研判 → 财报简述」综合评分，按分数段写入「我的」分组。

评分来源：``company.analysis.financialreport.analyze`` 汇总里的 ``score_total``
（张新民八看综合诊断，满分 100）。

三个分组（默认名可改）：
- ≥90 → 「财报简述90+」
- 80≤分<90 → 「财报简述80-90」
- 70≤分<80 → 「财报简述70-80」

默认过滤创业板（代码 300/301）与 ST/*ST 股票；扫描过程打印进度。

用法（在项目根目录）::

    .venv\\Scripts\\python.exe scripts/financial_score_to_mine.py
    .venv\\Scripts\\python.exe scripts/financial_score_to_mine.py --report-type 年报
    .venv\\Scripts\\python.exe scripts/financial_score_to_mine.py --report-type 半年报
    .venv\\Scripts\\python.exe scripts/financial_score_to_mine.py --report-type semi --workers 4
    .venv\\Scripts\\python.exe scripts/financial_score_to_mine.py --dry-run
    .venv\\Scripts\\python.exe scripts/financial_score_to_mine.py --codes 000333,000651,600519
    .venv\\Scripts\\python.exe scripts/financial_score_to_mine.py --no-replace

``--report-type`` 可选：年报(annual) / 半年报(semi) / 一季报(q1) / 三季报(q3)，默认年报。
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

from company.analysis.financialreport import (  # noqa: E402
    analyze,
    normalize_report_type,
    report_type_label,
)
from core.codes import normalize_code, safe_str  # noqa: E402
from core.paths import STOCK_INDEX_CACHE  # noqa: E402
from mine.service import service as mine_service  # noqa: E402

GROUP_GE_90 = "财报简述90+"
GROUP_80_90 = "财报简述80-90"
GROUP_70_80 = "财报简述70-80"
MAX_STOCKS_PER_GROUP = 1000  # 与 mine.service 上限一致

BUCKETS = (
    ("ge90", 90, None, GROUP_GE_90),
    ("80_90", 80, 90, GROUP_80_90),
    ("70_80", 70, 80, GROUP_70_80),
)

_print_lock = threading.Lock()


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


def _bucket_for(score: float) -> str | None:
    if score >= 90:
        return "ge90"
    if score >= 80:
        return "80_90"
    if score >= 70:
        return "70_80"
    return None


def _bucket_label(
    key: str | None,
    group_names: dict[str, str] | None = None,
) -> str:
    names = group_names or {}
    for item_key, lo, hi, default_name in BUCKETS:
        if item_key == key:
            name = names.get(item_key) or default_name
            if hi is None:
                return f"≥{lo} → {name}"
            return f"{lo}≤分<{hi} → {name}"
    return "未入组"


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


def _evaluate(
    code: str,
    name: str,
    *,
    report_type: str,
    force: bool,
) -> dict[str, Any]:
    pack = analyze(code, report_type=report_type, name=name, force=force)
    summary = pack.get("summary") if isinstance(pack.get("summary"), dict) else {}
    score_raw = summary.get("score_total")
    try:
        score = float(score_raw) if score_raw is not None else None
    except (TypeError, ValueError):
        score = None
    label = safe_str(pack.get("name")) or name or ""
    return {
        "code": code,
        "name": label,
        "score": score,
        "data_available": bool(pack.get("data_available")),
        "report_type": safe_str(pack.get("report_type")) or report_type,
        "latest_period": safe_str(pack.get("latest_period")),
        "bucket": _bucket_for(score) if score is not None else None,
    }


def _scan(
    candidates: list[dict[str, str]],
    *,
    report_type: str,
    force: bool,
    workers: int,
    group_names: dict[str, str] | None = None,
) -> dict[str, list[dict[str, Any]]]:
    buckets: dict[str, list[dict[str, Any]]] = {key: [] for key, *_ in BUCKETS}
    total = len(candidates)
    done = 0
    failed = 0
    no_data = 0
    below = 0
    names = group_names or {}

    def one(item: dict[str, str]) -> dict[str, Any]:
        code = item["code"]
        name = item.get("name") or ""
        # --codes 可能未带名称，评分后再按简称滤 ST
        if name and _is_st(name):
            return {
                "code": code,
                "name": name,
                "score": None,
                "skipped": "st",
                "data_available": False,
                "bucket": None,
            }
        try:
            row = _evaluate(code, name, report_type=report_type, force=force)
        except Exception as exc:  # noqa: BLE001
            return {
                "code": code,
                "name": name,
                "score": None,
                "error": str(exc),
                "data_available": False,
                "bucket": None,
            }
        label = safe_str(row.get("name")) or name
        if _is_st(label):
            row["name"] = label
            row["score"] = None
            row["bucket"] = None
            row["skipped"] = "st"
        return row

    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futures = [pool.submit(one, item) for item in candidates]
        for fut in as_completed(futures):
            done += 1
            try:
                row = fut.result()
            except Exception as exc:  # noqa: BLE001
                failed += 1
                _log(f"  ! 任务失败: {exc}")
                row = None

            if row is not None:
                code = safe_str(row.get("code"))
                name = safe_str(row.get("name"))
                if row.get("skipped") == "st":
                    _log(f"  [{done}/{total}] 跳过 ST {code} {name}")
                elif row.get("error"):
                    failed += 1
                    _log(f"  [{done}/{total}] ! {code} {name} 失败: {row['error']}")
                elif not row.get("data_available") or row.get("score") is None:
                    no_data += 1
                    _log(f"  [{done}/{total}] {code} {name} → 无财报数据")
                else:
                    score = float(row["score"])
                    bucket = row.get("bucket")
                    if bucket:
                        buckets[bucket].append(row)
                        _log(
                            f"  [{done}/{total}] ★ {code} {name} → {score:.0f} "
                            f"· {_bucket_label(bucket, names)}"
                        )
                    else:
                        below += 1
                        _log(f"  [{done}/{total}] {code} {name} → {score:.0f} · 未入组")

            if done % 25 == 0 or done == total:
                hit_n = sum(len(v) for v in buckets.values())
                pct = (done / total * 100) if total else 100.0
                _log(
                    f"  …进度 {done}/{total} ({pct:.1f}%) · "
                    f"≥90:{len(buckets['ge90'])} · 80-90:{len(buckets['80_90'])} · "
                    f"70-80:{len(buckets['70_80'])} · 未入组:{below} · "
                    f"无数据:{no_data} · 失败:{failed} · 入组合计:{hit_n}"
                )

    for key in buckets:
        buckets[key].sort(
            key=lambda r: (-float(r.get("score") or 0), safe_str(r.get("code")))
        )
    return buckets


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
            f"按分数保留前 {MAX_STOCKS_PER_GROUP} 只"
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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="财报简述综合评分 → 按分数段写入「我的」分组",
    )
    parser.add_argument("--group-ge90", default=GROUP_GE_90, help=f"≥90 分组名（默认 {GROUP_GE_90}）")
    parser.add_argument("--group-80-90", default=GROUP_80_90, help=f"80-90 分组名（默认 {GROUP_80_90}）")
    parser.add_argument("--group-70-80", default=GROUP_70_80, help=f"70-80 分组名（默认 {GROUP_70_80}）")
    parser.add_argument(
        "--codes",
        default="",
        help="只扫描这些代码（逗号分隔）；省略则从股票索引取全市场（已滤创业板/ST）",
    )
    parser.add_argument(
        "--report-type",
        default="annual",
        metavar="TYPE",
        help=(
            "财报口径：年报(annual) / 半年报(semi|中报) / 一季报(q1) / 三季报(q3)；"
            "中英文均可，默认年报"
        ),
    )
    parser.add_argument("--max-scan", type=int, default=0, help="最多扫描多少只（0=不限制）")
    parser.add_argument("--workers", type=int, default=4, help="并发数（默认 4）")
    parser.add_argument("--force", action="store_true", help="强制刷新东财财报缓存（更慢）")
    parser.add_argument(
        "--replace",
        dest="replace",
        action="store_true",
        default=True,
        help="写入前清空三个目标分组（默认开启）",
    )
    parser.add_argument(
        "--no-replace",
        dest="replace",
        action="store_false",
        help="不清空，只追加未在组内的股票",
    )
    parser.add_argument("--dry-run", action="store_true", help="只打印结果，不写入分组")
    return parser


def main(argv: list[str] | None = None) -> int:
    _configure_stdio()
    args = build_parser().parse_args(argv)
    started = time.time()

    try:
        report_type = normalize_report_type(safe_str(args.report_type) or "annual")
    except ValueError as exc:
        _log(f"参数错误: {exc}")
        return 2
    report_label = report_type_label(report_type)

    group_names = {
        "ge90": safe_str(args.group_ge90) or GROUP_GE_90,
        "80_90": safe_str(args.group_80_90) or GROUP_80_90,
        "70_80": safe_str(args.group_70_80) or GROUP_70_80,
    }

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
        f"开始评分 · 口径={report_label}({report_type}) · force={bool(args.force)} · "
        f"workers={args.workers}"
        + (" · dry-run" if args.dry_run else "")
        + ("" if args.dry_run else f" · replace={bool(args.replace)}")
    )
    _log(
        f"目标分组：≥90「{group_names['ge90']}」 / "
        f"80-90「{group_names['80_90']}」 / 70-80「{group_names['70_80']}」"
    )

    buckets = _scan(
        candidates,
        report_type=report_type,
        force=bool(args.force),
        workers=int(args.workers),
        group_names=group_names,
    )

    elapsed = time.time() - started
    _log(f"\n扫描完成（耗时 {elapsed:.1f}s）")
    for key, lo, hi, _default_name in BUCKETS:
        rows = buckets[key]
        band = f"≥{lo}" if hi is None else f"{lo}≤分<{hi}"
        _log(f"  {band} → 「{group_names[key]}」：{len(rows)} 只")
        for row in rows[:20]:
            _log(f"    {row.get('code')} {row.get('name')} · {float(row.get('score') or 0):.0f}")
        if len(rows) > 20:
            _log(f"    …另有 {len(rows) - 20} 只")

    if args.dry_run:
        _log("[dry-run] 跳过写入分组")
        return 0

    for key, _lo, _hi, _default_name in BUCKETS:
        name = group_names[key]
        hits = buckets[key]
        group = _ensure_group(name)
        gid = safe_str(group.get("id"))
        if args.replace:
            removed = _clear_group(gid)
            if removed:
                _log(f"分组「{name}」已清空 {removed} 只")
        if not hits:
            _log(f"分组「{name}」无命中，跳过写入")
            continue
        result = _add_to_group(gid, hits)
        added = result.get("added") or []
        skipped = result.get("skipped") or []
        final = result.get("group") or group
        _log(
            f"分组「{final.get('name')}」({final.get('id')}) "
            f"现有 {final.get('count')} 只 · 新加 {len(added)} · 已存在跳过 {len(skipped)}"
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
