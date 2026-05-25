from __future__ import annotations

from lorcana_engine_v2.core.context import (
    MoveDefinition,
    MoveEnumerationContext,
    MoveExecutionContext,
    MoveValidationContext,
)
from lorcana_engine_v2.core.results import RuntimeValidationResult


MoveValidationResult = RuntimeValidationResult


def input_card_id(context: MoveValidationContext | MoveExecutionContext) -> str | None:
    raw = context.args.get("cardId") or context.args.get("card_id")
    if raw is None:
        return None
    return str(raw)


__all__ = [
    "MoveDefinition",
    "MoveEnumerationContext",
    "MoveExecutionContext",
    "MoveValidationContext",
    "MoveValidationResult",
    "input_card_id",
]
