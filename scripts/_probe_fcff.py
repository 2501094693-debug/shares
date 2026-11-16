# -*- coding: utf-8 -*-
"""小样本探测：东财 F10 的 FCFF_BACK / FCFF_FORWARD 是否拿得到，以及八看/估值
实际采用的 FCF 落在哪个来源上。

三层验证：
1. 主报表 ``RPT_F10_FINANCE_MAINFINADATA`` 原始字段里是否真有 FCFF_BACK / FCFF_FORWARD；
2. 生产合并行（主报表 + 现金流量表）里 ``resolve_fcf`` 最终选了哪个来源；
3. 八看 ``analyze`` 产出的 ``metrics.cash``，即估值 DCF 实际消费的 FCF。

用法（项目根目录）::

    .venv\\Scripts\\python.exe scripts/_probe_fcff.py
    .venv\\Scripts\\python.exe scripts/_probe_fcff.py --codes 600519,000651
    .venv\\Scripts\\python.exe scripts/_probe_fcff.py --main-only --codes 600519,601398
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
for _p in (str(_ROOT / "backend"), str(_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from company.analysis.financialreport._common import pick, to_float  # noqa: E402
from company.analysis.financialreport._fields import CAPEX_FIELDS, OCF_FIELDS  # noqa: E402
from company.analysis.financialreport.engine import analyze  # noqa: E402
from company.analysis.financialreport.metrics import resolve_fcf  # noqa: E402
from company.news.financialreport._common import (  # noqa: E402
    MAIN_REPORT,
    em_get,
    is_annual,
    period_label,
)
from company.news.financialreport.fetcher import get_financial_report  # noqa: E402

DEFAULT_CODES = ["600519", "000651", "600276", "300750", "601398", "002412"]

_stats: dict[str, int] = {}


def _bump(key: str) -> None:
    _stats[key] = _stats.get(key, 0) + 1


def yi(value: float | None) -> str:
    if value is None:
        return "—"
    return f"{value / 1e8:,.2f}亿"


def probe_main(code: str) -> bool:
    """返回主报表里最新年报是否有可用披露 FCFF。"""
    print(f"\n===== {code} =====")
    try:
        main_rows = em_get(MAIN_REPORT, code, page_size=8)
    except Exception as exc:  # noqa: BLE001
        print(f"  主报表请求异常: {type(exc).__name__}: {exc}")
        _bump("主报表失败")
        return False
    if not main_rows:
        print("  主报表无数据")
        _bump("主报表无数据")
        return False

    keys: set[str] = set()
    for row in main_rows:
        keys |= set(row.keys())
    has_fields = "FCFF_BACK" in keys and "FCFF_FORWARD" in keys
    print(
        f"  主报表 行数={len(main_rows)} 字段数={len(keys)} "
        f"FCFF_BACK={'FCFF_BACK' in keys} FCFF_FORWARD={'FCFF_FORWARD' in keys}"
    )
    _bump("字段存在" if has_fields else "字段缺失")

    annual_main = [r for r in main_rows if is_annual(str(r.get("REPORT_DATE") or ""))][:3]
    for row in annual_main:
        day = str(row.get("REPORT_DATE") or "")
        print(
            f"    [原始] {period_label(day, str(row.get('REPORT_DATE_NAME') or ''))}: "
            f"BACK={yi(to_float(pick(row, 'FCFF_BACK')))} "
            f"FORWARD={yi(to_float(pick(row, 'FCFF_FORWARD')))}"
        )

    latest = (annual_main or main_rows)[0]
    disclosed = to_float(pick(latest, "FCFF_BACK", "FCFF_FORWARD"))
    _bump("最新期有披露值" if disclosed is not None else "最新期披露值为空")
    return disclosed is not None


def probe_full(code: str) -> None:
    # 合并行：OCF / Capex 到位后 resolve_fcf 的选择结果
    try:
        pack = get_financial_report(code, scope="merged", limit=12)
    except Exception as exc:  # noqa: BLE001
        print(f"  合并链路异常: {type(exc).__name__}: {exc}")
        return
    items = pack.get("items") or []
    print(f"  合并行数={len(items)}")
    if not items:
        print("  合并无数据")
        return

    annual = [r for r in items if is_annual(str(r.get("REPORT_DATE") or ""))][:3]
    for row in annual:
        day = str(row.get("REPORT_DATE") or "")
        ocf = to_float(pick(row, *OCF_FIELDS))
        capex = to_float(pick(row, *CAPEX_FIELDS))
        fcf, source, detail = resolve_fcf(row, ocf=ocf, capex=capex)
        back = detail.get("fcff_back")
        fwd = detail.get("fcff_forward")
        flag = ""
        if back is not None and fwd is not None and (back > 0) != (fwd > 0):
            flag = "  ⚠BACK/FORWARD 符号相反"
        print(
            f"    [合并] {row.get('PERIOD_LABEL') or day}: "
            f"BACK={yi(back)} FORWARD={yi(fwd)} "
            f"OCF={yi(ocf)} Capex={yi(capex)} "
            f"→ 采用={yi(fcf)} ({source}){flag}"
        )

    # 八看链路：metrics.cash 即估值 DCF 消费的 FCF
    try:
        result = analyze(code, "annual")
    except Exception as exc:  # noqa: BLE001
        print(f"  八看分析异常: {type(exc).__name__}: {exc}")
        return
    cash = ((result.get("metrics") or {}).get("cash")) or {}
    print(
        f"  [八看] fcf={yi(cash.get('fcf'))} source={cash.get('fcf_source')} "
        f"ocf={yi(cash.get('ocf'))} capex={yi(cash.get('capex'))}"
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--codes", default=",".join(DEFAULT_CODES))
    ap.add_argument("--main-only", action="store_true", help="只探测主报表原始字段，不跑合并/八看")
    args = ap.parse_args()
    codes = [c.strip() for c in args.codes.split(",") if c.strip()]
    for code in codes:
        probe_main(code)
        if not args.main_only:
            probe_full(code)
    if _stats:
        print("\n===== 汇总 =====")
        for key, count in _stats.items():
            print(f"  {key}: {count}/{len(codes)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
