"""公司新闻智能体包。

对外用法（需以 backend 为 Python 路径）::

    from news import collect_important_news
    # 或
    from news.agent import collect_important_news
"""

from .agent import collect_important_news

__all__ = ["collect_important_news"]
