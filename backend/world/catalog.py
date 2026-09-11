"""全球市场指标目录：指数、央行利率、国债、原油。"""

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

# 央行 / 政策利率数据源
RATES: dict[str, dict[str, Any]] = {
    "us": {"name": "美国", "source": "jin10", "attr_id": "24", "label": "美联储基准利率"},
    "eu": {"name": "欧元区", "source": "jin10", "attr_id": "21", "label": "欧洲央行主要再融资利率"},
    "uk": {"name": "英国", "source": "jin10", "attr_id": "26", "label": "英国央行基准利率"},
    "de": {"name": "德国", "source": "jin10", "attr_id": "21", "label": "欧洲央行主要再融资利率"},
    "fr": {"name": "法国", "source": "jin10", "attr_id": "21", "label": "欧洲央行主要再融资利率"},
    "jp": {"name": "日本", "source": "jin10", "attr_id": "22", "label": "日本央行政策利率"},
    "kr": {"name": "韩国", "source": "bok", "label": "韩国央行基准利率"},
    "cn": {"name": "中国", "source": "lpr", "label": "LPR(1年)"},
    "hk": {"name": "香港", "source": "hibor", "label": "HIBOR(3个月)"},
    "in": {"name": "印度", "source": "jin10", "attr_id": "68", "label": "印度央行回购利率"},
}

# 新浪全球国债收益率日线
BONDS: dict[str, dict[str, Any]] = {
    "us": {
        "name": "美国",
        "tenors": [
            {"id": "2y", "name": "2年期国债", "symbol": "US2YT"},
            {"id": "10y", "name": "10年期国债", "symbol": "US10YT"},
        ],
    },
    "eu": {
        "name": "欧元区",
        "tenors": [
            {"id": "2y", "name": "2年期国债(德)", "symbol": "DE2YT"},
            {"id": "10y", "name": "10年期国债(德)", "symbol": "DE10YT"},
        ],
    },
    "uk": {
        "name": "英国",
        "tenors": [
            {"id": "2y", "name": "2年期国债", "symbol": "GB2YT"},
            {"id": "10y", "name": "10年期国债", "symbol": "GB10YT"},
        ],
    },
    "de": {
        "name": "德国",
        "tenors": [
            {"id": "2y", "name": "2年期国债", "symbol": "DE2YT"},
            {"id": "10y", "name": "10年期国债", "symbol": "DE10YT"},
        ],
    },
    "fr": {
        "name": "法国",
        "tenors": [
            {"id": "2y", "name": "2年期国债", "symbol": "FR2YT"},
            {"id": "10y", "name": "10年期国债", "symbol": "FR10YT"},
        ],
    },
    "jp": {
        "name": "日本",
        "tenors": [
            {"id": "2y", "name": "2年期国债", "symbol": "JP2YT"},
            {"id": "10y", "name": "10年期国债", "symbol": "JP10YT"},
        ],
    },
    "kr": {
        "name": "韩国",
        "tenors": [
            {"id": "2y", "name": "2年期国债", "symbol": "KR2YT"},
            {"id": "10y", "name": "10年期国债", "symbol": "KR10YT"},
        ],
    },
    "cn": {
        "name": "中国",
        "tenors": [
            {"id": "2y", "name": "2年期国债", "symbol": "CN2YT"},
            {"id": "10y", "name": "10年期国债", "symbol": "CN10YT"},
        ],
    },
    "hk": {
        "name": "香港",
        "tenors": [
            {"id": "2y", "name": "2年期国债", "symbol": "HK2YT"},
            {"id": "10y", "name": "10年期国债", "symbol": "HK10YT"},
        ],
    },
    "in": {
        "name": "印度",
        "tenors": [
            {"id": "2y", "name": "2年期国债", "symbol": "IN2YT"},
            {"id": "10y", "name": "10年期国债", "symbol": "IN10YT"},
        ],
    },
}

OIL: list[dict[str, str]] = [
    {"id": "brent", "name": "布伦特原油", "symbol": "hf_OIL"},
    {"id": "wti", "name": "美国原油(WTI)", "symbol": "hf_CL"},
    {"id": "dubai", "name": "迪拜原油", "symbol": "hf_DBI"},
]

REGIONS = list(INDICES.keys())
