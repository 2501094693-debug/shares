"""最近几个交易日的涨停 / 跌停股票，按天区分。"""

from .service import DEFAULT_DAYS, service

__all__ = ["DEFAULT_DAYS", "service"]
