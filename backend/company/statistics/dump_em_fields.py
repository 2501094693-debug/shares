"""拉取东财 push2 已释义字段并打印。

    python company/statistics/dump_em_fields.py
    python company/statistics/dump_em_fields.py 000001
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

from core.codes import normalize_code, secid
from core.http import get_json

_EMPTY = {None, "", "-"}

# 同一接口、多入口，断连则换下一台
_HOSTS = (
    "https://push2delay.eastmoney.com",
    "https://push2.eastmoney.com",
    "https://82.push2.eastmoney.com",
    "https://71.push2.eastmoney.com",
)

# 个股 /api/qt/stock/get（不是列表 clist 的 f2/f12）
FIELD_GROUPS: dict[str, dict[str, str]] = {
    "证券信息": {
        "f57": "股票代码",
        "f58": "股票名称",
        "f729": "证券简称",
        "f730": "英文名称",
        "f59": "价格精度",
        "f152": "小数位数",
        "f80": "交易时段",
        "f86": "行情时间",
        "f189": "上市日期",
        "f127": "行业",
        "f198": "行业板块代码",
        "f128": "地区板块",
        "f129": "概念",
    },
    "买卖五档": {
        "f19": "买一价",
        "f20": "买一量",
        "f17": "买二价",
        "f18": "买二量",
        "f15": "买三价",
        "f16": "买三量",
        "f13": "买四价",
        "f14": "买四量",
        "f11": "买五价",
        "f12": "买五量",
        "f39": "卖一价",
        "f40": "卖一量",
        "f37": "卖二价",
        "f38": "卖二量",
        "f35": "卖三价",
        "f36": "卖三量",
        "f33": "卖四价",
        "f34": "卖四量",
        "f31": "卖五价",
        "f32": "卖五量",
    },
    "当日行情": {
        "f43": "最新价",
        "f169": "涨跌额",
        "f170": "涨跌幅",
        "f46": "今开",
        "f60": "昨收",
        "f44": "最高",
        "f45": "最低",
        "f71": "均价",
        "f51": "涨停价",
        "f52": "跌停价",
        "f171": "振幅",
        "f174": "52周最高",
        "f175": "52周最低",
    },
    "成交与盘口": {
        "f47": "成交量(手)",
        "f48": "成交额",
        "f168": "换手率",
        "f50": "量比",
        "f49": "外盘",
        "f161": "内盘",
        "f191": "委比",
        "f192": "委差",
        "f260": "盘后量",
        "f261": "盘后额",
    },
    "估值与每股": {
        "f162": "市盈率(动)",
        "f163": "市盈率(静)",
        "f164": "市盈率(TTM)",
        "f167": "市净率",
        "f55": "每股收益",
        "f92": "每股净资产",
        "f173": "净资产收益率",
    },
    "财务": {
        "f183": "净利润",
        "f184": "净利润同比",
        "f185": "营收同比",
        "f186": "毛利率",
        "f187": "净利率",
    },
    "股本与市值": {
        "f84": "总股本",
        "f85": "流通股",
        "f277": "流通A股",
        "f278": "发行股本",
        "f116": "总市值",
        "f117": "流通市值",
    },
}

def _empty(value: Any) -> bool:
    if isinstance(value, (dict, list)):
        return not value
    return value in _EMPTY


def _raw(code: str, fields: str) -> dict[str, Any]:
    params = {
        "fltt": "2",
        "invt": "2",
        "fields": fields,
        "secid": secid(code),
        "ut": "fa5fd1943c7b386f172d6893dbfba10b",
    }
    headers = {"Referer": "https://quote.eastmoney.com/", "Connection": "close"}
    for host in _HOSTS:
        try:
            payload = get_json(
                f"{host}/api/qt/stock/get",
                params=params,
                headers=headers,
                timeout=8,
            ) or {}
        except Exception:  # noqa: BLE001
            continue
        data = payload.get("data")
        if isinstance(data, dict) and data:
            return data
    return {}


def fetch(code: str) -> dict[str, dict[str, Any]]:
    """按 ``FIELD_GROUPS`` 分类拉取。买卖五档请求须带 ``f531``。"""
    code = normalize_code(code)
    if not code:
        raise ValueError("无效股票代码")

    out: dict[str, dict[str, Any]] = {}
    for title, group in FIELD_GROUPS.items():
        fields = ",".join(group)
        if title == "买卖五档":
            fields += ",f531"
        raw = _raw(code, fields)
        out[title] = {key: raw[key] for key in group if key in raw}
    return out


def print_fields(code: str, data: dict[str, dict[str, Any]], *, show_empty: bool) -> None:
    flat = {k: v for group in data.values() for k, v in group.items()}
    filled = {k: v for k, v in flat.items() if not _empty(v)}
    print(f"代码 {code}  已释义 {len(flat)} 个，有值 {len(filled)} 个，空值 {len(flat) - len(filled)} 个")
    if not show_empty and len(filled) < len(flat):
        print("空值已省略，加 --empty 可全部打印")
    for title, group in data.items():
        rows = [
            (key, FIELD_GROUPS[title][key], value)
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

    parser = argparse.ArgumentParser(description="打印东财个股已释义字段")
    parser.add_argument("code", nargs="?", default="600990")
    parser.add_argument("--empty", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    code = normalize_code(args.code)
    data = fetch(code)
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
