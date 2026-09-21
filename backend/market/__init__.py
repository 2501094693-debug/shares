"""市场行情包。

- ``api``      申万行业行情 FastAPI 路由
- ``sw``       行情树、资金流、东财数据源等实现
- ``shares``   成分股摊平，按涨跌排序
- ``steep``    最近几个交易日的涨停 / 跌停
- ``funds``    场内 ETF/LOF 与场外开放式基金
- ``industry`` 申万分类、成分股检索、地图标注
"""

from market.sw import service

__all__ = ["service"]
