"""单只股票的详情：盘口、K 线、画像、资讯。

- ``statistics``  东财 / 腾讯盘口指标
- ``line``        K 线与逐笔成交
- ``news``        采集源 + 详情页/画像集成（``cninfo`` · ``exchange`` · ``press`` · ``eastmoney`` · ``tonghuashun`` · ``xueqiu`` · ``feed`` · ``profile``）
- ``profile``     详情页组装（行业归属来自 ``industry`` 索引）
- ``api``         FastAPI 路由
"""
