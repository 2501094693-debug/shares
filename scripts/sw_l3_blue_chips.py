"""全市场申万三级行业「蓝筹股」扫描（逐行业输出，中文详细打印日志）。

判定口径
--------
遍历申万行业树里的每一个三级行业，读取该行业全部成分股，先按下面的
硬指标判定是否蓝筹，再按综合评分在行业内排序：

  硬指标（全部满足才算「严格蓝筹」，阈值均可用命令行调整/关闭）：
    1. 非 ST / *ST / 退市整理；
    2. 默认排除创业板（300/301）与科创板（688/689）；
    3. 总市值 >= --min-cap（默认 100 亿元）—— 行业龙头规模；
    4. ROE   >= --min-roe（默认 8%）—— 盈利能力；
    5. 静态 PE 与 PE_TTM 均满足 0 < PE <= --max-pe（默认 20）—— 估值合理且确实盈利；
    6. PB 合理：仅当 --max-pb > 0 时校验（默认关闭）；
    7. 股息率 >= --min-yield（默认 1%）—— 稳定现金分红。

  综合评分（0~100，仅用于行业内排序，不影响严格/相对判定）：
    市值 30 + ROE 30 + PE 15 + PB 10 + 股息率 15 + 净利润增速 10。

  默认：每个三级行业最多 1 只，且必须满足全部硬指标（严格蓝筹）。
  可用 --top-per-industry / 去掉 --strict-only 放宽（见 CLI）。

数据来源（复用 backend/market/industry，不再脚本内抓乐咕 HTML）
--------------------------------------------------------------
优先级：
  1. 全市场索引 ``stocks_index.json``（按 l3_code 分组，零网络）；
  2. 缺行业时走 ``IndustryService.get_constituents``（成分股缓存 + TTL，
     必要时才联网乐咕；全量扫描 ``update_index=False`` 避免每行业写索引）；
  3. ``--offline``：只用索引 / 过期也可用的 cons 缓存，绝不联网；
  4. ``--force``：忽略索引与缓存，强制联网刷新各行业成分股。

用法（项目根目录）::

    python scripts/sw_l3_blue_chips.py
    python scripts/sw_l3_blue_chips.py --offline --mine
    python scripts/sw_l3_blue_chips.py --min-cap 200 --min-roe 10 --max-pe 20
    python scripts/sw_l3_blue_chips.py --codes 850111.SI,850112.SI --dry-run
    python scripts/sw_l3_blue_chips.py --allow-relative --top-per-industry 3
    python scripts/sw_l3_blue_chips.py --verbose
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
import threading
import time
from collections import defaultdict
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
from core.paths import CONS_TTL, STOCK_INDEX_CACHE, cons_cache_path  # noqa: E402
from market.industry.service import service as industry_service  # noqa: E402
from market.industry.stocks.schema import METRIC_KEYS  # noqa: E402
from mine.service import service as mine_service  # noqa: E402

_print_lock = threading.Lock()

DEFAULT_GROUP = "申万三级行业蓝筹"
DEFAULT_WORKERS = 6
DEFAULT_MIN_CAP = 100.0
DEFAULT_MIN_ROE = 8.0
DEFAULT_MAX_PE = 20.0
DEFAULT_MAX_PB = 0.0  # 0 = 不校验
DEFAULT_MIN_YIELD = 1.0
DEFAULT_TOP_PER_INDUSTRY = 1
DEFAULT_STRICT_ONLY = True
DEFAULT_EXCLUDE_CHINEXT = True
DEFAULT_EXCLUDE_STAR = True
MAX_STOCKS_PER_GROUP = 1000  # 与 mine.service 上限一致

_CHINEXT_PREFIXES = ("300", "301")
_STAR_PREFIXES = ("688", "689")
_EMPTY_CELLS = frozenset({"nan", "None", "—", "-", "<NA>", "NaT", ""})


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
# 1. 数据加载：索引优先，缺行业再走 IndustryService
# ---------------------------------------------------------------------------


def _load_tree(force_refresh: bool = False) -> list[dict[str, Any]]:
    industry_service.get_tree(force_refresh=force_refresh)
    rows = industry_service.flat_l3()
    if not rows:
        raise RuntimeError("行业树无三级行业")
    _log(f"行业树读取成功：{len(rows)} 个申万三级行业")
    return rows


def _index_by_l3(*, rebuild_from_cons: bool = False) -> dict[str, list[dict[str, Any]]]:
    """从全市场索引按三级行业分组。空索引时可选择用 cons 缓存拼一份。"""
    store = industry_service.stocks
    stocks = store.all_stocks()
    if not stocks and rebuild_from_cons:
        _log("全市场索引为空，尝试用 cons/*.json 重建（不联网）…")
        store.rebuild_from_cons_cache()
        stocks = store.all_stocks()
    by_l3: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for stock in stocks:
        l3 = safe_str(stock.get("l3_code"))
        if l3:
            by_l3[l3].append(stock)
    return by_l3


def _cons_cache_meta(l3_code: str) -> tuple[bool, float]:
    """返回 (文件是否存在, 年龄秒)。不存在时年龄为 inf。"""
    path = cons_cache_path(l3_code)
    if not path.is_file():
        return False, math.inf
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        age = time.time() - float((data or {}).get("fetched_at") or 0)
        return True, max(0.0, age)
    except Exception:  # noqa: BLE001
        return True, math.inf


def _load_constituents(
    meta: dict[str, Any],
    *,
    force: bool = False,
    offline: bool = False,
    index_stocks: list[dict[str, Any]] | None = None,
) -> tuple[list[dict[str, Any]], str]:
    """返回 (股票列表, 来源标记)。

    来源：index / cache / cache(offline) / fetch
    """
    l3_code = safe_str(meta.get("code"))
    if not force and index_stocks:
        return list(index_stocks), "index"

    exists, age = _cons_cache_meta(l3_code)
    fresh = exists and age < CONS_TTL
    try:
        payload = industry_service.get_constituents(
            l3_code,
            force_refresh=bool(force),
            update_index=False,
            allow_stale=bool(offline),
        )
    except Exception as exc:  # noqa: BLE001
        if index_stocks:
            return list(index_stocks), f"index(fallback:{exc})"
        raise

    stocks = list(payload.get("stocks") or [])
    if force:
        source = "fetch"
    elif offline:
        source = "cache(offline)"
    elif fresh:
        source = "cache"
    else:
        source = "fetch"
    return stocks, source


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
    m: dict[str, float | None] = {key: _num(stock.get(key)) for key in METRIC_KEYS}

    reasons: list[str] = []
    if _is_st_or_delisted(name):
        reasons.append("ST/退市")
    if exclude_chinext and _is_chinext(code):
        reasons.append("创业板")
    if exclude_star and _is_star(code):
        reasons.append("科创板")

    cap, roe = m["market_cap"], m["roe"]
    pe_static, pe_ttm = m["pe"], m["pe_ttm"]
    pb, dy = m["pb"], m["dividend_yield"]

    if cap is None or cap < min_cap:
        reasons.append(f"市值<{min_cap:g}亿")
    if roe is None or roe < min_roe:
        reasons.append(f"ROE<{min_roe:g}%")
    # 静态 PE、动态 PE_TTM 都要盈利且不超过上限
    if pe_static is None or pe_static <= 0:
        reasons.append("静态PE缺失/亏损")
    elif max_pe > 0 and pe_static > max_pe:
        reasons.append(f"静态PE>{max_pe:g}")
    if pe_ttm is None or pe_ttm <= 0:
        reasons.append("PE_TTM缺失/亏损")
    elif max_pe > 0 and pe_ttm > max_pe:
        reasons.append(f"PE_TTM>{max_pe:g}")
    if max_pb > 0 and (pb is None or pb <= 0 or pb > max_pb):
        reasons.append(f"PB越界(>{max_pb:g})")
    if min_yield > 0 and (dy is None or dy < min_yield):
        reasons.append(f"股息率<{min_yield:g}%")

    eligible = bool(code) and not any(
        r in reasons for r in ("ST/退市", "创业板", "科创板")
    )
    strict = not reasons
    relative = (
        eligible
        and pe_static is not None
        and pe_static > 0
        and pe_ttm is not None
        and pe_ttm > 0
        and roe is not None
        and roe > 0
    )

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
    meta: dict[str, Any],
    args: argparse.Namespace,
    index_map: dict[str, list[dict[str, Any]]],
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
            meta,
            force=bool(args.force),
            offline=bool(args.offline),
            index_stocks=None if args.force else index_map.get(l3_code),
        )
    except Exception as exc:  # noqa: BLE001
        return {**base, "error": str(exc), "source": "error", "rows": [], "selected": []}

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
    # 默认 strict_only=True：不补相对龙头；仅显式 --allow-relative 时才补
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
        f"静PE{_fmt(m['pe'], '', 1):>6}  TTM{_fmt(m['pe_ttm'], '', 1):>6}  "
        f"PB{_fmt(m['pb'], '', 1):>6}  "
        f"股息{_fmt(m['dividend_yield'], '%', 1):>6}  "
        f"增速{_fmt(m['profit_growth'], '%', 1):>7}  · {flags}"
    )


def _log_industry(
    result: dict[str, Any], idx: int, total: int, *, verbose: bool
) -> None:
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

    if not verbose:
        return
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
    # 跨行业可能重复；严格蓝筹优先，同分保留先出现的
    dedup: dict[str, dict[str, Any]] = {}
    for row in rows:
        code = normalize_code(safe_str(row.get("code")))
        if not code:
            continue
        prev = dedup.get(code)
        if prev is None or (row.get("strict") and not prev.get("strict")):
            dedup[code] = row
    uniq = list(dedup.values())
    uniq.sort(
        key=lambda r: (
            0 if r.get("strict") else 1,
            -float(r.get("score") or 0),
            safe_str(r.get("code")),
        )
    )
    if len(uniq) > MAX_STOCKS_PER_GROUP:
        _log(
            f"警告：去重后 {len(uniq)} 只超过分组上限 {MAX_STOCKS_PER_GROUP}，"
            f"按严格/评分保留前 {MAX_STOCKS_PER_GROUP} 只"
        )
        uniq = uniq[:MAX_STOCKS_PER_GROUP]

    group = _ensure_group(name)
    gid = safe_str(group.get("id"))
    if replace:
        old = [
            normalize_code(safe_str(s.get("code")))
            for s in (group.get("stocks") or [])
            if isinstance(s, dict)
        ]
        old = [c for c in old if c]
        if old:
            removed = mine_service.remove_stocks(gid, old)
            _log(f"分组「{name}」已清空 {len(removed.get('removed') or [])} 只")

    codes = [normalize_code(safe_str(r.get("code"))) for r in uniq]
    codes = [c for c in codes if c]
    names = {
        normalize_code(safe_str(r.get("code"))): safe_str(r.get("name"))
        for r in uniq
        if normalize_code(safe_str(r.get("code")))
    }
    if not codes:
        _log(f"分组「{name}」无有效代码，跳过写入")
        return
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
    parser.add_argument(
        "--max-pe",
        type=float,
        default=DEFAULT_MAX_PE,
        help="静态 PE 与 PE_TTM 的共同上限（均需 0<PE≤该值），0=不限制上限",
    )
    parser.add_argument("--max-pb", type=float, default=DEFAULT_MAX_PB, help="最大 PB，0=不校验")
    parser.add_argument("--min-yield", type=float, default=DEFAULT_MIN_YIELD, help="最小股息率（%%），0=不校验")
    parser.add_argument(
        "--top-per-industry",
        type=int,
        default=DEFAULT_TOP_PER_INDUSTRY,
        help="每个行业最多输出几只（默认 1；0=该行业全部严格蓝筹）",
    )
    parser.add_argument(
        "--strict-only",
        dest="strict_only",
        action="store_true",
        default=DEFAULT_STRICT_ONLY,
        help="只输出严格蓝筹（默认开启）",
    )
    parser.add_argument(
        "--allow-relative",
        dest="strict_only",
        action="store_false",
        help="严格蓝筹不足时，用相对龙头补足名额",
    )
    parser.add_argument(
        "--exclude-chinext",
        dest="exclude_chinext",
        action="store_true",
        default=DEFAULT_EXCLUDE_CHINEXT,
        help="排除创业板 300/301（默认开启）",
    )
    parser.add_argument(
        "--include-chinext",
        dest="exclude_chinext",
        action="store_false",
        help="允许创业板",
    )
    parser.add_argument(
        "--exclude-star",
        dest="exclude_star",
        action="store_true",
        default=DEFAULT_EXCLUDE_STAR,
        help="排除科创板 688/689（默认开启）",
    )
    parser.add_argument(
        "--include-star",
        dest="exclude_star",
        action="store_false",
        help="允许科创板",
    )
    parser.add_argument("--codes", default="", help="只扫描这些三级行业代码（逗号分隔），空=全部")
    parser.add_argument("--workers", type=int, default=DEFAULT_WORKERS, help="缺缓存需联网时的并发数")
    parser.add_argument("--force", action="store_true", help="强制联网刷新行业成分股缓存（忽略索引）")
    parser.add_argument("--offline", action="store_true", help="只用索引/成分股缓存，不联网")
    parser.add_argument("--refresh-tree", action="store_true", help="强制重建申万行业树（需要 akshare）")
    parser.add_argument("--mine", action="store_true", help="把结果写入「我的」分组（默认关闭）")
    parser.add_argument("--group", default=DEFAULT_GROUP, help="写入分组名（需配合 --mine）")
    parser.add_argument("--no-replace", dest="replace", action="store_false", help="写分组时不清空、只追加")
    parser.set_defaults(replace=True)
    parser.add_argument("--dry-run", action="store_true", help="只打印，不写分组/文件")
    parser.add_argument("--out", default="", help="结果写入 JSON 文件路径；空=不写文件")
    parser.add_argument("--json", action="store_true", help="在结尾打印完整 JSON")
    parser.add_argument("--verbose", action="store_true", help="打印每行业未入选原因（默认不打）")
    return parser


def main(argv: list[str] | None = None) -> int:
    _configure_stdio()
    args = build_parser().parse_args(argv)
    if args.force and args.offline:
        _log("ERROR: --force 与 --offline 不能同时使用")
        return 2
    started = time.time()

    _log("=" * 78)
    _log("申万三级行业蓝筹股扫描 · 开始")
    boards = []
    if args.exclude_chinext:
        boards.append("排除创业板")
    if args.exclude_star:
        boards.append("排除科创板")
    _log(
        f"口径：市值≥{args.min_cap:g}亿 · ROE≥{args.min_roe:g}% · "
        f"0<静态PE/TTM≤{args.max_pe:g}"
        + (f" · PB≤{args.max_pb:g}" if args.max_pb > 0 else " · PB不校验")
        + (f" · 股息率≥{args.min_yield:g}%" if args.min_yield > 0 else " · 股息率不校验")
        + (f" · {'/'.join(boards)}" if boards else " · 含创业板/科创板")
    )
    _log(
        f"输出：每行业最多 {args.top_per_industry} 只"
        + ("（仅严格蓝筹）" if args.strict_only else "（严格蓝筹优先，不足补相对龙头）")
        + f" · 并发 {args.workers} · force={args.force} · offline={args.offline}"
    )
    _log(
        "数据：优先 stocks_index → IndustryService 成分股缓存"
        + ("（离线，过期缓存可用）" if args.offline else "（缺则联网）")
        + (f"；索引文件 {STOCK_INDEX_CACHE.name}" if STOCK_INDEX_CACHE.is_file() else "；无索引文件")
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

    index_map: dict[str, list[dict[str, Any]]] = {}
    if not args.force:
        index_map = _index_by_l3(rebuild_from_cons=bool(args.offline))
        covered = sum(1 for m in metas if safe_str(m.get("code")) in index_map)
        stock_n = sum(len(index_map.get(safe_str(m.get("code")), [])) for m in metas)
        _log(
            f"索引覆盖：{covered}/{len(metas)} 个行业 · {stock_n} 只股票"
            + ("（缺的行业将读 cons 缓存）" if args.offline else "（缺的行业将按需拉成分股）")
        )

    results: list[dict[str, Any]] = []
    total = len(metas)
    done = 0
    failed = 0
    source_counts: dict[str, int] = defaultdict(int)
    t0 = time.time()

    # 索引已覆盖的行业本地算即可；真正缺数据的才丢进线程池（避免无意义并发）
    local_metas: list[dict[str, Any]] = []
    remote_metas: list[dict[str, Any]] = []
    for meta in metas:
        code = safe_str(meta.get("code"))
        if args.force or code not in index_map:
            remote_metas.append(meta)
        else:
            local_metas.append(meta)

    def _handle(result: dict[str, Any]) -> None:
        nonlocal done, failed
        done += 1
        if result.get("error"):
            failed += 1
        else:
            source_counts[safe_str(result.get("source")) or "unknown"] += 1
        results.append(result)
        _log_industry(result, done, total, verbose=bool(args.verbose))
        if done % 25 == 0 or done == total:
            _log(
                f"  ---- 进度 {done}/{total} · 成功 {len(results) - failed} · 失败 {failed} "
                f"· 耗时 {time.time() - t0:.0f}s ----"
            )

    for meta in local_metas:
        _handle(_scan_industry(meta, args, index_map))

    if remote_metas:
        workers = 1 if args.offline else max(1, int(args.workers))
        _log(
            f"需补拉/读缓存的行业 {len(remote_metas)} 个"
            + (f"（并发 {workers}）" if not args.offline else "（离线串行读缓存）")
        )
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {
                pool.submit(_scan_industry, meta, args, index_map): meta
                for meta in remote_metas
            }
            for fut in as_completed(futures):
                try:
                    result = fut.result()
                except Exception as exc:  # noqa: BLE001
                    failed += 1
                    done += 1
                    meta = futures[fut]
                    _log(f"[{done}/{total}] {meta.get('code')} 任务异常：{exc}")
                    continue
                _handle(result)

    order = {safe_str(m.get("code")): i for i, m in enumerate(metas)}
    results.sort(key=lambda r: order.get(r["l3_code"], 9999))

    all_selected = [row for r in results for row in r.get("selected") or []]
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
    if source_counts:
        src_text = " · ".join(f"{k} {v}" for k, v in sorted(source_counts.items()))
        _log(f"数据来源统计：{src_text}")
    _log("=" * 78)

    if args.mine and not args.dry_run:
        try:
            _write_mine_group(
                all_selected, safe_str(args.group) or DEFAULT_GROUP, bool(args.replace)
            )
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
                "max_pe": args.max_pe,  # 静态 PE 与 PE_TTM 共用上限
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
            "sources": dict(source_counts),
        },
        "industries": [
            {
                k: r[k]
                for k in (
                    "l3_code",
                    "l3_name",
                    "l1_name",
                    "l2_name",
                    "source",
                    "total",
                    "strict_count",
                    "relative_count",
                    "selected",
                )
            }
            for r in results
        ],
    }

    if args.out.strip() and not args.dry_run:
        out_path = Path(args.out.strip())
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        _log(f"结果已写入 {out_path}")
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
