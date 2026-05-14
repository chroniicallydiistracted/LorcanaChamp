from __future__ import annotations

import json
from collections import Counter
from dataclasses import replace
from pathlib import Path
from typing import Any

from lorcana_bot.card_logic import ExecutionStatus, MappingStatus
from lorcana_bot.cards import CardDatabase, CardDef
from lorcana_bot.importers.lorcanito_source_mapper import (
    collect_status_counts,
    map_raw_ability,
    map_replacement_ability,
    map_static_ability,
    project_action_effects,
    project_activated_abilities,
    project_keyword_defs,
    project_keywords,
    project_triggers,
    project_unsupported_abilities,
)
from lorcana_bot.importers.lorcanito_source_schema import LorcanitoSourceImportReport


def load_lorcanito_source_database(
    path: str | Path = "data/lorcanito_extracted/cards.normalized.json",
) -> CardDatabase:
    db, report = import_lorcanito_source_cards(path)
    if report.errors:
        raise ValueError("; ".join(report.errors))
    return db


def import_lorcanito_source_cards(
    path: str | Path = "data/lorcanito_extracted/cards.normalized.json",
) -> tuple[CardDatabase, LorcanitoSourceImportReport]:
    source_path = Path(path)
    payload = json.loads(source_path.read_text(encoding="utf-8"))
    raw_cards = payload.get("cards", payload if isinstance(payload, list) else [])
    cards: list[CardDef] = []
    errors: list[str] = []
    warnings: list[str] = []

    for index, raw in enumerate(raw_cards):
        if not isinstance(raw, dict):
            errors.append(f"card[{index}] is not an object")
            continue
        try:
            cards.append(_card_from_raw(raw))
        except Exception as exc:
            errors.append(f"{raw.get('id') or index}: {exc}")

    report = build_source_import_report(cards, warnings=warnings, errors=errors)
    return CardDatabase(cards), report


def _card_from_raw(raw: dict[str, Any]) -> CardDef:
    source_abilities = tuple(
        map_raw_ability(dict(ability, _source_index=index))
        for index, ability in enumerate(raw.get("abilities", []))
        if isinstance(ability, dict)
    )
    source_effects = tuple(effect for ability in source_abilities for effect in ability.effects)
    source_triggers = tuple(ability.trigger for ability in source_abilities if ability.trigger is not None)
    source_static = tuple(map_static_ability(ability.raw) for ability in source_abilities if ability.kind == "static")
    source_replacements = tuple(map_replacement_ability(ability.raw) for ability in source_abilities if ability.kind == "replacement")

    base = CardDef(
        id=str(raw.get("id") or raw.get("canonicalId") or raw.get("sourceFile")),
        full_name=_full_name(raw),
        ink=_ink(raw),
        cost=int(raw.get("cost") or 0),
        inkable=bool(raw.get("inkable", False)),
        card_type=_card_type(raw),
        strength=_int_or_none(raw.get("strength")),
        willpower=_int_or_none(raw.get("willpower")),
        lore=_int_or_none(raw.get("lore")),
        move_cost=_int_or_none(raw.get("moveCost")),
        version=str(raw.get("version") or ""),
        colors=tuple(str(value).lower() for value in raw.get("inkType", []) if value),
        name=raw.get("name"),
        simple_name=raw.get("name"),
        subtypes=tuple(raw.get("classifications", [])),
        rarity=raw.get("rarity"),
        set_code=str(raw.get("set") or ""),
        collector_number=str(raw.get("cardNumber") or ""),
        rules_text=_rules_text(raw.get("text")),
        abilities=tuple(raw.get("abilities", [])),
        source_abilities=source_abilities,
        source_effects=source_effects,
        source_triggers=source_triggers,
        source_static_abilities=source_static,
        source_replacement_abilities=source_replacements,
        raw_lorcanito_source=dict(raw),
        source_mapping_status=_card_mapping_status(source_abilities),
        source_execution_status=_card_execution_status(source_abilities),
        raw=dict(raw),
    )
    keyword_defs = project_keyword_defs(base)
    keywords = project_keywords(base)
    effects = project_action_effects(base)
    triggers = project_triggers(base)
    activated = project_activated_abilities(base)
    unsupported = project_unsupported_abilities(base)
    return replace(
        base,
        keywords=keywords,
        keyword_defs=keyword_defs,
        effects=effects,
        triggers=triggers,
        activated_abilities=activated,
        unsupported_abilities=unsupported,
    )


def build_source_import_report(
    cards: list[CardDef], *, warnings: list[str] | None = None, errors: list[str] | None = None
) -> LorcanitoSourceImportReport:
    ability_types: Counter[str] = Counter()
    effect_types: Counter[str] = Counter()
    trigger_events: Counter[str] = Counter()
    trigger_on: Counter[str] = Counter()
    conditions: Counter[str] = Counter()
    target_aliases: Counter[str] = Counter()
    target_selectors: Counter[str] = Counter()
    costs: Counter[str] = Counter()
    unsupported: Counter[str] = Counter()
    patterns: Counter[str] = Counter()
    source_files = {card.raw_lorcanito_source.get("sourceFile") for card in cards if card.raw_lorcanito_source.get("sourceFile")}

    for card in cards:
        for ability in card.source_abilities:
            ability_types[ability.kind] += 1
            if ability.execution_status != ExecutionStatus.EXECUTABLE:
                unsupported[ability.execution_status] += 1
                patterns[f"ability.type:{ability.kind}:{ability.execution_status}"] += 1
            if ability.trigger:
                trigger_events[ability.trigger.event] += 1
                if ability.trigger.on:
                    trigger_on[str(ability.trigger.on)] += 1
            if ability.condition:
                conditions[ability.condition.kind] += 1
            for cost in ability.costs:
                costs[cost.kind] += 1
            for effect in ability.effects:
                _count_effect(effect, effect_types, conditions, target_aliases, target_selectors, unsupported, patterns)

    mapping_counts, execution_counts = collect_status_counts(cards)
    return LorcanitoSourceImportReport(
        cards_loaded=len(cards),
        ability_records_loaded=sum(len(card.source_abilities) for card in cards),
        source_files_loaded=len(source_files),
        ability_type_counts=dict(sorted(ability_types.items())),
        effect_type_counts=dict(sorted(effect_types.items())),
        trigger_event_counts=dict(sorted(trigger_events.items())),
        trigger_on_counts=dict(sorted(trigger_on.items())),
        condition_type_counts=dict(sorted(conditions.items())),
        target_alias_counts=dict(sorted(target_aliases.items())),
        target_selector_counts=dict(sorted(target_selectors.items())),
        cost_type_counts=dict(sorted(costs.items())),
        mapping_status_counts=dict(sorted(mapping_counts.items())),
        execution_status_counts=dict(sorted(execution_counts.items())),
        fully_structured_cards=sum(card.source_mapping_status == MappingStatus.STRUCTURALLY_MAPPED for card in cards),
        partially_structured_cards=sum(card.source_mapping_status == MappingStatus.PARTIALLY_MAPPED for card in cards),
        executable_cards=sum(card.source_execution_status == ExecutionStatus.EXECUTABLE for card in cards),
        mapped_not_executable_cards=sum(card.source_execution_status == ExecutionStatus.MAPPED_NOT_EXECUTABLE for card in cards),
        unsupported_cards=sum(card.source_execution_status not in {ExecutionStatus.EXECUTABLE, ExecutionStatus.MAPPED_NOT_EXECUTABLE} for card in cards),
        unsupported_by_reason=dict(sorted(unsupported.items())),
        top_unsupported_patterns=[{"pattern": key, "count": value} for key, value in patterns.most_common(20)],
        warnings=warnings or [],
        errors=errors or [],
    )


def _count_effect(effect, effect_types, conditions, target_aliases, target_selectors, unsupported, patterns) -> None:
    effect_types[effect.kind] += 1
    if effect.condition:
        conditions[effect.condition.kind] += 1
    if effect.target:
        if effect.target.alias:
            target_aliases[effect.target.alias] += 1
        if effect.target.selector:
            target_selectors[effect.target.selector] += 1
    if effect.execution_status != ExecutionStatus.EXECUTABLE:
        unsupported[effect.execution_status] += 1
        patterns[f"effect.type:{effect.kind}:{effect.execution_status}"] += 1
    for child in (*effect.effects, *effect.branches):
        _count_effect(child, effect_types, conditions, target_aliases, target_selectors, unsupported, patterns)


def _full_name(raw: dict[str, Any]) -> str:
    name = str(raw.get("name") or raw.get("id") or "Unknown")
    version = raw.get("version")
    return f"{name} - {version}" if version else name


def _ink(raw: dict[str, Any]) -> str:
    ink = raw.get("inkType") or []
    if isinstance(ink, list) and ink:
        return str(ink[0]).lower()
    return "amber"


def _card_type(raw: dict[str, Any]) -> str:
    value = str(raw.get("cardType") or "action").lower()
    return value if value in {"character", "action", "item", "location"} else "action"


def _int_or_none(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _rules_text(value: Any) -> str | None:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        parts: list[str] = []
        for item in value:
            if isinstance(item, dict):
                parts.extend(str(item[key]) for key in ("title", "description") if item.get(key))
            elif item:
                parts.append(str(item))
        return " ".join(parts)
    return None


def _card_mapping_status(abilities) -> str:
    if not abilities:
        return MappingStatus.RAW_PRESERVED
    statuses = {ability.mapping_status for ability in abilities}
    if statuses == {MappingStatus.STRUCTURALLY_MAPPED}:
        return MappingStatus.STRUCTURALLY_MAPPED
    if MappingStatus.STRUCTURALLY_MAPPED in statuses:
        return MappingStatus.PARTIALLY_MAPPED
    return MappingStatus.UNSUPPORTED


def _card_execution_status(abilities) -> str:
    if not abilities:
        return ExecutionStatus.EXECUTABLE
    statuses = {ability.execution_status for ability in abilities}
    if statuses == {ExecutionStatus.EXECUTABLE}:
        return ExecutionStatus.EXECUTABLE
    if ExecutionStatus.EXECUTABLE in statuses or ExecutionStatus.MAPPED_NOT_EXECUTABLE in statuses:
        return ExecutionStatus.MAPPED_NOT_EXECUTABLE
    return sorted(statuses)[0]
