"""全市场「历史低位」扫描：最近一个交易日最低价 → 上一个更低交易日的间隔。

对每只股票（默认排除创业板 300/301 与 ST/*ST）：
  - 取最近一个交易日（日线最后一根）的最低价 low；
  - 向前回溯最近一个严格更低的 low 所在交易日；
  - 计算两者之间间隔的交易日数（sessions）；
  - 未找到更低交易日（上市以来未见更低）的股票不算在内。

先打印每只股票的结果，再把间隔数最大的 N 只（默认 100）写入「我的」分组
（默认分组名「历史低位」）。

用法（项目根目录）::

    .venv\\Scripts\\python.exe scripts/history_low_gap.py
    .venv\\Scripts\\python.exe scripts/history_low_gap.py --top 100 --workers 8
    .venv\\Scripts\\python.exe scripts/history_low_gap.py --codes 000333,600519 --dry-run
    .venv\\Scripts\\python.exe scripts/history_low_gap.py --group 历史低位 --no-replace
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Any

_SCRIPT = Path(__file__).resolve()
_ROOT = _SCRIPT.parents[1]
_BACKEND = _ROOT / "backend"
for path in (_BACKEND, _ROOT):
    text = str(path)
    if text not in sys.path:
        sys.path.insert(0, text)

from company.analysis.line.extremum.service import analyze_extremum  # noqa: E402
from core.codes import normalize_code, safe_str  # noqa: E402
from core.fmt import to_float  # noqa: E402
from core.paths import STOCK_INDEX_CACHE  # noqa: E402
from mine.service import service as mine_service  # noqa: E402

_print_lock = threading.Lock()

DEFAULT_GROUP = "历史低位"
DEFAULT_TOP = 100
DEFAULT_WORKERS = 6
MAX_STOCKS_PER_GROUP = 1000


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


def _compute(code: str, name: str, today: str) -> dict[str, Any]:
    try:
        pack = analyze_extremum(code, today)
    except Exception as exc:  # noqa: BLE001
        return {
            "code": code,
            "name": name,
            "found": False,
            "sessions": None,
            "error": str(exc),
        }

    label = safe_str(pack.get("name")) or name
    if _is_st(label):
        return {
            "code": code,
            "name": label,
            "found": False,
            "sessions": None,
            "skipped": "st",
        }

    low = (pack.get("extremum") or {}).get("low") or {}
    prior_date = low.get("date")
    sessions = low.get("sessions")
    if prior_date is None or sessions is None:
        # 上市以来未见更低（或数据不足）：不算在内
        return {
            "code": code,
            "name": label,
            "found": False,
            "sessions": None,
            "target_date": safe_str(pack.get("date")),
            "target_low": to_float((pack.get("prices") or {}).get("low")),
            "no_prior_lower": True,
        }

    return {
        "code": code,
        "name": label,
        "found": True,
        "sessions": int(sessions),
        "gap": low.get("gap"),
        "target_date": safe_str(pack.get("date")),
        "target_low": to_float(low.get("target_price")),
        "prior_date": safe_str(prior_date),
        "prior_low": to_float(low.get("found_price")),
    }


def _scan(
    candidates: list[dict[str, str]],
    *,
    today: str,
    workers: int,
) -> list[dict[str, Any]]:
    total = len(candidates)
    done = 0
    found = 0
    not_found = 0
    failed = 0
    skipped = 0
    results: list[dict[str, Any]] = []
    t0 = time.time()

    def one(item: dict[str, str]) -> dict[str, Any]:
        return _compute(item["code"], item.get("name") or "", today)

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
            if row.get("skipped") == "st":
                skipped += 1
                _log(f"  [{done}/{total}] 跳过 ST {code} {name}")
                continue
            if row.get("error"):
                failed += 1
                _log(f"  [{done}/{total}] ! {code} {name} 失败: {row['error']}")
                continue
            if not row.get("found"):
                not_found += 1
                if row.get("no_prior_lower"):
                    _log(
                        f"  [{done}/{total}] {code} {name} → 未找到更低交易日（不算）"
                    )
                else:
                    _log(f"  [{done}/{total}] {code} {name} → 无结果（不算）")
            else:
                found += 1
                results.append(row)
                sess = row.get("sessions")
                _log(
                    f"  [{done}/{total}] {code} {name} → 间隔 {sess} 个交易日 "
                    f"（{row.get('target_date')} 低点 {row.get('target_low')} "
                    f"← {row.get('prior_date')} {row.get('prior_low')}）"
                )

            if done % 50 == 0 or done == total:
                elapsed = time.time() - t0
                _log(
                    f"  -- 进度 {done}/{total} · 找到 {found} · 未找到 {not_found} "
                    f"· ST跳过 {skipped} · 失败 {failed} · {elapsed:.0f}s --"
                )

    return results


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
            f"按间隔保留前 {MAX_STOCKS_PER_GROUP} 只"
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
        description="最近交易日最低价 → 上一个更低交易日间隔 Top 写入「我的」分组",
    )
    parser.add_argument("--group", default=DEFAULT_GROUP, help=f"写入分组名（默认 {DEFAULT_GROUP}）")
    parser.add_argument("--top", type=int, default=DEFAULT_TOP, help=f"写入只数（默认 {DEFAULT_TOP}）")
    parser.add_argument("--workers", type=int, default=DEFAULT_WORKERS, help="并发数")
    parser.add_argument("--today", default="", help="结束日 YYYYMMDD / YYYY-MM-DD；空=今天")
    parser.add_argument("--codes", default="", help="只扫描这些代码（逗号分隔）")
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

    today_raw = (args.today or "").strip()
    if today_raw:
        today = today_raw
    else:
        today = datetime.now().strftime("%Y%m%d")

    if safe_str(args.codes):
        candidates = _parse_codes(args.codes)
        _log(f"候选来自 --codes：{len(candidates)} 只")
    else:
        candidates = _load_index_candidates()
        _log(f"候选来自股票索引（已滤创业板/ST）：{len(candidates)} 只")

    if not candidates:
        _log("没有可扫描的候选股票")
        return 1

    _log(f"开始扫描 · 截止日={today} · workers={args.workers}" + (" · dry-run" if args.dry_run else ""))

    results = _scan(candidates, today=today, workers=int(args.workers))

    # 间隔数降序；相同间隔按代码升序
    results.sort(key=lambda r: (-int(r.get("sessions") or 0), safe_str(r.get("code"))))
    top_n = max(1, int(args.top))
    top_rows = results[:top_n]

    elapsed = time.time() - started
    _log("")
    _log(f"=== 找到 {len(results)} 只有更低前低的股票 · 取间隔最大的 {len(top_rows)} 只 ===")
    for i, row in enumerate(top_rows, start=1):
        _log(
            f"{i:4d}  {row.get('code')} {(row.get('name') or '')[:10]:<10}  "
            f"间隔 {row.get('sessions')} 个交易日  "
            f"低点日 {row.get('target_date')} ({row.get('target_low')})  "
            f"前低日 {row.get('prior_date')} ({row.get('prior_low')})"
        )
    _log(f"\n扫描完成（耗时 {elapsed:.1f}s）：有效 {len(results)} · 输出 {len(top_rows)}")

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
            result = _write_mine_group(top_rows, group_name=group_name, replace=bool(args.replace))
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
            "today": today,
            "candidates": len(candidates),
            "found": len(results),
            "top": len(top_rows),
            "elapsed_sec": round(elapsed, 1),
            "exclude": ["创业板(300/301)", "ST"],
            "mine": mine_meta,
        },
        "items": top_rows,
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
