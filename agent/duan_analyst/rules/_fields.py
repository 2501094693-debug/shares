"""段永平看业务：复用东财字段，并补毛利率、杠杆。"""

from __future__ import annotations

from agent.buffett_analyst.rules._fields import (  # noqa: F401
    CAPEX_FIELDS,
    EQUITY_FIELDS,
    NET_PROFIT_FIELDS,
    OCF_FIELDS,
    REVENUE_FIELDS,
    TOTAL_ASSETS_FIELDS,
    TOTAL_LIAB_FIELDS,
)

GROSS_MARGIN_FIELDS = ["XSMLL"]
NET_MARGIN_FIELDS = ["XSJLL"]
ROE_FIELDS = ["ROEJQ", "WEIGHTAVG_ROE"]
DEBT_RATIO_FIELDS = ["ZCFZL", "DEBT_ASSET_RATIO"]
