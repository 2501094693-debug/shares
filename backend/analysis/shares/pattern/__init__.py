"""形态：分组方案（groups OR / 至少 M/N）。"""

from analysis.shares.pattern.core import (
    analyze_one_pattern,
    assemble_pattern,
    load_pattern_scheme,
    normalize_pattern_params,
    pattern_fingerprint,
    screen_scheme,
)
from analysis.shares.pattern.scheme import (
    describe_scheme,
    evaluate_scheme,
    match_day,
    normalize_day_list,
    normalize_day_raw,
    normalize_scheme,
    scheme_fingerprint,
    scheme_has_rules,
)

__all__ = [
    "analyze_one_pattern",
    "assemble_pattern",
    "describe_scheme",
    "evaluate_scheme",
    "load_pattern_scheme",
    "match_day",
    "normalize_day_list",
    "normalize_day_raw",
    "normalize_pattern_params",
    "normalize_scheme",
    "pattern_fingerprint",
    "scheme_fingerprint",
    "scheme_has_rules",
    "screen_scheme",
]
