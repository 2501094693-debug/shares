"""命令行：按多日日线条件 / 形态 / 对比 / 组合 AST 筛选。

示例：

    python -m analysis.shares --days
    python -m analysis.shares --spec conditions.json --top 30
    python -m analysis.shares --spec conditions.json --logic or --top 30
    python -m analysis.shares --compare settle.json --top 30
    python -m analysis.shares --compose tree.json --top 30
    python -m analysis.shares --code 600519 --date 2026-09-23 --pct-chg-min 1 --lower-ratio-min 0.4
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[2]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from analysis.shares.common.conditions import normalize_logic
from analysis.shares.common.days import list_trade_days
from analysis.shares.compare import load_compare_scheme, screen_compare
from analysis.shares.compose import load_compose_tree, screen_compose
from analysis.shares.pattern import load_pattern_scheme, screen_scheme
from analysis.shares.screen import screen_shares


def _print_table(items: list[dict]) -> None:
    if not items:
        print("  无结果")
        return
    print(f"  {'#':>3} {'代码':<8} {'名称':<10} {'命中日':>4} {'最近日':<12}")
    for row in items:
        name = str(row.get("name") or "")[:10]
        print(
            f"  {row.get('rank', ''):>3} {row.get('code', ''):<8} {name:<10} "
            f"{row.get('matched_days', 0):>4} {str(row.get('as_of') or ''):<12}"
        )
        for day in row.get("days") or []:
            m = day.get("metrics") or {}
            print(
                f"       {day.get('date')}: pct={m.get('pct_chg')} "
                f"max+={m.get('max_gain')} max-={m.get('max_drop')} "
                f"body={m.get('body_pct')} "
                f"lower_r={m.get('lower_ratio')} upper_r={m.get('upper_ratio')} "
                f"body_r={m.get('body_ratio')} {day.get('spec_text')}"
            )
        for comp in row.get("comps") or []:
            print(
                f"       cmp[{comp.get('id') or comp.get('kind')}]: "
                f"{comp.get('spec_text') or comp.get('label')}"
            )
            if comp.get("kind") == "pair":
                left = comp.get("left") or {}
                right = comp.get("right") or {}
                print(
                    f"         {left.get('date')}={left.get('value')} vs "
                    f"{right.get('date')}={right.get('value')} "
                    f"ratio={comp.get('ratio')} delta={comp.get('delta')}"
                )
            elif comp.get("kind") == "trend":
                vals = comp.get("values") or []
                chain = " → ".join(
                    f"{v.get('date')}={v.get('value')}" for v in vals
                )
                print(
                    f"         hits={comp.get('pair_hits')}/{comp.get('pair_need')}  {chain}"
                )
        if row.get("branches"):
            latest = row.get("latest") or {}
            print(
                f"       branches={','.join(row.get('branches') or [])} "
                f"quiet={row.get('quiet_count')} "
                f"lower_r={latest.get('lower_ratio')} body={latest.get('body_pct')} "
                f"score={row.get('score')}"
            )
        elif row.get("score") is not None and row.get("comps"):
            print(f"       score={row.get('score')} matched_comps={row.get('matched_comps')}")


def _load_specs(args: argparse.Namespace) -> tuple[list[dict], str]:
    """返回 (days, logic)；logic 优先 CLI，其次 JSON 文件。"""
    file_logic = ""
    if args.spec:
        path = Path(args.spec)
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict) and "days" in data:
            file_logic = str(data.get("logic") or "")
            days = list(data["days"] or [])
        elif isinstance(data, list):
            days = data
        else:
            raise SystemExit("条件文件须为 day 条件数组，或含 days 字段的对象")
        logic = normalize_logic(args.logic if args.logic else file_logic)
        return days, logic

    if not args.date:
        return [], normalize_logic(args.logic)

    one: dict = {"date": args.date}
    if args.pct_chg_min is not None:
        one["pct_chg_min"] = args.pct_chg_min
    if args.pct_chg_max is not None:
        one["pct_chg_max"] = args.pct_chg_max
    if args.max_gain_min is not None:
        one["max_gain_min"] = args.max_gain_min
    if args.max_gain_max is not None:
        one["max_gain_max"] = args.max_gain_max
    if args.max_drop_min is not None:
        one["max_drop_min"] = args.max_drop_min
    if args.max_drop_max is not None:
        one["max_drop_max"] = args.max_drop_max
    if args.body_pct_min is not None:
        one["body_pct_min"] = args.body_pct_min
    if args.body_pct_max is not None:
        one["body_pct_max"] = args.body_pct_max
    if args.lower_ratio_min is not None:
        one["lower_ratio_min"] = args.lower_ratio_min
    if args.lower_ratio_max is not None:
        one["lower_ratio_max"] = args.lower_ratio_max
    if args.upper_ratio_min is not None:
        one["upper_ratio_min"] = args.upper_ratio_min
    if args.upper_ratio_max is not None:
        one["upper_ratio_max"] = args.upper_ratio_max
    if args.body_ratio_min is not None:
        one["body_ratio_min"] = args.body_ratio_min
    if args.body_ratio_max is not None:
        one["body_ratio_max"] = args.body_ratio_max
    return [one], normalize_logic(args.logic)


def _load_json_scheme(path: str) -> dict:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise SystemExit("方案文件须为 JSON 对象")
    if isinstance(data.get("scheme"), dict):
        return data["scheme"]
    return data


def _print_result(data: dict, *, as_json: bool) -> None:
    if as_json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return
    print(
        f"fingerprint={data.get('fingerprint')}  "
        f"mode={data.get('mode') or data.get('logic') or '-'}  "
        f"candidates={data.get('candidate_count')}  analyzed={data.get('analyzed_count')}  "
        f"results={data.get('result_count')}"
    )
    for line in data.get("spec_summary") or []:
        print(" ", line)
    print(data.get("note") or "")
    print()
    _print_table(list(data.get("items") or []))
    errors = data.get("errors") or []
    if errors:
        print()
        print("errors:", "; ".join(errors[:12]))


def main() -> None:
    parser = argparse.ArgumentParser(description="按多日日线条件 / 形态 / 对比 / 组合 AST 筛选股票")
    parser.add_argument("--days", type=int, nargs="?", const=22, help="列出近 N 个交易日（默认 22）")
    parser.add_argument("--spec", default="", help="筛选式条件 JSON 文件路径")
    parser.add_argument("--pattern", default="", help="形态方案 JSON（含 groups）")
    parser.add_argument("--compare", default="", help="对比式方案 JSON（含 comps）")
    parser.add_argument("--compose", "--scheme", dest="compose", default="", help="统一 AST 方案 JSON（含 nodes）")
    parser.add_argument("--date", default="", help="单日条件：交易日 YYYY-MM-DD")
    parser.add_argument(
        "--logic",
        default="",
        choices=["", "and", "or"],
        help="多日组合：and 全部满足 / or 任一满足 / not 全部不满足（默认 and；也可写在 --spec JSON 的 logic 字段）",
    )
    parser.add_argument("--pct-chg-min", type=float, default=None)
    parser.add_argument("--pct-chg-max", type=float, default=None)
    parser.add_argument("--max-gain-min", type=float, default=None)
    parser.add_argument("--max-gain-max", type=float, default=None)
    parser.add_argument("--max-drop-min", type=float, default=None)
    parser.add_argument("--max-drop-max", type=float, default=None)
    parser.add_argument("--body-pct-min", type=float, default=None)
    parser.add_argument("--body-pct-max", type=float, default=None)
    parser.add_argument("--lower-ratio-min", type=float, default=None)
    parser.add_argument("--lower-ratio-max", type=float, default=None)
    parser.add_argument("--upper-ratio-min", type=float, default=None)
    parser.add_argument("--upper-ratio-max", type=float, default=None)
    parser.add_argument("--body-ratio-min", type=float, default=None)
    parser.add_argument("--body-ratio-max", type=float, default=None)
    parser.add_argument("--code", default="", help="只分析一只股票")
    parser.add_argument("--top", type=int, default=40, help="前 N 名，0=全部")
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--json", action="store_true", help="JSON 输出")
    args = parser.parse_args()

    if (
        args.days is not None
        and not args.spec
        and not args.date
        and not args.compare
        and not args.pattern
        and not args.compose
    ):
        pack = list_trade_days(args.days)
        if args.json:
            print(json.dumps(pack, ensure_ascii=False, indent=2))
            return
        print(f"近 {pack.get('count')} 个交易日：")
        for item in pack.get("items") or []:
            print(f"  [{item.get('label')}] {item.get('date')}")
        print()
        print("筛选字段：", ", ".join((pack.get("fields") or {}).keys()))
        print("对比字段：", ", ".join((pack.get("compare_fields") or {}).keys()))
        return

    top = None if args.top <= 0 else args.top
    code = args.code.strip()

    if args.compose:
        tree = load_compose_tree({"scheme": _load_json_scheme(args.compose)})
        data = screen_compose(
            tree,
            code=code,
            workers=args.workers,
            top=top,
        )
        _print_result(data, as_json=args.json)
        return

    if args.compare:
        scheme = load_compare_scheme({"scheme": _load_json_scheme(args.compare)})
        data = screen_compare(
            scheme,
            code=code,
            workers=args.workers,
            top=top,
        )
        _print_result(data, as_json=args.json)
        return

    if args.pattern:
        scheme = load_pattern_scheme({"scheme": _load_json_scheme(args.pattern)})
        data = screen_scheme(
            scheme,
            code=code,
            workers=args.workers,
            top=top,
        )
        _print_result(data, as_json=args.json)
        return

    specs, logic = _load_specs(args)
    if not specs:
        parser.error(
            "请用 --days 列出交易日，或 --spec / --date / --compare / --pattern / --compose 指定条件"
        )
    data = screen_shares(
        day_specs=specs,
        logic=logic,
        code=code,
        workers=args.workers,
        top=top,
    )
    _print_result(data, as_json=args.json)


if __name__ == "__main__":
    main()
