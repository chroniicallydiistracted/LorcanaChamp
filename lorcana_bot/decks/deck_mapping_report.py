from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any

from lorcana_bot.cards import CardDef

from .deck_schema import ResolvedDeck
from .runtime_executability import (
    DeckRuntimeSupport,
    classify_deck_runtime_support,
    load_current_card_defs,
)
from .trigger_blocker_report import (
    build_milestone_recommendation,
    build_trigger_audit_rows,
    build_trigger_summary,
)

SCHEMA_VERSION = 1
CLASSIFICATION_SOURCE = "current_python_runtime"


def classify_deck_playability(deck: ResolvedDeck, card_defs: dict[str, CardDef] | None = None) -> str:
    return classify_deck_runtime_support(deck, card_defs).playability


def build_deck_mapping_summary(
    deck: ResolvedDeck,
    card_defs: dict[str, CardDef] | None = None,
    runtime_support: DeckRuntimeSupport | None = None,
) -> dict[str, Any]:
    card_defs = card_defs if card_defs is not None else load_current_card_defs()
    runtime_support = runtime_support or classify_deck_runtime_support(deck, card_defs)
    count_by_card_id = {card.card_id or card.raw_name: card.count for card in deck.cards}
    executable_unique = sum(1 for result in runtime_support.card_results if result.status == "executable")
    mapped_not_unique = sum(1 for result in runtime_support.card_results if result.status in {"projected_but_requires_pending_input", "scaffold_only"})
    unsupported_unique = sum(1 for result in runtime_support.card_results if result.status in {"unsupported", "source_preserved"})
    executable_copies = sum(count_by_card_id.get(result.card_id, 1) for result in runtime_support.card_results if result.status == "executable")
    mapped_not_copies = sum(count_by_card_id.get(result.card_id, 1) for result in runtime_support.card_results if result.status in {"projected_but_requires_pending_input", "scaffold_only"})
    unsupported_copies = sum(count_by_card_id.get(result.card_id, 1) for result in runtime_support.card_results if result.status in {"unsupported", "source_preserved"})
    by_unique = Counter(runtime_support.blockers_by_unique_cards)
    by_copies = Counter(runtime_support.blockers_by_copies)
    stale_by_copies = Counter(runtime_support.stale_blockers_ignored_by_copies)
    stored_by_copies = Counter(runtime_support.stored_blockers_by_copies)
    runtime_blockers_by_card = _runtime_blockers_by_card(deck, card_defs)
    playability = runtime_support.playability
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
        "stored_resolved_deck_blockers": _top_counter(stored_by_copies),
        "fresh_runtime_blockers": _top_counter(by_copies),
        "stale_blockers_ignored": _top_counter(stale_by_copies),
        "recommended_engine_work": _recommended_engine_work_order(by_copies, {deck.id: by_unique}),
        "runtime_blockers_by_card": runtime_blockers_by_card,
        "fresh_runtime_blockers_by_card": runtime_blockers_by_card,
        "best_use": _best_use(deck, playability),
    }


def build_suite_mapping_report(resolved_decks: list[ResolvedDeck], card_defs: dict[str, CardDef] | None = None) -> dict[str, Any]:
    card_defs = card_defs if card_defs is not None else load_current_card_defs()

    unique_total: Counter[str] = Counter()
    copy_total: Counter[str] = Counter()
    deck_presence: Counter[str] = Counter()
    by_deck: dict[str, Counter[str]] = {}
    summaries = []
    runtime_by_deck: dict[str, DeckRuntimeSupport] = {
        deck.id: classify_deck_runtime_support(deck, card_defs) for deck in resolved_decks
    }

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
        runtime_support = runtime_by_deck[deck.id]
        summary = build_deck_mapping_summary(deck, card_defs, runtime_support)
        summaries.append(summary)
        by_unique = Counter(runtime_support.blockers_by_unique_cards)
        by_copies = Counter(runtime_support.blockers_by_copies)
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
                    runtime_by_deck[item.id].playability not in {"fully_executable", "mostly_executable"},
                    sum(runtime_by_deck[item.id].blockers_by_copies.values()),
                    item.id,
                ),
            )[:5]
        ],
        "decks": summaries,
    }


def _blocker_counters(deck: ResolvedDeck, card_defs: dict[str, CardDef] | None = None) -> tuple[Counter[str], Counter[str]]:
    card_defs = card_defs if card_defs is not None else load_current_card_defs()
    support = classify_deck_runtime_support(deck, card_defs)
    return Counter(support.blockers_by_unique_cards), Counter(support.blockers_by_copies)


def _runtime_blockers_by_card(deck: ResolvedDeck, card_defs: dict[str, CardDef]) -> list[dict[str, Any]]:
    rows = []
    support_by_card_id = {
        result.card_id: result for result in classify_deck_runtime_support(deck, card_defs).card_results
    }
    for card in deck.cards:
        classification = support_by_card_id.get(card.card_id or card.raw_name)
        if classification is None or not classification.blockers:
            continue
        rows.append(
            {
                "card_id": card.card_id,
                "full_name": card.full_name or card.raw_name,
                "count": card.count,
                "runtime_status": classification.status,
                "runtime_blockers": list(classification.blockers),
                "fresh_runtime_blockers": list(classification.fresh_runtime_blockers),
                "stale_blockers_ignored": list(classification.stale_blockers_ignored),
                "runtime_paths_required": list(classification.runtime_paths_required),
                "runtime_paths_verified": list(classification.runtime_paths_verified),
                "stored_source_execution_status": card.source_execution_status,
                "stored_unsupported_blockers": list(card.unsupported_blockers),
                "stored_resolved_deck_blockers": list(card.unsupported_blockers),
            }
        )
    return rows


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
