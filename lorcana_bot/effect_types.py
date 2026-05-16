from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class ConditionContext:
    """Context for evaluating trigger conditions and effect conditions.

    This dataclass provides the runtime context for condition evaluation,
    including actor, source, target, event information, and board state.
    Used in both trigger matching and bag resolution recheck.
    """
    actor: int  # Controller of the card with the ability
    controller: int  # Who is evaluating (same as actor for most cases)
    source: int | None  # Instance ID of the card with the ability
    target: int | None  # Target of the effect/action
    event: Any | None  # GameEvent or PendingTriggeredEvent that triggered this
    event_payload: dict[str, Any]  # Extended payload data
    turn_player: int  # Currently active player
    # B2: Extended context for advanced conditions
    subject_card_id: int | None = None  # Subject of the trigger event
    attacker_id: int | None = None  # Challenger in challenge events
    defender_id: int | None = None  # Defended character in challenge events
    happened_in_challenge: bool = False  # Whether event happened in challenge


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
        # B4: Scry, search, reveal, and deck routing effects
        "scry",
        "look_at_top",
        "reveal_top_card",
        "reveal_hand",
        "reveal_cards",
        "search_deck",
        "put_card_in_hand",
        "put_card_on_top",
        "put_card_on_bottom",
        "put_card_in_discard",
        "shuffle_deck",
        "name_a_card",
        "reveal_and_route",
    }
)

# Resolution requirement kinds for pending effects
RESOLUTION_REQUIREMENTS = frozenset({
    "choice",
    "optional",
    "named_card",
    "amount",
    "destination",
    "ordering",
    "opponent_choice",
    "scry_ordering",
    "reveal_routing",
    "search_selection",
    "reveal_selection",
})
