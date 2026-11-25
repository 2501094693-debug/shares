"""股性（gene）：按 MACD 金叉 / 即将金叉观察后续 DIF≥DEA 段涨跌幅。

- ``analyze_gene``            主入口：拉日线后扫描
- ``analyze_gene_from_macd``  纯函数：在已有 MACD 序列上计算
- ``nearest_prior_extrema``   金叉日相对此前最近峰/谷贴近度
- ``resolve_preset``          两套默认参数 ``10,20,7`` / ``12,26,9``
"""

from __future__ import annotations

from company.analysis.line.gene.config import (
    ALLOWED_PRESETS,
    DEFAULT_EXTREMA_LAYERS,
    DEFAULT_PRESET,
    MACD_PRESETS,
)
from company.analysis.line.gene.core import (
    analyze_gene_from_macd,
    nearest_prior_extrema,
    resolve_preset,
)
from company.analysis.line.gene.service import analyze_gene

__all__ = [
    "ALLOWED_PRESETS",
    "DEFAULT_EXTREMA_LAYERS",
    "DEFAULT_PRESET",
    "MACD_PRESETS",
    "analyze_gene",
    "analyze_gene_from_macd",
    "nearest_prior_extrema",
    "resolve_preset",
]
