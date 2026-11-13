"""估值分析模块：DCF 绝对估值 + 相对估值 + 安全边际。

复用系统现有能力：
- company.analysis.financialreport.engine  —— 财报八看（FCF/OCF/资本开支/负债/现金/ROE/毛利率等）
- company.statistics.quote.fetch.fetch_pe_history —— 历史 PE/PB/PS 每日序列
- company.profile.get_stock_profile —— 当前价/总市值/总股本/行业
- company.analysis.competition.compare.compare_peers —— 同业横截面基准
"""

from __future__ import annotations

from .engine import run_valuation, ValuationInput, ValuationResult
from .dcf import dcf_valuate, DcfAssumptions, DcfResult
from .relative import relative_valuate, RelativeResult

__all__ = [
    "run_valuation",
    "ValuationInput",
    "ValuationResult",
    "dcf_valuate",
    "DcfAssumptions",
    "DcfResult",
    "relative_valuate",
    "RelativeResult",
]
