"""Reusable data-quality rules and the engine that applies them."""

from core.quality.engine import QualityEngine, rules_for
from core.quality.rules import (
    DuplicateRule,
    GapRule,
    NotNullRule,
    RangeRule,
    Rule,
    RuleResult,
)

__all__ = [
    "DuplicateRule",
    "GapRule",
    "NotNullRule",
    "QualityEngine",
    "RangeRule",
    "Rule",
    "RuleResult",
    "rules_for",
]
