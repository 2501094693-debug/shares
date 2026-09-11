import sys

sys.path.insert(0, ".")
from core.http import browser_get

url = "https://datacenter-web.eastmoney.com/api/data/v1/get"
reports = [
    "RPT_ECONOMICVALUE_JPAN",
    "RPT_ECONOMICVALUE_BRITAIN",
    "RPT_ECONOMICVALUE_GER",
    "RPT_ECONOMICVALUE_USA",
    "RPT_ECONOMICVALUE_HK",
    "RPT_ECONOMICVALUE_AUSTRALIA",
    "RPT_ECONOMICVALUE_CA",
    "RPT_ECONOMICVALUE_CH",
    "RPT_ECONOMICVALUE_INDIA",
]

for emg_num in range(342250, 342280):
    emg = f"EMG00{emg_num}"
    for report in reports:
        params = {
            "reportName": report,
            "columns": "ALL",
            "filter": f'(INDICATOR_ID="{emg}")',
            "pageNumber": "1",
            "pageSize": "3",
            "sortColumns": "REPORT_DATE",
            "sortTypes": "-1",
            "source": "WEB",
            "client": "WEB",
        }
        try:
            r = browser_get(url, params=params, timeout=5)
            d = r.json()
            rows = (d.get("result") or {}).get("data") or []
            if rows:
                row = rows[0]
                print(emg, report, row.get("INDICATOR_NAME"), row.get("VALUE"), row.get("REPORT_DATE"))
        except Exception:
            pass
