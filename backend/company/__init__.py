"""单只股票的详情：盘口、K 线、画像。

- ``statistics``  东财 / 腾讯盘口指标
- ``line``        K 线与逐笔成交
- ``news``        巨潮公告（orgId 解析 / 分类 / 调研 / PDF）
- ``profile``     详情页组装（行业归属来自 ``industry`` 索引）
- ``api``         FastAPI 路由

交易所公告、七报七网、研报仍在同级的 ``message`` 包。
"""
