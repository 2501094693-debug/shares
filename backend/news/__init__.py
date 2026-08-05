"""公司新闻智能体包。

对外用法::

    from news import collect_important_news
    # 或
    from news.agent import collect_important_news
"""

from news.agent import collect_important_news

__all__ = ["collect_important_news"]
