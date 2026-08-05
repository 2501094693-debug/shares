"""调试：用 akshare 拉一只股票的公告，检查列名与日期范围。

用法（在 backend 目录下）::

    python -m news.scripts.run_test_notices

注意：begin_date / end_date 必须是 YYYYMMDD（与线上 fetch_notices 一致）。
"""

from __future__ import annotations

import sys

import akshare as ak


def main() -> int:
    df = ak.stock_individual_notice_report(
        security="600719",
        symbol="全部",
        begin_date="20240801",
        end_date="20260803",
    )
    print("COLS", list(df.columns))
    print("LEN", len(df))
    if df.empty:
        return 0

    print("ROW0", df.iloc[0].to_dict())
    for col in df.columns:
        name = str(col)
        if "日期" in name or "时间" in name or "date" in name.lower():
            series = df[col].astype(str)
            print("DATECOL", col, series.min(), series.max())
    return 0


if __name__ == "__main__":
    sys.exit(main())
