"""股票数据：成分股索引、盘口、K 线、注册地。

子包：
- ``common``  市场代码 / HTTP / 格式化 / TTL 缓存（包内共享）
- ``index``   成分股拉取 + 全市场搜索索引
- ``quote``   个股盘口
- ``kline``   K 线 / 分时
- ``geo``     上市公司注册地

行业树在 ``data.industry``，本包只通过回调消费三级行业的 code/name。
调用方按子包导入，例如 ``from data.stocks.quote import fetch_stock_quote``。
"""
