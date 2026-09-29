"""用巴菲特规则引擎筛全部「优秀」生意，并写入分组「优秀生意」。

在项目根目录运行::

    .venv\\Scripts\\python.exe backend/scripts/buffett_excellent_to_mine.py

默认扫描股票索引里的全部股票，引擎给出 ``business_type=优秀`` 的会加入「我的 → 优秀生意」
（分组不存在则新建；已在组内的会跳过）。全市场大约半小时，可随时 Ctrl+C。

其它用法::

    .venv\\Scripts\\python.exe backend/scripts/buffett_excellent_to_mine.py --dry-run
    .venv\\Scripts\\python.exe backend/scripts/buffett_excellent_to_mine.py --min-roe 15
    .venv\\Scripts\\python.exe backend/scripts/buffett_excellent_to_mine.py --codes 000333,000651
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
_BACKEND = _SCRIPT.parents[1]
_ROOT = _SCRIPT.parents[2]
for path in (_BACKEND, _ROOT):
    text = str(path)
    if text not in sys.path:
        sys.path.insert(0, text)

from agent.buffett_analyst.rules import run_buffett_analysis  # noqa: E402
from agent.buffett_rules_service import public_buffett_rules  # noqa: E402
from agent.tools.financials import fetch_statement_frames  # noqa: E402
from core.codes import normalize_code, safe_str  # noqa: E402
from core.paths import STOCK_INDEX_CACHE  # noqa: E402
from mine.service import service as mine_service  # noqa: E402

DEFAULT_GROUP = "优秀生意"
TARGET_TYPE = "优秀"
DEFAULT_MIN_ROE = 0.0  # 0=扫描索引全部，不按 ROE 预筛
DEFAULT_OUT = "backend/cache/buffett_excellent.json"
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


def _parse_roe(raw: Any) -> float | None:
    text = safe_str(raw).replace("%", "").replace(",", "").strip()
    if not text or text in {"—", "-", "nan", "None"}:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _load_index_candidates(*, min_roe: float) -> list[dict[str, str]]:
    if not STOCK_INDEX_CACHE.is_file():
        raise FileNotFoundError(f"缺少股票索引: {STOCK_INDEX_CACHE}")
    payload = json.loads(STOCK_INDEX_CACHE.read_text(encoding="utf-8"))
    rows = payload.get("stocks") if isinstance(payload, dict) else payload
    if not isinstance(rows, list):
        raise ValueError("stocks_index.json 格式异常")

    out: list[dict[str, str]] = []
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        code = normalize_code(safe_str(row.get("code")))
        if not code or code in seen:
            continue
        roe = _parse_roe(row.get("roe"))
        # 索引 ROE 缺失仍送进引擎，避免漏掉「优秀」
        if min_roe > 0 and roe is not None and roe < min_roe:
            continue
        seen.add(code)
        out.append(
            {
                "code": code,
                "name": safe_str(row.get("name")),
                "roe": f"{roe:.2f}" if roe is not None else "",
            }
        )

    out.sort(
        key=lambda item: float(item["roe"]) if item["roe"] else -1e9,
        reverse=True,
    )
    return out


def _parse_codes(raw: str) -> list[dict[str, str]]:
    parts = re.split(r"[,，\s;；|]+", safe_str(raw))
    out: list[dict[str, str]] = []
    seen: set[str] = set()
    for part in parts:
        code = normalize_code(part)
        if not code or code in seen:
            continue
        seen.add(code)
        out.append({"code": code, "name": ""})
    return out


def _evaluate(code: str, name: str, *, force: bool) -> dict[str, Any]:
    fin = fetch_statement_frames(code, limit=60, force=force)
    annual = fin.get("annual") or []
    recent = fin.get("recent") or []
    merged = fin.get("merged") or []
    errors = list(fin.get("errors") or [])
    if not merged:
        errors.append("未能获取最新定期报告")
    engine = run_buffett_analysis(annual, recent, merged=merged)
    stock = {"code": code, "name": name or "", "market": ""}
    result = public_buffett_rules(stock=stock, engine=engine, errors=errors)
    if not result.get("stock_name") and name:
        result["stock_name"] = name
    return result


def _scan(
    candidates: list[dict[str, str]],
    *,
    force: bool,
    workers: int,
    limit: int,
) -> list[dict[str, Any]]:
    hits: list[dict[str, Any]] = []
    stop = threading.Event()
    total = len(candidates)
    done = 0

    def one(item: dict[str, str]) -> dict[str, Any] | None:
        if stop.is_set():
            return None
        code = item["code"]
        name = item.get("name") or ""
        try:
            result = _evaluate(code, name, force=force)
        except Exception as exc:  # noqa: BLE001
            _log(f"  ! {code} {name or ''} 失败: {exc}")
            return None
        btype = safe_str(result.get("business_type")) or "未知"
        reason = safe_str(result.get("business_reason"))
        label = result.get("stock_name") or name or ""
        mark = "★" if btype == TARGET_TYPE else " "
        _log(f"  {mark} {code} {label} → {btype}" + (f" · {reason}" if reason else ""))
        if btype == TARGET_TYPE:
            return result
        return None

    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futures = [pool.submit(one, item) for item in candidates]
        for fut in as_completed(futures):
            done += 1
            try:
                hit = fut.result()
            except Exception as exc:  # noqa: BLE001
                _log(f"  ! 任务失败: {exc}")
                hit = None
            if hit:
                hits.append(hit)
                if limit > 0 and len(hits) >= limit:
                    stop.set()
                    for pending in futures:
                        pending.cancel()
                    break
            if done % 25 == 0 or done == total:
                _log(f"  …进度 {done}/{total}，已命中{TARGET_TYPE} {len(hits)}")
    hits.sort(key=lambda row: safe_str(row.get("stock_code")))
    if limit > 0:
        hits = hits[:limit]
    return hits


def _ensure_group(name: str) -> dict[str, Any]:
    listed = mine_service.list_groups().get("groups") or []
    for group in listed:
        if safe_str(group.get("name")) == name:
            return mine_service.get_group(safe_str(group.get("id")))
    return mine_service.create_group(name)


def _add_to_group(group_id: str, hits: list[dict[str, Any]]) -> dict[str, Any]:
    codes = [safe_str(row.get("stock_code")) for row in hits if safe_str(row.get("stock_code"))]
    names = {
        safe_str(row.get("stock_code")): safe_str(row.get("stock_name"))
        for row in hits
        if safe_str(row.get("stock_code"))
    }
    return mine_service.add_stocks(group_id, codes, names=names)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="巴菲特规则引擎筛「优秀」股票，并写入「我的」分组",
    )
    parser.add_argument("--group", default=DEFAULT_GROUP, help=f"目标分组名（默认 {DEFAULT_GROUP}）")
    parser.add_argument(
        "--codes",
        default="",
        help="只扫描这些代码（逗号分隔）；省略则扫描股票索引",
    )
    parser.add_argument(
        "--min-roe",
        type=float,
        default=DEFAULT_MIN_ROE,
        help="索引预筛最低 ROE%%（默认 0=全市场；15=只扫索引高 ROE，更快但可能漏票）",
    )
    parser.add_argument(
        "--out",
        default=DEFAULT_OUT,
        help=f"命中名单 JSON（默认 {DEFAULT_OUT}；传空字符串则不写文件）",
    )
    parser.add_argument("--max-scan", type=int, default=0, help="最多扫描多少只候选（0=不限制）")
    parser.add_argument("--limit", type=int, default=0, help=f"最多收录多少只「{TARGET_TYPE}」（0=不限制）")
    parser.add_argument("--workers", type=int, default=4, help="并发数（默认 4）")
    parser.add_argument("--force", action="store_true", help="强制刷新东财财报（更慢）")
    parser.add_argument("--dry-run", action="store_true", help="只打印结果，不写入分组")
    return parser


def main(argv: list[str] | None = None) -> int:
    _configure_stdio()
    args = build_parser().parse_args(argv)
    started = time.time()

    if safe_str(args.codes):
        candidates = _parse_codes(args.codes)
        _log(f"候选来自 --codes：{len(candidates)} 只")
    else:
        candidates = _load_index_candidates(min_roe=float(args.min_roe))
        if float(args.min_roe) > 0:
            _log(
                f"候选来自股票索引（ROE≥{args.min_roe:g}% 或 ROE 缺失）：{len(candidates)} 只"
            )
        else:
            _log(f"候选来自股票索引（全市场）：{len(candidates)} 只")

    if args.max_scan and args.max_scan > 0:
        candidates = candidates[: int(args.max_scan)]
        _log(f"截断为前 {len(candidates)} 只")

    if not candidates:
        _log("没有可扫描的候选股票")
        return 1

    _log(
        f"开始扫描 · force={bool(args.force)} · workers={args.workers}"
        + (f" · limit={args.limit}" if args.limit else "")
        + (
            " · dry-run"
            if args.dry_run
            else f" · 命中写入分组「{safe_str(args.group) or DEFAULT_GROUP}」"
        )
    )
    hits = _scan(
        candidates,
        force=bool(args.force),
        workers=int(args.workers),
        limit=int(args.limit or 0),
    )
    _log(f"\n命中「{TARGET_TYPE}」{len(hits)} 只（耗时 {time.time() - started:.1f}s）")
    for row in hits:
        _log(
            f"  {row.get('stock_code')} {row.get('stock_name')}"
            f" · {row.get('business_reason') or ''}"
        )

    out_path = safe_str(args.out) if args.out is not None else DEFAULT_OUT
    if out_path:
        path = Path(out_path)
        if not path.is_absolute():
            path = _ROOT / path
        payload = [
            {
                "code": safe_str(row.get("stock_code")),
                "name": safe_str(row.get("stock_name")),
                "business_type": safe_str(row.get("business_type")),
                "business_reason": safe_str(row.get("business_reason")),
            }
            for row in hits
        ]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        _log(f"已写入 {path}")

    if not hits:
        _log(f"未找到{TARGET_TYPE}生意，分组未改动")
        return 0

    if args.dry_run:
        _log(f"[dry-run] 跳过写入分组「{args.group}」")
        return 0

    group = _ensure_group(safe_str(args.group) or DEFAULT_GROUP)
    result = _add_to_group(safe_str(group.get("id")), hits)
    added = result.get("added") or []
    skipped = result.get("skipped") or []
    final = result.get("group") or group
    _log(
        f"\n分组「{final.get('name')}」({final.get('id')}) "
        f"现有 {final.get('count')} 只 · 新加 {len(added)} · 已存在跳过 {len(skipped)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
