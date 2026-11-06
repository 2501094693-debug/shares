"""同花顺个股「五日」分时成交（精确到秒）。

入口：``fetch_fivedays`` / ``fetch_day``。
"""

from company.line.fivedays.ths import fetch_day, fetch_fivedays

__all__ = ["fetch_day", "fetch_fivedays"]
