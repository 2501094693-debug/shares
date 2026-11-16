"""python -m company.analysis.deal 002384 --bin-by both

打印四象限汇总（笔数 / 金额 / 手数）与定步长分箱分布，``--json`` 输出完整载荷。
"""

from __future__ import annotations

import argparse
import json

from company.analysis.deal.fundflow.core import BIN_BY_MODES, EVENT_TYPES
from company.analysis.deal.fundflow.service import DEFAULT_MIN_AMOUNT, fetch_big_deal_stats

_LABELS = {
    "active_buy": "主动买",
    "active_sell": "主动卖",
    "passive_buy": "被动买",
    "passive_sell": "被动卖",
}


def _wan(value: float) -> str:
    return f"{float(value or 0) / 10_000:,.2f}"


def _print_bins(title: str, bins: list[dict], unit: str) -> None:
    if not bins:
        print(f"  {title}：无样本")
        return
    filled = [cell for cell in bins if cell.get("count")]
    print(f"  {title}（{len(bins)} 档，其中非空 {len(filled)} 档）")
    for cell in filled:
        print(
            f"    {cell['lo']}~{cell['hi']} {unit}"
            f"  笔数 {cell['count']:>4}  金额 {_wan(cell['amount']):>14} 万"
            f"  手数 {cell['volume_lots']:>10}"
        )


def main() -> int:
    try:
        import sys

        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass

    parser = argparse.ArgumentParser(description="同花顺大单资金动向统计")
    parser.add_argument("code", help="股票代码，如 002384")
    parser.add_argument(
        "--min-amount",
        type=float,
        default=DEFAULT_MIN_AMOUNT,
        help="大单金额门槛（元），默认 1000 万",
    )
    parser.add_argument(
        "--bin-by",
        default="amount",
        choices=BIN_BY_MODES,
        help="分箱口径：amount 金额 / lots 手数 / both 两套",
    )
    parser.add_argument("--day", default="", help="交易日 YYYY-MM-DD，历史日只读缓存")
    parser.add_argument("--refresh", action="store_true", help="强制重拉 HQ（仅当日有效）")
    parser.add_argument("--json", action="store_true", help="输出完整载荷")
    args = parser.parse_args()

    data = fetch_big_deal_stats(
        args.code,
        min_amount=args.min_amount,
        bin_by=args.bin_by,
        force=args.refresh,
        day=args.day,
    )
    if args.json:
        print(json.dumps(data, ensure_ascii=False, indent=2, default=float))
        return 0

    print(
        f"{data['code']} {data['session_day']}  min_amount={data['min_amount']:,.0f}  "
        f"total={data['total_count']}  bin_by={data['bin_by']}  "
        f"cached={'是' if data['cached'] else '否'}  source={data['source'] or '-'}"
    )
    print(f"  {'象限':<8}{'笔数':>6}{'金额(万)':>16}{'手数':>12}")
    for event in EVENT_TYPES:
        item = data[event]
        print(
            f"  {_LABELS[event]:<8}{item['count']:>6}"
            f"{_wan(item['amount']):>16}{item['volume_lots']:>12}"
        )
    print(
        f"  买盘合计 {data['buy']['count']} 笔 {_wan(data['buy']['amount'])} 万；"
        f"卖盘合计 {data['sell']['count']} 笔 {_wan(data['sell']['amount'])} 万"
    )
    print(
        f"  净额 {_wan(data['net_amount'])} 万；主动净额 {_wan(data['active_net_amount'])} 万"
    )

    for event in EVENT_TYPES:
        item = data[event]
        if "amount_bins" in item:
            _print_bins(f"{_LABELS[event]} 金额分布（步长 100 万）", item["amount_bins"], "元")
        if "lots_bins" in item:
            _print_bins(f"{_LABELS[event]} 手数分布（步长 100 手）", item["lots_bins"], "手")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())