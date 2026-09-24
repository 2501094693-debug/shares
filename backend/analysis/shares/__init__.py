"""日线多日条件筛选。

子包：

- ``common``  共用：候选池、指标、条件、配置、任务服务、AST
- ``screen``  筛选：按交易日区间条件
- ``compare`` 对比：跨日指标比较 / 趋势
- ``pattern`` 形态：分组方案（groups / M/N）
- ``compose`` 组合：统一 AST（三种能力一次评估）

用法示例见 ``python -m analysis.shares --help``。
"""

from analysis.shares.common import list_trade_days, service
from analysis.shares.compare import screen_compare
from analysis.shares.compose import screen_compose
from analysis.shares.pattern import screen_scheme
from analysis.shares.screen import screen_shares

__all__ = [
    "list_trade_days",
    "screen_shares",
    "screen_scheme",
    "screen_compare",
    "screen_compose",
    "service",
]
