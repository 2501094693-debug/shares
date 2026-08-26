"""个股社区情绪：采集源 + CLI。

采集源：
  - ``eastmoney``    东方财富社区（股吧帖子 / 正文 / 回复 / 搜索 / 人气榜 / 千股千评）
  - ``xueqiu``       雪球社区（讨论帖 / 正文 / 评论 / 搜索 / 热股榜 / 热帖 / 关注快照）
  - ``tonghuashun``  同花顺圈子（手机讨论流 / 评论预览 / 讨论热度）

    python -m company.emotion 600519
    python -m company.emotion.eastmoney 600519 --kind hot --json
    python -m company.emotion.xueqiu 600519 --replies --json
    python -m company.emotion.xueqiu --post 406619710 --replies
    python -m company.emotion.tonghuashun 600519 --json
"""

from company.emotion.eastmoney import (
    KINDS,
    SORTS,
    SOURCE,
    fetch_article,
    fetch_company,
    fetch_hot_list,
    fetch_posts,
    fetch_rank,
    fetch_replies,
    fetch_scores,
    list_page_url,
    main,
    post_url,
    query_hot_page,
    query_post_page,
    query_rank_history,
    query_rank_intraday,
    query_reply_page,
    query_scores,
    query_search_page,
    rank_page_url,
    resolve_kind,
    resolve_sort,
    scores_page_url,
    search_page_url,
    search_posts,
)

__all__ = [
    "KINDS",
    "SORTS",
    "SOURCE",
    "fetch_article",
    "fetch_company",
    "fetch_hot_list",
    "fetch_posts",
    "fetch_rank",
    "fetch_replies",
    "fetch_scores",
    "list_page_url",
    "main",
    "post_url",
    "query_hot_page",
    "query_post_page",
    "query_rank_history",
    "query_rank_intraday",
    "query_reply_page",
    "query_scores",
    "query_search_page",
    "rank_page_url",
    "resolve_kind",
    "resolve_sort",
    "scores_page_url",
    "search_page_url",
    "search_posts",
]
