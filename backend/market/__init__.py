"""申万行业行情包。

- ``api``    FastAPI 路由
- ``sw``     行情树、资金流、东财数据源等实现
- ``steep``  最近几个交易日的涨停 / 跌停
"""

from market.sw import service

__all__ = ["service"]
