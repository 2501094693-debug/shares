"""从乐咕乐股拉取某个申万三级行业的成分股表。

不走 akshare：它会按列名 rename，而乐咕页表头常被 JSON-LD 污染，
列名对不上就会整表错位。这里按 **列下标** 取值。

列位置（0 起）：
    0 序号  1 股票代码  2 股票简称  3 纳入时间  4 申万3级
    5 细分概念（不采集）
    6 价格  7 市盈率  8 市盈率ttm  9 市净率  10 ROE  11 股息率
    12 市值  13 近1日涨幅  14 近5日涨幅  15 今年以来涨幅
    16 净利润增速  17 营收增速

对外：``fetch_third_cons(l3_code) → DataFrame``，列名是上面的中文，
``StockStore`` 再用 ``_normalize_row`` 收成英文 key。
"""

from __future__ import annotations

from io import StringIO

import pandas as pd
import requests

from data.stocks.index.schema import EMPTY_CELLS

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    )
}

# (列下标, 输出列名)。行情列缺失时填空，不报错。
_COL_SPECS: list[tuple[int, str]] = [
    (1, "股票代码"),
    (2, "股票简称"),
    (3, "纳入时间"),
    (4, "申万3级"),
    (6, "价格"),
    (7, "市盈率"),
    (8, "市盈率ttm"),
    (9, "市净率"),
    (10, "ROE"),
    (11, "股息率"),
    (12, "市值"),
    (13, "近1日涨幅"),
    (14, "近5日涨幅"),
    (15, "今年以来涨幅"),
    (16, "净利润增速"),
    (17, "营收增速"),
]


def _series_at(df: pd.DataFrame, idx: int) -> pd.Series:
    """按列下标取值。列不够或格子是 NaN / 「—」时返回空字符串。"""
    if df.shape[1] <= idx:
        return pd.Series([""] * len(df), index=df.index, dtype=object)
    series = df.iloc[:, idx].where(pd.notna(df.iloc[:, idx]), "")
    series = series.astype(str).str.strip()
    return series.map(lambda x: "" if x in EMPTY_CELLS else x)


def fetch_third_cons(symbol: str) -> pd.DataFrame:
    """拉取三级行业 ``symbol``（如 ``850111.SI``）的成分股。

    至少要有代码 / 简称 / 纳入时间（下标 1..3）；行情列缺失则填空。
    """
    url = f"https://legulegu.com/stockdata/index-composition?industryCode={symbol}"
    resp = requests.get(url, headers=HEADERS, timeout=60)
    resp.raise_for_status()
    df = pd.read_html(StringIO(resp.text))[0]

    if df.shape[1] < 4:
        raise ValueError(f"成分股表格列数异常: {df.shape[1]}")

    out = pd.DataFrame({name: _series_at(df, idx) for idx, name in _COL_SPECS})
    out = out[out["股票代码"].str.len() > 0]
    out = out[~out["股票代码"].isin(["nan", "None", "-"])]
    return out.reset_index(drop=True)


if __name__ == "__main__":
    result = fetch_third_cons("850111.SI")
    print(result.head())
    print("columns", list(result.columns))
    print("count", len(result))
