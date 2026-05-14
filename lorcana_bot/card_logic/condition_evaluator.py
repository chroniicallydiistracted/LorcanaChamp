from __future__ import annotations

from .conditions import SourceConditionDef


def is_simple_condition_executable(condition: SourceConditionDef | None) -> bool:
    """Milestone B0 placeholder for future source-condition execution."""

    return condition is None or condition.kind in {"always", "target_damaged"}
