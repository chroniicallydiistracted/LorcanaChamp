from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from lorcana_bot.card_logic import AbilityKind, ExecutionStatus, SourceEffectDef
from lorcana_bot.card_logic.resolution_requirements import analyze_resolution_requirements
from lorcana_bot.cards import CardDef
from lorcana_bot.importers.lorcanito_source_importer import import_lorcanito_source_cards
from lorcana_bot.play_modes import get_shift_rules

from .deck_schema import ResolvedDeck, ResolvedDeckCard
from .trigger_blocker_report import (
    analyze_source_trigger_projection,
    build_milestone_recommendation,
    build_trigger_audit_rows,
    build_trigger_summary,
)

SCHEMA_VERSION = 1
CRITICAL_BLOCKERS = {
    "unsupported_trigger",
    "unsupported_static_effect",
    "unsupported_replacement_effect",
    "unsupported_activated_ability",
    "unsupported_effect:choice",
    "unsupported_effect:scry",
    "unsupported_effect:search-deck",
}
CLASSIFICATION_SOURCE = "current_python_runtime"


@dataclass(frozen=True, slots=True)
class RuntimeCardClassification:
    status: str
    blockers: tuple[str, ...]


def load_current_card_defs(source_json: str | Path = "data/lorcanito_extracted/cards.normalized.json") -> dict[str, CardDef]:
    source_path = Path(source_json)
    if not source_path.exists():
        return {}
    db, _ = import_lorcanito_source_cards(source_path)
    return {card.id: card for card in db.all_cards()}


def classify_deck_playability(deck: ResolvedDeck, card_defs: dict[str, CardDef] | None = None) -> str:
    card_defs = card_defs if card_defs is not None else load_current_card_defs()
    validation = deck.validation or {}
    if validation.get("valid") is False or validation.get("unresolved_cards") or validation.get("ambiguous_cards") or validation.get("banned_cards"):
        return "invalid"
    if len(deck.playable_decklist_ids) != deck.deck_total_declared:
        return "invalid"
    classifications = [_classify_card_runtime(card, card_defs) for card in deck.cards]
    blocker_copies = sum(card.count for card, classification in zip(deck.cards, classifications) if classification.blockers)
    if blocker_copies == 0 and all(classification.status == ExecutionStatus.EXECUTABLE for classification in classifications):
        return "fully_executable"
    blockers = {blocker for classification in classifications for blocker in classification.blockers}
    if _has_critical_blocker(blockers):
        return "partially_executable"
    total = max(deck.deck_total_declared, 1)
    if blocker_copies <= total * 0.10:
        return "mostly_executable"
    if sum(card.count for card, classification in zip(deck.cards, classifications) if classification.status != ExecutionStatus.EXECUTABLE) > total * 0.50:
        return "source_only"
    return "partially_executable"


def build_deck_mapping_summary(deck: ResolvedDeck, card_defs: dict[str, CardDef] | None = None) -> dict[str, Any]:
    card_defs = card_defs if card_defs is not None else load_current_card_defs()
    classifications = {_card_key(card): _classify_card_runtime(card, card_defs) for card in deck.cards}
    executable_unique = sum(1 for card in deck.cards if card.resolved and classifications[_card_key(card)].status == ExecutionStatus.EXECUTABLE)
    mapped_not_unique = sum(1 for card in deck.cards if card.resolved and classifications[_card_key(card)].status == ExecutionStatus.MAPPED_NOT_EXECUTABLE)
    unsupported_unique = sum(
        1
        for card in deck.cards
        if classifications[_card_key(card)].status
        not in {ExecutionStatus.EXECUTABLE, ExecutionStatus.MAPPED_NOT_EXECUTABLE}
    )
    executable_copies = sum(card.count for card in deck.cards if card.resolved and classifications[_card_key(card)].status == ExecutionStatus.EXECUTABLE)
    mapped_not_copies = sum(card.count for card in deck.cards if card.resolved and classifications[_card_key(card)].status == ExecutionStatus.MAPPED_NOT_EXECUTABLE)
    unsupported_copies = sum(
        card.count
        for card in deck.cards
        if classifications[_card_key(card)].status
        not in {ExecutionStatus.EXECUTABLE, ExecutionStatus.MAPPED_NOT_EXECUTABLE}
    )
    by_unique, by_copies = _blocker_counters(deck, card_defs)
    runtime_blockers_by_card = _runtime_blockers_by_card(deck, card_defs)
    playability = classify_deck_playability(deck, card_defs)
    return {
        "schema_version": SCHEMA_VERSION,
        "classification_source": CLASSIFICATION_SOURCE,
        "deck_id": deck.id,
        "name": deck.name,
        "valid": bool(deck.validation.get("valid")),
        "playability": playability,
        "stored_playability": deck.playability,
        "total_cards": deck.deck_total_declared,
        "unique_cards": len(deck.cards),
        "resolved_unique_cards": sum(1 for card in deck.cards if card.resolved),
        "unresolved_unique_cards": sum(1 for card in deck.cards if not card.resolved),
        "executable_unique_cards": executable_unique,
        "mapped_not_executable_unique_cards": mapped_not_unique,
        "unsupported_unique_cards": unsupported_unique,
        "executable_copies": executable_copies,
        "mapped_not_executable_copies": mapped_not_copies,
        "unsupported_copies": unsupported_copies,
        "top_blockers_by_unique_cards": _top_counter(by_unique),
        "top_blockers_by_copies": _top_counter(by_copies),
        "recommended_engine_work": _recommended_engine_work_order(by_copies, {deck.id: by_unique}),
        "runtime_blockers_by_card": runtime_blockers_by_card,
        "best_use": _best_use(deck, playability),
    }


def build_suite_mapping_report(resolved_decks: list[ResolvedDeck], card_defs: dict[str, CardDef] | None = None) -> dict[str, Any]:
    card_defs = card_defs if card_defs is not None else load_current_card_defs()

    unique_total: Counter[str] = Counter()
    copy_total: Counter[str] = Counter()
    deck_presence: Counter[str] = Counter()
    by_deck: dict[str, Counter[str]] = {}
    summaries = []

    # Build trigger audit rows
    resolved_decks_dict = []
    for deck in resolved_decks:
        deck_dict = {
            "id": deck.id,
            "name": getattr(deck, 'name', deck.id),
            "cards": [{"card_id": card.card_id, "count": card.count} for card in deck.cards]
        }
        resolved_decks_dict.append(deck_dict)

    trigger_rows = build_trigger_audit_rows(resolved_decks_dict, card_defs)

    # Build trigger summary
    trigger_summary = build_trigger_summary(trigger_rows)

    # Build milestone recommendation
    milestone_rec = build_milestone_recommendation(trigger_summary, trigger_rows)

    for deck in sorted(resolved_decks, key=lambda item: item.id):
        summary = build_deck_mapping_summary(deck, card_defs)
        summaries.append(summary)
        by_unique, by_copies = _blocker_counters(deck, card_defs)
        unique_total.update(by_unique)
        copy_total.update(by_copies)
        by_deck[deck.id] = by_unique
        for blocker in by_unique:
            deck_presence[blocker] += 1
    work_order = _recommended_engine_work_order(copy_total, by_deck)
    # Use trigger milestone if available
    trigger_milestone = milestone_rec.get("recommended_next_milestone", "none")
    final_milestone = trigger_milestone if trigger_milestone != "unknown" else (work_order[0]["category"] if work_order else "none")

    playability_counts = Counter(summary["playability"] for summary in summaries)
    return {
        "schema_version": SCHEMA_VERSION,
        "classification_source": CLASSIFICATION_SOURCE,
        "total_decks": len(resolved_decks),
        "valid_decks": sum(1 for deck in resolved_decks if deck.validation.get("valid")),
        "invalid_decks": sum(1 for deck in resolved_decks if not deck.validation.get("valid")),
        "fully_executable_decks": playability_counts["fully_executable"],
        "mostly_executable_decks": playability_counts["mostly_executable"],
        "partially_executable_decks": playability_counts["partially_executable"],
        "source_only_decks": playability_counts["source_only"],
        "top_blockers_by_unique_cards": _top_counter(unique_total, 30),
        "top_blockers_by_copies": _top_counter(copy_total, 30),
        "top_blockers_by_deck_presence": _top_counter(deck_presence, 30),
        "recommended_next_milestone": final_milestone,
        "recommended_engine_work_order": work_order,
        "trigger_blocker_summary": trigger_summary,
        "best_first_gauntlet_candidates": [
            deck.id
            for deck in sorted(
                resolved_decks,
                key=lambda item: (
                    classify_deck_playability(item, card_defs) not in {"fully_executable", "mostly_executable"},
                    sum(card.count for card in item.cards if _classify_card_runtime(card, card_defs).blockers),
                    item.id,
                ),
            )[:5]
        ],
        "decks": summaries,
    }


def _classify_card_runtime(card: ResolvedDeckCard, card_defs: dict[str, CardDef]) -> RuntimeCardClassification:
    if not card.resolved:
        return RuntimeCardClassification(ExecutionStatus.UNSUPPORTED_ENGINE_MECHANIC, ("unresolved_card",))
    if not card.card_id:
        return RuntimeCardClassification(ExecutionStatus.UNSUPPORTED_ENGINE_MECHANIC, ("missing_card_id",))
    card_def = card_defs.get(card.card_id)
    if card_def is None:
        return RuntimeCardClassification(ExecutionStatus.UNSUPPORTED_ENGINE_MECHANIC, ("missing_current_card_definition",))
    blockers = _runtime_blockers_for_card(card_def)
    if blockers:
        return RuntimeCardClassification(ExecutionStatus.MAPPED_NOT_EXECUTABLE, blockers)
    return RuntimeCardClassification(ExecutionStatus.EXECUTABLE, ())


def _card_key(card: ResolvedDeckCard) -> str:
    return card.card_id or card.canonical_id or card.raw_name


def _runtime_blockers_for_card(card: CardDef) -> tuple[str, ...]:
    blockers: list[str] = []
    for ability in card.source_abilities:
        if ability.kind == AbilityKind.TRIGGERED:
            analysis = analyze_source_trigger_projection(card, ability)
            if not analysis.can_project:
                blockers.extend(blocker for blocker in analysis.blockers if blocker != "activated_ability_reported_separately")
        elif ability.kind == AbilityKind.ACTIVATED:
            blockers.append("unsupported_activated_ability")
            blockers.extend(_cost_blockers(ability.costs))
            blockers.extend(_condition_blockers(ability.condition))
            blockers.extend(_effect_blockers(effect) for effect in ability.effects)
        elif ability.kind == AbilityKind.STATIC:
            blockers.append("unsupported_static_effect")
            blockers.extend(_effect_blockers(effect) for effect in ability.effects)
        elif ability.kind == AbilityKind.REPLACEMENT:
            blockers.append("unsupported_replacement_effect")
            blockers.extend(_effect_blockers(effect) for effect in ability.effects)
        elif ability.kind == AbilityKind.ACTION:
            blockers.extend(_cost_blockers(ability.costs))
            blockers.extend(_condition_blockers(ability.condition))
            blockers.extend(_effect_blockers(effect) for effect in ability.effects)
        elif ability.kind not in {AbilityKind.KEYWORD} and ability.execution_status != ExecutionStatus.EXECUTABLE:
            blockers.append(f"unsupported_ability:{ability.kind}")

    if not card.source_abilities:
        blockers.extend(_effect_blockers(effect) for effect in card.source_effects)

    for static_ability in card.source_static_abilities:
        blockers.append(f"unsupported_static_effect:{static_ability.kind}")
        if static_ability.effect:
            blockers.extend(_effect_blockers(static_ability.effect))
        blockers.extend(_condition_blockers(static_ability.condition))
    for replacement_ability in card.source_replacement_abilities:
        blockers.append(f"unsupported_replacement_effect:{replacement_ability.replaces}")
        if replacement_ability.replacement:
            blockers.extend(_effect_blockers(replacement_ability.replacement))
        blockers.extend(_condition_blockers(replacement_ability.condition))

    keyword_names = {str(keyword).upper() for keyword in card.keywords}
    keyword_names.update(str(keyword.keyword).upper() for keyword in card.keyword_defs)
    if "SING_TOGETHER" in keyword_names or "SINGTOGETHER" in keyword_names:
        blockers.append("keyword:SING_TOGETHER")
    shift_rules = get_shift_rules(card)
    if shift_rules is not None:
        if shift_rules.unsupported_reason:
            blockers.append(f"unsupported_shift:{shift_rules.unsupported_reason}")
        elif shift_rules.ink_cost is None:
            blockers.append("unsupported_shift:missing_cost")

    if not card.source_abilities:
        for unsupported in card.unsupported_abilities:
            raw_kind = str(unsupported.get("type") or unsupported.get("kind") or unsupported.get("_unsupported_reason") or "unknown")
            blockers.append(f"unsupported_ability:{raw_kind}")

    if not card.source_abilities and card.source_execution_status not in {ExecutionStatus.EXECUTABLE, ExecutionStatus.MAPPED_NOT_EXECUTABLE} and not blockers:
        blockers.append(f"source_execution_status:{card.source_execution_status}")
    return _normalize_blockers(_flatten_blockers(blockers))


def _flatten_blockers(items: list[Any]) -> list[str]:
    blockers: list[str] = []
    for item in items:
        if isinstance(item, str):
            blockers.append(item)
        elif isinstance(item, tuple):
            blockers.extend(str(value) for value in item if value)
        elif isinstance(item, list):
            blockers.extend(str(value) for value in item if value)
    return blockers


def _normalize_blockers(blockers: list[str]) -> tuple[str, ...]:
    unique = set(blockers)
    if any(blocker.startswith("unsupported_static_effect:") for blocker in unique):
        unique.discard("unsupported_static_effect")
    if any(blocker.startswith("unsupported_replacement_effect:") for blocker in unique):
        unique.discard("unsupported_replacement_effect")
    if any(blocker.startswith("unsupported_trigger_") for blocker in unique):
        unique.discard("unsupported_trigger")
    return tuple(sorted(unique))


def _effect_blockers(effect: SourceEffectDef) -> tuple[str, ...]:
    blockers: list[str] = []
    if effect.execution_status != ExecutionStatus.EXECUTABLE:
        blockers.append(f"unsupported_effect:{effect.kind}")
    if effect.target is not None and effect.target.execution_status != ExecutionStatus.EXECUTABLE:
        blockers.append(f"unsupported_target:{effect.target.kind}:{effect.target.selector or effect.target.alias or 'unknown'}")
    blockers.extend(_condition_blockers(effect.condition))
    requirements = analyze_resolution_requirements(effect)
    blockers.extend(f"unsupported_resolution_requirement:{requirement}" for requirement in requirements.unsupported_requirements)
    for child in (*effect.effects, *effect.branches):
        blockers.extend(_effect_blockers(child))
    return tuple(blockers)


def _condition_blockers(condition: Any | None) -> tuple[str, ...]:
    if condition is None or condition.execution_status == ExecutionStatus.EXECUTABLE:
        return ()
    return (f"unsupported_condition:{condition.kind}",)


def _cost_blockers(costs: tuple[Any, ...]) -> tuple[str, ...]:
    blockers: list[str] = []
    for cost in costs:
        if cost.execution_status != ExecutionStatus.EXECUTABLE:
            blockers.append(f"unsupported_cost:{cost.kind}")
        if getattr(cost, "selector", None) is not None and cost.selector.execution_status != ExecutionStatus.EXECUTABLE:
            blockers.append(f"unsupported_target:{cost.selector.kind}:{cost.selector.selector or cost.selector.alias or 'unknown'}")
        blockers.extend(_cost_blockers(getattr(cost, "components", ())))
    return tuple(blockers)


def _blocker_counters(deck: ResolvedDeck, card_defs: dict[str, CardDef] | None = None) -> tuple[Counter[str], Counter[str]]:
    card_defs = card_defs if card_defs is not None else load_current_card_defs()
    by_unique: Counter[str] = Counter()
    by_copies: Counter[str] = Counter()
    for card in deck.cards:
        for blocker in _classify_card_runtime(card, card_defs).blockers:
            by_unique[blocker] += 1
            by_copies[blocker] += card.count
    return by_unique, by_copies


def _runtime_blockers_by_card(deck: ResolvedDeck, card_defs: dict[str, CardDef]) -> list[dict[str, Any]]:
    rows = []
    for card in deck.cards:
        classification = _classify_card_runtime(card, card_defs)
        if not classification.blockers:
            continue
        rows.append(
            {
                "card_id": card.card_id,
                "full_name": card.full_name or card.raw_name,
                "count": card.count,
                "runtime_status": classification.status,
                "runtime_blockers": list(classification.blockers),
                "stored_source_execution_status": card.source_execution_status,
                "stored_unsupported_blockers": list(card.unsupported_blockers),
            }
        )
    return rows


def _has_critical_blocker(blockers: set[str]) -> bool:
    return bool(blockers & CRITICAL_BLOCKERS) or any(
        blocker.startswith(("unsupported_resolution_requirement", "unsupported_static_effect:", "unsupported_replacement_effect:", "unsupported_trigger_"))
        for blocker in blockers
    )


def _top_counter(counter: Counter[str], limit: int = 20) -> list[dict[str, Any]]:
    return [{"blocker": key, "count": value} for key, value in sorted(counter.items(), key=lambda item: (-item[1], item[0]))[:limit]]


def _best_use(deck: ResolvedDeck, playability: str) -> str:
    if not deck.validation.get("valid"):
        return "invalid"
    if playability == "fully_executable":
        return "strength_benchmark"
    if playability == "mostly_executable":
        return "diagnostic_gauntlet"
    return "coverage_discovery"


def _recommended_engine_work_order(copy_counts: Counter[str], by_deck: dict[str, Counter[str]]) -> list[dict[str, Any]]:
    category_copies: Counter[str] = Counter()
    category_decks: dict[str, set[str]] = defaultdict(set)
    category_unique: Counter[str] = Counter()
    for deck_id, unique_counts in by_deck.items():
        for blocker, unique_count in unique_counts.items():
            category = _work_category(blocker)
            category_unique[category] += unique_count
            category_decks[category].add(deck_id)
    for blocker, copies in copy_counts.items():
        category_copies[_work_category(blocker)] += copies
    rows = []
    for category in sorted(category_copies):
        rows.append(
            {
                "category": category,
                "affected_copies": category_copies[category],
                "affected_decks": len(category_decks.get(category, set())),
                "affected_unique_cards": category_unique[category],
            }
        )
    return sorted(rows, key=lambda row: (-row["affected_copies"], -row["affected_decks"], _category_priority(row["category"]), row["category"]))


def _work_category(blocker: str) -> str:
    if blocker == "unsupported_trigger" or blocker.startswith("unsupported_trigger_"):
        return "real_bag_and_triggers"
    if blocker == "unsupported_activated_ability" or blocker.startswith("unsupported_cost:"):
        return "activated_abilities"
    if blocker in {"keyword:SINGER", "keyword:SING_TOGETHER"}:
        return "singer_songs"
    if blocker == "keyword:SHIFT" or blocker.startswith("unsupported_shift:"):
        return "shift"
    if blocker.startswith("unsupported_target:") or blocker.startswith("unsupported_resolution_requirement"):
        return "target_choice_prompts"
    if blocker.startswith("unsupported_effect:scry") or blocker.startswith("unsupported_effect:search-deck") or blocker.startswith("unsupported_effect:reveal"):
        return "scry_search_reveal"
    if blocker == "unsupported_static_effect" or blocker.startswith("unsupported_static_effect:"):
        return "static_effect_registry"
    if blocker == "unsupported_replacement_effect" or blocker.startswith("unsupported_replacement_effect:"):
        return "replacement_prevention"
    if blocker.startswith("unsupported_effect:move-damage"):
        return "move_damage"
    return "other_source_execution"


def _category_priority(category: str) -> int:
    order = {
        "real_bag_and_triggers": 0,
        "activated_abilities": 1,
        "singer_songs": 2,
        "shift": 3,
        "target_choice_prompts": 4,
        "scry_search_reveal": 5,
        "static_effect_registry": 6,
        "replacement_prevention": 7,
        "move_damage": 8,
        "other_source_execution": 99,
    }
    return order.get(category, 50)
