from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class EffectResolutionContext:
    actor: int
    source: int | None = None
    target: int | None = None
    choice: Any | None = None
    optional_choices: dict[str, bool] = field(default_factory=dict)
    # B2: Trigger context fields for proper effect resolution
    event: Any | None = None
    event_payload: dict[str, Any] = field(default_factory=dict)
    pending_trigger_id: str | None = None
    trigger_source: int | None = None
    trigger_subject: int | None = None
    current_targets: tuple[int, ...] = ()


SUPPORTED_EFFECT_KINDS = frozenset(
    {
        "draw",
        "gain_lore",
        "lose_lore",
        "deal_damage",
        "remove_damage",
        "banish",
        "discard",
        "return_to_hand",
        "ready",
        "exert",
        "cost_reduction",
        "keyword_grant",
        "temporary_modifier",
        "choice",
        "optional",
        "sequence",
        "conditional",
        "for_each",
    }
)
