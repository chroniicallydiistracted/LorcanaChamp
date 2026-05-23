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
    """Runtime context carried through action-effect resolution.

    actor is always the original effect controller / semantic player.
    chooser is the current player supplying input when different from actor.

    This dataclass is frozen intentionally. Do not mutate it. Use
    dataclasses.replace() or helper builders in EffectResolver.
    """
    actor: int
    source: int | None = None
    target: int | None = None
    choice: Any | None = None
    optional_choices: dict[str, bool] = field(default_factory=dict)

    # Current chooser, if a nested chooser/optional/opponent choice is active.
    chooser: int | None = None

    # Trigger context fields for proper effect resolution.
    event: Any | None = None
    event_payload: dict[str, Any] = field(default_factory=dict)
    pending_trigger_id: str | None = None
    trigger_source: int | None = None
    trigger_subject: int | None = None

    # Lorcanito-aligned selection state.
    current_targets: tuple[int, ...] = ()
    context_targets: tuple[int, ...] = ()
    slotted_targets: dict[str, Any] | None = None
    destinations: tuple[dict[str, Any], ...] = ()

    # Additional pending/action resolution input.
    named_card: str | None = None
    amount_choice: int | None = None
    choice_index: int | None = None
    resolve_optional: bool | None = None
    enter_play_exerted: bool | None = None
    target_selection_resolved: bool = False

    # Lorcanito sequence resolution allows a targeted child step to find no
    # valid targets, mark lastEffectPerformed=false, and continue resolving
    # later sequence steps. Direct non-sequence leaf resolution should still
    # raise when a required target is missing.
    allow_missing_targets: bool = False

    # Result state used by if-you-do / downstream dynamic effects.
    last_effect_performed: bool = False
    last_effect_target_count: int = 0


SUPPORTED_EFFECT_KINDS = frozenset(
    {
        "draw",
        "gain_lore",
        "lose_lore",
        "deal_damage",
        "move_damage",
        "move_to_location",
        "remove_damage",
        "banish",
        "discard",
        "return_to_hand",
        "return_from_discard",
        "ready",
        "exert",
        "cost_reduction",
        "additional_inkwell",
        "pay_cost",
        "keyword_grant",
        "temporary_modifier",
        "choice",
        "select_target",
        "restriction",
        "optional",
        "sequence",
        "conditional",
        "for_each",
        # B4: Scry, search, reveal, and deck routing effects
        "scry",
        "look_at_top",
        "reveal_top_card",
        "count",
        "reveal_hand",
        "reveal_cards",
        "search_deck",
        "put_card_in_hand",
        "put_card_on_top",
        "put_card_on_bottom",
        "put_card_in_discard",
        "shuffle_deck",
        "shuffle_into_deck",
        "name_a_card",
        "reveal_and_route",
        "put_into_inkwell",
        "draw_until_hand_size",
        "play_card",
        "grant_ability",
        "grant_abilities_while_here",
        "grant_discard_inkability",
        "create_replacement_effect",
        "return_random_from_inkwell",
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
