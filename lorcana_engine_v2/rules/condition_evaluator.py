from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class ConditionContext:
    actor: int
    source_id: int | None = None
    target_id: int | None = None
    event_payload: dict[str, Any] | None = None


class ConditionEvaluator:
    def evaluate(self, state, ctx, raw_condition: Any, context: ConditionContext) -> bool:
        if raw_condition is None:
            return True
        if not isinstance(raw_condition, dict):
            return False
        kind = raw_condition.get("type") or raw_condition.get("kind")
        if kind in {None, "always"}:
            return True
        if kind in {"no-damage", "has-no-damage"}:
            target = context.target_id if context.target_id is not None else context.source_id
            return target is not None and state.cards[target].damage <= 0
        if kind == "not":
            return not self.evaluate(state, ctx, raw_condition.get("condition"), context)
        if kind == "and":
            return all(self.evaluate(state, ctx, item, context) for item in raw_condition.get("conditions", ()))
        if kind == "or":
            return any(self.evaluate(state, ctx, item, context) for item in raw_condition.get("conditions", ()))
        return False
