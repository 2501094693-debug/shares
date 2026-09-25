"""国债收益率与央行利率目录。"""

from __future__ import annotations

from typing import Any

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
