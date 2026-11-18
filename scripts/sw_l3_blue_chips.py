"""全市场申万三级行业「蓝筹股」扫描（逐行业输出，中文详细打印日志）。

判定口径
--------
遍历申万行业树里的每一个三级行业，读取该行业全部成分股，先按下面的
硬指标判定是否蓝筹，再按综合评分在行业内排序：

  硬指标（全部满足才算「严格蓝筹」，阈值均可用命令行调整/关闭）：
    1. 非 ST / *ST / 退市整理；
    2. 总市值 >= --min-cap（默认 100 亿元）—— 行业龙头规模；
    3. ROE   >= --min-roe（默认 8%）—— 盈利能力；
    4. 0 < PE_TTM <= --max-pe（默认 40）—— 估值合理且确实盈利；
    5. PB 合理：仅当 --max-pb > 0 时校验（默认关闭）；
    6. 股息率 >= --min-yield（默认 1%）—— 稳定现金分红。

  综合评分（0~100，仅用于行业内排序，不影响严格/相对判定）：
    市值 30 + ROE 30 + PE 15 + PB 10 + 股息率 15 + 净利润增速 10。

  未满足全部硬指标、但满足「非 ST 且 PE_TTM>0 且 ROE>0」的股票，作为
  「相对龙头（未达严格蓝筹）」一并打印，便于逐行业对照；加 --strict-only
  可让它们不进入最终结果。

数据来源（兼容本机 akshare 不可用的情况）
----------------------------------------
- 行业树：直接读 backend/cache/industry_tree.json 的 flat_l3；
- 成分股：直接读 backend/cache/cons/<行业代码>.json（6 小时 TTL）；
  缓存缺失/过期时用 requests + pandas 抓乐咕网页（不走 akshare）并回写缓存。
  缓存过期时会联网刷新；加 --offline 可强制只消费现有缓存（不联网）。
- 可选：加 --mine 把结果写入「我的」分组（默认关闭，仅打印 + JSON）。

用法（项目根目录）::

    python scripts/sw_l3_blue_chips.py
    python scripts/sw_l3_blue_chips.py --min-cap 200 --min-roe 10 --max-pe 30 --top-per-industry 5
    python scripts/sw_l3_blue_chips.py --codes 850111.SI,850112.SI --dry-run
    python scripts/sw_l3_blue_chips.py --offline --out scripts/blue_chips.json
    python scripts/sw_l3_blue_chips.py --force --top-per-industry 5
    python scripts/sw_l3_blue_chips.py --mine --group 申万三级蓝筹
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from io import StringIO
from pathlib import Path
from typing import Any

_SCRIPT = Path(__file__).resolve()
_ROOT = _SCRIPT.parents[1]
_BACKEND = _ROOT / "backend"
for path in (_BACKEND, _ROOT):
    text = str(path)
    if text not in sys.path:
        sys.path.insert(0, text)

import pandas as pd  # noqa: E402
import requests  # noqa: E402

from core.codes import normalize_code, safe_str  # noqa: E402
from core.fmt import to_float  # noqa: E402
from core.paths import (  # noqa: E402
    CONS_TTL,
    TREE_CACHE,
    cons_cache_path,
    ensure_cache_dirs,
)
from mine.service import service as mine_service  # noqa: E402

_print_lock = threading.Lock()

DEFAULT_GROUP = "申万三级行业蓝筹"
DEFAULT_WORKERS = 6
DEFAULT_MIN_CAP = 100.0
DEFAULT_MIN_ROE = 8.0
DEFAULT_MAX_PE = 40.0
DEFAULT_MAX_PB = 0.0  # 0 = 不校验
DEFAULT_MIN_YIELD = 1.0
DEFAULT_TOP_PER_INDUSTRY = 3

_CHINEXT_PREFIXES = ("300", "301")
_STAR_PREFIXES = ("688", "689")
_EMPTY_CELLS = frozenset({"nan", "None", "—", "-", "<NA>", "NaT", ""})

# 乐咕成分股表按列下标取值（见 backend/market/industry/stocks/cons_fetcher.py）
_COL_SPECS: list[tuple[int, str]] = [
    (1, "股票代码"),
    (2, "股票简称"),
    (3, "纳入时间"),
    (4, "申万3级"),
    (6, "价格"),
    (7, "市盈率"),
    (8, "市盈率ttm"),
    (9, "市净率"),
    (10, "ROE"),
    (11, "股息率"),
    (12, "市值"),
    (13, "近1日涨幅"),
    (14, "近5日涨幅"),
    (15, "今年以来涨幅"),
    (16, "净利润增速"),
    (17, "营收增速"),
]
_ROW_FIELDS = {
    "price": "价格",
    "pe": "市盈率",
    "pe_ttm": "市盈率ttm",
    "pb": "市净率",
    "roe": "ROE",
    "dividend_yield": "股息率",
    "market_cap": "市值",
    "change_1d": "近1日涨幅",
    "change_5d": "近5日涨幅",
    "change_ytd": "今年以来涨幅",
    "profit_growth": "净利润增速",
    "revenue_growth": "营收增速",
}
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    )
}


def _configure_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except Exception:  # noqa: BLE001
                pass


def _log(message: str = "") -> None:
    with _print_lock:
        print(message, flush=True)


def _is_st_or_delisted(name: str) -> bool:
    text = safe_str(name).upper().replace(" ", "")
    return "ST" in text or "退" in text


def _is_chinext(code: str) -> bool:
    return code.startswith(_CHINEXT_PREFIXES)


def _is_star(code: str) -> bool:
    return code.startswith(_STAR_PREFIXES)


def _num(value: Any) -> float | None:
    """通用数值：去千分位、去 %；市值列「63.76」按亿元原样返回。"""
    if value is None:
        return None
    if isinstance(value, str):
        value = value.replace(",", "").replace("%", "").strip()
        if value in _EMPTY_CELLS:
            return None
    return to_float(value)


def _fmt(value: float | None, suffix: str = "", digits: int = 2) -> str:
    if value is None:
        return "—"
    return f"{value:.{digits}f}{suffix}"


# ---------------------------------------------------------------------------
# 1. 行业树 / 成分股（直接读缓存，缺缓存走乐咕网页，不依赖 akshare）
# ---------------------------------------------------------------------------


def _load_tree(force_refresh: bool = False) -> list[dict[str, Any]]:
    if TREE_CACHE.is_file() and not force_refresh:
        payload = json.loads(TREE_CACHE.read_text(encoding="utf-8"))
        rows = payload.get("flat_l3") or []
        if not rows:
            raise RuntimeError(f"行业树缓存无三级行业: {TREE_CACHE}")
        _log(f"行业树读取成功：{len(rows)} 个申万三级行业（缓存 {TREE_CACHE.name}）")
        return [r for r in rows if isinstance(r, dict)]

    _log("行业树缓存缺失/需刷新，尝试通过 akshare 重建（需要 akshare 可正常 import）...")
    try:
        from market.industry.tree.builder import IndustryTree  # noqa: PLC0415

        IndustryTree().get_tree(force_refresh=True)
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(
            f"无法重建行业树（akshare 不可用？）: {exc}。"
            f"可先把有效的 {TREE_CACHE} 放回缓存目录再运行。"
        ) from exc
    payload = json.loads(TREE_CACHE.read_text(encoding="utf-8"))
    rows = [r for r in (payload.get("flat_l3") or []) if isinstance(r, dict)]
    _log(f"行业树重建完成：{len(rows)} 个申万三级行业")
    return rows


def _cell(row: dict[str, Any], key: str) -> str:
    value = row.get(key, "")
    if value is None:
        return ""
    if isinstance(value, float) and pd.isna(value):
        return ""
    text = str(value).strip()
    return "" if text in _EMPTY_CELLS else text


def _series_at(df: pd.DataFrame, idx: int) -> pd.Series:
    if df.shape[1] <= idx:
        return pd.Series([""] * len(df), index=df.index, dtype=object)
    series = df.iloc[:, idx].where(pd.notna(df.iloc[:, idx]), "")
    series = series.astype(str).str.strip()
    return series.map(lambda x: "" if x in _EMPTY_CELLS else x)


def _fetch_cons(l3_code: str) -> list[dict[str, Any]]:
    """抓乐咕三级行业成分股网页 → 规范化股票行。"""
    url = f"https://legulegu.com/stockdata/index-composition?industryCode={l3_code}"
    last_error: Exception | None = None
    for attempt in range(1, 3):
        try:
            resp = requests.get(url, headers=_HEADERS, timeout=(5, 45))
            resp.raise_for_status()
            df = pd.read_html(StringIO(resp.text))[0]
            if df.shape[1] < 4:
                raise ValueError(f"成分股表格列数异常: {df.shape[1]}")
            table = pd.DataFrame({name: _series_at(df, idx) for idx, name in _COL_SPECS})
            table = table[table["股票代码"].str.len() > 0]
            table = table[~table["股票代码"].isin(["nan", "None", "-"])]
            return table.reset_index(drop=True).to_dict("records")
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            if attempt < 2:
                time.sleep(1.0 * attempt)
    raise RuntimeError(f"抓取失败: {last_error}")


def _normalize(raw: dict[str, Any], meta: dict[str, Any]) -> dict[str, Any]:
    full = _cell(raw, "股票代码")
    row: dict[str, Any] = {
        "code": full.split(".")[0] if full else "",
        "full_code": full,
        "name": _cell(raw, "股票简称"),
        "include_date": _cell(raw, "纳入时间"),
        "l1_name": meta.get("l1_name", ""),
        "l2_name": meta.get("l2_name", ""),
        "l3_name": _cell(raw, "申万3级") or meta.get("name", ""),
        "l3_code": meta.get("code", ""),
    }
    for key, column in _ROW_FIELDS.items():
        row[key] = _cell(raw, column)
    return row


def _read_cons_cache(l3_code: str) -> dict[str, Any] | None:
    path = cons_cache_path(l3_code)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None
    return data if isinstance(data, dict) else None


def _load_constituents(
    meta: dict[str, Any], *, force: bool = False, offline: bool = False
) -> tuple[list[dict[str, Any]], str]:
    """返回 (股票列表, 来源标记 cache/fetch/stale)。失败抛异常。"""
    l3_code = safe_str(meta.get("code"))
    cached = _read_cons_cache(l3_code)
    age = time.time() - float((cached or {}).get("fetched_at") or 0)
    if cached and offline:
        return list(cached.get("stocks") or []), "cache(offline)"
    if cached and not force and age < CONS_TTL:
        return list(cached.get("stocks") or []), "cache"

    try:
        raw_rows = _fetch_cons(l3_code)
        stocks = [_normalize(r, meta) for r in raw_rows]
        ensure_cache_dirs()
        cons_cache_path(l3_code).write_text(
            json.dumps(
                {
                    "industry": meta,
                    "count": len(stocks),
                    "stocks": stocks,
                    "fetched_at": time.time(),
                    "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        return stocks, "fetch"
    except Exception as exc:  # noqa: BLE001
        if cached:
            return list(cached.get("stocks") or []), f"stale({exc})"
        raise


# ---------------------------------------------------------------------------
# 2. 蓝筹判定 / 评分
# ---------------------------------------------------------------------------


def _score(m: dict[str, float | None]) -> float:
    """综合评分 0~100：市值30 + ROE30 + PE15 + PB10 + 股息15 + 增速10。"""
    total = 0.0
    cap, roe = m["market_cap"], m["roe"]
    pe, pb = m["pe_ttm"], m["pb"]
    dy, growth = m["dividend_yield"], m["profit_growth"]
    if cap is not None and cap > 0:
        total += min(30.0, math.log10(cap + 1.0) / math.log10(2001.0) * 30.0)
    if roe is not None and roe > 0:
        total += min(30.0, roe / 20.0 * 30.0)
    if pe is not None and 0 < pe <= 60:
        total += 15.0 * (1.0 - pe / 60.0)
    if pb is not None and 0 < pb <= 10:
        total += 10.0 * (1.0 - pb / 10.0)
    if dy is not None and dy > 0:
        total += min(15.0, dy / 5.0 * 15.0)
    if growth is not None and growth > 0:
        total += min(10.0, growth / 30.0 * 10.0)
    return round(total, 1)


def _evaluate(
    stock: dict[str, Any],
    *,
    min_cap: float,
    min_roe: float,
    max_pe: float,
    max_pb: float,
    min_yield: float,
    exclude_chinext: bool,
    exclude_star: bool,
) -> dict[str, Any]:
    code = normalize_code(safe_str(stock.get("code")))
    name = safe_str(stock.get("name"))
    m: dict[str, float | None] = {key: _num(stock.get(key)) for key in _ROW_FIELDS}

    reasons: list[str] = []
    if _is_st_or_delisted(name):
        reasons.append("ST/退市")
    if exclude_chinext and _is_chinext(code):
        reasons.append("创业板")
    if exclude_star and _is_star(code):
        reasons.append("科创板")

    cap, roe = m["market_cap"], m["roe"]
    pe, pb = m["pe_ttm"], m["pb"]
    dy = m["dividend_yield"]

    if cap is None or cap < min_cap:
        reasons.append(f"市值<{min_cap:g}亿")
    if roe is None or roe < min_roe:
        reasons.append(f"ROE<{min_roe:g}%")
    if pe is None or pe <= 0:
        reasons.append("PE_TTM缺失/亏损")
    elif max_pe > 0 and pe > max_pe:
        reasons.append(f"PE>{max_pe:g}")
    if max_pb > 0 and (pb is None or pb <= 0 or pb > max_pb):
        reasons.append(f"PB越界(>{max_pb:g})")
    if min_yield > 0 and (dy is None or dy < min_yield):
        reasons.append(f"股息率<{min_yield:g}%")

    eligible = bool(code) and not any(
        r in reasons for r in ("ST/退市", "创业板", "科创板")
    )
    strict = not reasons
    # 相对龙头：非 ST/板块排除，且确实盈利（PE>0、ROE>0）
    relative = eligible and pe is not None and pe > 0 and roe is not None and roe > 0

    return {
        "code": code,
        "name": name,
        "metrics": m,
        "score": _score(m),
        "strict": strict,
        "relative": relative,
        "eligible": eligible,
        "reasons": reasons,
    }


def _scan_industry(
    meta: dict[str, Any], args: argparse.Namespace
) -> dict[str, Any]:
    l3_code = safe_str(meta.get("code"))
    l3_name = safe_str(meta.get("name"))
    base = {
        "l3_code": l3_code,
        "l3_name": l3_name,
        "l1_name": safe_str(meta.get("l1_name")),
        "l2_name": safe_str(meta.get("l2_name")),
    }
    try:
        stocks, source = _load_constituents(
            meta, force=bool(args.force), offline=bool(args.offline)
        )
    except Exception as exc:  # noqa: BLE001
        return {**base, "error": str(exc), "source": "error", "rows": []}

    rows = [
        _evaluate(
            s,
            min_cap=float(args.min_cap),
            min_roe=float(args.min_roe),
            max_pe=float(args.max_pe),
            max_pb=float(args.max_pb),
            min_yield=float(args.min_yield),
            exclude_chinext=bool(args.exclude_chinext),
            exclude_star=bool(args.exclude_star),
        )
        for s in stocks
    ]
    strict_rows = sorted(
        (r for r in rows if r["strict"]), key=lambda r: (-r["score"], r["code"])
    )
    relative_rows = sorted(
        (r for r in rows if r["relative"] and not r["strict"]),
        key=lambda r: (-r["score"], r["code"]),
    )
    top = max(0, int(args.top_per_industry))
    selected = [
        {**r, "tier": "严格蓝筹"}
        for r in (strict_rows[:top] if top else strict_rows)
    ]
    if not args.strict_only:
        need = (top - len(selected)) if top else 0
        if need > 0 or top == 0:
            selected += [
                {**r, "tier": "相对龙头（未达严格蓝筹）"}
                for r in (relative_rows[:need] if top else relative_rows)
            ]
    return {
        **base,
        "source": source,
        "total": len(rows),
        "strict_count": len(strict_rows),
        "relative_count": len(relative_rows),
        "selected": selected,
        "rows": rows,
    }


# ---------------------------------------------------------------------------
# 3. 详细日志
# ---------------------------------------------------------------------------


def _log_row(row: dict[str, Any], prefix: str = "    ") -> None:
    m = row["metrics"]
    flags = f"评分{row['score']:5.1f} · {row['tier']}"
    _log(
        f"{prefix}{row['code']} {(row['name'] or '')[:8]:<8}  "
        f"市值{_fmt(m['market_cap'], '亿', 1):>9}  ROE{_fmt(m['roe'], '%', 1):>7}  "
        f"PE{_fmt(m['pe_ttm'], '', 1):>7}  PB{_fmt(m['pb'], '', 1):>6}  "
        f"股息{_fmt(m['dividend_yield'], '%', 1):>6}  "
        f"增速{_fmt(m['profit_growth'], '%', 1):>7}  · {flags}"
    )


def _log_industry(result: dict[str, Any], idx: int, total: int) -> None:
    head = (
        f"[{idx:3d}/{total}] {result['l3_code']} {result['l3_name']} "
        f"（{result['l1_name']} / {result['l2_name']}）"
    )
    if result.get("error"):
        _log(f"{head} · 失败：{result['error']}")
        return
    _log(
        f"{head} · 成分股 {result['total']} · 严格蓝筹 {result['strict_count']} "
        f"· 相对龙头 {result['relative_count']} · 来源 {result['source']}"
    )
    if result["selected"]:
        for row in result["selected"]:
            _log_row(row)
    else:
        _log("    （无符合条件的蓝筹股）")

    rejected = [r for r in result["rows"] if not r["strict"] and not r["relative"]]
    if rejected:
        _log(f"    · 未入选 {len(rejected)} 只（原因）：")
        for r in rejected:
            reason = "、".join(r["reasons"]) or "未满足硬指标"
            _log(f"        {r['code']} {(r['name'] or '')[:8]:<8} → {reason}")


# ---------------------------------------------------------------------------
# 4. 写入「我的」分组（可选）
# ---------------------------------------------------------------------------


def _ensure_group(name: str) -> dict[str, Any]:
    for group in mine_service.list_groups().get("groups") or []:
        if safe_str(group.get("name")) == name:
            return mine_service.get_group(safe_str(group.get("id")))
    return mine_service.create_group(name)


def _write_mine_group(rows: list[dict[str, Any]], name: str, replace: bool) -> None:
    if not rows:
        _log(f"分组「{name}」无结果，跳过写入")
        return
    group = _ensure_group(name)
    gid = safe_str(group.get("id"))
    if replace:
        old = [
            normalize_code(safe_str(s.get("code")))
            for s in (group.get("stocks") or [])
            if isinstance(s, dict)
        ]
        removed = mine_service.remove_stocks(gid, [c for c in old if c])
        if removed.get("removed"):
            _log(f"分组「{name}」已清空 {len(removed['removed'])} 只")
    codes = [r["code"] for r in rows if r["code"]]
    names = {r["code"]: r["name"] for r in rows if r["code"]}
    result = mine_service.add_stocks(gid, codes, names=names)
    final = result.get("group") or group
    _log(
        f"分组「{final.get('name')}」写入完成：新加 {len(result.get('added') or [])} · "
        f"已存在 {len(result.get('skipped') or [])} · 现共 {final.get('count')}"
    )


# ---------------------------------------------------------------------------
# 5. CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="遍历每个申万三级行业，找出蓝筹股（详细中文日志）",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--min-cap", type=float, default=DEFAULT_MIN_CAP, help="最小总市值（亿元）")
    parser.add_argument("--min-roe", type=float, default=DEFAULT_MIN_ROE, help="最小 ROE（%%）")
    parser.add_argument("--max-pe", type=float, default=DEFAULT_MAX_PE, help="最大 PE_TTM，0=不限制")
    parser.add_argument("--max-pb", type=float, default=DEFAULT_MAX_PB, help="最大 PB，0=不校验")
    parser.add_argument("--min-yield", type=float, default=DEFAULT_MIN_YIELD, help="最小股息率（%%），0=不校验")
    parser.add_argument("--top-per-industry", type=int, default=DEFAULT_TOP_PER_INDUSTRY, help="每个行业输出的蓝筹数量，0=全部")
    parser.add_argument("--strict-only", action="store_true", help="只输出满足全部硬指标的严格蓝筹")
    parser.add_argument("--exclude-chinext", action="store_true", help="排除创业板 300/301")
    parser.add_argument("--exclude-star", action="store_true", help="排除科创板 688/689")
    parser.add_argument("--codes", default="", help="只扫描这些三级行业代码（逗号分隔），空=全部")
    parser.add_argument("--workers", type=int, default=DEFAULT_WORKERS, help="并发抓成分股数")
    parser.add_argument("--force", action="store_true", help="强制联网刷新行业成分股缓存")
    parser.add_argument("--offline", action="store_true", help="只用现有成分股缓存，忽略过期时间（不联网）")
    parser.add_argument("--refresh-tree", action="store_true", help="强制重建申万行业树（需要 akshare）")
    parser.add_argument("--mine", action="store_true", help="把结果写入「我的」分组（默认关闭）")
    parser.add_argument("--group", default=DEFAULT_GROUP, help="写入分组名（需配合 --mine）")
    parser.add_argument("--no-replace", dest="replace", action="store_false", help="写分组时不清空、只追加")
    parser.set_defaults(replace=True)
    parser.add_argument("--dry-run", action="store_true", help="只打印，不写分组/文件")
    parser.add_argument("--out", default="", help="结果写入 JSON 文件路径；空=不写文件")
    parser.add_argument("--json", action="store_true", help="在结尾打印完整 JSON")
    return parser


def main(argv: list[str] | None = None) -> int:
    _configure_stdio()
    args = build_parser().parse_args(argv)
    started = time.time()

    _log("=" * 78)
    _log("申万三级行业蓝筹股扫描 · 开始")
    _log(
        f"口径：市值≥{args.min_cap:g}亿 · ROE≥{args.min_roe:g}% · "
        f"0<PE≤{args.max_pe:g}" + (f" · PB≤{args.max_pb:g}" if args.max_pb > 0 else " · PB不校验")
        + (f" · 股息率≥{args.min_yield:g}%" if args.min_yield > 0 else " · 股息率不校验")
    )
    _log(
        f"输出：每行业前 {args.top_per_industry} 只"
        + ("（仅严格蓝筹）" if args.strict_only else "（严格蓝筹优先，不足补相对龙头）")
        + f" · 并发 {args.workers} · force={args.force} · offline={args.offline}"
    )
    _log("=" * 78)

    try:
        tree = _load_tree(force_refresh=bool(args.refresh_tree))
    except Exception as exc:  # noqa: BLE001
        _log(f"ERROR: 加载行业树失败：{exc}")
        return 1

    wanted = {
        p.strip()
        for p in re.split(r"[,，\s;；|]+", safe_str(args.codes))
        if p.strip()
    }
    if wanted:
        metas = [m for m in tree if safe_str(m.get("code")) in wanted]
        _log(f"按 --codes 过滤：指定 {len(wanted)} 个，命中 {len(metas)} 个三级行业")
    else:
        metas = tree
    if not metas:
        _log("没有可扫描的三级行业")
        return 1

    results: list[dict[str, Any]] = []
    total = len(metas)
    done = 0
    failed = 0
    t0 = time.time()

    with ThreadPoolExecutor(max_workers=max(1, int(args.workers))) as pool:
        futures = {pool.submit(_scan_industry, meta, args): meta for meta in metas}
        for fut in as_completed(futures):
            done += 1
            try:
                result = fut.result()
            except Exception as exc:  # noqa: BLE001
                failed += 1
                meta = futures[fut]
                _log(f"[{done}/{total}] {meta.get('code')} 任务异常：{exc}")
                continue
            results.append(result)
            _log_industry(result, done, total)
            if done % 25 == 0 or done == total:
                _log(
                    f"  ---- 进度 {done}/{total} · 成功 {len(results)} · 失败 {failed} "
                    f"· 耗时 {time.time() - t0:.0f}s ----"
                )

    # 保持行业树顺序
    order = {safe_str(m.get("code")): i for i, m in enumerate(metas)}
    results.sort(key=lambda r: order.get(r["l3_code"], 9999))

    all_selected = [row for r in results for row in r["selected"]]
    strict_total = sum(1 for row in all_selected if row["strict"])
    relative_total = len(all_selected) - strict_total
    industries_with = sum(1 for r in results if r.get("selected"))
    elapsed = time.time() - started

    _log("")
    _log("=" * 78)
    _log(
        f"扫描完成：三级行业 {total} · 有蓝筹的行业 {industries_with} · "
        f"入选 {len(all_selected)} 只（严格蓝筹 {strict_total} · 相对龙头 {relative_total}）"
        f" · 失败行业 {failed} · 耗时 {elapsed:.1f}s"
    )
    _log("=" * 78)

    if args.mine and not args.dry_run:
        try:
            _write_mine_group(all_selected, safe_str(args.group) or DEFAULT_GROUP, bool(args.replace))
        except Exception as exc:  # noqa: BLE001
            _log(f"ERROR: 写入分组失败：{exc}")
            return 1
    elif args.mine:
        _log(f"[dry-run] 跳过写入分组「{args.group}」（本会写入 {len(all_selected)} 只）")

    payload = {
        "meta": {
            "criteria": {
                "min_cap_yi": args.min_cap,
                "min_roe_pct": args.min_roe,
                "max_pe_ttm": args.max_pe,
                "max_pb": args.max_pb,
                "min_yield_pct": args.min_yield,
                "top_per_industry": args.top_per_industry,
                "strict_only": bool(args.strict_only),
            },
            "industries_total": total,
            "industries_with_blue_chips": industries_with,
            "selected_total": len(all_selected),
            "failed_industries": failed,
            "elapsed_sec": round(elapsed, 1),
        },
        "industries": [
            {
                k: r[k]
                for k in ("l3_code", "l3_name", "l1_name", "l2_name", "source", "total", "strict_count", "relative_count", "selected")
            }
            for r in results
        ],
    }

    if args.out.strip() and not args.dry_run:
        out_path = Path(args.out.strip())
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        _log(f"结果已写入 {out_path}")
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
