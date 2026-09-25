"""全球股指目录（东财 push2 secid）。"""

from __future__ import annotations

from typing import Any

# 东财 push2：A 股 i:交易所.代码；海外 i:100.代码
INDICES: dict[str, dict[str, Any]] = {
    "us": {
        "name": "美国",
        "items": [
            {"code": "DJIA", "name": "道琼斯", "secid": "100.DJIA"},
            {"code": "SPX", "name": "标普500", "secid": "100.SPX"},
            {"code": "NDX", "name": "纳斯达克", "secid": "100.NDX"},
        ],
    },
    "eu": {
        "name": "泛欧",
        "items": [
            {"code": "SX5E", "name": "欧洲斯托克50", "secid": "100.SX5E"},
        ],
    },
    "uk": {
        "name": "英国",
        "items": [
            {"code": "FTSE", "name": "英国富时100", "secid": "100.FTSE"},
        ],
    },
    "de": {
        "name": "德国",
        "items": [
            {"code": "GDAXI", "name": "德国DAX", "secid": "100.GDAXI"},
        ],
    },
    "fr": {
        "name": "法国",
        "items": [
            {"code": "FCHI", "name": "法国CAC40", "secid": "100.FCHI"},
        ],
    },
    "jp": {
        "name": "日本",
        "items": [
            {"code": "N225", "name": "日经225", "secid": "100.N225"},
        ],
    },
    "kr": {
        "name": "韩国",
        "items": [
            {"code": "KS11", "name": "韩国KOSPI", "secid": "100.KS11"},
        ],
    },
    "cn": {
        "name": "中国",
        "items": [
            {"code": "000001", "name": "上证指数", "secid": "1.000001"},
            {"code": "399001", "name": "深证成指", "secid": "0.399001"},
            {"code": "000300", "name": "沪深300", "secid": "1.000300"},
            {"code": "399006", "name": "创业板指", "secid": "0.399006"},
        ],
    },
    "hk": {
        "name": "香港",
        "items": [
            {"code": "HSI", "name": "恒生指数", "secid": "100.HSI"},
        ],
    },
    "in": {
        "name": "印度",
        "items": [
            {"code": "SENSEX", "name": "印度孟买SENSEX", "secid": "100.SENSEX"},
        ],
    },
}

REGIONS = list(INDICES.keys())
