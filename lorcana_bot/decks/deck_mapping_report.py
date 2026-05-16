from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any

from .deck_schema import ResolvedDeck
from .trigger_blocker_report import build_trigger_audit_rows, build_trigger_summary, build_milestone_recommendation
from lorcana_bot.importers.lorcanito_source_importer import import_lorcanito_source_cards

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


def classify_deck_playability(deck: ResolvedDeck) -> str:
    validation = deck.validation or {}
    if validation.get("valid") is False or validation.get("unresolved_cards") or validation.get("ambiguous_cards") or validation.get("banned_cards"):
        return "invalid"
    if len(deck.playable_decklist_ids) != deck.deck_total_declared:
        return "invalid"
    blocker_copies = sum(card.count for card in deck.cards if card.unsupported_blockers)
    if blocker_copies == 0 and all(card.source_execution_status == "executable" for card in deck.cards if card.resolved):
        return "fully_executable"
    blockers = {blocker for card in deck.cards for blocker in card.unsupported_blockers}
    if blockers & CRITICAL_BLOCKERS or any(blocker.startswith("unsupported_resolution_requirement") for blocker in blockers):
        return "partially_executable"
    total = max(deck.deck_total_declared, 1)
    if blocker_copies <= total * 0.10:
        return "mostly_executable"
    if sum(card.count for card in deck.cards if card.source_execution_status != "executable") > total * 0.50:
        return "source_only"
    return "partially_executable"


def build_deck_mapping_summary(deck: ResolvedDeck) -> dict[str, Any]:
    executable_unique = sum(1 for card in deck.cards if card.resolved and card.source_execution_status == "executable" and not card.unsupported_blockers)
    mapped_not_unique = sum(1 for card in deck.cards if card.resolved and card.source_execution_status == "mapped_not_executable")
    unsupported_unique = sum(1 for card in deck.cards if card.resolved and card.source_execution_status not in {"executable", "mapped_not_executable"})
    executable_copies = sum(card.count for card in deck.cards if card.resolved and card.source_execution_status == "executable" and not card.unsupported_blockers)
    mapped_not_copies = sum(card.count for card in deck.cards if card.resolved and card.source_execution_status == "mapped_not_executable")
    unsupported_copies = sum(
        card.count
        for card in deck.cards
        if card.resolved and (card.source_execution_status not in {"executable", "mapped_not_executable"} or bool(card.unsupported_blockers))
    )
    by_unique, by_copies = _blocker_counters(deck)
    return {
        "schema_version": SCHEMA_VERSION,
        "deck_id": deck.id,
        "name": deck.name,
        "valid": bool(deck.validation.get("valid")),
        "playability": deck.playability if deck.playability != "invalid" or deck.validation else classify_deck_playability(deck),
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
        "best_use": _best_use(deck),
    }


def build_suite_mapping_report(resolved_decks: list[ResolvedDeck], card_defs: dict[str, CardDef] | None = None) -> dict[str, Any]:
    # Load card definitions if not provided
    if card_defs is None:
        from pathlib import Path
        source_path = Path("data/lorcanito_extracted/cards.normalized.json")
        if source_path.exists():
            db, _ = import_lorcanito_source_cards(source_path)
            card_defs = {card.id: card for card in db.all_cards()}
        else:
            card_defs = {}

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
        summary = build_deck_mapping_summary(deck)
        summaries.append(summary)
        by_unique, by_copies = _blocker_counters(deck)
        unique_total.update(by_unique)
        copy_total.update(by_copies)
        by_deck[deck.id] = by_unique
        for blocker in by_unique:
            deck_presence[blocker] += 1
    work_order = _recommended_engine_work_order(copy_total, by_deck)
    # Use trigger milestone if available
    trigger_milestone = milestone_rec.get("recommended_next_milestone", "none")
    final_milestone = trigger_milestone if trigger_milestone != "unknown" else (work_order[0]["category"] if work_order else "none")

    return {
        "schema_version": SCHEMA_VERSION,
        "total_decks": len(resolved_decks),
        "valid_decks": sum(1 for deck in resolved_decks if deck.validation.get("valid")),
        "invalid_decks": sum(1 for deck in resolved_decks if not deck.validation.get("valid")),
        "fully_executable_decks": sum(1 for deck in resolved_decks if deck.playability == "fully_executable"),
        "mostly_executable_decks": sum(1 for deck in resolved_decks if deck.playability == "mostly_executable"),
        "partially_executable_decks": sum(1 for deck in resolved_decks if deck.playability == "partially_executable"),
        "source_only_decks": sum(1 for deck in resolved_decks if deck.playability == "source_only"),
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
                    item.playability not in {"fully_executable", "mostly_executable"},
                    sum(card.count for card in item.cards if card.unsupported_blockers),
                    item.id,
                ),
            )[:5]
        ],
        "decks": summaries,
    }


def _blocker_counters(deck: ResolvedDeck) -> tuple[Counter[str], Counter[str]]:
    by_unique: Counter[str] = Counter()
    by_copies: Counter[str] = Counter()
    for card in deck.cards:
        for blocker in card.unsupported_blockers:
            by_unique[blocker] += 1
            by_copies[blocker] += card.count
    return by_unique, by_copies


def _top_counter(counter: Counter[str], limit: int = 20) -> list[dict[str, Any]]:
    return [{"blocker": key, "count": value} for key, value in sorted(counter.items(), key=lambda item: (-item[1], item[0]))[:limit]]


def _best_use(deck: ResolvedDeck) -> str:
    if not deck.validation.get("valid"):
        return "invalid"
    if deck.playability == "fully_executable":
        return "strength_benchmark"
    if deck.playability == "mostly_executable":
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
    if blocker == "unsupported_trigger" or blocker == "unsupported_trigger":
        return "real_bag_and_triggers"
    if blocker == "unsupported_activated_ability" or blocker.startswith("unsupported_cost:"):
        return "activated_abilities"
    if blocker in {"keyword:SINGER", "keyword:SING_TOGETHER"}:
        return "singer_songs"
    if blocker == "keyword:SHIFT":
        return "shift"
    if blocker.startswith("unsupported_target:") or blocker.startswith("unsupported_resolution_requirement"):
        return "target_choice_prompts"
    if blocker.startswith("unsupported_effect:scry") or blocker.startswith("unsupported_effect:search-deck") or blocker.startswith("unsupported_effect:reveal"):
        return "scry_search_reveal"
    if blocker == "unsupported_static_effect":
        return "static_effect_registry"
    if blocker == "unsupported_replacement_effect":
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
