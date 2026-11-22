"""炒作分析聚合：筹码门槛 + 十大股东/流通股东 + 剔重基金 + 热度。"""

from __future__ import annotations

import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from core.codes import normalize_code
from core.fmt import fmt_shares, fmt_yi_wan, to_float

from company.analysis.speculation.heat import build_heat
from company.statistics.holdings.fund_holders import fetch_fund_holders
from company.statistics.holdings.holders import fetch_top_holders
from company.statistics.quote.fetch.free_float import calc as calc_free_float

logger = logging.getLogger(__name__)

_SIT_RULES = (
    ("long", "长期坐庄", 0.33),
    ("mid", "中期坐庄", 0.25),
    ("short", "短期坐庄", 0.10),
)

_NAME_STRIP_RE = re.compile(r"[\s\-_/·•（）()【】\[\]「」『』]+")


def _norm_name(value: Any) -> str:
    text = str(value or "").strip().lower()
    if not text:
        return ""
    return _NAME_STRIP_RE.sub("", text)


def _holder_keys(items: list[dict[str, Any]]) -> set[str]:
    keys: set[str] = set()
    for item in items:
        name = _norm_name(item.get("name"))
        if name:
            keys.add(name)
        code = str(item.get("holder_code") or item.get("code") or "").strip().lower()
        if code:
            keys.add(code)
    return keys


def _build_chip(code: str) -> dict[str, Any]:
    data = calc_free_float(code)
    free_shares = to_float(data.get("free_float_shares"))
    free_mcap = to_float(data.get("free_float_market_cap"))
    sit: dict[str, Any] = {}
    for key, label, pct in _SIT_RULES:
        shares = free_shares * pct if free_shares is not None else None
        mcap = free_mcap * pct if free_mcap is not None else None
        sit[key] = {
            "key": key,
            "label": label,
            "pct": pct,
            "pct_fmt": f"{pct:.0%}",
            "shares": shares,
            "shares_fmt": fmt_shares(shares),
            "market_cap": mcap,
            "market_cap_fmt": fmt_yi_wan(mcap, unit_yi=True),
        }
    return {
        "code": data.get("code") or code,
        "name": data.get("name") or "",
        "price": data.get("price"),
        "price_fmt": data.get("price_fmt") or "",
        "end_date": data.get("end_date") or "",
        "source": data.get("source") or "eastmoney",
        "note": "自由流通口径：东财 FREELIQCI_SHARES；坐庄门槛为规则阈值，非庄家识别。",
        "total_shares": data.get("total_shares"),
        "total_shares_fmt": data.get("total_shares_fmt") or "",
        "float_shares": data.get("float_shares"),
        "float_shares_fmt": data.get("float_shares_fmt") or "",
        "free_float_shares": free_shares,
        "free_float_shares_fmt": data.get("free_float_shares_fmt") or "",
        "total_market_cap": data.get("total_market_cap"),
        "total_market_cap_fmt": data.get("total_market_cap_fmt") or "",
        "float_market_cap": data.get("float_market_cap"),
        "float_market_cap_fmt": data.get("float_market_cap_fmt") or "",
        "free_float_market_cap": free_mcap,
        "free_float_market_cap_fmt": data.get("free_float_market_cap_fmt") or "",
        "sit": sit,
    }


def _safe_holders(code: str, scope: str, report_date: str | None) -> dict[str, Any]:
    try:
        return fetch_top_holders(code, report_date=report_date, scope=scope)
    except Exception as exc:  # noqa: BLE001
        logger.warning("炒作十大股东失败 %s scope=%s: %s", code, scope, exc)
        return {
            "code": code,
            "scope": scope,
            "items": [],
            "count": 0,
            "error": str(exc),
            "report_date": report_date or "",
            "report_dates": [],
        }


def _safe_funds(code: str, report_date: str | None) -> dict[str, Any]:
    try:
        return fetch_fund_holders(code, report_date=report_date)
    except Exception as exc:  # noqa: BLE001
        logger.warning("炒作基金持股失败 %s: %s", code, exc)
        return {
            "code": code,
            "items": [],
            "count": 0,
            "error": str(exc),
            "report_date": report_date or "",
        }


def _summarize_funds(
    fund_pack: dict[str, Any],
    *,
    top_keys: set[str],
    total_shares: float | None,
) -> dict[str, Any]:
    """基金持股汇总：剔除前十大股东（名称/代码命中），占比分母=总股本。"""
    items_in = list(fund_pack.get("items") or [])
    kept: list[dict[str, Any]] = []
    excluded = 0
    seen: set[str] = set()
    fund_shares = 0.0
    for item in items_in:
        if not isinstance(item, dict):
            continue
        code = str(item.get("code") or "").strip().lower()
        name = _norm_name(item.get("name"))
        dedupe = code or name
        if dedupe and dedupe in seen:
            excluded += 1
            continue
        if dedupe:
            seen.add(dedupe)
        in_top = (code and code in top_keys) or (name and name in top_keys)
        if in_top:
            excluded += 1
            continue
        shares = to_float(item.get("shares"))
        if shares is not None:
            fund_shares += shares
        ratio_raw = to_float(item.get("total_share_ratio_raw"))
        if ratio_raw is None and shares is not None and total_shares:
            ratio_raw = shares / total_shares * 100
        kept.append(
            {
                **item,
                "total_share_ratio_raw": ratio_raw,
                "total_share_ratio": (
                    f"{ratio_raw:.2f}%" if ratio_raw is not None else item.get("total_share_ratio") or ""
                ),
            }
        )

    ratio = None
    if total_shares and total_shares > 0 and fund_shares > 0:
        ratio = fund_shares / total_shares * 100
    elif kept:
        summed = 0.0
        any_ratio = False
        for item in kept:
            r = to_float(item.get("total_share_ratio_raw"))
            if r is not None:
                summed += r
                any_ratio = True
        if any_ratio:
            ratio = summed

    return {
        "report_date": fund_pack.get("report_date") or "",
        "source": fund_pack.get("source") or "eastmoney",
        "denominator": "total_shares",
        "denominator_label": "总股本",
        "count": len(kept),
        "shares": fund_shares if fund_shares > 0 else None,
        "shares_fmt": fmt_shares(fund_shares if fund_shares > 0 else None),
        "ratio": ratio,
        "ratio_fmt": f"{ratio:.2f}%" if ratio is not None else "",
        "excluded_in_top10": excluded,
        "raw_count": int(fund_pack.get("count") or len(items_in)),
        "items": kept,
        "error": fund_pack.get("error") or "",
        "note": "已按名称/代码剔除前十大股东中的基金；占比分母为总股本。",
    }


def build_speculation(
    code: str,
    *,
    holders_date: str | None = None,
    funds_date: str | None = None,
    include_heat: bool = True,
) -> dict[str, Any]:
    """聚合炒作分析数据包。"""
    code = normalize_code(code)
    if not code:
        raise ValueError("缺少股票代码")

    holders_date = (holders_date or "").strip() or None
    funds_date = (funds_date or "").strip() or None

    chip: dict[str, Any] = {}
    holders: dict[str, Any] = {}
    free_holders: dict[str, Any] = {}
    fund_raw: dict[str, Any] = {}
    heat: dict[str, Any] = {}
    section_errors: dict[str, str] = {}

    with ThreadPoolExecutor(max_workers=5) as pool:
        futures = {
            pool.submit(_build_chip, code): "chip",
            pool.submit(_safe_holders, code, "holders", holders_date): "holders",
            pool.submit(_safe_holders, code, "free", holders_date): "free_holders",
            pool.submit(_safe_funds, code, funds_date or holders_date): "funds",
        }
        if include_heat:
            futures[pool.submit(build_heat, code)] = "heat"
        results: dict[str, Any] = {}
        for fut in as_completed(futures):
            key = futures[fut]
            try:
                results[key] = fut.result()
            except Exception as exc:  # noqa: BLE001
                logger.warning("炒作分析分段失败 %s %s: %s", code, key, exc)
                section_errors[key] = str(exc)

    chip = results.get("chip") or {}
    holders = results.get("holders") or {"items": [], "scope": "holders"}
    free_holders = results.get("free_holders") or {"items": [], "scope": "free"}
    fund_raw = results.get("funds") or {"items": []}
    heat = results.get("heat") or {}

    if not chip and "chip" in section_errors:
        chip = {"error": section_errors["chip"]}
    if holders.get("error"):
        section_errors["holders"] = str(holders["error"])
    if free_holders.get("error"):
        section_errors["free_holders"] = str(free_holders["error"])
    if fund_raw.get("error"):
        section_errors["funds"] = str(fund_raw["error"])

    total_shares = to_float(chip.get("total_shares")) or to_float(holders.get("total_shares"))
    top_keys = _holder_keys(list(holders.get("items") or []))
    # 流通前十也参与剔除，避免同一股东在流通榜出现却漏剔
    top_keys |= _holder_keys(list(free_holders.get("items") or []))
    funds = _summarize_funds(fund_raw, top_keys=top_keys, total_shares=total_shares)

    name = (
        chip.get("name")
        or holders.get("name")
        or free_holders.get("name")
        or ""
    )

    return {
        "module": "speculation",
        "code": code,
        "name": name,
        "as_of": time.strftime("%Y-%m-%d %H:%M:%S"),
        "chip": chip,
        "holders": {
            "scope": "holders",
            "label": "前十大股东",
            "report_date": holders.get("report_date") or "",
            "report_dates": holders.get("report_dates") or [],
            "total_shares": holders.get("total_shares"),
            "total_shares_fmt": holders.get("total_shares_fmt") or "",
            "count": holders.get("count") or len(holders.get("items") or []),
            "items": holders.get("items") or [],
            "error": holders.get("error") or "",
        },
        "free_holders": {
            "scope": "free",
            "label": "前十大流通股东",
            "report_date": free_holders.get("report_date") or "",
            "report_dates": free_holders.get("report_dates") or [],
            "total_shares": free_holders.get("total_shares"),
            "total_shares_fmt": free_holders.get("total_shares_fmt") or "",
            "count": free_holders.get("count") or len(free_holders.get("items") or []),
            "items": free_holders.get("items") or [],
            "error": free_holders.get("error") or "",
        },
        "funds": funds,
        "heat": heat,
        "errors": section_errors,
    }
