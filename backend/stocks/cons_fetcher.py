"""Fetch L3 constituents, bypassing broken akshare column rename."""

from __future__ import annotations

from io import StringIO

import pandas as pd
import requests

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    )
}

# 乐咕乐股成分股表按位置取值（表头常被 JSON-LD 污染，不能依赖列名）
# 0序号 1股票代码 2股票简称 3纳入时间 4申万3级
# 5细分概念（不采集） 6价格 7市盈率 8市盈率ttm 9市净率 10ROE(%) 11股息率
# 12市值(亿元) 13近1日涨幅 14近5日涨幅 15今年以来涨幅
# 16净利润增速(%) 17营收增速(%)
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
    """按列下标取值；列不存在或空值时返回空字符串。"""
    if df.shape[1] <= idx:
        return pd.Series([""] * len(df), index=df.index, dtype=object)
    s = df.iloc[:, idx].where(pd.notna(df.iloc[:, idx]), "")
    s = s.astype(str).str.strip()
    bad = {"nan", "None", "—", "-", "<NA>", "NaT"}
    return s.map(lambda x: "" if x in bad else x)


def fetch_third_cons(symbol: str) -> pd.DataFrame:
    url = f"https://legulegu.com/stockdata/index-composition?industryCode={symbol}"
    resp = requests.get(url, headers=HEADERS, timeout=60)
    resp.raise_for_status()
    df = pd.read_html(StringIO(resp.text))[0]

    # 至少要有代码/简称/纳入时间（下标 1..3）；行情列缺失则填空
    if df.shape[1] < 4:
        raise ValueError(f"成分股表格列数异常: {df.shape[1]}")

    out = pd.DataFrame({name: _series_at(df, idx) for idx, name in _COL_SPECS})

    # 过滤空行 / 无效代码
    out = out[out["股票代码"].str.len() > 0]
    out = out[~out["股票代码"].isin(["nan", "None", "-"])]
    return out.reset_index(drop=True)


if __name__ == "__main__":
    result = fetch_third_cons("850111.SI")
    print(result.head())
    print("columns", list(result.columns))
    print("count", len(result))
