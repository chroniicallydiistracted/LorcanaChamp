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
    """Get effect definitions from a source ability object.

    Supports:
    - SourceAbilityDef.effects
    - SourceAbilityDef.raw["effect"], raw["effects"], raw["staticEffect"], raw["replacementEffect"]
    - raw dict equivalents
    """
    if obj is None:
        return ()

    if hasattr(obj, "effects"):
        effs = getattr(obj, "effects", None)
        if effs:
            return tuple(effs)

    raw = getattr(obj, "raw", None)
    if isinstance(raw, dict):
        raw_effects = (
            raw.get("effects")
            or raw.get("effect")
            or raw.get("staticEffect")
            or raw.get("replacementEffect")
        )
        if raw_effects is None:
            return ()
        if isinstance(raw_effects, (list, tuple)):
            return tuple(raw_effects)
        return (raw_effects,)

    if isinstance(obj, dict):
        raw_effects = (
            obj.get("effects")
            or obj.get("effect")
            or obj.get("staticEffect")
            or obj.get("replacementEffect")
        )
        if raw_effects is None:
            return ()
        if isinstance(raw_effects, (list, tuple)):
            return tuple(raw_effects)
        return (raw_effects,)

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


def source_effect_target(obj: Any) -> Any:
    """Get the target object from a source effect object."""
    if obj is None:
        return None
    if hasattr(obj, "target"):
        return getattr(obj, "target", None)
    raw = getattr(obj, "raw", None)
    if isinstance(raw, dict) and "target" in raw:
        return raw.get("target")
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


def _normalize_target_string(value: str) -> str:
    """Normalize a raw Lorcanito target alias/selector into an engine target alias."""
    raw = value.strip()
    lowered = raw.lower().replace("-", "_").replace(" ", "_")
    uppered = raw.upper()

    if raw in TARGET_ALIAS_MAP:
        return TARGET_ALIAS_MAP[raw]
    if lowered in TARGET_ALIAS_MAP:
        return TARGET_ALIAS_MAP[lowered]
    if uppered in TARGET_ALIAS_MAP:
        return TARGET_ALIAS_MAP[uppered]

    alias_map = {
        "SELF": "self",
        "SOURCE": "source",
        "CONTROLLER": "controller",
        "YOU": "controller",
        "OPPONENT": "opponent",
        "EACH_OPPONENT": "each_opponent",
        "EVENT_SOURCE": "event_source",
        "EVENT_TARGET": "event_target",
        "TRIGGER_SUBJECT": "trigger_subject",
        "YOUR_CHARACTERS": "your_characters",
        "YOUR_OTHER_CHARACTERS": "your_other_characters",
        "OPPOSING_CHARACTERS": "opposing_characters",
        "ALL_OPPOSING_CHARACTERS": "opposing_characters",
        "ALL_CHARACTERS": "all_characters",
        "ANY_CHARACTER": "any_character",
        "CHOSEN_CHARACTER": "chosen_character",
        "CHOSEN_OPPOSING_CHARACTER": "chosen_opposing_character",
        "CHOSEN_DAMAGED_CHARACTER": "chosen_character",
        "CHOSEN_ITEM": "chosen_item",
        "CHOSEN_LOCATION": "chosen_location",
        "CHOSEN_PLAYER": "chosen_player",
        "YOUR_ITEMS": "your_items",
        "YOUR_LOCATIONS": "your_locations",
    }
    return alias_map.get(uppered, lowered)


def source_target_alias(obj: Any) -> str | dict[str, Any] | None:
    """Normalize a source effect target into an engine target alias.

    Supports:
    - raw string aliases
    - raw dict target objects
    - SourceTargetDef dataclasses with alias/selector/card_types/classifications
    """
    raw = source_effect_target(obj)
    if raw is None:
        return None

    if isinstance(raw, str):
        return _normalize_target_string(raw)

    if isinstance(raw, dict):
        alias = raw.get("alias") or raw.get("selector") or raw.get("type") or raw.get("kind")
        if isinstance(alias, str):
            return _normalize_target_string(alias)
        return raw

    alias = getattr(raw, "alias", None)
    if isinstance(alias, str) and alias:
        return _normalize_target_string(alias)

    selector = getattr(raw, "selector", None)
    if isinstance(selector, str) and selector:
        return _normalize_target_string(selector)

    kind = getattr(raw, "kind", None)
    if isinstance(kind, str) and kind:
        return _normalize_target_string(kind)

    return None


def source_target_selector(obj: Any) -> dict[str, Any] | None:
    """Extract selector query data from a source target object."""
    raw = source_effect_target(obj)

    if isinstance(raw, dict):
        return raw

    if raw is None or isinstance(raw, str):
        return None

    selector: dict[str, Any] = {}

    alias = getattr(raw, "alias", None)
    raw_selector = getattr(raw, "selector", None)
    kind = getattr(raw, "kind", None)
    if alias:
        selector["alias"] = alias
    if raw_selector:
        selector["selector"] = raw_selector
    if kind:
        selector["kind"] = kind

    card_types = getattr(raw, "card_types", None)
    classifications = getattr(raw, "classifications", None)
    controller = getattr(raw, "controller", None)
    owner = getattr(raw, "owner", None)
    exclude_self = getattr(raw, "exclude_self", None)

    if card_types:
        selector["card_types"] = tuple(card_types)
    if classifications:
        selector["classifications"] = tuple(classifications)
    if controller:
        selector["controller"] = controller
    if owner:
        selector["owner"] = owner
    if exclude_self is not None:
        selector["exclude_self"] = bool(exclude_self)

    return selector or None


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