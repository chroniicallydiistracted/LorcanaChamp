"""Trigger blocker report module for detailed trigger classification."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from lorcana_bot.card_logic import (
    ExecutionStatus,
    SourceAbilityDef,
    SourceConditionDef,
    SourceEffectDef,
    SourceTriggerDef,
)
from lorcana_bot.importers.lorcanito_source_mapper import (
    ENGINE_EFFECT_MAP,
    SUPPORTED_AMOUNT_SHAPES,
    SUPPORTED_CONDITION_KINDS,
    SUPPORTED_TARGET_ALIASES,
    SUPPORTED_TRIGGER_EFFECT_KINDS,
    SUPPORTED_TRIGGER_EVENTS,
)
from lorcana_bot.cards import CardDef


# Supported trigger on values (separate from effect target aliases)
# 2C: Added string filters for CHARACTERS_HERE, YOUR_ITEMS, etc.
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
    # 2C: Supported string filters
    "CHARACTERS_HERE",
    "CHARACTER_HERE",
    "ANY_ITEM",
    "YOUR_ACTIONS",
    "YOUR_SONGS",
    "YOUR_CHARACTERS_OR_LOCATIONS",
    "YOUR_CHARACTERS_OR_LOCATIONS_WITH_CARD_UNDER",
})

# Supported engine effect kinds for trigger projection (mapped from source kinds)
SUPPORTED_TRIGGER_ENGINE_EFFECT_KINDS = frozenset({
    "draw",
    "gain_lore",
    "lose_lore",
    "deal_damage",
    "move_damage",
    "remove_damage",
    "banish",
    "discard",
    "return_to_hand",
    "return_from_discard",
    "ready",
    "exert",
    "cost_reduction",
    "pay_cost",
    "additional_inkwell",
    "keyword_grant",
    "temporary_modifier",
    "optional",
    "sequence",
    "choice",
    "select_target",
    "restriction",
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
    "put_into_inkwell",
    "shuffle_deck",
    "shuffle_into_deck",
    "draw_until_hand_size",
    "name_a_card",
    "reveal_and_route",
    "play_card",
    "grant_ability",
    "create_replacement_effect",
    "return_random_from_inkwell",
})


# Blocker family to recommended engine work mapping
BLOCKER_FAMILY_ENGINE_WORK = {
    "trigger_event": "broader_trigger_projection",
    "trigger_on": "broader_trigger_projection",
    "effect_unsupported": "scry_search_reveal",  # default, varies by effect kind
    "target_unsupported": "target_choice_prompts",
    "condition_unsupported": "condition_evaluator_expansion",
    "resolution_requirement": "pending_effect_prompts",
    "static_dependency": "static_effect_registry",
    "replacement_dependency": "replacement_prevention",
    "activated_dependency": "activated_abilities",
    "parser_gap": "unknown_parser_hardening",
    "unknown": "unknown_parser_hardening",
}

# Effect kind to specific recommended engine work
EFFECT_KIND_ENGINE_WORK = {
    "scry": "scry_search_reveal",
    "search-deck": "scry_search_reveal",
    "reveal": "scry_search_reveal",
    "reveal-and-route": "scry_search_reveal",
    "reveal-hand": "scry_search_reveal",
    "reveal-inkwell": "scry_search_reveal",
    "reveal-top-card": "scry_search_reveal",
    "name-a-card": "scry_search_reveal",
    "cost-reduction": "triggered_cost_modifiers",
    "gain-lore": "broader_trigger_projection",
    "lose-lore": "broader_trigger_projection",
    "draw": "broader_trigger_projection",
    "deal-damage": "broader_trigger_projection",
    "put-damage": "broader_trigger_projection",
    "remove-damage": "broader_trigger_projection",
    "ready": "broader_trigger_projection",
    "exert": "broader_trigger_projection",
    "gain-keyword": "temporary_keyword_modifiers",
    "modify-stat": "temporary_stat_modifiers",
    "return-to-hand": "target_choice_prompts",
    "banish": "target_choice_prompts",
    "create-replacement-effect": "replacement_prevention",
    "move-damage": "move_damage",
    "grant-ability": "temporary_ability_modifiers",
    "play-card": "play_card",
}

# Resolution requirement kinds
RESOLUTION_REQUIREMENT_KINDS = {
    "choice",
    "optional",
    "named_card",
    "amount",
    "destination",
    "ordering",
    "opponent_choice",
    "scry_ordering",
    "reveal_routing",
}


@dataclass
class TriggerProjectionAnalysis:
    """Analysis result for a source trigger's projection feasibility."""

    source_ability: SourceAbilityDef
    can_project: bool = False
    projected_trigger_id: str | None = None
    blockers: tuple[str, ...] = field(default_factory=tuple)
    effect_kinds: tuple[str, ...] = field(default_factory=tuple)
    target_kinds: tuple[str, ...] = field(default_factory=tuple)
    condition_kinds: tuple[str, ...] = field(default_factory=tuple)
    cost_kinds: tuple[str, ...] = field(default_factory=tuple)
    resolution_requirements: tuple[str, ...] = field(default_factory=tuple)
    recommended_engine_work: tuple[str, ...] = field(default_factory=tuple)
    failure_reasons: tuple[str, ...] = field(default_factory=tuple)

    @property
    def primary_blocker(self) -> str | None:
        """Return the most specific blocker."""
        if not self.blockers:
            return None
        # Prefer specific blockers over broad unsupported_trigger
        specific_blockers = [b for b in self.blockers if ":" in b]
        if specific_blockers:
            return specific_blockers[0]
        return self.blockers[0]

    @property
    def blocker_family(self) -> str:
        """Determine blocker family from primary blocker."""
        blocker = self.primary_blocker
        if blocker is None:
            return "unknown"

        if blocker.startswith("unsupported_trigger_event:"):
            return "trigger_event"
        if blocker.startswith("unsupported_trigger_on:"):
            return "trigger_on"
        if blocker.startswith("unsupported_trigger_effect:"):
            return "effect_unsupported"
        if blocker.startswith("unsupported_trigger_target:"):
            return "target_unsupported"
        if blocker.startswith("unsupported_trigger_condition:"):
            return "condition_unsupported"
        if blocker.startswith("unsupported_trigger_resolution_requirement:"):
            return "resolution_requirement"
        if blocker == "unsupported_trigger_static_dependency":
            return "static_dependency"
        if blocker.startswith("unsupported_static_effect:"):
            return "static_effect_unsupported"
        if blocker == "unsupported_trigger_replacement_dependency":
            return "replacement_dependency"
        if blocker == "unsupported_trigger_activated_dependency":
            return "activated_dependency"
        if blocker == "unsupported_trigger_parser_gap":
            return "parser_gap"
        if blocker == "unsupported_trigger_unknown":
            return "unknown"
        if blocker == "unsupported_trigger":
            return "unknown"

        return "unknown"


# 2C: Supported keys in trigger on object filters
SUPPORTED_FILTER_KEYS = frozenset({
    "controller",
    "owner",
    "cardType",
    "cardTypes",
    "classification",
    "classifications",
    "name",
    "hasKeyword",
    "excludeSelf",
    "filters",
})

# 2C: Supported filter types within filters[]
SUPPORTED_FILTER_TYPES = frozenset({
    "ink-type",
    "damaged",
    "exerted",
    "ready",
    "has-keyword",
    "has-classification",
    "at-location",
})


def _analyze_trigger_on_filter(on_filter: dict[str, Any]) -> str | None:
    """Analyze a trigger on filter object for supported keys.

    Returns a blocker string if unsupported, None if supported.
    2C: Extended to support object filter keys including filters[].
    """
    for key in on_filter:
        if key not in SUPPORTED_FILTER_KEYS:
            return f"unsupported_trigger_on:complex_filter:{key}"

    # Check filters array if present
    filters_list = on_filter.get("filters")
    if filters_list is not None:
        if not isinstance(filters_list, list):
            return "unsupported_trigger_on:complex_filter:filters"
        for f in filters_list:
            if not isinstance(f, dict):
                return "unsupported_trigger_on:complex_filter:filters"
            filter_type = f.get("type")
            if filter_type not in SUPPORTED_FILTER_TYPES:
                return f"unsupported_trigger_on:complex_filter:filters:{filter_type}"

    # All keys are supported
    return None


def analyze_source_trigger_projection(
    card: CardDef,
    ability: SourceAbilityDef,
) -> TriggerProjectionAnalysis:
    """Analyze whether a source trigger ability can be projected as executable.

    This function performs the same analysis that project_triggers() uses,
    but returns detailed blocker information for reporting purposes.
    """
    # Initialize with extracted info
    effect_kinds = tuple(_extract_effect_kinds(ability.effects))
    target_kinds = tuple(_extract_target_kinds(ability.effects))
    condition_kinds = tuple(_extract_condition_kinds(ability.condition))
    cost_kinds = tuple(c.kind for c in ability.costs)
    resolution_requirements = tuple(_extract_resolution_requirements(ability))

    blockers: list[str] = []
    failure_reasons: list[str] = []

    # Check if this is a triggered ability
    if ability.kind == "activated":
        # B9: Activated abilities now have a separate execution path in the engine.
        # However, they still can't be projected as triggers since they require
        # player activation during main phase rather than automatic trigger.
        # Return a non-blocking marker for reporting purposes only.
        return TriggerProjectionAnalysis(
            source_ability=ability,
            can_project=False,  # Still can't project as trigger, but tracked separately
            blockers=("activated_ability_reported_separately",),
            effect_kinds=effect_kinds,
            target_kinds=target_kinds,
            condition_kinds=condition_kinds,
            cost_kinds=cost_kinds,
            resolution_requirements=resolution_requirements,
            failure_reasons=("activated abilities are executed via USE_ABILITY action",),
            recommended_engine_work=("activated_abilities",),
        )
    if ability.kind != "triggered":
        blockers.append("unsupported_trigger_unknown")
        return TriggerProjectionAnalysis(
            source_ability=ability,
            can_project=False,
            blockers=tuple(blockers),
            effect_kinds=effect_kinds,
            target_kinds=target_kinds,
            condition_kinds=condition_kinds,
            cost_kinds=cost_kinds,
            resolution_requirements=resolution_requirements,
            failure_reasons=tuple(failure_reasons),
            recommended_engine_work=_get_recommended_work(blockers),
        )

    trigger = ability.trigger
    if not trigger:
        blockers.append("unsupported_trigger_unknown")
        return TriggerProjectionAnalysis(
            source_ability=ability,
            can_project=False,
            blockers=tuple(blockers),
            effect_kinds=effect_kinds,
            target_kinds=target_kinds,
            condition_kinds=condition_kinds,
            cost_kinds=cost_kinds,
            resolution_requirements=resolution_requirements,
            failure_reasons=tuple(failure_reasons),
            recommended_engine_work=_get_recommended_work(blockers),
        )

    # Check trigger event
    if trigger.event not in SUPPORTED_TRIGGER_EVENTS:
        blockers.append(f"unsupported_trigger_event:{trigger.event}")
        failure_reasons.append(f"trigger event '{trigger.event}' not supported")

    # Check trigger on
    if trigger.on:
        # Complex filter check
        if isinstance(trigger.on, dict):
            blocker = _analyze_trigger_on_filter(trigger.on)
            if blocker:
                blockers.append(blocker)
                failure_reasons.append(f"trigger on filter has unsupported key: {blocker}")
        elif trigger.on not in SUPPORTED_TRIGGER_ON_VALUES:
            blockers.append(f"unsupported_trigger_on:{trigger.on}")
            failure_reasons.append(f"trigger on '{trigger.on}' not supported")

    # Check effects
    all_effects_supported = True
    for effect in ability.effects:
        effect_blocker = _analyze_effect_support(effect)
        if effect_blocker:
            blockers.append(effect_blocker)
            all_effects_supported = False

    # Check target requirements
    for effect in ability.effects:
        target_blocker = _analyze_target_support(effect)
        if target_blocker:
            blockers.append(target_blocker)

    # Check condition
    if ability.condition:
        cond_kind = ability.condition.kind
        if cond_kind not in SUPPORTED_CONDITION_KINDS:
            blockers.append(f"unsupported_trigger_condition:{cond_kind}")
            failure_reasons.append(f"condition kind '{cond_kind}' not supported")

    # Check resolution requirements
    for req in resolution_requirements:
        blockers.append(f"unsupported_trigger_resolution_requirement:{req}")
        failure_reasons.append(f"resolution requirement '{req}' not supported")

    # Can we project?
    can_project = (
        len(blockers) == 0 and
        trigger.event in SUPPORTED_TRIGGER_EVENTS
    )

    if can_project:
        projected_id = ability.id or f"{card.id}:trigger:{card.source_abilities.index(ability)}"
        return TriggerProjectionAnalysis(
            source_ability=ability,
            can_project=True,
            projected_trigger_id=projected_id,
            blockers=(),
            effect_kinds=effect_kinds,
            target_kinds=target_kinds,
            condition_kinds=condition_kinds,
            cost_kinds=cost_kinds,
            resolution_requirements=resolution_requirements,
            recommended_engine_work=(),
        )

    return TriggerProjectionAnalysis(
        source_ability=ability,
        can_project=False,
        blockers=tuple(blockers),
        effect_kinds=effect_kinds,
        target_kinds=target_kinds,
        condition_kinds=condition_kinds,
        cost_kinds=cost_kinds,
        resolution_requirements=resolution_requirements,
        failure_reasons=tuple(failure_reasons),
        recommended_engine_work=_get_recommended_work(blockers),
    )


def _extract_effect_kinds(effects: tuple[SourceEffectDef, ...]) -> list[str]:
    """Recursively extract effect kinds from an effect tree."""
    kinds = []
    for effect in effects:
        kinds.append(effect.kind)
        if effect.effects:
            kinds.extend(_extract_effect_kinds(effect.effects))
        if effect.branches:
            kinds.extend(_extract_effect_kinds(effect.branches))
    return kinds


def _extract_target_kinds(effects: tuple[SourceEffectDef, ...]) -> list[str]:
    """Extract target alias kinds from an effect tree."""
    kinds = []
    for effect in effects:
        if effect.target:
            kinds.append(effect.target.alias or effect.target.selector or "unknown")
        if effect.effects:
            kinds.extend(_extract_target_kinds(effect.effects))
        if effect.branches:
            kinds.extend(_extract_target_kinds(effect.branches))
    return kinds


def _extract_condition_kinds(condition: SourceConditionDef | None) -> list[str]:
    """Extract condition kinds, including nested and/or/not."""
    if not condition:
        return []
    kinds = [condition.kind]
    if hasattr(condition, 'operands') and condition.operands:
        for op in condition.operands:
            kinds.extend(_extract_condition_kinds(op))
    return kinds


# 4C: Amount shape detection helper (mirrors lorcanito_source_mapper logic)
def _get_amount_shape_from_raw(raw_amount: Any) -> str | None:
    """Determine the shape of an amount value.

    Returns a shape identifier or None for unsupported shapes.
    4C: Used to filter amount resolution requirements to shapes Brief 4A resolver supports.
    """
    if raw_amount is None:
        return "static_integer"  # No amount = 0, but shape is supported

    # Static integer
    if isinstance(raw_amount, int):
        return "static_integer"

    # Numeric string (e.g., "2")
    if isinstance(raw_amount, str) and raw_amount.isdigit():
        return "numeric_string"
    if raw_amount == "all":
        return "all_cards"

    # Static object: {"type": "static", "amount": N}
    if isinstance(raw_amount, dict):
        if raw_amount.get("type") == "static" and "amount" in raw_amount:
            return "static_object"
        # Event snapshot: {"type": "event-snapshot", "key": "drawnCount"}
        if raw_amount.get("type") == "event-snapshot":
            key = raw_amount.get("key")
            if key == "drawnCount":
                return "event_snapshot_drawn_count"
            if key == "cardsUnderCountBeforeBanish":
                return "event_snapshot_cards_under_count"
        if raw_amount.get("type") == "cards-under-self":
            return "cards_under_self"
        if raw_amount.get("type") == "lore-value-of":
            target = raw_amount.get("target")
            if isinstance(target, dict) and target.get("selector") == "chosen":
                return "lore_value_of_target"
        if raw_amount.get("type") == "up-to":
            try:
                if int(raw_amount.get("value") or 0) > 0:
                    return "up_to_choice"
            except (TypeError, ValueError):
                return None
        if raw_amount.get("type") == "filtered-count":
            return "filtered_count"
        if raw_amount.get("type") == "difference":
            return "difference"
        if raw_amount.get("type") == "trigger-amount":
            return "trigger_amount"

    # Unsupported shape
    return None


# 4C: Supported amount shapes that Brief 4A resolver can handle
SUPPORTED_AMOUNT_SHAPES_FOR_REPORT = frozenset({
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


def _extract_resolution_requirements(ability: SourceAbilityDef) -> list[str]:
    """Determine resolution requirements from ability structure.

    4C: Amount resolution requirement is only reported for unsupported shapes.
    Scry ordering resolution requirement is not reported since Brief 4B supports pending scry.
    """
    requirements = []

    # Recursively check all effects
    def _check_effect(effect: SourceEffectDef) -> None:
        if effect.kind == "choice":
            pass
        if effect.kind == "scry":
            # 4C: Do not report scry_ordering as blocker since Brief 4B
            # supports creating pending scry ordering through bag completion
            pass
        if effect.kind == "reveal-and-route":
            requirements.append("reveal_routing")
        if effect.kind == "name-a-card":
            requirements.append("named_card")
        if effect.raw.get("ordering"):
            requirements.append("ordering")
        if effect.raw.get("destination"):
            requirements.append("destination")
        # 4C: Check amount shape - only report as blocker for unsupported shapes
        raw_amount = effect.raw.get("amount") if effect.raw and "amount" in effect.raw else getattr(effect, "amount", None)
        if raw_amount is not None:
            amount_shape = _get_amount_shape_from_raw(raw_amount)
            if amount_shape is None:
                # Unsupported amount shape - report as blocker
                requirements.append("amount")
            # Supported amount shapes are handled by Brief 4A resolver

        # Recursively check child effects
        for child in effect.effects:
            _check_effect(child)

        # Check branches (for conditional effects)
        if hasattr(effect, 'branches') and effect.branches:
            for branch in effect.branches:
                for branch_effect in branch.effects:
                    _check_effect(branch_effect)

    # Check all top-level effects
    for effect in ability.effects:
        _check_effect(effect)

    # Check if ability is optional
    if ability.auto_resolve is False:
        requirements.append("optional")

    # Check for opponent choices (guard against mock objects without target attr)
    for effect in ability.effects:
        if hasattr(effect, 'target') and effect.target and effect.target.alias in {"OPPONENT", "CHOSEN_PLAYER"}:
            requirements.append("opponent_choice")

    return list(set(requirements))


def _analyze_effect_support(effect: SourceEffectDef) -> str | None:
    """Check if effect kind is supported for trigger projection."""
    kind = effect.kind

    # Check if effect kind is in the engine map
    if kind not in ENGINE_EFFECT_MAP:
        return f"unsupported_trigger_effect:{kind}"

    # Check if mapped kind is supported
    mapped_kind = ENGINE_EFFECT_MAP[kind]
    if mapped_kind not in SUPPORTED_TRIGGER_ENGINE_EFFECT_KINDS:
        return f"unsupported_trigger_effect:{kind}"

    # Recursively check children
    for child in effect.effects:
        blocker = _analyze_effect_support(child)
        if blocker:
            return blocker

    return None


def _analyze_target_support(effect: SourceEffectDef) -> str | None:
    """Check if effect target is supported for trigger projection."""
    target = effect.target
    if not target:
        return None

    # B3: CHOSEN_* targets are now supported via pending effect layer
    # Check if target alias is supported
    if target.alias:
        if target.alias not in SUPPORTED_TARGET_ALIASES:
            return f"unsupported_trigger_target:{target.alias}"

    # Check if selector is supported (chosen implies target prompt)
    # B3: Selector-based chosen targets are also supported via pending effects
    if target.selector == "chosen":
        return None  # Now supported via pending effect layer

    # Recursively check children
    for child in effect.effects:
        blocker = _analyze_target_support(child)
        if blocker:
            return blocker

    return None


def _get_recommended_work(blockers: list[str]) -> tuple[str, ...]:
    """Determine recommended engine work from blockers."""
    work_set = set()

    for blocker in blockers:
        if blocker.startswith("unsupported_trigger_event:"):
            work_set.add("broader_trigger_projection")
        elif blocker.startswith("unsupported_trigger_on:"):
            work_set.add("broader_trigger_projection")
        elif blocker.startswith("unsupported_trigger_effect:"):
            effect_kind = blocker.split(":")[1] if ":" in blocker else ""
            if effect_kind in EFFECT_KIND_ENGINE_WORK:
                work_set.add(EFFECT_KIND_ENGINE_WORK[effect_kind])
            else:
                work_set.add("other_source_execution")  # B2: Unknown effect kinds map to other_source_execution
        elif blocker.startswith("unsupported_trigger_target:"):
            work_set.add("target_choice_prompts")
        elif blocker.startswith("unsupported_trigger_condition:"):
            work_set.add("condition_evaluator_expansion")
        elif blocker.startswith("unsupported_trigger_resolution_requirement:"):
            req = blocker.split(":")[1] if ":" in blocker else ""
            if req in {"choice", "optional", "amount", "destination", "opponent_choice"}:
                work_set.add("target_choice_prompts")
            elif req in {"scry_ordering", "reveal_routing", "named_card"}:
                work_set.add("scry_search_reveal")
            elif req == "ordering":
                work_set.add("deck_ordering")
            else:
                work_set.add("pending_effect_prompts")
        elif blocker == "unsupported_trigger_static_dependency":
            work_set.add("static_effect_registry")
        elif blocker == "unsupported_trigger_replacement_dependency":
            work_set.add("replacement_prevention")
        elif blocker == "unsupported_trigger_activated_dependency":
            work_set.add("activated_abilities")
        elif blocker in {"unsupported_trigger_parser_gap", "unsupported_trigger_unknown", "unsupported_trigger"}:
            work_set.add("unknown_parser_hardening")

    return tuple(sorted(work_set))


def build_trigger_audit_rows(
    resolved_decks: list[dict[str, Any]],
    card_defs: dict[str, CardDef],
) -> list[dict[str, Any]]:
    """Build audit rows for all triggers in resolved decks."""
    rows = []

    for deck in resolved_decks:
        deck_id = deck.get("id", "unknown")
        deck_name = deck.get("name", "unknown")

        for card_entry in deck.get("cards", []):
            card_id = card_entry.get("card_id")
            if not card_id or card_id not in card_defs:
                continue

            card_def = card_defs[card_id]
            card_count = card_entry.get("count", 1)
            ink = card_entry.get("ink")
            card_type = card_entry.get("card_type")
            full_name = card_entry.get("full_name", card_def.full_name)

            # Analyze each source ability
            for idx, ability in enumerate(card_def.source_abilities or []):
                if ability.kind != "triggered":
                    continue

                analysis = analyze_source_trigger_projection(card_def, ability)
                trigger = ability.trigger

                row = {
                    "deck_id": deck_id,
                    "deck_name": deck_name,
                    "card_id": card_id,
                    "canonical_id": card_entry.get("canonical_id"),
                    "card_name": card_def.full_name,
                    "card_version": card_entry.get("version"),
                    "full_name": full_name,
                    "card_count": card_count,
                    "ink": ink,
                    "card_type": card_type,
                    "ability_index": idx,
                    "ability_id": ability.id,
                    "ability_name": ability.name,
                    "ability_kind": ability.kind,
                    "trigger_event": trigger.event if trigger else None,
                    "trigger_on": trigger.on if trigger else None,
                    "trigger_timing": trigger.timing if trigger else None,
                    "trigger_source_zones": list(ability.source_zones) if ability.source_zones else ["play"],
                    "effect_kinds": list(analysis.effect_kinds),
                    "target_kinds": list(analysis.target_kinds),
                    "condition_kinds": list(analysis.condition_kinds),
                    "cost_kinds": list(analysis.cost_kinds),
                    "resolution_requirements": list(analysis.resolution_requirements),
                    "raw_trigger": dict(trigger.raw) if trigger else {},
                    "raw_ability": dict(ability.raw),
                    "projection_status": "projected" if analysis.can_project else "not_projected",
                    "execution_status": "executable" if analysis.can_project else "mapped_not_executable",
                    "blockers": list(analysis.blockers),
                    "primary_blocker": analysis.primary_blocker,
                    "blocker_family": analysis.blocker_family,
                    "recommended_engine_work": list(analysis.recommended_engine_work),
                    "appears_in_deck": True,
                    "copy_weight": card_count,
                    "deck_presence_weight": 1,
                }
                rows.append(row)

    return rows


def build_trigger_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Build summary statistics from audit rows."""
    total_rows = len(rows)
    projected_rows = sum(1 for r in rows if r["projection_status"] == "projected")
    blocked_rows = sum(1 for r in rows if r["projection_status"] != "projected")

    # Copy-weighted statistics
    blocked_copies = sum(r["copy_weight"] for r in rows if r["projection_status"] != "projected")
    broad_unsupported = sum(
        r["copy_weight"] for r in rows
        if r.get("primary_blocker") and "unsupported_trigger" in r["primary_blocker"]
        and ":" not in r["primary_blocker"]
    )

    # By primary blocker (exclude projected)
    blocker_copies = Counter()
    blocker_cards = {}  # blocker -> set of card_ids
    blocker_decks = {}  # blocker -> set of deck_ids

    for row in rows:
        if row["projection_status"] == "projected":
            continue
        blocker = row.get("primary_blocker") or "unknown"
        deck_id = row.get("deck_id")
        card_id = row.get("card_id")
        copies = row.get("copy_weight", 1)

        blocker_copies[blocker] += copies
        if blocker not in blocker_cards:
            blocker_cards[blocker] = set()
        blocker_cards[blocker].add(card_id)
        if deck_id:
            if blocker not in blocker_decks:
                blocker_decks[blocker] = set()
            blocker_decks[blocker].add(deck_id)

    # Build by_primary_blocker output
    by_primary_blocker_copies = []
    for blocker, copies in sorted(blocker_copies.items(), key=lambda x: (-x[1], x[0])):
        unique_cards = len(blocker_cards.get(blocker, set()))
        deck_presence = len(blocker_decks.get(blocker, set()))
        # B2: Handle "unknown" blocker specially and guard against empty tuple
        work_result = _get_recommended_work([blocker]) if blocker != "unknown" else ()
        recommended = work_result[0] if work_result else "unknown_parser_hardening"

        by_primary_blocker_copies.append({
            "blocker": blocker,
            "copies": copies,
            "unique_cards": unique_cards,
            "deck_presence": deck_presence,
            "example_cards": [],  # TODO: implement if needed
            "recommended_engine_work": recommended,
        })

    # Build by_recommended_engine_work
    work_copies = Counter()
    work_cards = {}  # work -> set of card_ids
    work_decks = {}  # work -> set of deck_ids

    for row in rows:
        if row["projection_status"] == "projected":
            continue
        for work in row.get("recommended_engine_work", []):
            copies = row.get("copy_weight", 1)
            deck_id = row.get("deck_id")
            card_id = row.get("card_id")
            work_copies[work] += copies
            if work not in work_cards:
                work_cards[work] = set()
            work_cards[work].add(card_id)
            if deck_id:
                if work not in work_decks:
                    work_decks[work] = set()
                work_decks[work].add(deck_id)

    by_recommended_engine_work = []
    for work in sorted(work_copies.keys(), key=lambda x: -work_copies[x]):
        blockers_for_work = list(set(
            r["primary_blocker"]
            for r in rows
            if work in r.get("recommended_engine_work", [])
            and r["projection_status"] != "projected"
        ))
        by_recommended_engine_work.append({
            "recommended_engine_work": work,
            "copies": work_copies[work],
            "unique_cards": len(work_cards.get(work, set())),
            "deck_presence": len(work_decks.get(work, set())),
            "blockers": sorted(blockers_for_work),
        })

    # B2: By trigger event with per-event sets for correct aggregation
    by_trigger_event = []
    event_copies = Counter()
    event_cards = defaultdict(set)  # event -> set of card_ids
    event_decks = defaultdict(set)  # event -> set of deck_ids

    for row in rows:
        if row["projection_status"] == "projected":
            continue
        event = row.get("trigger_event") or "unknown"
        copies = row.get("copy_weight", 1)
        deck_id = row.get("deck_id")
        card_id = row.get("card_id")
        event_copies[event] += copies
        event_cards[event].add(card_id)
        if deck_id:
            event_decks[event].add(deck_id)

    for event in sorted(event_copies.keys(), key=lambda x: -event_copies[x]):
        by_trigger_event.append({
            "trigger_event": event,
            "copies": event_copies[event],
            "unique_cards": len(event_cards[event]),
            "deck_presence": len(event_decks[event]),
        })

    # B2: By trigger on with per-event sets
    by_trigger_on = []
    on_copies = Counter()
    on_cards = defaultdict(set)
    on_decks = defaultdict(set)

    for row in rows:
        if row["projection_status"] == "projected":
            continue
        on_val = row.get("trigger_on")
        # B2: Handle complex trigger_on values (dict/list) that aren't hashable
        if on_val is None:
            on_val = "unknown"
        elif isinstance(on_val, dict):
            # Convert dict to a stable string representation
            on_val = f"filter:{json.dumps(on_val, sort_keys=True)}"
        elif isinstance(on_val, list):
            on_val = f"list:{len(on_val)}"
        else:
            on_val = str(on_val)
        copies = row.get("copy_weight", 1)
        deck_id = row.get("deck_id")
        card_id = row.get("card_id")
        on_copies[on_val] += copies
        on_cards[on_val].add(card_id)
        if deck_id:
            on_decks[on_val].add(deck_id)

    for on_val in sorted(on_copies.keys(), key=lambda x: -on_copies[x]):
        by_trigger_on.append({
            "trigger_on": on_val,
            "copies": on_copies[on_val],
            "unique_cards": len(on_cards[on_val]),
            "deck_presence": len(on_decks[on_val]),
        })

    # B2: By effect kind with per-kind sets
    by_effect_kind = []
    effect_copies = Counter()
    effect_cards = defaultdict(set)
    effect_decks = defaultdict(set)

    for row in rows:
        if row["projection_status"] == "projected":
            continue
        for ek in row.get("effect_kinds", []):
            copies = row.get("copy_weight", 1)
            deck_id = row.get("deck_id")
            card_id = row.get("card_id")
            effect_copies[ek] += copies
            effect_cards[ek].add(card_id)
            if deck_id:
                effect_decks[ek].add(deck_id)

    for ek in sorted(effect_copies.keys(), key=lambda x: -effect_copies[x]):
        by_effect_kind.append({
            "effect_kind": ek,
            "copies": effect_copies[ek],
            "unique_cards": len(effect_cards[ek]),
            "deck_presence": len(effect_decks[ek]),
        })

    # B2: By condition kind with per-kind sets
    by_condition_kind = []
    cond_copies = Counter()
    cond_cards = defaultdict(set)
    cond_decks = defaultdict(set)

    for row in rows:
        if row["projection_status"] == "projected":
            continue
        for ck in row.get("condition_kinds", []):
            copies = row.get("copy_weight", 1)
            deck_id = row.get("deck_id")
            card_id = row.get("card_id")
            cond_copies[ck] += copies
            cond_cards[ck].add(card_id)
            if deck_id:
                cond_decks[ck].add(deck_id)

    for ck in sorted(cond_copies.keys(), key=lambda x: -cond_copies[x]):
        by_condition_kind.append({
            "condition_kind": ck,
            "copies": cond_copies[ck],
            "unique_cards": len(cond_cards[ck]),
            "deck_presence": len(cond_decks[ck]),
        })

    # B2: By target kind with per-kind sets
    by_target_kind = []
    target_copies = Counter()
    target_cards = defaultdict(set)
    target_decks = defaultdict(set)

    for row in rows:
        if row["projection_status"] == "projected":
            continue
        for tk in row.get("target_kinds", []):
            copies = row.get("copy_weight", 1)
            deck_id = row.get("deck_id")
            card_id = row.get("card_id")
            target_copies[tk] += copies
            target_cards[tk].add(card_id)
            if deck_id:
                target_decks[tk].add(deck_id)

    for tk in sorted(target_copies.keys(), key=lambda x: -target_copies[x]):
        by_target_kind.append({
            "target_kind": tk,
            "copies": target_copies[tk],
            "unique_cards": len(target_cards[tk]),
            "deck_presence": len(target_decks[tk]),
        })

    # B2: By resolution requirement with per-kind sets
    by_resolution_requirement = []
    res_copies = Counter()
    res_cards = defaultdict(set)
    res_decks = defaultdict(set)

    for row in rows:
        if row["projection_status"] == "projected":
            continue
        for rr in row.get("resolution_requirements", []):
            copies = row.get("copy_weight", 1)
            deck_id = row.get("deck_id")
            card_id = row.get("card_id")
            res_copies[rr] += copies
            res_cards[rr].add(card_id)
            if deck_id:
                res_decks[rr].add(deck_id)

    for rr in sorted(res_copies.keys(), key=lambda x: -res_copies[x]):
        by_resolution_requirement.append({
            "resolution_requirement": rr,
            "copies": res_copies[rr],
            "unique_cards": len(res_cards[rr]),
            "deck_presence": len(res_decks[rr]),
        })

    return {
        "summary": {
            "total_decks": len(set(r.get("deck_id", "unknown") for r in rows)),
            "total_trigger_rows": total_rows,
            "projected_trigger_rows": projected_rows,
            "blocked_trigger_rows": blocked_rows,
            "blocked_trigger_copies": blocked_copies,
            "broad_unsupported_trigger_copies": broad_unsupported,
            "unclassified_trigger_rows": sum(1 for r in rows if not r.get("primary_blocker")),
        },
        "by_primary_blocker_copies": by_primary_blocker_copies,
        "by_primary_blocker_unique_cards": [],  # Can be derived
        "by_primary_blocker_deck_presence": [],  # Can be derived
        "by_trigger_event": by_trigger_event,
        "by_trigger_on": by_trigger_on,
        "by_effect_kind": by_effect_kind,
        "by_target_kind": by_target_kind,
        "by_condition_kind": by_condition_kind,
        "by_resolution_requirement": by_resolution_requirement,
        "by_recommended_engine_work": by_recommended_engine_work,
        "top_cards_by_blocked_copies": [],  # Can be derived
        "top_decks_by_blocked_copies": [],  # Can be derived
    }


def build_projection_failures(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Build projection failures report."""
    failures = []

    for row in rows:
        if row["projection_status"] == "projected":
            continue

        failure = {
            "card_id": row["card_id"],
            "full_name": row["full_name"],
            "source_file": row.get("raw_ability", {}).get("_source_file", ""),
            "ability_index": row["ability_index"],
            "trigger_event": row["trigger_event"],
            "trigger_on": row["trigger_on"],
            "effect_kinds": row["effect_kinds"],
            "target_kinds": row["target_kinds"],
            "condition_kinds": row["condition_kinds"],
            "resolution_requirements": row["resolution_requirements"],
            "failure_reasons": list(row.get("blockers", [])),
            "raw_snippet": str(row.get("raw_trigger", {}))[:500],
            "deck_ids": [row["deck_id"]],
            "copy_weight": row["copy_weight"],
            "recommended_engine_work": row["recommended_engine_work"],
        }
        failures.append(failure)

    # Summary
    failure_reason_counts_copies = Counter()
    failure_reason_counts_unique = Counter()

    for f in failures:
        card_id = f["card_id"]
        copies = f["copy_weight"]
        for reason in f["failure_reasons"]:
            failure_reason_counts_copies[reason] += copies
            failure_reason_counts_unique[card_id] += 1

    high_impact_failures = sorted(
        failures,
        key=lambda x: (-x["copy_weight"], -len(x["failure_reasons"]))
    )[:20]

    return {
        "failures": failures,
        "summary": {
            "failure_reason_counts_by_copies": dict(failure_reason_counts_copies),
            "failure_reason_counts_by_unique_cards": dict(failure_reason_counts_unique),
            "high_impact_failures": high_impact_failures,
        },
    }


def build_milestone_recommendation(summary: dict[str, Any], rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Build next engine milestone recommendation."""
    # Score each candidate
    candidates = {
        "target_choice_prompts": {"copies": 0, "unique_cards": 0, "deck_presence": 0, "blockers": []},
        "scry_search_reveal": {"copies": 0, "unique_cards": 0, "deck_presence": 0, "blockers": []},
        "activated_abilities": {"copies": 0, "unique_cards": 0, "deck_presence": 0, "blockers": []},
        "singer_songs": {"copies": 0, "unique_cards": 0, "deck_presence": 0, "blockers": []},
        "shift": {"copies": 0, "unique_cards": 0, "deck_presence": 0, "blockers": []},
        "static_effect_registry": {"copies": 0, "unique_cards": 0, "deck_presence": 0, "blockers": []},
        "condition_evaluator_expansion": {"copies": 0, "unique_cards": 0, "deck_presence": 0, "blockers": []},
        "replacement_prevention": {"copies": 0, "unique_cards": 0, "deck_presence": 0, "blockers": []},
        "broader_trigger_projection": {"copies": 0, "unique_cards": 0, "deck_presence": 0, "blockers": []},
        "unknown_parser_hardening": {"copies": 0, "unique_cards": 0, "deck_presence": 0, "blockers": []},
        "move_damage": {"copies": 0, "unique_cards": 0, "deck_presence": 0, "blockers": []},
        "deck_ordering": {"copies": 0, "unique_cards": 0, "deck_presence": 0, "blockers": []},
        "pending_effect_prompts": {"copies": 0, "unique_cards": 0, "deck_presence": 0, "blockers": []},
        "other_source_execution": {"copies": 0, "unique_cards": 0, "deck_presence": 0, "blockers": []},
    }

    # B2: Use per-work sets for unique cards/decks aggregation
    from collections import defaultdict
    work_cards = defaultdict(set)
    work_decks = defaultdict(set)
    work_copies = defaultdict(int)

    for row in rows:
        if row["projection_status"] == "projected":
            continue

        copies = row.get("copy_weight", 1)
        deck_id = row.get("deck_id")
        card_id = row.get("card_id")

        for work in row.get("recommended_engine_work", []):
            work_copies[work] += copies
            work_cards[work].add(card_id)
            work_decks[work].add(deck_id)

            if work in candidates:
                candidates[work]["copies"] = work_copies[work]
                candidates[work]["unique_cards"] = len(work_cards[work])
                candidates[work]["deck_presence"] = len(work_decks[work])

                blocker = row.get("primary_blocker")
                if blocker and blocker not in candidates[work]["blockers"]:
                    candidates[work]["blockers"].append(blocker)

    # Calculate scores
    scored_candidates = []
    for name, data in candidates.items():
        copies = data["copies"]
        unique = data["unique_cards"]
        decks = data["deck_presence"]

        score = copies * 3 + unique * 5 + decks * 10

        # Bonuses
        if name == "target_choice_prompts":
            score += 30
        elif name == "scry_search_reveal":
            score += 20
        elif name == "activated_abilities":
            score += 25
        elif name == "singer_songs":
            score += 25
        elif name == "shift":
            score += 20
        elif name == "static_effect_registry":
            score += 10
        elif name == "replacement_prevention":
            score += 5

        # Prerequisites
        if name == "target_choice_prompts" and any("CHOSEN" in b for b in data["blockers"]):
            score += 50
        if name == "condition_evaluator_expansion" and data["copies"] > 50:
            score += 30
        if name == "broader_trigger_projection" and any("not_projected" in b for b in data["blockers"]):
            score += 25

        # Penalties
        penalties = {
            "replacement_prevention": 30,
            "static_effect_registry": 20,
            "scry_search_reveal": 15,
            "target_choice_prompts": 10,
            "singer_songs": 10,
            "activated_abilities": 10,
            "shift": 5,
        }
        score -= penalties.get(name, 0)

        scored_candidates.append({
            "milestone": name,
            "score": score,
            "copies_affected": copies,
            "unique_cards_affected": unique,
            "deck_presence": decks,
            "representative_blockers": data["blockers"][:5],
            "representative_cards": [],
            "dependencies": [],
            "notes": "",
        })

    # Sort by score
    scored_candidates.sort(key=lambda x: (-x["score"], x["milestone"]))

    # Determine recommended
    if scored_candidates:
        recommended = scored_candidates[0]["milestone"]
        recommended_data = scored_candidates[0]

        # Confidence based on score gap
        if len(scored_candidates) > 1:
            gap = scored_candidates[0]["score"] - scored_candidates[1]["score"]
            if gap > 100:
                confidence = "high"
            elif gap > 30:
                confidence = "medium"
            else:
                confidence = "low"
        else:
            confidence = "high"

        reason = f"Recommended based on copy/unique/deck impact scoring. Top blocker: {recommended_data['representative_blockers'][0] if recommended_data['representative_blockers'] else 'unknown'}"
    else:
        recommended = "unknown"
        confidence = "low"
        reason = "No blockers found"

    # Do not prioritize
    do_not_prioritize = [
        {"milestone": "replacement_prevention", "reason": "low copy impact in current 12 decks"},
        {"milestone": "singer_songs", "reason": "no sing triggers in current decks"},
    ]

    return {
        "schema_version": 1,
        "recommended_next_milestone": recommended,
        "confidence": confidence,
        "reason": reason,
        "ranked_candidates": scored_candidates,
        "do_not_prioritize_yet": do_not_prioritize,
    }
