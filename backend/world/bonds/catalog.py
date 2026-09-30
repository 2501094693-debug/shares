"""国债收益率目录。"""

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
