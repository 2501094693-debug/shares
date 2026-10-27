"""两路数据源的适配层：分时成交 + 资金动向。

都走系统已有实现，这里只做「统一组织 + 失败降级」，不新增网络接口：

- 分时成交：``company.line.fetcher.fetch_ticks``
  东财 3 秒逐笔快照优先，腾讯兜底，同花顺（登录后）最后；自带磁盘缓存。
- 资金动向：``scope=big_deal``（同花顺 HQ 大资金动向）→ 真实大单逐笔。

大单明细拉不到时整条链路不失败：退化为只用分时成交自身推断，并在 ``notes``
里标注，避免一个源抖动就整批数据作废。
"""

from __future__ import annotations

import logging
from typing import Any

from core.codes import normalize_code

logger = logging.getLogger(__name__)


def load_ticks(code: str, *, day: str = "", force: bool = False) -> dict[str, Any]:
    """分时成交（逐笔快照）。空包也算成功，由调用方判断。"""
    from company.line.fetcher import fetch_ticks

    norm = normalize_code(code) or code
    pack = fetch_ticks(norm, pos=0, force=force, day=day)
    if not isinstance(pack, dict):
        return {"code": norm, "items": [], "source": ""}
    pack.setdefault("items", [])
    return pack


def load_big_deals(
    code: str,
    *,
    day: str = "",
    force: bool = False,
) -> tuple[dict[str, Any], str]:
    """同花顺 HQ 大资金动向（真实大单逐笔）。返回 ``(pack, error)``。"""
    from company.statistics.fundflow.fetcher import get_fund_flow

    norm = normalize_code(code) or code
    try:
        pack = get_fund_flow(
            norm,
            scope="big_deal",
            source="tonghuashun",
            limit=0,
            # 门槛由 window 求解器按 threshold 统一切，这里全量取
            min_amount=0.0,
            force=force,
            day=day,
        )
    except Exception as exc:  # noqa: BLE001
        logger.info("deal big_deal skip %s: %s", norm, exc)
        return {"code": norm, "items": [], "source": ""}, str(exc)
    if not isinstance(pack, dict):
        return {"code": norm, "items": [], "source": ""}, "大单明细返回非字典"
    pack.setdefault("items", [])
    return pack, ""
