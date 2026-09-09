"""A 股交易时段（上海时区），与前端 ``cnMarketPhase`` 对齐。

live：集合竞价 / 连续竞价 / 科创创业板盘后。
lunch：午休。closed：周末及其余时间。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Literal

CN_TZ = timezone(timedelta(hours=8))

MarketPhase = Literal["live", "lunch", "closed"]


def cn_now(now: datetime | None = None) -> datetime:
    if now is None:
        return datetime.now(CN_TZ)
    if now.tzinfo is None:
        return now.replace(tzinfo=CN_TZ)
    return now.astimezone(CN_TZ)


def market_phase(now: datetime | None = None) -> MarketPhase:
    """当前 A 股时段。"""
    stamp = cn_now(now)
    weekday = stamp.weekday()  # Mon=0 … Sun=6
    if weekday >= 5:
        return "closed"
    minutes = stamp.hour * 60 + stamp.minute + stamp.second / 60
    if (
        (9 * 60 + 15 <= minutes < 9 * 60 + 25)
        or (9 * 60 + 30 <= minutes < 11 * 60 + 30)
        or (13 * 60 <= minutes < 15 * 60)
        or (15 * 60 + 5 <= minutes < 15 * 60 + 31)
    ):
        return "live"
    if 11 * 60 + 30 <= minutes < 13 * 60:
        return "lunch"
    return "closed"


def is_cn_market_live(now: datetime | None = None) -> bool:
    """是否处于需要刷新最新一根 K 的时段。"""
    return market_phase(now) == "live"


# 常规收盘 15:00，科创/创业板盘后到 15:31。收盘快照以此为界。
_SESSION_CLOSE_HOUR = 15
_SESSION_CLOSE_MINUTE = 31
_SESSION_OPEN_HOUR = 9
_SESSION_OPEN_MINUTE = 15


def _at_clock(day: datetime, hour: int, minute: int) -> datetime:
    return day.replace(hour=hour, minute=minute, second=0, microsecond=0)


def last_session_close(now: datetime | None = None) -> datetime:
    """最近一次交易日盘后结束时刻（15:31）。周末回退到周五。"""
    stamp = cn_now(now)
    weekday = stamp.weekday()
    if weekday >= 5:
        friday = stamp - timedelta(days=weekday - 4)
        return _at_clock(friday, _SESSION_CLOSE_HOUR, _SESSION_CLOSE_MINUTE)
    today_close = _at_clock(stamp, _SESSION_CLOSE_HOUR, _SESSION_CLOSE_MINUTE)
    if stamp >= today_close:
        return today_close
    days_back = 3 if weekday == 0 else 1
    return _at_clock(stamp - timedelta(days=days_back), _SESSION_CLOSE_HOUR, _SESSION_CLOSE_MINUTE)


def today_session_open(now: datetime | None = None) -> datetime | None:
    """当日 9:15 开盘；周末返回 None。"""
    stamp = cn_now(now)
    if stamp.weekday() >= 5:
        return None
    return _at_clock(stamp, _SESSION_OPEN_HOUR, _SESSION_OPEN_MINUTE)


def today_lunch_start(now: datetime | None = None) -> datetime | None:
    """当日 11:30 午休开始；周末返回 None。"""
    stamp = cn_now(now)
    if stamp.weekday() >= 5:
        return None
    return _at_clock(stamp, 11, 30)
