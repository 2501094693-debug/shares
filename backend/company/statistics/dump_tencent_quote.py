"""拉取腾讯 qt 实时盘口并按分类打印。

    python company/statistics/dump_tencent_quote.py
    python company/statistics/dump_tencent_quote.py 000001
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

_BACKEND = Path(__file__).resolve().parents[2]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from core.codes import normalize_code, tencent_symbol
from core.http import get_text

_EMPTY = {None, "", "-"}
_QUOTE_URL = "https://qt.gtimg.cn/q="

# 下标对应 qt.gtimg.cn 返回串用 ~ 切开后的位置
FIELD_GROUPS: dict[str, dict[int, str]] = {
    "证券信息": {
        1: "股票名称",
        2: "股票代码",
        30: "行情时间",
        82: "货币",
    },
    "买卖五档": {
        9: "买一价",
        10: "买一量",
        11: "买二价",
        12: "买二量",
        13: "买三价",
        14: "买三量",
        15: "买四价",
        16: "买四量",
        17: "买五价",
        18: "买五量",
        19: "卖一价",
        20: "卖一量",
        21: "卖二价",
        22: "卖二量",
        23: "卖三价",
        24: "卖三量",
        25: "卖四价",
        26: "卖四量",
        27: "卖五价",
        28: "卖五量",
    },
    "当日行情": {
        3: "最新价",
        31: "涨跌额",
        32: "涨跌幅",
        5: "今开",
        4: "昨收",
        33: "最高",
        34: "最低",
        51: "均价",
        47: "涨停价",
        48: "跌停价",
        43: "振幅",
        67: "52周最高",
        68: "52周最低",
    },
    "成交与盘口": {
        6: "成交量(手)",
        37: "成交额(万)",
        38: "换手率",
        49: "量比",
        7: "外盘",
        8: "内盘",
        35: "最近成交",
    },
    "估值": {
        52: "市盈率(动)",
        53: "市盈率(静)",
        39: "市盈率(TTM)",
        46: "市净率",
    },
    "股本与市值": {
        72: "总股本",
        73: "流通股",
        44: "流通市值(亿)",
        45: "总市值(亿)",
    },
}


def _empty(value: Any) -> bool:
    if isinstance(value, (dict, list)):
        return not value
    return value in _EMPTY


def _parts(code: str) -> list[str]:
    symbol = tencent_symbol(code)
    text = get_text(
        _QUOTE_URL + symbol,
        headers={"Referer": "https://gu.qq.com/"},
        timeout=10,
    )
    if '="' not in text:
        return []
    body = text.split('="', 1)[1].rsplit('"', 1)[0]
    return body.split("~")


def fetch(code: str) -> dict[str, dict[str, Any]]:
    """一次拉 qt 全文，再按 ``FIELD_GROUPS`` 切开。"""
    code = normalize_code(code)
    if not code:
        raise ValueError("无效股票代码")
    parts = _parts(code)
    out: dict[str, dict[str, Any]] = {}
    for title, group in FIELD_GROUPS.items():
        row: dict[str, Any] = {}
        for idx, _label in group.items():
            if idx < len(parts) and parts[idx] != "":
                row[f"p{idx}"] = parts[idx]
        out[title] = row
    return out


def print_fields(code: str, data: dict[str, dict[str, Any]], *, show_empty: bool) -> None:
    flat = {k: v for group in data.values() for k, v in group.items()}
    filled = {k: v for k, v in flat.items() if not _empty(v)}
    print(f"代码 {code}  已释义 {len(flat)} 个，有值 {len(filled)} 个，空值 {len(flat) - len(filled)} 个")
    if not show_empty and len(filled) < len(flat):
        print("空值已省略，加 --empty 可全部打印")
    for title, group in data.items():
        labels = FIELD_GROUPS[title]
        rows = [
            (key, labels[int(key[1:])], value)
            for key, value in group.items()
            if show_empty or not _empty(value)
        ]
        if not rows:
            continue
        print(f"\n[{title}]\n{'字段':<8}{'含义':<16}值")
        print("-" * 72)
        for key, label, value in rows:
            print(f"{key:<8}{label:<16}{value}")


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass

    parser = argparse.ArgumentParser(description="打印腾讯个股实时盘口")
    parser.add_argument("code", nargs="?", default="600519")
    parser.add_argument("--empty", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    code = normalize_code(args.code)
    try:
        data = fetch(code)
    except Exception as exc:  # noqa: BLE001
        print(f"请求失败: {exc}", file=sys.stderr)
        return 1
    if not any(data.values()):
        print(f"未拉到字段: {code}", file=sys.stderr)
        return 1
    if args.json:
        out = data if args.empty else {
            title: {k: v for k, v in group.items() if not _empty(v)}
            for title, group in data.items()
        }
        print(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        print_fields(code, data, show_empty=args.empty)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
