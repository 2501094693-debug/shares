import akshare as ak
df = ak.stock_individual_notice_report(
    security="600719",
    symbol="全部",
    begin_date="2024-08-01",
    end_date="2026-08-03",
)
print("COLS", list(df.columns))
print("LEN", len(df))
if not df.empty:
    print("ROW0", df.iloc[0].to_dict())
    print("MIN", df.iloc[:, :].astype(str).head())
    for c in df.columns:
        if "日期" in str(c) or "时间" in str(c) or "date" in str(c).lower():
            print("DATECOL", c, df[c].astype(str).min(), df[c].astype(str).max())
