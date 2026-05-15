"""Canonical source effect/ability/cost/target normalization helpers.

This module provides a single canonical mapping layer between Lorcanito source
dataclasses and LorcanaChamp engine identifiers. All card_logic, abilities,
static_effects, replacement_effects, and trigger_blocker_report modules should
import from here rather than using ad hoc isinstance(dict) checks.

Reference: Lorcanito lorcana-engine/src/runtime-moves/moves/core/play-card.ts,
  play-card-rules.ts, and effect-kind definitions.
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from lorcana_bot.state import GameState
    from lorcana_bot.engine import GameEngine


# ----------------------------------------------------------------------
# Effect kind canonicalization
# ----------------------------------------------------------------------
# Maps Lorcanito source effect kinds to LorcanaChamp EffectDef kind strings.

EFFECT_KIND_MAP: dict[str, str] = {
    # Lore changes
    "gain-lore": "gain_lore",
    "gain_lore": "gain_lore",
    "gain_lore_from_location": "gain_lore",  # treated as gain_lore
    "lose-lore": "lose_lore",
    "lose_lore": "lose_lore",
    # Damage
    "deal-damage": "deal_damage",
    "deal_damage": "deal_damage",
    "put-damage": "deal_damage",  # put-damage -> deal_damage in our model
    "put_damage": "deal_damage",
    "remove-damage": "remove_damage",
    "remove_damage": "remove_damage",
    # Movement
    "return-to-hand": "return_to_hand",
    "return_to_hand": "return_to_hand",
    "return-to-deck": "put_on_top",  # or discard depending on context
    "move-to-location": "move_to_location",
    "move_to_location": "move_to_location",
    "put-under": "put_under",
    "put_under": "put_under",
    "move-cards-from-under": "move_cards_from_under",
    "move_cards_from_under": "move_cards_from_under",
    # Banish / discard
    "banish": "banish",
    "discard": "discard",
    # Ready / exert
    "ready": "ready",
    "exert": "exert",
    # Deck / hand
    "draw": "draw",
    "scry": "scry",
    "search-deck": "search_deck",
    "look_at_top": "scry",  # scry-like operation
    "reveal-top-card": "reveal_top_card",
    "reveal_top_card": "reveal_top_card",
    "reveal-hand": "reveal_hand",
    "reveal_hand": "reveal_hand",
    "reveal-cards": "reveal_cards",
    "reveal_cards": "reveal_cards",
    "reveal-and-route": "reveal_and_route",
    "reveal_and_route": "reveal_and_route",
    "put-on-top": "put_on_top",
    "put_on_top": "put_on_top",
    "put-on-bottom": "put_on_bottom",
    "put_on_bottom": "put_on_bottom",
    "put-in-hand": "put_card_in_hand",
    "put_card_in_hand": "put_card_in_hand",
    "put-in-discard": "put_card_in_discard",
    "put_card_in_discard": "put_card_in_discard",
    "shuffle-deck": "shuffle_deck",
    "shuffle_deck": "shuffle_deck",
    "name-a-card": "name_a_card",
    "name_a_card": "name_a_card",
    # Keywords / modifiers
    "gain-keyword": "keyword_grant",
    "gain_keyword": "keyword_grant",
    "modify-stat": "temporary_modifier",
    "modify_stat": "temporary_modifier",
    "cost-reduction": "cost_reduction",
    "cost_reduction": "cost_reduction",
    # Control flow (LorcanaChamp kinds)
    "sequence": "sequence",
    "optional": "optional",
    "choice": "choice",
    "or": "choice",
    "conditional": "conditional",
    "for-each": "for_each",
    "for_each": "for_each",
    # Support
    "support": "support",
    # Quest
    "quest": "quest",
}


def to_engine_effect_kind(kind: str) -> str:
    """Convert a Lorcanito source effect kind to LorcanaChamp EffectDef kind."""
    normalized = kind.lower().strip().replace("-", "_").replace(" ", "_")
    return EFFECT_KIND_MAP.get(normalized, EFFECT_KIND_MAP.get(kind, normalized))


# ----------------------------------------------------------------------
# Source dataclass normalization helpers
# ----------------------------------------------------------------------
# Accepts either a Lorcanito source dataclass or a raw dict.

def source_ability_kind(obj: Any) -> str | None:
    """Get the kind (kind/kind) from a source ability object."""
    if obj is None:
        return None
    if hasattr(obj, "kind"):
        return getattr(obj, "kind", None)
    if isinstance(obj, dict):
        return obj.get("kind") or obj.get("type")
    return None


def source_ability_effects(obj: Any) -> tuple:
    """Get the effects tuple from a source ability object."""
    if obj is None:
        return ()
    if hasattr(obj, "effects"):
        effs = getattr(obj, "effects", None)
        if effs is not None:
            return tuple(effs)
    if isinstance(obj, dict):
        return tuple(obj.get("effects") or ())
    return ()


def source_ability_costs(obj: Any) -> tuple:
    """Get the costs tuple from a source ability object."""
    if obj is None:
        return ()
    if hasattr(obj, "costs"):
        cs = getattr(obj, "costs", None)
        if cs is not None:
            return tuple(cs)
    if isinstance(obj, dict):
        return tuple(obj.get("costs") or ())
    return ()


def source_ability_trigger(obj: Any) -> Any:
    """Get the trigger from a source ability object."""
    if obj is None:
        return None
    if hasattr(obj, "trigger"):
        return getattr(obj, "trigger", None)
    if isinstance(obj, dict):
        return obj.get("trigger")
    return None


def source_effect_kind(obj: Any) -> str | None:
    """Get the effect kind from a source effect object."""
    if obj is None:
        return None
    if hasattr(obj, "kind"):
        return getattr(obj, "kind", None)
    if isinstance(obj, dict):
        return obj.get("kind") or obj.get("type")
    return None


def source_effect_target(obj: Any) -> str | None:
    """Get the target alias from a source effect object."""
    if obj is None:
        return None
    if hasattr(obj, "target"):
        return getattr(obj, "target", None)
    if isinstance(obj, dict):
        return obj.get("target")
    return None


def source_effect_amount(obj: Any) -> int | None:
    """Get the amount from a source effect object."""
    if obj is None:
        return None
    if hasattr(obj, "amount"):
        amt = getattr(obj, "amount", None)
        if amt is not None:
            return int(amt)
    if isinstance(obj, dict):
        raw = obj.get("amount")
        if raw is not None:
            return int(raw)
    return None


def source_effect_condition(obj: Any) -> Any:
    """Get the condition from a source effect object."""
    if obj is None:
        return None
    if hasattr(obj, "condition"):
        return getattr(obj, "condition", None)
    if isinstance(obj, dict):
        return obj.get("condition")
    return None


# ----------------------------------------------------------------------
# Target alias normalization
# ----------------------------------------------------------------------
# Maps Lorcanito selector keys to LorcanaChamp effect target aliases.

TARGET_ALIAS_MAP: dict[str, str] = {
    "self": "self",
    "source": "source",
    "controller": "controller",
    "opponent": "opponent",
    "each_opponent": "each_opponent",
    "event_source": "event_source",
    "event_target": "event_target",
    "trigger_subject": "trigger_subject",
    "current_targets": "current_targets",
    "chosen_character": "chosen_character",
    "chosen_opposing_character": "chosen_opposing_character",
    "chosen_player": "chosen_player",
    "your_characters": "your_characters",
    "your_other_characters": "your_other_characters",
    "opposing_characters": "opposing_characters",
    "all_characters": "all_characters",
    "damaged_characters": "damaged_characters",
    "opposing_damaged_characters": "opposing_damaged_characters",
    "your_items": "your_items",
    "your_locations": "your_locations",
    "any_character": "any_character",
    "any_item": "any_item",
    "any_location": "any_location",
    # Lorcanito aliases
    "you": "controller",
    "opposing_character": "chosen_opposing_character",
    "opposing_char": "chosen_opposing_character",
}


def source_target_alias(obj: Any) -> str | None:
    """Normalize a target/selector from a source effect to engine target alias."""
    raw = source_effect_target(obj)
    if raw is None:
        return None
    if isinstance(raw, str):
        return TARGET_ALIAS_MAP.get(raw, raw)
    # Object query — represented as dict in Lorcanito source
    if isinstance(raw, dict):
        # Return the raw dict for query-based targeting (handled separately)
        return raw
    return None


def source_target_selector(obj: Any) -> dict[str, Any] | None:
    """Extract selector query dict from a source effect (for complex targeting)."""
    raw = source_effect_target(obj)
    if isinstance(raw, dict):
        return raw
    return None


# ----------------------------------------------------------------------
# Cost kind normalization
# ----------------------------------------------------------------------

COST_KIND_MAP: dict[str, str] = {
    "ink": "ink",
    "spend_ink": "ink",
    "exert_source": "exert_source",
    "exert": "exert_source",
    "banish_self": "banish_self",
    "banish": "banish_self",
    "discard": "discard",
    "discard_random": "discard",  # marked random in raw
    "tap": "exert_source",
    "ready": "ready",
}


def to_engine_cost_kind(kind: str) -> str:
    """Convert a Lorcanito source cost kind to LorcanaChamp cost kind."""
    normalized = kind.lower().strip().replace("-", "_").replace(" ", "_")
    return COST_KIND_MAP.get(normalized, normalized)


# ----------------------------------------------------------------------
# Static effect kind normalization
# ----------------------------------------------------------------------

STATIC_EFFECT_KIND_MAP: dict[str, str] = {
    "modify-stat": "modify_stat",
    "modify_stat": "modify_stat",
    "gain-keyword": "gain_keyword",
    "gain_keyword": "gain_keyword",
    "cost-reduction": "cost_reduction",
    "cost_reduction": "cost_reduction",
    "restriction": "restriction",
    "property-modification": "property_modification",
    "property_modification": "property_modification",
}


def to_engine_static_kind(kind: str) -> str:
    """Convert a Lorcanito static effect kind to LorcanaChamp static effect kind."""
    normalized = kind.lower().strip().replace("-", "_").replace(" ", "_")
    return STATIC_EFFECT_KIND_MAP.get(normalized, normalized)


# ----------------------------------------------------------------------
# Replacement effect kind normalization
# ----------------------------------------------------------------------

REPLACEMENT_KIND_MAP: dict[str, str] = {
    "prevent-damage": "prevent_damage",
    "prevent_damage": "prevent_damage",
    "replace-banish": "replace_banish",
    "replace_banish": "replace_banish",
    "redirect-damage": "redirect_damage",
    "redirect_damage": "redirect_damage",
}


def to_engine_replacement_kind(kind: str) -> str:
    """Convert a Lorcanito replacement effect kind to LorcanaChamp replacement kind."""
    normalized = kind.lower().strip().replace("-", "_").replace(" ", "_")
    return REPLACEMENT_KIND_MAP.get(normalized, normalized)


# ----------------------------------------------------------------------
# Trigger event normalization
# ----------------------------------------------------------------------
# Maps Lorcanito trigger event names to LorcanaChamp canonical trigger names.

TRIGGER_EVENT_MAP: dict[str, str] = {
    "play": "play",
    "quest": "quest",
    "challenge": "challenge",
    "banish": "banish",
    "banish-in-challenge": "banish-in-challenge",
    "start-turn": "start-turn",
    "start_turn": "start-turn",
    "end-turn": "end-turn",
    "end_turn": "end-turn",
    "ink": "ink",
    "challenged": "challenged",
    "deal-damage": "deal-damage",
    "deal_damage": "deal-damage",
    "damage": "deal-damage",
    "discard": "discard",
    "draw": "draw",
    "return-to-hand": "return-to-hand",
    "return_to_hand": "return-to-hand",
    "ready": "ready",
    "exert": "exert",
    "move": "move",
    "gain-lore": "gain-lore",
    "gain_lore": "gain-lore",
    "lose-lore": "lose-lore",
    "lose_lore": "lose-lore",
    "support": "support",
    "leave-play": "leave-play",
    "be-chosen": "be-chosen",
    "be_chosen": "be-chosen",
    "boost": "boost",
}


def to_canonical_trigger(event: str) -> str:
    """Convert a Lorcanito trigger event name to LorcanaChamp canonical name."""
    normalized = event.lower().strip().replace("-", "_")
    return TRIGGER_EVENT_MAP.get(normalized, TRIGGER_EVENT_MAP.get(event, event))