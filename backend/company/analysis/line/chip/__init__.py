"""筹码分布（CYQ）：同花顺手机端日线接口 + 本地换手衰减推演。

同花顺手机端个股日线上的「筹码分布」由日线 OHLC + 换手率滚动推演：

- 首日：全部流通筹码按当日三角分布铺满 ``[low, high]``；
- 每日：旧筹码按换手率衰减，当日成交按三角分布注入；
- 输出：获利比例 / 平均成本 / 70%·90% 成本区间 / 集中度 / 筹码峰。

``ths`` 负责取数（``d.10jqka.com.cn/v6/line/hs_{code}/01/*.js``），
``core`` 负责计算，``service`` 负责编排与回退，``api`` 暴露 HTTP 路由。
"""

from company.analysis.line.chip.core import (
    DEFAULT_BINS,
    DEFAULT_DECAY,
    run_chip,
    summarize_chips,
)
from company.analysis.line.chip.service import chip_meta, load_daily, run_symbol, to_payload

__all__ = [
    "DEFAULT_BINS",
    "DEFAULT_DECAY",
    "chip_meta",
    "load_daily",
    "run_chip",
    "run_symbol",
    "summarize_chips",
    "to_payload",
]
