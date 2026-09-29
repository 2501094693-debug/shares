"""财务数据、盈利能力与估值诊断智能体。

架构（与其他智能体无关）：
  Collect → Ledger（结构化台账）→ Gauge（规则仪表盘）→ Brief（分节叙述）→ Save
"""

from agent.fundamentals_agent.pipeline import run_fundamentals

__all__ = ["run_fundamentals"]
