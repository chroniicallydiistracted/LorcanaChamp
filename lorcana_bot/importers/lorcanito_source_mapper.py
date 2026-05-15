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
from lorcana_bot.card_logic.resolution_requirements import analyze_resolution_requirements
from lorcana_bot.cards import AbilityCostDef, AbilityDef, CardDef, EffectDef, KeywordDef, TriggerDef
from lorcana_bot.effect_types import SUPPORTED_EFFECT_KINDS

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
    "shuffle-into-deck",
    "support",
}

ENGINE_EFFECT_MAP = {
    "draw": "draw",
    "gain-lore": "gain_lore",
    "lose-lore": "lose_lore",
    "deal-damage": "deal_damage",
    "put-damage": "deal_damage",
    "remove-damage": "remove_damage",
    "banish": "banish",
    "discard": "discard",
    "return-to-hand": "return_to_hand",
    "ready": "ready",
    "exert": "exert",
    "cost-reduction": "cost_reduction",
    "gain-keyword": "keyword_grant",
    "modify-stat": "temporary_modifier",
    "optional": "optional",
    "sequence": "sequence",
    "conditional": "conditional",
    "for-each": "for_each",
    "choice": "choice",
    # B4: Scry, search, reveal, and deck routing effects
    "scry": "scry",
    "reveal": "reveal_top_card",
    "reveal-and-route": "reveal_and_route",
    "reveal-hand": "reveal_hand",
    "reveal-inkwell": "reveal_cards",
    "reveal-top-card": "reveal_top_card",
    "search-deck": "search_deck",
    "put-in-hand": "put_card_in_hand",
    "put-on-top": "put_card_on_top",
    "put-on-bottom": "put_card_on_bottom",
    "shuffle-into-deck": "shuffle_deck",
    "name-a-card": "name_a_card",
}

TARGET_MAP = {
    "SELF": "self",
    "CONTROLLER": "controller",
    "ACTOR": "actor",
    "YOU": "you",
    "OPPONENT": "opponent",
    "EACH_OPPONENT": "opponent",
    "CHOSEN_CHARACTER": "chosen_character",
    "CHOSEN_OPPOSING_CHARACTER": "opposing_character",
    "CHOSEN_DAMAGED_CHARACTER": "chosen_character",
    "YOUR_CHARACTERS": "your_characters",
    "YOUR_OTHER_CHARACTERS": "your_other_characters",
    "ALL_OPPOSING_CHARACTERS": "opposing_characters",
    # B2: Event-derived targets for trigger projection
    "EVENT_SOURCE": "event_source",
    "EVENT_TARGET": "event_target",
    "TRIGGER_SUBJECT": "trigger_subject",
    "DAMAGED_CHARACTERS": "damaged_characters",
    "ALL_CHARACTERS": "all_characters",
}

EXECUTABLE_TARGET_ALIASES = frozenset(TARGET_MAP)
EXECUTABLE_CONDITIONS = {"always", "target_damaged"}
EXECUTABLE_COSTS = {"exert"}


def map_raw_ability(raw: dict[str, Any]) -> SourceAbilityDef:
    kind = str(raw.get("type") or raw.get("kind") or AbilityKind.UNKNOWN)
    mapping = MappingStatus.STRUCTURALLY_MAPPED if kind in KNOWN_ABILITY_KINDS else MappingStatus.UNSUPPORTED
    execution = _ability_execution_status(kind)
    effects = tuple(_raw_effects(raw))
    trigger = map_raw_trigger(raw["trigger"]) if isinstance(raw.get("trigger"), dict) else None
    costs = map_raw_cost(raw.get("cost") if "cost" in raw else raw.get("costs"))
    condition = map_raw_condition(raw.get("condition")) if raw.get("condition") is not None else None
    if effects and any(effect.execution_status != ExecutionStatus.EXECUTABLE for effect in effects):
        execution = _first_non_executable(effect.execution_status for effect in effects)
    if trigger and trigger.execution_status != ExecutionStatus.EXECUTABLE:
        execution = trigger.execution_status
    if costs and any(cost.execution_status != ExecutionStatus.EXECUTABLE for cost in costs):
        execution = _first_non_executable(cost.execution_status for cost in costs)
    if condition and condition.execution_status != ExecutionStatus.EXECUTABLE:
        execution = condition.execution_status
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
        children = _child_effects(raw, "sequence")
    branches = _child_effects(raw, "branches") or _child_effects(raw, "effects") if kind in {"choice", "or"} else ()
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
        execution = ExecutionStatus.UNSUPPORTED_TARGETING
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
    execution = ExecutionStatus.EXECUTABLE if kind in EXECUTABLE_CONDITIONS else ExecutionStatus.UNSUPPORTED_CONDITION
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
    execution = ExecutionStatus.EXECUTABLE if kind in EXECUTABLE_COSTS else ExecutionStatus.UNSUPPORTED_COST
    return SourceCostDef(
        kind=kind,
        amount=amount if isinstance(amount, (int, str)) else None,
        selector=selector,
        raw=raw,
        mapping_status=MappingStatus.STRUCTURALLY_MAPPED,
        execution_status=execution,
    )


def map_raw_trigger(raw: dict[str, Any]) -> SourceTriggerDef:
    event = str(raw.get("event") or "unknown")
    execution = ExecutionStatus.UNSUPPORTED_TRIGGER
    if event in {"play"}:
        execution = ExecutionStatus.MAPPED_NOT_EXECUTABLE
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
    return SourceStaticEffectDef(
        kind=str(raw.get("staticEffect") or raw.get("effect", {}).get("type") if isinstance(raw.get("effect"), dict) else raw.get("type", "static")),
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


# Supported trigger events for B2 trigger projection
SUPPORTED_TRIGGER_EVENTS = frozenset({
    "play",
    "quest", 
    "challenge",
    "banish",
    "start-turn",
    "end-turn",
    "ink",
    "move",
    "challenged",
    "damage",
    "exert",
    "ready",
})

# Supported effect kinds for projected triggers
SUPPORTED_TRIGGER_EFFECT_KINDS = frozenset({
    "draw",
    "gain-lore",
    "lose-lore",
    "deal-damage",
    "put-damage",
    "remove-damage",
    "banish",
    "discard",
    "return-to-hand",
    "ready",
    "exert",
    "gain-keyword",
    "gain-keywords",
    "modify-stat",
    "optional",
    "sequence",
    "conditional",
})

# Supported target aliases for trigger projection
# B2: Includes event-derived targets for trigger projection
# NOTE: CHOSEN_* targets are NOT supported - they require player choice prompts
# B3: Supported target aliases for trigger projection
# CHOSEN_* aliases are supported via pending effect layer
SUPPORTED_TARGET_ALIASES = frozenset({
    "SELF",
    "CONTROLLER",
    "ACTOR",
    "YOU",
    "OPPONENT",
    "EACH_OPPONENT",
    "YOUR_CHARACTERS",
    "YOUR_OTHER_CHARACTERS",
    "ALL_OPPOSING_CHARACTERS",
    "OPPOSING_CHARACTERS",
    # B2: Event-derived targets
    "EVENT_SOURCE",
    "EVENT_TARGET",
    "TRIGGER_SUBJECT",
    "DAMAGED_CHARACTERS",
    "ALL_CHARACTERS",
    # B3: CHOSEN_* targets supported via pending effect layer
    "CHOSEN_CHARACTER",
    "CHOSEN_OPPOSING_CHARACTER",
    "CHOSEN_DAMAGED_CHARACTER",
    "CHOSEN_ITEM",
    "CHOSEN_LOCATION",
    "CHOSEN_PLAYER",
    "CHOSEN_CARD",
    "CHOSEN_CARD_FROM_HAND",
    "CHOSEN_CARD_FROM_DISCARD",
    "CHOSEN_CARD_FROM_DECK",
})

# Supported condition kinds for trigger projection
# B2: Expanded with all conditions appearing in real decks
# B3: Removed conditions that cannot be truthfully evaluated (stub-only or raise)
SUPPORTED_CONDITION_KINDS = frozenset({
    # Basic conditions (fully implemented)
    "always",
    "your-turn",
    "opponent-turn",
    "during-turn",
    "turn",
    # Count conditions (fully implemented)
    "has-character-count",
    "has-item-count",
    "has-location-count",
    "has-location-in-play",
    "has-another-character",
    # Character property conditions (fully implemented)
    "has-character-with-keyword",
    "has-character-with-classification",
    "has-character-with-strength",
    "has-named-character",
    "has-named-item",
    # Status conditions (fully implemented)
    "is-exerted",
    "exerted",
    "has-any-damage",
    "no-damage",
    "self-has-damage",
    # Resource conditions (fully implemented)
    "inkwell-count",
    "resource-count",
    # Advanced conditions (fully implemented)
    "target-query",
    "comparison",
    "lore-comparison",
    "card-type-comparison",
    # Event-based conditions (fully implemented)
    "in-challenge",
    "being-challenged",
    # Context conditions (fully implemented)
    "play-context",
    # Logical conditions (fully implemented with error propagation)
    "and",
    "or",
    "not",
    "if",
    # Additional conditions (fully implemented)
    "opponent-has-damaged-character",
    "first-turn-non-otp",
    "is-named",
    "stat-threshold",
})

# Blocked condition kinds - these cannot be truthfully evaluated at runtime
# They block trigger projection rather than allowing incorrect execution
BLOCKED_CONDITION_KINDS = frozenset({
    # Requires tracking state not currently available
    "banished-in-challenge-this-turn",
    "has-card-under",
    "at-location",
    "has-granted-ability",
    "target-aggregate-comparison",
    "trigger-subject-had-card-under",
    "put-card-under-any-this-turn",
    "put-card-under-self-this-turn",
    # Requires card instance tracking
    "used-shift",
})


def project_triggers(card: CardDef) -> tuple[TriggerDef, ...]:
    """Project source triggers into executable TriggerDefs.
    
    Returns an empty tuple if no source triggers can be projected.
    Source triggers stay source-only if:
    - The trigger event is not supported
    - The trigger condition is not supported
    - The trigger effect is not supported
    - The trigger target is not supported
    - The trigger requires unsupported resolution requirements
    """
    if not card.source_abilities:
        return ()
    
    triggers: list[TriggerDef] = []
    for idx, ability in enumerate(card.source_abilities):
        if ability.kind != "triggered":
            continue
        
        trigger = ability.trigger
        if not trigger:
            continue
        
        # Check if trigger event is supported
        if trigger.event not in SUPPORTED_TRIGGER_EVENTS:
            continue
        
        # Check if all effects are supported
        projected_effects: list[EffectDef] = []
        all_effects_supported = True
        
        for effect in ability.effects:
            projected = _project_trigger_effect(effect)
            if projected is None:
                all_effects_supported = False
                break
            projected_effects.append(projected)
        
        if not all_effects_supported:
            continue
        
        # Check if condition is supported (if any)
        projected_condition: dict[str, Any] | None = None
        if ability.condition:
            if ability.condition.kind not in SUPPORTED_CONDITION_KINDS:
                continue
            projected_condition = _project_trigger_condition(ability.condition)
            if projected_condition is None:
                continue
        
        # Check source_zones (play is always supported)
        source_zones = tuple(ability.source_zones) if ability.source_zones else ("play",)
        
        # Build TriggerDef
        trigger_def = TriggerDef(
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
        triggers.append(trigger_def)
    
    return tuple(triggers)


def _project_trigger_effect(effect: SourceEffectDef) -> EffectDef | None:
    """Project a source effect into an EffectDef for trigger execution.
    
    Returns None if the effect cannot be projected.
    
    B3: CHOSEN_* targets are now allowed - they will be resolved via pending effect
    system at runtime, allowing triggers with chosen targets to project.
    """
    kind = ENGINE_EFFECT_MAP.get(effect.kind)
    if not kind:
        return None
    
    if kind not in SUPPORTED_EFFECT_KINDS:
        return None
    
    # Check target if present
    target = None
    if effect.target:
        if effect.target.execution_status != ExecutionStatus.EXECUTABLE:
            return None
        # B2: Check against SUPPORTED_TARGET_ALIASES for trigger projection
        # B3: CHOSEN_* aliases are now supported via pending effect layer
        if effect.target.alias and effect.target.alias not in SUPPORTED_TARGET_ALIASES:
            return None
        target = _project_target(effect.target)
    
    # Check condition if present
    condition = None
    if effect.condition:
        if effect.condition.execution_status != ExecutionStatus.EXECUTABLE:
            return None
        condition = _project_trigger_condition(effect.condition)
    
    # Project children
    children: tuple[EffectDef, ...] = ()
    if effect.effects:
        projected_children = []
        for child in effect.effects:
            p = _project_trigger_effect(child)
            if p is None:
                return None
            projected_children.append(p)
        children = tuple(projected_children)
    
    # Project branches for choice/or
    branches: tuple[EffectDef, ...] = ()
    if effect.branches and effect.kind in {"choice", "or"}:
        projected_branches = []
        for branch in effect.branches:
            p = _project_trigger_effect(branch)
            if p is None:
                return None
            projected_branches.append(p)
        branches = tuple(projected_branches)
    
    # Extract value
    value = effect.raw.get("attribute") or effect.raw.get("stat") or effect.raw.get("cardType") or effect.choice
    keyword = effect.raw.get("keyword")
    
    if effect.kind == "modify-stat":
        value = {str(effect.raw.get("attribute") or "strength"): effect.amount or effect.raw.get("modifier", 0)}
    
    return EffectDef(
        kind=kind,
        amount=int(effect.amount or 0) if isinstance(effect.amount, int) or str(effect.amount or "").isdigit() else 0,
        target=target,
        value=value,
        keyword=_keyword_constant(str(keyword)) if keyword else None,
        effects=children,
        condition=condition,
        optional=effect.kind == "optional" or bool(effect.optional),
        duration=effect.duration if isinstance(effect.duration, str) else None,
        raw=asdict(effect),
    )


def _project_trigger_condition(condition: SourceConditionDef) -> dict[str, Any] | None:
    """Project a source condition into engine format.
    
    Returns None if the condition kind is not supported.
    """
    if condition.kind == "always":
        return {"kind": "always"}
    
    if condition.kind in SUPPORTED_CONDITION_KINDS:
        # Map source condition to engine condition format
        result: dict[str, Any] = {"kind": condition.kind}
        
        if condition.value is not None:
            result["value"] = condition.value
        if condition.comparison is not None:
            result["comparison"] = condition.comparison
        if condition.subject is not None:
            result["subject"] = condition.subject
        
        # Handle logical conditions
        if condition.kind in {"and", "or", "not"} and condition.operands:
            inner_conditions = []
            for op in condition.operands:
                p = _project_trigger_condition(op)
                if p is None:
                    return None
                inner_conditions.append(p)
            if condition.kind == "not":
                result["condition"] = inner_conditions[0] if inner_conditions else None
            else:
                result["conditions"] = inner_conditions
        
        return result
    
    return None


def project_activated_abilities(card: CardDef) -> tuple[AbilityDef, ...]:
    abilities: list[AbilityDef] = []
    for index, ability in enumerate(card.source_abilities):
        if ability.kind != AbilityKind.ACTIVATED:
            continue
        if any(cost.kind not in EXECUTABLE_COSTS for cost in ability.costs):
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
                costs=tuple(AbilityCostDef("exert_source") if cost.kind == "exert" else AbilityCostDef(cost.kind) for cost in ability.costs),
                raw=ability.raw,
            )
        )
    return tuple(abilities)


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


def _project_effect(effect: SourceEffectDef) -> EffectDef | None:
    kind = ENGINE_EFFECT_MAP.get(effect.kind)
    if not kind or kind not in SUPPORTED_EFFECT_KINDS:
        return None
    target = _project_target(effect.target)
    if effect.target is not None and target is None:
        return None
    if effect.condition and effect.condition.execution_status != ExecutionStatus.EXECUTABLE:
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
        amount=int(effect.amount or 0) if isinstance(effect.amount, int) or str(effect.amount or "").isdigit() else 0,
        target=target,
        value=value,
        keyword=_keyword_constant(str(keyword)) if keyword else None,
        effects=nested,
        condition=_project_condition(effect.condition),
        optional=effect.kind == "optional" or bool(effect.optional),
        duration=effect.duration if isinstance(effect.duration, str) else None,
        raw=asdict(effect),
    )


def _project_target(target: SourceTargetDef | None) -> str | None:
    if target is None:
        return None
    if target.alias:
        return TARGET_MAP.get(target.alias)
    return None


def _project_condition(condition: SourceConditionDef | None) -> dict[str, Any] | None:
    if condition is None:
        return None
    if condition.kind == "always":
        return {"kind": "always"}
    if condition.kind == "target_damaged":
        return {"kind": "target_damaged"}
    return None


def _ability_execution_status(kind: str) -> str:
    if kind == AbilityKind.KEYWORD:
        return ExecutionStatus.EXECUTABLE
    if kind in {AbilityKind.STATIC, AbilityKind.REPLACEMENT, AbilityKind.TRIGGERED, AbilityKind.ACTIVATED}:
        return ExecutionStatus.MAPPED_NOT_EXECUTABLE
    if kind == AbilityKind.ACTION:
        return ExecutionStatus.EXECUTABLE
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
    if kind not in ENGINE_EFFECT_MAP:
        return ExecutionStatus.UNSUPPORTED_ENGINE_MECHANIC
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
