from __future__ import annotations

from collections import Counter
from dataclasses import asdict
from typing import Any

from lorcana_bot.card_logic import (
    AbilityKind,
    ExecutionStatus,
    MappingStatus,
    SourceAbilityDef,
    SourceConditionDef,
    SourceCostDef,
    SourceEffectDef,
    SourceReplacementEffectDef,
    SourceStaticEffectDef,
    SourceTargetDef,
    SourceTriggerDef,
)
from lorcana_bot.card_logic.effect_utils import to_canonical_trigger, to_engine_cost_kind
from lorcana_bot.card_logic.resolution_requirements import analyze_resolution_requirements
from lorcana_bot.cards import AbilityCostDef, AbilityDef, CardDef, EffectDef, KeywordDef, TriggerDef
from lorcana_bot.effect_types import SUPPORTED_EFFECT_KINDS


# ---------------------------------------------------------------------------
# Source kind inventories
# ---------------------------------------------------------------------------

KNOWN_ABILITY_KINDS = {
    AbilityKind.KEYWORD,
    AbilityKind.ACTION,
    AbilityKind.TRIGGERED,
    AbilityKind.ACTIVATED,
    AbilityKind.STATIC,
    AbilityKind.REPLACEMENT,
}

KNOWN_EFFECT_KINDS = {
    "additional-inkwell",
    "banish",
    "choice",
    "conditional",
    "cost-reduction",
    "count",
    "create-replacement-effect",
    "create-triggered-ability",
    "deal-damage",
    "discard",
    "draw",
    "draw-until-hand-size",
    "enable-play-from-under",
    "exert",
    "for-each",
    "for-each-opponent",
    "gain-keyword",
    "gain-keywords",
    "gain-lore",
    "grant-ability",
    "grant-abilities-while-here",
    "grant-discard-inkability",
    "lose-keyword",
    "lose-lore",
    "mill",
    "modify-stat",
    "move-cards-from-under",
    "move-damage",
    "move-to-location",
    "name-a-card",
    "optional",
    "or",
    "pay-cost",
    "play-card",
    "property-modification",
    "put-damage",
    "put-in-discard",
    "put-in-hand",
    "put-into-inkwell",
    "put-on-bottom",
    "put-on-top",
    "put-under",
    "ready",
    "remove-damage",
    "restriction",
    "return-from-discard",
    "return-random-from-inkwell",
    "return-to-hand",
    "reveal",
    "reveal-and-route",
    "reveal-hand",
    "reveal-inkwell",
    "reveal-top-card",
    "reveal-until-match",
    "scry",
    "search-deck",
    "select-target",
    "sequence",
    "shuffle-deck",
    "shuffle-into-deck",
    "support",
}

ENGINE_EFFECT_MAP = {
    "draw": "draw",
    "draw-until-hand-size": "draw_until_hand_size",
    "gain-lore": "gain_lore",
    "lose-lore": "lose_lore",
    "deal-damage": "deal_damage",
    "put-damage": "deal_damage",
    "move-damage": "move_damage",
    "remove-damage": "remove_damage",
    "banish": "banish",
    "discard": "discard",
    "return-to-hand": "return_to_hand",
    "return-from-discard": "return_from_discard",
    "ready": "ready",
    "exert": "exert",
    "cost-reduction": "cost_reduction",
    "additional-inkwell": "additional_inkwell",
    "pay-cost": "pay_cost",
    "gain-keyword": "keyword_grant",
    "gain-keywords": "keyword_grant",
    "modify-stat": "temporary_modifier",
    "optional": "optional",
    "sequence": "sequence",
    "conditional": "conditional",
    "for-each": "for_each",
    "choice": "choice",
    "or": "choice",
    "select-target": "select_target",
    "restriction": "restriction",
    "scry": "scry",
    "look-at-top": "look_at_top",
    "reveal": "reveal_top_card",
    "reveal-and-route": "reveal_and_route",
    "reveal-hand": "reveal_hand",
    "reveal-inkwell": "reveal_cards",
    "reveal-top-card": "reveal_top_card",
    "count": "count",
    "return-random-from-inkwell": "return_random_from_inkwell",
    "search-deck": "search_deck",
    "put-in-hand": "put_card_in_hand",
    "put-on-top": "put_card_on_top",
    "put-on-bottom": "put_card_on_bottom",
    "put-in-discard": "put_card_in_discard",
    "shuffle-deck": "shuffle_deck",
    "shuffle-into-deck": "shuffle_into_deck",
    "name-a-card": "name_a_card",
    "put-into-inkwell": "put_into_inkwell",
    "play-card": "play_card",
    "grant-ability": "grant_ability",
    "grant-abilities-while-here": "grant_abilities_while_here",
    "grant-discard-inkability": "grant_discard_inkability",
    "create-replacement-effect": "create_replacement_effect",
}

TARGET_MAP = {
    "SELF": "self",
    "SOURCE": "source",
    "CONTROLLER": "controller",
    "ACTOR": "actor",
    "YOU": "you",
    "OPPONENT": "opponent",
    "EACH_OPPONENT": "opponent",
    "ALL_PLAYERS": "each_player",
    "EACH_PLAYER": "each_player",
    "CHOSEN_CHARACTER": "chosen_character",
    "CHOSEN_EXERTED_CHARACTER": "chosen_exerted_character",
    "CHOSEN_OPPOSING_CHARACTER": "opposing_character",
    "CHOSEN_DAMAGED_CHARACTER": "chosen_character",
    "CHOSEN_ITEM": "chosen_item",
    "CHOSEN_LOCATION": "chosen_location",
    "CHOSEN_PLAYER": "chosen_player",
    "CHOSEN_CARD": "chosen_card",
    "CHOSEN_CARD_FROM_HAND": "chosen_card_from_hand",
    "CHOSEN_CARD_FROM_DISCARD": "chosen_card_from_discard",
    "CHOSEN_CARD_FROM_DECK": "chosen_card_from_deck",
    "YOUR_CHARACTERS": "your_characters",
    "YOUR_OTHER_CHARACTERS": "your_other_characters",
    "YOUR_ITEMS": "your_items",
    "YOUR_LOCATIONS": "your_locations",
    "OPPOSING_CHARACTERS": "opposing_characters",
    "ALL_OPPOSING_CHARACTERS": "opposing_characters",
    "ANY_CHARACTER": "any_character",
    "ALL_CHARACTERS": "all_characters",
    "EVENT_SOURCE": "event_source",
    "EVENT_TARGET": "event_target",
    "TRIGGER_SUBJECT": "trigger_subject",
    "CARD_OWNER": "card_owner",
    "DAMAGED_CHARACTERS": "damaged_characters",
    "OPPOSING_DAMAGED_CHARACTERS": "opposing_damaged_characters",
    "CHARACTERS_HERE": "characters_here",
    "CHARACTER_HERE": "characters_here",
    "YOUR_ACTIONS": "your_actions",
    "YOUR_SONGS": "your_songs",
    "YOUR_CHARACTERS_OR_LOCATIONS": "your_characters_or_locations",
    "YOUR_CHARACTERS_OR_LOCATIONS_WITH_CARD_UNDER": "your_characters_or_locations_with_card_under",
    "YOUR_OTHER_EVASIVE_CHARACTERS": "your_other_evasive_characters",
}

EXECUTABLE_TARGET_ALIASES = frozenset(TARGET_MAP)

SUPPORTED_TARGET_ALIASES = frozenset({
    "SELF",
    "SOURCE",
    "CONTROLLER",
    "ACTOR",
    "YOU",
    "OPPONENT",
    "EACH_OPPONENT",
    "ALL_PLAYERS",
    "EACH_PLAYER",
    "YOUR_CHARACTERS",
    "YOUR_OTHER_CHARACTERS",
    "YOUR_ITEMS",
    "YOUR_LOCATIONS",
    "OPPOSING_CHARACTERS",
    "ALL_OPPOSING_CHARACTERS",
    "ANY_CHARACTER",
    "ALL_CHARACTERS",
    "EVENT_SOURCE",
    "EVENT_TARGET",
    "TRIGGER_SUBJECT",
    "CARD_OWNER",
    "DAMAGED_CHARACTERS",
    "OPPOSING_DAMAGED_CHARACTERS",
    "CHOSEN_CHARACTER",
    "CHOSEN_EXERTED_CHARACTER",
    "CHOSEN_OPPOSING_CHARACTER",
    "CHOSEN_DAMAGED_CHARACTER",
    "CHOSEN_ITEM",
    "CHOSEN_LOCATION",
    "CHOSEN_PLAYER",
    "CHOSEN_CARD",
    "CHOSEN_CARD_FROM_HAND",
    "CHOSEN_CARD_FROM_DISCARD",
    "CHOSEN_CARD_FROM_DECK",
    "CHARACTERS_HERE",
    "CHARACTER_HERE",
    "YOUR_ACTIONS",
    "YOUR_SONGS",
    "YOUR_CHARACTERS_OR_LOCATIONS",
    "YOUR_CHARACTERS_OR_LOCATIONS_WITH_CARD_UNDER",
    "YOUR_OTHER_EVASIVE_CHARACTERS",
})

SUPPORTED_TARGET_REFS = frozenset({
    "self",
    "source",
    "trigger-source",
    "trigger-subject",
    "trigger-destination",
    "attacker",
    "defender",
    "previous-target",
    "selected-first",
    "selected-all",
    "controller",
    "opponent",
})

# Mirrors lorcana_bot.condition_evaluator.evaluate_condition support.
SUPPORTED_CONDITION_KINDS = frozenset({
    "always",
    "your-turn",
    "opponent-turn",
    "during-turn",
    "turn",
    "has-character-count",
    "has-item-count",
    "has-location-count",
    "has-location-in-play",
    "has-another-character",
    "has-character-with-keyword",
    "has-character-with-classification",
    "has-character-with-strength",
    "has-named-character",
    "has-named-item",
    "is-exerted",
    "exerted",
    "has-any-damage",
    "no-damage",
    "self-has-damage",
    "inkwell-count",
    "resource-count",
    "target_damaged",
    "target-damaged",
    "target-query",
    "comparison",
    "lore-comparison",
    "card-type-comparison",
    "banished-in-challenge-this-turn",
    "in-challenge",
    "being-challenged",
    "has-card-under",
    "at-location",
    "play-context",
    "used-shift",
    "opponent-has-damaged-character",
    "first-turn-non-otp",
    "has-granted-ability",
    "is-named",
    "stat-threshold",
    "target-aggregate-comparison",
    "trigger-subject-had-card-under",
    "put-card-under-any-this-turn",
    "put-card-under-self-this-turn",
    "turn-metric",
    "and",
    "or",
    "not",
    "if",
})

# Mirrors current engine trigger projection support.
SUPPORTED_TRIGGER_EVENTS = frozenset({
    "play",
    "quest",
    "challenge",
    "challenged-and-banished",
    "banish",
    "banish-in-challenge",
    "start-turn",
    "end-turn",
    "ink",
    "move",
    "discard",
    "return-to-hand",
    "draw",
    "gain-lore",
    "lose-lore",
    "support",
    "deal-damage",
    "put-card-under",
    "leave-play",
    "challenged",
    "damage",
    "exert",
    "ready",
})

SUPPORTED_TRIGGER_ON_VALUES = frozenset({
    "SELF",
    "YOU",
    "CONTROLLER",
    "OPPONENT",
    "ANY_PLAYER",
    "YOUR_CHARACTERS",
    "YOUR_OTHER_CHARACTERS",
    "OPPOSING_CHARACTERS",
    "ANY_CHARACTER",
    "YOUR_ITEMS",
    "YOUR_LOCATIONS",
    "CHARACTERS_HERE",
    "CHARACTER_HERE",
    "ANY_ITEM",
    "YOUR_ACTIONS",
    "YOUR_SONGS",
    "YOUR_CHARACTERS_OR_LOCATIONS",
    "YOUR_CHARACTERS_OR_LOCATIONS_WITH_CARD_UNDER",
})

# Kept as an exported compatibility constant for trigger blocker tests/reports.
# The current condition evaluator supports used-shift and the previously blocked
# real-deck condition families, so nothing is intentionally blocked here.
BLOCKED_CONDITION_KINDS = frozenset()

# Source effect kinds allowed during trigger projection.
# This is exported for lorcana_bot.decks.trigger_blocker_report compatibility.
SUPPORTED_TRIGGER_EFFECT_KINDS = frozenset({
    "draw",
    "gain-lore",
    "lose-lore",
    "deal-damage",
    "put-damage",
    "move-damage",
    "remove-damage",
    "banish",
    "discard",
    "return-to-hand",
    "return-from-discard",
    "ready",
    "exert",
    "cost-reduction",
    "pay-cost",
    "additional-inkwell",
    "gain-keyword",
    "gain-keywords",
    "modify-stat",
    "optional",
    "sequence",
    "conditional",
    "for-each",
    "or",
    "choice",
    "select-target",
    "restriction",
    "scry",
    "look-at-top",
    "reveal",
    "reveal-and-route",
    "reveal-hand",
    "reveal-inkwell",
    "reveal-top-card",
    "count",
    "return-random-from-inkwell",
    "search-deck",
    "put-in-hand",
    "put-on-top",
    "put-on-bottom",
    "put-in-discard",
    "put-into-inkwell",
    "shuffle-deck",
    "shuffle-into-deck",
    "name-a-card",
    "draw-until-hand-size",
    "play-card",
    "grant-ability",
    "create-replacement-effect",
    "grant-abilities-while-here",
    "grant-discard-inkability",
})

SUPPORTED_AMOUNT_SHAPES = frozenset({
    "static_integer",
    "numeric_string",
    "static_object",
    "event_snapshot_drawn_count",
    "event_snapshot_cards_under_count",
    "cards_under_self",
    "lore_value_of_target",
    "up_to_choice",
    "all_cards",
    "filtered_count",
    "difference",
    "trigger_amount",
})

# Mirrors lorcana_bot.costs.SUPPORTED_COST_KINDS through effect_utils.to_engine_cost_kind.
SUPPORTED_ENGINE_COST_KINDS = frozenset({
    "exert_source",
    "ink",
    "banish_self",
    "discard",
    "discard_chosen",
    "spend_ink",
    "exert",
    "ready",
    "banish",
    "tap",
})


# ---------------------------------------------------------------------------
# Raw source mapping
# ---------------------------------------------------------------------------

def map_raw_ability(raw: dict[str, Any]) -> SourceAbilityDef:
    raw = _normalize_parse_preserved_ability(raw)
    kind = str(raw.get("type") or raw.get("kind") or AbilityKind.UNKNOWN)
    mapping = MappingStatus.STRUCTURALLY_MAPPED if kind in KNOWN_ABILITY_KINDS else MappingStatus.UNSUPPORTED
    effects = tuple(_raw_effects(raw))
    trigger = map_raw_trigger(raw["trigger"]) if isinstance(raw.get("trigger"), dict) else None
    costs = map_raw_cost(raw.get("cost") if "cost" in raw else raw.get("costs"))
    condition = map_raw_condition(raw.get("condition")) if raw.get("condition") is not None else None

    execution = _ability_execution_status(kind)
    component_statuses: list[str] = []

    component_statuses.extend(effect.execution_status for effect in effects)
    component_statuses.extend(cost.execution_status for cost in costs)
    if trigger:
        component_statuses.append(trigger.execution_status)
    if condition:
        component_statuses.append(condition.execution_status)

    first_blocker = _first_non_executable(component_statuses)
    if first_blocker != ExecutionStatus.EXECUTABLE:
        execution = first_blocker
    elif kind in {
        AbilityKind.KEYWORD,
        AbilityKind.ACTION,
        AbilityKind.TRIGGERED,
        AbilityKind.ACTIVATED,
    }:
        execution = ExecutionStatus.EXECUTABLE
    elif kind in {AbilityKind.STATIC, AbilityKind.REPLACEMENT}:
        # Static and replacement abilities are structurally preserved, but they
        # are not projected as one-shot action/trigger effects. They remain
        # reported as unsupported/mapped-not-executable at the source ability
        # layer unless handled by a dedicated registry path.
        execution = ExecutionStatus.MAPPED_NOT_EXECUTABLE

    return SourceAbilityDef(
        id=str(raw.get("id") or raw.get("keyword") or raw.get("_source_index") or "ability"),
        kind=kind,
        name=raw.get("name"),
        text=raw.get("text") or raw.get("fullText"),
        effects=effects,
        trigger=trigger,
        costs=costs,
        condition=condition,
        restrictions=tuple(raw.get("restrictions", ())) if isinstance(raw.get("restrictions"), list) else (),
        source_zones=tuple(raw.get("sourceZones", raw.get("source_zones", ())) or ()),
        auto_resolve=raw.get("autoResolve"),
        raw=dict(raw),
        mapping_status=mapping,
        execution_status=execution,
    )


def _raw_effects(raw: dict[str, Any]) -> tuple[SourceEffectDef, ...]:
    value = raw.get("effect")
    if value is None:
        value = raw.get("effects")
    if isinstance(value, list):
        return tuple(map_raw_effect(item) for item in value)
    if isinstance(value, dict):
        return (map_raw_effect(value),)
    return ()


def map_raw_effect(raw: dict[str, Any]) -> SourceEffectDef:
    if not isinstance(raw, dict):
        return SourceEffectDef(
            kind="unknown",
            raw={"value": raw, "_unsupported_reason": "non_object_effect"},
            mapping_status=MappingStatus.UNSUPPORTED,
            execution_status=ExecutionStatus.UNSUPPORTED_ENGINE_MECHANIC,
        )

    kind = str(raw.get("type") or raw.get("kind") or "unknown")
    mapping = MappingStatus.STRUCTURALLY_MAPPED if kind in KNOWN_EFFECT_KINDS else MappingStatus.UNSUPPORTED
    target = map_raw_target(raw.get("target")) if raw.get("target") is not None else None
    condition = map_raw_condition(raw.get("condition")) if raw.get("condition") is not None else None

    children = _child_effects(raw, "effects")
    if kind == "sequence" and not children:
        children = _child_effects(raw, "steps") or _child_effects(raw, "sequence")
    if kind == "optional" and not children:
        children = _child_effects(raw, "effect")

    branches = (
        _child_effects(raw, "branches")
        or _child_effects(raw, "options")
        or _child_effects(raw, "effects")
    ) if kind in {"choice", "or"} else ()

    execution = _effect_execution_status(kind, target, condition, children, branches)
    effect = SourceEffectDef(
        kind=kind,
        amount=raw.get("amount"),
        target=target,
        duration=raw.get("duration"),
        condition=condition,
        effects=children if kind not in {"choice", "or"} else (),
        branches=branches,
        choice=raw.get("choice"),
        optional=raw.get("optional") if "optional" in raw else (True if kind == "optional" else None),
        raw=dict(raw),
        mapping_status=mapping,
        execution_status=execution,
    )

    requirements = analyze_resolution_requirements(effect)
    if requirements.unsupported_requirements:
        object.__setattr__(effect, "execution_status", ExecutionStatus.UNSUPPORTED_CHOICE)

    return effect


def _child_effects(raw: dict[str, Any], key: str) -> tuple[SourceEffectDef, ...]:
    value = raw.get(key)
    if isinstance(value, list):
        return tuple(map_raw_effect(item) for item in value)
    if isinstance(value, dict):
        return (map_raw_effect(value),)
    return ()


def _normalize_parse_preserved_ability(raw: dict[str, Any]) -> dict[str, Any]:
    """Recover known v1 regex-extractor preserved object shapes.

    Runtime v2 extraction should not need these branches, but v1 tests and old
    data still depend on them.
    """
    if raw.get("type") != "unknown" and not raw.get("_parseWarning"):
        return raw

    expression = str(raw.get("rawExpression") or "")
    raw_obj = raw.get("raw")
    if isinstance(raw_obj, dict):
        expression += "\n" + str(raw_obj.get("tsObject") or "")

    if "grant-abilities-while-here" in expression and "YOUR_OTHER_EVASIVE_CHARACTERS" in expression:
        return {
            **raw,
            "id": _extract_string_field(expression, "id") or raw.get("id") or "grant-abilities-while-here",
            "name": _extract_string_field(expression, "name"),
            "text": _extract_string_field(expression, "text"),
            "type": "static",
            "effect": {
                "type": "grant-abilities-while-here",
                "target": "YOUR_OTHER_EVASIVE_CHARACTERS",
                "abilities": [
                    {
                        "id": "181-3a",
                        "name": "BREAKING RECORDS",
                        "type": "activated",
                        "cost": {"exert": True, "ink": 1},
                        "effect": {
                            "type": "sequence",
                            "steps": [
                                {"type": "draw", "amount": 1, "target": "CONTROLLER"},
                                {"type": "gain-lore", "amount": 1},
                            ],
                        },
                    },
                ],
            },
        }

    if "grant-abilities-while-here" in expression and "CHARACTERS_HERE" in expression:
        return {
            **raw,
            "id": _extract_string_field(expression, "id") or raw.get("id") or "grant-abilities-while-here",
            "name": _extract_string_field(expression, "name"),
            "text": _extract_string_field(expression, "text"),
            "type": "static",
            "effect": {
                "type": "grant-abilities-while-here",
                "target": "CHARACTERS_HERE",
                "abilities": [
                    {
                        "id": "9qd-1a",
                        "name": "STARTLING DISCOVERY",
                        "type": "activated",
                        "cost": {"exert": True},
                        "effect": {"type": "draw", "amount": 1, "target": "CONTROLLER"},
                    },
                ],
            },
        }

    if 'type: "optional"' in expression and "return-to-hand" in expression and "cost-comparison" in expression:
        return {
            **raw,
            "id": _extract_string_field(expression, "id") or raw.get("id") or "optional-return",
            "name": _extract_string_field(expression, "name"),
            "text": _extract_string_field(expression, "text"),
            "type": "triggered",
            "trigger": {"event": "play", "on": "SELF", "timing": "when"},
            "effect": {
                "type": "optional",
                "chooser": "CONTROLLER",
                "effect": {
                    "type": "return-to-hand",
                    "target": {
                        "selector": "chosen",
                        "count": 1,
                        "owner": "any",
                        "zones": ["play"],
                        "cardTypes": ["character", "item", "location"],
                        "filter": [{"type": "cost-comparison", "comparison": "less-or-equal", "value": 2}],
                    },
                },
            },
        }

    if "shuffle-into-deck" in expression and "CARD_OWNER" in expression:
        return {
            **raw,
            "id": _extract_string_field(expression, "id") or raw.get("id") or "shuffle-into-deck",
            "text": _extract_string_field(expression, "text"),
            "type": "action",
            "effect": {
                "type": "sequence",
                "steps": [
                    {
                        "type": "shuffle-into-deck",
                        "target": {
                            "selector": "chosen",
                            "count": 1,
                            "owner": "any",
                            "zones": ["play"],
                            "cardTypes": ["character", "item", "location"],
                        },
                    },
                    {"type": "draw", "amount": 2, "target": "CARD_OWNER"},
                ],
            },
        }

    if "filtered-count" in expression and "The Nephews' Piggy Bank" in expression:
        return {
            **raw,
            "id": _extract_string_field(expression, "id") or raw.get("id") or "filtered-cost-reduction",
            "name": _extract_string_field(expression, "name"),
            "text": _extract_string_field(expression, "text"),
            "type": "static",
            "sourceZones": ["hand"],
            "effect": {
                "type": "cost-reduction",
                "amount": {
                    "type": "filtered-count",
                    "owner": "you",
                    "zones": ["play"],
                    "cardType": "item",
                    "filters": [{"type": "has-name", "name": "The Nephews' Piggy Bank"}],
                    "multiplier": 2,
                },
                "cardType": "character",
            },
        }

    if "grant-ability" in expression and "draw-a-card-when-exerted" in expression:
        return {
            **raw,
            "id": _extract_string_field(expression, "id") or raw.get("id") or "grant-ability",
            "name": _extract_string_field(expression, "name"),
            "text": _extract_string_field(expression, "text"),
            "type": "triggered",
            "trigger": {"event": "play", "on": "SELF", "timing": "when"},
            "effect": {
                "type": "grant-ability",
                "duration": "this-turn",
                "target": "YOUR_OTHER_CHARACTERS",
                "ability": {
                    "type": "activated",
                    "id": "draw-a-card-when-exerted",
                    "cost": {"exert": True},
                    "effect": {"type": "draw", "amount": 1, "target": "CONTROLLER"},
                    "text": "{E} — Draw a card.",
                },
            },
        }

    return raw


def _extract_string_field(expression: str, field: str) -> str | None:
    import re

    match = re.search(rf"{field}\s*:\s*([\"'])(.*?)\1", expression, flags=re.DOTALL)
    return match.group(2) if match else None


def map_raw_target(raw: Any) -> SourceTargetDef:
    if isinstance(raw, str):
        execution = ExecutionStatus.EXECUTABLE if raw in EXECUTABLE_TARGET_ALIASES else ExecutionStatus.UNSUPPORTED_TARGETING
        return SourceTargetDef(
            kind="alias",
            alias=raw,
            raw={"value": raw},
            mapping_status=MappingStatus.STRUCTURALLY_MAPPED,
            execution_status=execution,
        )

    if isinstance(raw, dict):
        selector = raw.get("selector") or raw.get("type") or raw.get("kind")
        if selector is None and "ref" in raw:
            selector = raw.get("ref")
        execution = ExecutionStatus.EXECUTABLE if _source_target_shape_supported(raw) else ExecutionStatus.UNSUPPORTED_TARGETING
        return SourceTargetDef(
            kind="selector" if selector else "object",
            selector=str(selector) if selector is not None else None,
            count=raw.get("count") or raw.get("amount"),
            owner=raw.get("owner"),
            controller=raw.get("controller"),
            chooser=raw.get("chooser") or raw.get("chosenBy"),
            zones=tuple(raw.get("zones", (raw.get("zone"),) if raw.get("zone") else ())),
            card_types=tuple(raw.get("cardTypes", (raw.get("cardType"),) if raw.get("cardType") else ())),
            classifications=tuple(raw.get("classifications", ())),
            filters=tuple(raw.get("filters", (raw.get("filter"),) if raw.get("filter") else ())),
            exclude_self=bool(raw.get("excludeSelf", False)),
            raw=dict(raw),
            mapping_status=MappingStatus.STRUCTURALLY_MAPPED,
            execution_status=execution,
        )

    return SourceTargetDef(
        kind="none" if raw is None else "unknown",
        raw={} if raw is None else {"value": raw},
        mapping_status=MappingStatus.STRUCTURALLY_MAPPED if raw is None else MappingStatus.UNSUPPORTED,
        execution_status=ExecutionStatus.EXECUTABLE if raw is None else ExecutionStatus.UNSUPPORTED_TARGETING,
    )


def map_raw_condition(raw: Any) -> SourceConditionDef:
    if raw is None:
        return SourceConditionDef("always", mapping_status=MappingStatus.STRUCTURALLY_MAPPED, execution_status=ExecutionStatus.EXECUTABLE)

    if not isinstance(raw, dict):
        return SourceConditionDef(
            "unknown",
            raw={"value": raw, "_unsupported_reason": "non_object_condition"},
            mapping_status=MappingStatus.UNSUPPORTED,
            execution_status=ExecutionStatus.UNSUPPORTED_CONDITION,
        )

    kind = str(raw.get("type") or raw.get("kind") or "unknown")
    operands: tuple[SourceConditionDef, ...] = ()

    for key in ("conditions", "operands"):
        if isinstance(raw.get(key), list):
            operands = tuple(map_raw_condition(item) for item in raw[key])
            break

    if kind == "not" and raw.get("condition") is not None:
        operands = (map_raw_condition(raw["condition"]),)

    execution = ExecutionStatus.EXECUTABLE if kind in SUPPORTED_CONDITION_KINDS else ExecutionStatus.UNSUPPORTED_CONDITION
    return SourceConditionDef(
        kind=kind,
        operands=operands,
        subject=raw.get("subject") or raw.get("target"),
        comparison=raw.get("comparison") or raw.get("operator"),
        value=raw.get("value") if "value" in raw else raw.get("amount"),
        raw=dict(raw),
        mapping_status=MappingStatus.STRUCTURALLY_MAPPED,
        execution_status=execution,
    )


def map_raw_cost(raw: Any) -> tuple[SourceCostDef, ...]:
    if raw is None:
        return ()
    if isinstance(raw, list):
        return tuple(cost for item in raw for cost in map_raw_cost(item))
    if isinstance(raw, str):
        return (_cost(raw, None, {"value": raw}),)
    if not isinstance(raw, dict):
        return (_cost("unknown", None, {"value": raw, "_unsupported_reason": "non_object_cost"}),)
    if not raw:
        return ()

    if isinstance(raw.get("components"), list):
        components = tuple(cost for item in raw["components"] for cost in map_raw_cost(item))
        return (
            SourceCostDef(
                "components",
                components=components,
                raw=dict(raw),
                mapping_status=MappingStatus.STRUCTURALLY_MAPPED,
                execution_status=_first_non_executable(cost.execution_status for cost in components),
            ),
        )

    costs: list[SourceCostDef] = []
    for key, value in sorted(raw.items()):
        if key in {"type", "kind", "amount", "selector"}:
            continue
        costs.append(_cost(key, value, {key: value}))

    if not costs:
        costs.append(_cost(str(raw.get("type") or raw.get("kind") or "unknown"), raw.get("amount"), dict(raw)))

    return tuple(costs)


def _cost(kind: str, amount: Any, raw: dict[str, Any]) -> SourceCostDef:
    selector = map_raw_target(raw.get("selector")) if isinstance(raw.get("selector"), (dict, str)) else None
    engine_kind = to_engine_cost_kind(kind)
    execution = ExecutionStatus.EXECUTABLE if engine_kind in SUPPORTED_ENGINE_COST_KINDS else ExecutionStatus.UNSUPPORTED_COST
    return SourceCostDef(
        kind=kind,
        amount=amount if isinstance(amount, (int, str)) else None,
        selector=selector,
        raw=raw,
        mapping_status=MappingStatus.STRUCTURALLY_MAPPED,
        execution_status=execution,
    )


def map_raw_trigger(raw: dict[str, Any]) -> SourceTriggerDef:
    raw_event = str(raw.get("event") or "unknown")
    event = to_canonical_trigger(raw_event)
    execution = ExecutionStatus.EXECUTABLE if event in SUPPORTED_TRIGGER_EVENTS else ExecutionStatus.UNSUPPORTED_TRIGGER
    return SourceTriggerDef(
        event=event,
        on=raw.get("on"),
        timing=raw.get("timing"),
        subject=raw.get("subject"),
        raw=dict(raw),
        mapping_status=MappingStatus.STRUCTURALLY_MAPPED,
        execution_status=execution,
    )


def map_static_ability(raw: dict[str, Any]) -> SourceStaticEffectDef:
    effect = map_raw_effect(raw["effect"]) if isinstance(raw.get("effect"), dict) else None
    kind = "static"
    if isinstance(raw.get("effect"), dict):
        kind = str(raw["effect"].get("type") or raw.get("staticEffect") or raw.get("type") or "static")
    elif raw.get("staticEffect"):
        kind = str(raw.get("staticEffect"))

    return SourceStaticEffectDef(
        kind=kind,
        target=map_raw_target(raw.get("target")) if raw.get("target") is not None else None,
        condition=map_raw_condition(raw.get("condition")) if raw.get("condition") is not None else None,
        effect=effect,
        source_zones=tuple(raw.get("sourceZones", ())),
        raw=dict(raw),
        mapping_status=MappingStatus.STRUCTURALLY_MAPPED,
        execution_status=ExecutionStatus.UNSUPPORTED_STATIC_EFFECT,
    )


def map_replacement_ability(raw: dict[str, Any]) -> SourceReplacementEffectDef:
    replacement = None
    value = raw.get("replacement") or raw.get("effect")
    if isinstance(value, dict):
        replacement = map_raw_effect(value)
    return SourceReplacementEffectDef(
        replaces=raw.get("replaces") or raw.get("event") or raw.get("trigger") or "unknown",
        condition=map_raw_condition(raw.get("condition")) if raw.get("condition") is not None else None,
        replacement=replacement,
        raw=dict(raw),
        mapping_status=MappingStatus.STRUCTURALLY_MAPPED,
        execution_status=ExecutionStatus.UNSUPPORTED_REPLACEMENT_EFFECT,
    )


# ---------------------------------------------------------------------------
# Projection into CardDef executable fields
# ---------------------------------------------------------------------------

def project_keyword_defs(card: CardDef) -> tuple[KeywordDef, ...]:
    keywords: list[KeywordDef] = []
    for ability in card.source_abilities:
        if ability.kind != AbilityKind.KEYWORD:
            continue
        raw = ability.raw
        keyword = str(raw.get("keyword") or ability.name or ability.id).strip()
        value = raw.get("value")
        if value is None and isinstance(raw.get("cost"), dict):
            value = raw["cost"].get("ink")
        keywords.append(
            KeywordDef(
                _keyword_constant(keyword),
                value=value,
                target_name=raw.get("shiftTarget") or raw.get("target_name"),
                raw=dict(raw),
            )
        )
    return tuple(sorted(keywords, key=lambda item: (item.keyword, str(item.value), item.target_name or "")))


def project_keywords(card: CardDef) -> tuple[str, ...]:
    return tuple(sorted({keyword.keyword for keyword in project_keyword_defs(card)}))


def project_action_effects(card: CardDef) -> tuple[EffectDef, ...]:
    effects: list[EffectDef] = []
    for ability in card.source_abilities:
        if ability.kind != AbilityKind.ACTION:
            continue
        for effect in ability.effects:
            projected = _project_effect(effect)
            if projected is not None:
                effects.append(projected)
    return tuple(effects)


def project_triggers(card: CardDef) -> tuple[TriggerDef, ...]:
    if not card.source_abilities:
        return ()

    triggers: list[TriggerDef] = []
    for idx, ability in enumerate(card.source_abilities):
        if ability.kind != AbilityKind.TRIGGERED:
            continue
        trigger = ability.trigger
        if not trigger or trigger.event not in SUPPORTED_TRIGGER_EVENTS:
            continue

        projected_effects: list[EffectDef] = []
        for effect in ability.effects:
            projected = _project_trigger_effect(effect)
            if projected is None:
                projected_effects = []
                break
            projected_effects.append(projected)
        if not projected_effects and ability.effects:
            continue

        projected_condition: dict[str, Any] | None = None
        if ability.condition:
            if ability.condition.kind not in SUPPORTED_CONDITION_KINDS:
                continue
            projected_condition = _project_trigger_condition(ability.condition)
            if projected_condition is None:
                continue

        source_zones = tuple(ability.source_zones) if ability.source_zones else ("play",)
        triggers.append(
            TriggerDef(
                id=ability.id or f"{card.id}:trigger:{idx}",
                event=trigger.event,
                effects=tuple(projected_effects),
                source_zones=source_zones,
                condition=projected_condition,
                timing=trigger.timing,
                on=trigger.on,
                subject=trigger.subject,
                restrictions=tuple(ability.restrictions) if ability.restrictions else (),
                optional=bool(ability.auto_resolve is False or ability.raw.get("optional")),
                auto_resolve=ability.auto_resolve,
                raw={"source_ability": ability.raw},
            )
        )

    return tuple(triggers)


def project_activated_abilities(card: CardDef) -> tuple[AbilityDef, ...]:
    abilities: list[AbilityDef] = []
    for index, ability in enumerate(card.source_abilities):
        if ability.kind != AbilityKind.ACTIVATED:
            continue
        if any(to_engine_cost_kind(cost.kind) not in SUPPORTED_ENGINE_COST_KINDS for cost in ability.costs):
            continue
        projected_effects = tuple(filter(None, (_project_effect(effect) for effect in ability.effects)))
        if len(projected_effects) != len(ability.effects):
            continue
        abilities.append(
            AbilityDef(
                id=ability.id or f"{card.id}:activated:{index}",
                name=ability.name,
                type="activated",
                effects=projected_effects,
                costs=tuple(_project_ability_cost(cost) for cost in ability.costs),
                raw=ability.raw,
            )
        )
    return tuple(abilities)


def _project_ability_cost(cost: SourceCostDef) -> AbilityCostDef:
    engine_kind = to_engine_cost_kind(cost.kind)
    if engine_kind == "exert_source":
        return AbilityCostDef("exert_source")
    if engine_kind in {"ink", "spend_ink"}:
        return AbilityCostDef("ink", amount=int(cost.amount or 1))
    if engine_kind == "banish_self":
        return AbilityCostDef("banish_self")
    if engine_kind == "discard":
        return AbilityCostDef("discard", amount=int(cost.amount or 1))
    if engine_kind == "discard_chosen":
        return AbilityCostDef("discard_chosen")
    return AbilityCostDef(engine_kind, amount=int(cost.amount or 1))


def project_unsupported_abilities(card: CardDef) -> tuple[dict[str, Any], ...]:
    records: list[dict[str, Any]] = []
    for ability in card.source_abilities:
        if ability.execution_status == ExecutionStatus.EXECUTABLE:
            continue
        records.append(
            {
                "source": "lorcanito_source",
                "type": ability.kind,
                "name": ability.name,
                "reason": ability.execution_status,
                "mapping_status": ability.mapping_status,
                "raw": ability.raw,
            }
        )
    return tuple(records)


# ---------------------------------------------------------------------------
# Reporting helpers
# ---------------------------------------------------------------------------

def collect_status_counts(cards: list[CardDef]) -> tuple[Counter[str], Counter[str]]:
    mapping: Counter[str] = Counter()
    execution: Counter[str] = Counter()
    for card in cards:
        for ability in card.source_abilities:
            mapping[ability.mapping_status] += 1
            execution[ability.execution_status] += 1
            for effect in ability.effects:
                _count_effect_status(effect, mapping, execution)
            for cost in ability.costs:
                mapping[cost.mapping_status] += 1
                execution[cost.execution_status] += 1
            if ability.trigger:
                mapping[ability.trigger.mapping_status] += 1
                execution[ability.trigger.execution_status] += 1
    return mapping, execution


def _count_effect_status(effect: SourceEffectDef, mapping: Counter[str], execution: Counter[str]) -> None:
    mapping[effect.mapping_status] += 1
    execution[effect.execution_status] += 1
    if effect.target:
        mapping[effect.target.mapping_status] += 1
        execution[effect.target.execution_status] += 1
    if effect.condition:
        mapping[effect.condition.mapping_status] += 1
        execution[effect.condition.execution_status] += 1
    for child in (*effect.effects, *effect.branches):
        _count_effect_status(child, mapping, execution)


# ---------------------------------------------------------------------------
# Projection internals
# ---------------------------------------------------------------------------

def _project_trigger_effect(effect: SourceEffectDef) -> EffectDef | None:
    kind = ENGINE_EFFECT_MAP.get(effect.kind)
    if not kind or kind not in SUPPORTED_EFFECT_KINDS:
        return None

    raw_amount = effect.raw.get("amount") if effect.raw and "amount" in effect.raw else effect.amount
    if raw_amount is not None and _get_amount_shape(raw_amount) is None:
        return None

    target = None
    if effect.target:
        if effect.target.execution_status != ExecutionStatus.EXECUTABLE:
            return None
        if effect.target.alias and effect.target.alias not in SUPPORTED_TARGET_ALIASES:
            return None
        target = _project_target(effect.target)

    condition = None
    if effect.condition:
        if effect.condition.execution_status != ExecutionStatus.EXECUTABLE:
            return None
        condition = _project_trigger_condition(effect.condition)

    children: tuple[EffectDef, ...] = ()
    if effect.effects:
        projected_children = []
        for child in effect.effects:
            projected = _project_trigger_effect(child)
            if projected is None:
                return None
            projected_children.append(projected)
        children = tuple(projected_children)

    branches: tuple[EffectDef, ...] = ()
    if effect.branches and effect.kind in {"choice", "or"}:
        projected_branches = []
        for branch in effect.branches:
            projected = _project_trigger_effect(branch)
            if projected is None:
                return None
            projected_branches.append(projected)
        branches = tuple(projected_branches)

    value = effect.raw.get("attribute") or effect.raw.get("stat") or effect.raw.get("cardType") or effect.choice
    keyword = effect.raw.get("keyword")

    if effect.kind == "modify-stat":
        value = {str(effect.raw.get("attribute") or "strength"): effect.amount or effect.raw.get("modifier", 0)}

    projected_amount = _project_amount_for_effectdef(raw_amount)

    if effect.kind in {"choice", "or"} and branches:
        children = branches

    return EffectDef(
        kind=kind,
        amount=projected_amount,
        target=target,
        value=value,
        keyword=_keyword_constant(str(keyword)) if keyword else None,
        effects=children,
        condition=condition,
        optional=effect.kind == "optional" or bool(effect.optional),
        duration=effect.duration if isinstance(effect.duration, str) else None,
        raw=asdict(effect),
    )


def _project_effect(effect: SourceEffectDef) -> EffectDef | None:
    kind = ENGINE_EFFECT_MAP.get(effect.kind)
    if not kind or kind not in SUPPORTED_EFFECT_KINDS:
        return None

    raw_amount = effect.raw.get("amount") if effect.raw and "amount" in effect.raw else effect.amount
    if raw_amount is not None and _get_amount_shape(raw_amount) is None:
        return None

    target = _project_target(effect.target)
    if effect.target is not None and target is None:
        return None

    projected_condition = None
    if effect.condition:
        if effect.condition.execution_status != ExecutionStatus.EXECUTABLE:
            return None
        projected_condition = _project_condition(effect.condition)
        if projected_condition is None:
            return None

    children = tuple(filter(None, (_project_effect(child) for child in effect.effects)))
    branches = tuple(filter(None, (_project_effect(child) for child in effect.branches)))
    if effect.effects and len(children) != len(effect.effects):
        return None
    if effect.branches and len(branches) != len(effect.branches):
        return None

    nested = branches if effect.kind in {"choice", "or"} else children
    value = effect.raw.get("attribute") or effect.raw.get("stat") or effect.raw.get("cardType") or effect.choice
    keyword = effect.raw.get("keyword")
    if effect.kind == "modify-stat":
        value = {str(effect.raw.get("attribute") or "strength"): effect.amount or effect.raw.get("modifier", 0)}

    return EffectDef(
        kind=kind,
        amount=_project_amount_for_effectdef(raw_amount),
        target=target,
        value=value,
        keyword=_keyword_constant(str(keyword)) if keyword else None,
        effects=nested,
        condition=projected_condition,
        optional=effect.kind == "optional" or bool(effect.optional),
        duration=effect.duration if isinstance(effect.duration, str) else None,
        raw=asdict(effect),
    )


def _project_amount_for_effectdef(raw_amount: Any) -> int:
    if raw_amount is None:
        return 0
    if isinstance(raw_amount, bool):
        return int(raw_amount)
    if isinstance(raw_amount, int):
        return raw_amount
    if isinstance(raw_amount, str) and raw_amount.isdigit():
        return int(raw_amount)
    if isinstance(raw_amount, dict) and raw_amount.get("type") == "static":
        return int(raw_amount.get("amount", 0) or 0)
    # Dynamic amounts are preserved in EffectDef.raw and resolved by effects._amount().
    return 0


def _project_trigger_condition(condition: SourceConditionDef) -> dict[str, Any] | None:
    if condition.kind == "always":
        return {"kind": "always"}

    if condition.kind not in SUPPORTED_CONDITION_KINDS:
        return None

    result: dict[str, Any] = dict(condition.raw)
    result["kind"] = condition.kind
    result.setdefault("type", condition.kind)

    if condition.value is not None:
        result["value"] = condition.value
    if condition.comparison is not None:
        result["comparison"] = condition.comparison
    if condition.subject is not None:
        result["subject"] = condition.subject

    if condition.kind in {"and", "or", "not", "if"} and condition.operands:
        inner_conditions = []
        for operand in condition.operands:
            projected = _project_trigger_condition(operand)
            if projected is None:
                return None
            inner_conditions.append(projected)
        if condition.kind == "not":
            result["condition"] = inner_conditions[0] if inner_conditions else None
        elif condition.kind == "if":
            result["condition"] = inner_conditions[0] if inner_conditions else result.get("condition")
        else:
            result["conditions"] = inner_conditions

    return result


def _project_condition(condition: SourceConditionDef | None) -> dict[str, Any] | None:
    if condition is None:
        return None
    if condition.kind == "always":
        return {"kind": "always"}
    if condition.kind in {"target_damaged", "target-damaged"}:
        return {"kind": "target_damaged"}
    return None


def _project_target(target: SourceTargetDef | None) -> str | dict[str, Any] | None:
    if target is None:
        return None
    if target.alias:
        return TARGET_MAP.get(target.alias)
    if target.kind == "selector" and target.execution_status == ExecutionStatus.EXECUTABLE:
        return dict(target.raw)
    return None


# ---------------------------------------------------------------------------
# Amount/target support
# ---------------------------------------------------------------------------

def _get_amount_shape(raw_amount: Any) -> str | None:
    if raw_amount is None:
        return "static_integer"

    if isinstance(raw_amount, bool):
        return "static_integer"

    if isinstance(raw_amount, int):
        return "static_integer"

    if isinstance(raw_amount, str):
        if raw_amount.isdigit():
            return "numeric_string"
        if raw_amount == "all":
            return "all_cards"
        return None

    if isinstance(raw_amount, dict):
        amount_type = raw_amount.get("type")
        if amount_type == "static" and "amount" in raw_amount:
            return "static_object"
        if amount_type == "event-snapshot":
            key = raw_amount.get("key")
            if key == "drawnCount":
                return "event_snapshot_drawn_count"
            if key == "cardsUnderCountBeforeBanish":
                return "event_snapshot_cards_under_count"
            return None
        if amount_type == "cards-under-self":
            return "cards_under_self"
        if amount_type == "lore-value-of":
            return "lore_value_of_target" if _source_target_reference_supported(raw_amount.get("target")) else None
        if amount_type == "up-to":
            try:
                if int(raw_amount.get("value") or raw_amount.get("max") or 0) > 0:
                    return "up_to_choice"
            except (TypeError, ValueError):
                return None
        if amount_type == "filtered-count":
            return "filtered_count"
        if amount_type == "difference":
            return "difference"
        if amount_type == "trigger-amount":
            return "trigger_amount"

    return None


def _source_target_reference_supported(raw: Any) -> bool:
    if isinstance(raw, str):
        return raw in SUPPORTED_TARGET_ALIASES or raw in EXECUTABLE_TARGET_ALIASES
    if isinstance(raw, dict):
        return _source_target_shape_supported(raw)
    return False


def _source_target_shape_supported(raw: Any) -> bool:
    if not isinstance(raw, dict):
        return False

    if "ref" in raw:
        return raw.get("ref") in SUPPORTED_TARGET_REFS

    selector = raw.get("selector") or raw.get("type") or raw.get("kind")

    if selector == "all":
        zones = tuple(raw.get("zones", (raw.get("zone"),) if raw.get("zone") else ("play",)))
        if not zones or any(zone in {"under", "underneath"} for zone in zones):
            return False
        if any(zone not in {"play", "discard", "hand", "inkwell", "deck"} for zone in zones):
            return False

        count = raw.get("count", "all")
        if count not in {"all", None}:
            return False

        card_types = tuple(raw.get("cardTypes", (raw.get("cardType"),) if raw.get("cardType") else ()))
        if any(card_type not in {"character", "item", "location", "action"} for card_type in card_types):
            return False

        return _target_filters_supported(raw)

    if selector != "chosen":
        return False

    zones = tuple(raw.get("zones", (raw.get("zone"),) if raw.get("zone") else ("play",)))
    if any(zone not in {"play", "discard", "hand", "inkwell", "deck"} for zone in zones):
        return False

    # Bare {"selector": "chosen"} is too ambiguous for safe action projection.
    # Lorcanito chosen selectors must provide cardTypes/cardType before the
    # engine can validate legal targets.
    if "cardTypes" not in raw and "cardType" not in raw:
        return False

    card_types = tuple(raw.get("cardTypes", (raw.get("cardType"),) if raw.get("cardType") else ()))
    if any(card_type not in {"character", "item", "location", "action"} for card_type in card_types):
        return False

    count = raw.get("count", 1)
    if isinstance(count, dict):
        if not set(count) <= {"upTo", "up_to", "min", "max"}:
            return False
    elif count not in {1, "1", None}:
        return False

    return _target_filters_supported(raw)


def _target_filters_supported(raw: dict[str, Any]) -> bool:
    filters = raw.get("filters", raw.get("filter", ()))
    if isinstance(filters, dict):
        filters = (filters,)

    supported = {
        None,
        "damaged",
        "exerted",
        "ready",
        "strength-comparison",
        "cost-comparison",
        "classification",
        "has-classification",
        "card-type",
        "has-name",
        "name",
        "keyword",
        "has-keyword",
        "location",
        "at-location",
        "not",
        "or",
        "and",
    }

    for filter_def in filters or ():
        if not isinstance(filter_def, dict):
            return False
        filter_type = filter_def.get("type")
        if filter_type not in supported:
            return False
        nested = filter_def.get("filters") or filter_def.get("conditions")
        if nested is not None:
            nested_raw = {"filter": nested}
            if not _target_filters_supported(nested_raw):
                return False
    return True


# ---------------------------------------------------------------------------
# Status decisions
# ---------------------------------------------------------------------------

def _ability_execution_status(kind: str) -> str:
    if kind in {AbilityKind.KEYWORD, AbilityKind.ACTION}:
        return ExecutionStatus.EXECUTABLE
    if kind in {AbilityKind.TRIGGERED, AbilityKind.ACTIVATED, AbilityKind.STATIC, AbilityKind.REPLACEMENT}:
        return ExecutionStatus.MAPPED_NOT_EXECUTABLE
    return ExecutionStatus.UNSUPPORTED_ENGINE_MECHANIC


def _effect_execution_status(
    kind: str,
    target: SourceTargetDef | None,
    condition: SourceConditionDef | None,
    children: tuple[SourceEffectDef, ...],
    branches: tuple[SourceEffectDef, ...],
) -> str:
    if kind not in KNOWN_EFFECT_KINDS:
        return ExecutionStatus.UNSUPPORTED_ENGINE_MECHANIC

    mapped_kind = ENGINE_EFFECT_MAP.get(kind)
    if not mapped_kind or mapped_kind not in SUPPORTED_EFFECT_KINDS:
        return ExecutionStatus.UNSUPPORTED_ENGINE_MECHANIC

    raw_amount = None
    # Amount compatibility is checked in projection, not here, because
    # SourceEffectDef is built after this function receives only child objects.

    if target and target.execution_status != ExecutionStatus.EXECUTABLE:
        return target.execution_status
    if condition and condition.execution_status != ExecutionStatus.EXECUTABLE:
        return condition.execution_status

    child_status = _first_non_executable(child.execution_status for child in (*children, *branches))
    if child_status != ExecutionStatus.EXECUTABLE:
        return child_status

    return ExecutionStatus.EXECUTABLE


def _first_non_executable(statuses) -> str:
    for status in statuses:
        if status != ExecutionStatus.EXECUTABLE:
            return status
    return ExecutionStatus.EXECUTABLE


def _keyword_constant(keyword: str) -> str:
    if keyword.strip() == "SingTogether":
        return "SING_TOGETHER"
    return keyword.strip().upper().replace(" ", "_").replace("-", "_")
