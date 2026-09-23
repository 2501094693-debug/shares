"""国内期货：按交易所分类树、列表检索。

- ``taxonomy``  东财市场代码（m:113 等）
- ``fetcher``   东财 clist 拉取
- ``store``     分类列表缓存 + 全局搜索索引
- ``service``   API 门面
- ``api``       FastAPI 路由
"""
