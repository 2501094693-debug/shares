"""组合：统一 AST（筛选 + 形态 + 对比一次评估）。"""

from analysis.shares.common.ast import (
    describe_tree,
    evaluate_tree,
    from_compare,
    from_pattern,
    from_screen,
    load_compose_tree,
    normalize_compose_params,
    normalize_tree,
    tree_fingerprint,
    tree_has_rules,
)
from analysis.shares.compose.core import (
    analyze_one_compose,
    assemble_compose,
    screen_compose,
)

__all__ = [
    "analyze_one_compose",
    "assemble_compose",
    "describe_tree",
    "evaluate_tree",
    "from_compare",
    "from_pattern",
    "from_screen",
    "load_compose_tree",
    "normalize_compose_params",
    "normalize_tree",
    "screen_compose",
    "tree_fingerprint",
    "tree_has_rules",
]
