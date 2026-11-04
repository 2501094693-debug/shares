"""全市场股息率>阈值扫描，命中写入「我的」分组。

对股票索引里的每只股票（默认排除科创板 688/689、创业板 300/301、
ST/*ST、名称含「退」的退市股）对照东财全市场列表的股息率（``f133``）：
  - 有效且 ``股息率 > 阈值``（默认 4）→ 命中；
  - 缺失、非正值均打印明细但不入组。

股息率来源：东财 push2 ``clist`` 全市场列表字段 ``f133``（单位 %）。

用法（项目根目录）::

    .venv\\Scripts\\python.exe scripts/dividend_yield_to_mine.py
    .venv\\Scripts\\python.exe scripts/dividend_yield_to_mine.py --min-yield 4 --group 股息率>4
    .venv\\Scripts\\python.exe scripts/dividend_yield_to_mine.py --codes 000001,601318 --dry-run
    .venv\\Scripts\\python.exe scripts/dividend_yield_to_mine.py --no-replace
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
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

from core.codes import normalize_code, safe_str  # noqa: E402
from core.fmt import to_float  # noqa: E402
from core.http import get_json  # noqa: E402
from core.paths import STOCK_INDEX_CACHE  # noqa: E402
from mine.service import service as mine_service  # noqa: E402

DEFAULT_GROUP = "股息率>4"
DEFAULT_MIN_YIELD = 4.0
MAX_STOCKS_PER_GROUP = 1000  # 与 mine.service 上限一致

# 创业板：深市 300 / 301；科创板：沪市 688 / 689
_CHINEXT_PREFIXES = ("300", "301")
_STAR_PREFIXES = ("688", "689")

_UT = "b2884a393a59ad64002292a3e90d46a5"
_FS = (
    "m:0+t:6+f:!2,m:0+t:13+f:!2,m:0+t:80+f:!2,"
    "m:1+t:2+f:!2,m:1+t:23+f:!2,m:0+t:7+f:!2,m:1+t:3+f:!2"
)
_FIELDS = "f12,f14,f2,f3,f133,f115,f23,f20"
_HEADERS = {
    "Referer": "https://quote.eastmoney.com/center/gridlist.html",
    "Accept": "application/json, text/plain, */*",
}
_PAGE = 200
_HOSTS = (
    "https://push2delay.eastmoney.com/api/qt/clist/get",
    "https://push2.eastmoney.com/api/qt/clist/get",
    "https://82.push2.eastmoney.com/api/qt/clist/get",
    "https://71.push2.eastmoney.com/api/qt/clist/get",
)
_WORKERS = 6


def _configure_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except Exception:  # noqa: BLE001
                pass


def _log(message: str) -> None:
    print(message, flush=True)


def _is_chinext(code: str) -> bool:
    return code.startswith(_CHINEXT_PREFIXES)


def _is_star(code: str) -> bool:
    return code.startswith(_STAR_PREFIXES)


def _is_st_or_delisted(name: str) -> bool:
    """ST / *ST / 退市整理等：名称含 ST 或「退」。"""
    text = safe_str(name).upper().replace(" ", "")
    return "ST" in text or "退" in text


def _is_a_share(code: str) -> bool:
    """只保留 A 股常见板块前缀，排除 B 股 200/900 等。"""
    return code.startswith(("60", "68", "00", "30", "8", "4", "92"))


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
    skipped_star = 0
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
        if _is_star(code):
            skipped_star += 1
            continue
        if _is_st_or_delisted(name):
            skipped_st += 1
            continue
        seen.add(code)
        out.append({"code": code, "name": name})

    out.sort(key=lambda item: item["code"])
    _log(
        f"索引过滤：跳过创业板 {skipped_cyb} · 科创板 {skipped_star} · "
        f"ST/退市 {skipped_st} · 剩余 {len(out)}"
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
        if _is_chinext(code):
            _log(f"  跳过创业板 {code}")
            continue
        if _is_star(code):
            _log(f"  跳过科创板 {code}")
            continue
        seen.add(code)
        out.append({"code": code, "name": ""})
    return out


def _fmt_num(value: Any, digits: int = 2) -> str:
    number = to_float(value)
    if number is None:
        return "—"
    return f"{number:.{digits}f}"


def _page(pn: int) -> dict[str, Any]:
    params = {
        "pn": str(pn),
        "pz": str(_PAGE),
        "po": "1",
        "np": "1",
        "fltt": "2",
        "invt": "2",
        "fid": "f133",
        "fs": _FS,
        "fields": _FIELDS,
        "ut": _UT,
    }
    last_error: Exception | None = None
    for round_i in range(2):
        for url in _HOSTS:
            try:
                payload = get_json(
                    url,
                    params=params,
                    headers=_HEADERS,
                    timeout=(3, 12),
                    retries=0,
                )
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                continue
            data = payload.get("data") if isinstance(payload, dict) else None
            if isinstance(data, dict):
                return payload
            last_error = RuntimeError("东财股息率列表返回非 JSON")
        time.sleep(0.4 * (round_i + 1))
    raise RuntimeError(f"东财股息率列表失败: {last_error}")


def _rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    data = payload.get("data") or {}
    diff = data.get("diff") or []
    if isinstance(diff, dict):
        diff = list(diff.values())
    return [item for item in diff if isinstance(item, dict)]


def fetch_dividend_yields() -> dict[str, dict[str, Any]]:
    """股票短码 → 股息率 / 现价 / 涨跌 / PE / PB。"""
    first = _page(1)
    data = first.get("data") or {}
    total = int(to_float(data.get("total")) or 0)
    first_rows = _rows(first)
    page_size = len(first_rows) or _PAGE
    pages = max(1, math.ceil(total / page_size)) if total else 1
    batches = [first_rows]

    if pages > 1:
        rest = list(range(2, pages + 1))
        by_pn: dict[int, list[dict[str, Any]]] = {}
        with ThreadPoolExecutor(max_workers=_WORKERS) as pool:
            futs = {pool.submit(_page, pn): pn for pn in rest}
            for fut in as_completed(futs):
                pn = futs[fut]
                try:
                    by_pn[pn] = _rows(fut.result())
                except Exception as exc:  # noqa: BLE001
                    _log(f"  东财股息率 pn={pn} 重试: {exc}")
                    time.sleep(0.6)
                    by_pn[pn] = _rows(_page(pn))
        for pn in rest:
            batches.append(by_pn[pn])

    out: dict[str, dict[str, Any]] = {}
    for batch in batches:
        for item in batch:
            code = str(item.get("f12") or "").strip()
            if not code:
                continue
            out[code] = {
                "code": code,
                "name": str(item.get("f14") or "").strip(),
                "price": to_float(item.get("f2")),
                "change_pct": to_float(item.get("f3")),
                "dividend_yield": to_float(item.get("f133")),
                "pe_ttm": to_float(item.get("f115")),
                "pb": to_float(item.get("f23")),
                "market_cap": to_float(item.get("f20")),
            }
    return out


def _scan(
    candidates: list[dict[str, str]],
    quotes: dict[str, dict[str, Any]],
    *,
    min_yield: float,
) -> list[dict[str, Any]]:
    total = len(candidates)
    hits: list[dict[str, Any]] = []
    hit_n = 0
    miss_n = 0
    no_dy_n = 0
    skipped_st = 0
    t0 = time.time()

    for i, item in enumerate(candidates, start=1):
        code = item["code"]
        name = safe_str(item.get("name"))
        quote = quotes.get(code) if isinstance(quotes.get(code), dict) else {}
        label = safe_str(quote.get("name")) or name or ""

        if _is_st_or_delisted(label):
            skipped_st += 1
            _log(f"  [{i}/{total}] 跳过 ST/退市 {code} {label}")
            continue

        dy = to_float(quote.get("dividend_yield"))
        price = to_float(quote.get("price"))
        change_pct = to_float(quote.get("change_pct"))
        pe = to_float(quote.get("pe_ttm"))
        pb = to_float(quote.get("pb"))

        detail = (
            f"股息率={_fmt_num(dy)}% · 现价={_fmt_num(price)} · "
            f"涨跌={_fmt_num(change_pct)}% · PE(TTM)={_fmt_num(pe)} · "
            f"PB={_fmt_num(pb)}"
        )

        if dy is None or dy <= 0:
            no_dy_n += 1
            _log(f"  [{i}/{total}] {code} {label} → 无有效股息率 · {detail}")
            continue

        if dy > min_yield:
            hit_n += 1
            row = {
                "code": code,
                "name": label,
                "dividend_yield": dy,
                "price": price,
                "change_pct": change_pct,
                "pe_ttm": pe,
                "pb": pb,
            }
            hits.append(row)
            _log(f"  [{i}/{total}] ★ 命中 {code} {label} → {detail}")
        else:
            miss_n += 1
            _log(f"  [{i}/{total}] {code} {label} → 未入组 · {detail}")

        if i % 50 == 0 or i == total:
            elapsed = time.time() - t0
            _log(
                f"  -- 进度 {i}/{total} · 命中 {hit_n} · 未入组 {miss_n} · "
                f"无股息率 {no_dy_n} · ST跳过 {skipped_st} · "
                f"{elapsed:.0f}s --"
            )

    hits.sort(
        key=lambda r: (-float(r.get("dividend_yield") or 0), safe_str(r.get("code")))
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
            f"按股息率保留前 {MAX_STOCKS_PER_GROUP} 只"
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
        description="股息率>阈值 → 写入「我的」分组（排除科创/创业板/ST/退市）",
    )
    parser.add_argument(
        "--group",
        default=DEFAULT_GROUP,
        help=f"写入分组名（默认 {DEFAULT_GROUP}）",
    )
    parser.add_argument(
        "--min-yield",
        type=float,
        default=DEFAULT_MIN_YIELD,
        help=f"股息率下限（不含，默认 {DEFAULT_MIN_YIELD}）",
    )
    parser.add_argument("--codes", default="", help="只扫描这些代码（逗号分隔）")
    parser.add_argument("--max-scan", type=int, default=0, help="最多扫描多少只（0=不限制）")
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
    return parser


def main(argv: list[str] | None = None) -> int:
    _configure_stdio()
    args = build_parser().parse_args(argv)
    started = time.time()

    min_yield = float(args.min_yield)
    if min_yield < 0:
        _log("参数错误：--min-yield 必须 ≥ 0")
        return 2

    if safe_str(args.codes):
        candidates = _parse_codes(args.codes)
        _log(f"候选来自 --codes：{len(candidates)} 只")
    else:
        candidates = _load_index_candidates()
        _log(f"候选来自股票索引（已滤科创/创业板/ST/退市）：{len(candidates)} 只")

    if args.max_scan and args.max_scan > 0:
        candidates = candidates[: int(args.max_scan)]
        _log(f"截断为前 {len(candidates)} 只")

    if not candidates:
        _log("没有可扫描的候选股票")
        return 1

    _log("拉取东财全市场股息率…")
    quotes = fetch_dividend_yields() or {}
    _log(f"股息率列表就绪：{len(quotes)} 只")

    group_name = safe_str(args.group) or DEFAULT_GROUP
    _log(
        f"开始逐个筛选 · 股息率>{min_yield:g}% · 分组「{group_name}」"
        + (" · dry-run" if args.dry_run else f" · replace={bool(args.replace)}")
    )

    hits = _scan(candidates, quotes, min_yield=min_yield)

    elapsed = time.time() - started
    _log(f"\n扫描完成（耗时 {elapsed:.1f}s）· 命中 {len(hits)} 只")
    for row in hits:
        _log(
            f"  {row.get('code')} {row.get('name')} · "
            f"股息率={_fmt_num(row.get('dividend_yield'))}% · "
            f"现价={_fmt_num(row.get('price'))} · "
            f"涨跌={_fmt_num(row.get('change_pct'))}% · "
            f"PE(TTM)={_fmt_num(row.get('pe_ttm'))} · "
            f"PB={_fmt_num(row.get('pb'))}"
        )

    if args.dry_run:
        _log("[dry-run] 跳过写入分组")
        return 0

    _write_mine_group(hits, group_name=group_name, replace=bool(args.replace))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
