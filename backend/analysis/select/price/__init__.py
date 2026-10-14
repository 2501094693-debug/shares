"""价格区间位置：目标交易日 OHLC 在区间同类价格中的排名/总数/百分比。"""
from __future__ import annotations

from analysis.select.price.service import FIELDS, price_position

__all__ = ["FIELDS", "ORDER_ASC", "ORDER_DESC", "price_position"]
ORDER_ASC = "asc"
ORDER_DESC = "desc"
