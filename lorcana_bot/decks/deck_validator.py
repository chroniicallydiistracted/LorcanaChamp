from __future__ import annotations

from collections import Counter
from typing import Any

from .deck_resolver import normalize_card_name
from .deck_schema import ResolvedDeck

SCHEMA_VERSION = 1


def validate_resolved_deck(deck: ResolvedDeck) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    copy_limit_violations: list[dict[str, Any]] = []
    unresolved_cards: list[dict[str, Any]] = []
    ambiguous_cards: list[dict[str, Any]] = []
    banned_cards: list[dict[str, Any]] = []
    unknown_legality_cards: list[str] = []
    raw_total = sum(card.count for card in deck.cards)

    if deck.format != "core_constructed":
        errors.append(f"unsupported_format:{deck.format}")
    if deck.deck_total_declared != raw_total:
        errors.append(f"deck_total_declared_mismatch:{deck.deck_total_declared}!={raw_total}")
    if deck.deck_total_resolved != sum(card.count for card in deck.cards if card.resolved):
        errors.append("deck_total_resolved_mismatch")
    if raw_total < 60:
        errors.append(f"deck_below_minimum:{raw_total}")
    if len(deck.resolved_ink_colors) > 2:
        errors.append(f"too_many_inks:{','.join(deck.resolved_ink_colors)}")
    if tuple(sorted(deck.raw_ink_colors)) != tuple(sorted(deck.resolved_ink_colors)):
        warnings.append("raw_ink_colors_mismatch")

    for card in deck.cards:
        if not isinstance(card.count, int) or card.count <= 0:
            errors.append(f"non_positive_count:{card.raw_name}")
        if not card.resolved:
            item = {"name": card.raw_name, "reason": card.resolution_error, "candidate_ids": list(card.candidate_ids)}
            if card.resolution_error == "ambiguous_name":
                ambiguous_cards.append(item)
            else:
                unresolved_cards.append(item)
            continue
        if card.raw_type and card.card_type and _normalized_type(card.raw_type) != _normalized_type(card.card_type):
            warnings.append(f"raw_type_mismatch:{card.raw_name}:{card.raw_type}!={card.card_type}")
        unknown_legality_cards.append(card.full_name or card.raw_name)

    if unresolved_cards:
        errors.append("unresolved_cards")
    if ambiguous_cards:
        errors.append("ambiguous_cards")

    counts: Counter[str] = Counter()
    examples = {(_deck_building_identity(card)): card for card in deck.cards}
    for card in deck.cards:
        counts[_deck_building_identity(card)] += card.count
    for identity, count in sorted(counts.items()):
        if count > 4:
            card = examples[identity]
            copy_limit_violations.append({"identity": identity, "name": card.full_name or card.raw_name, "count": count, "maximum": 4})
            errors.append(f"copy_limit:{card.full_name or card.raw_name}:{count}")

    return {
        "schema_version": SCHEMA_VERSION,
        "valid": not errors and not banned_cards,
        "errors": sorted(errors),
        "warnings": sorted(set(warnings)),
        "deck_total_declared": deck.deck_total_declared,
        "deck_total_actual": raw_total,
        "resolved_ink_colors": list(deck.resolved_ink_colors),
        "copy_limit_violations": copy_limit_violations,
        "unresolved_cards": unresolved_cards,
        "ambiguous_cards": ambiguous_cards,
        "banned_cards": banned_cards,
        "unknown_legality_cards": sorted(set(unknown_legality_cards)),
    }


def _deck_building_identity(card) -> str:
    return normalize_card_name(card.full_name or card.raw_name)


def _normalized_type(value: str) -> str:
    key = value.strip().lower()
    return "action" if key == "song" else key
