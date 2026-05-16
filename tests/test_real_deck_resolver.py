from lorcana_bot.decks.deck_resolver import build_source_card_index, normalize_card_name, resolve_deck_card
from lorcana_bot.decks.deck_schema import RawDeckCard


def _records():
    return [
        {"id": "a1", "canonicalId": "ca", "name": "Ariel", "version": "On Human Legs", "inkType": ["amber"], "cardType": "character", "cost": 4},
        {"id": "a2", "canonicalId": "ca", "name": "Ariel", "version": "On Human Legs", "inkType": ["amber"], "cardType": "character", "set": "002", "cardNumber": 1},
        {"id": "b1", "canonicalId": "cb", "name": "Mickey Mouse", "version": "Brave Little Tailor", "inkType": ["ruby"], "cardType": "character"},
        {"id": "b2", "canonicalId": "cc", "name": "Mickey Mouse", "version": "Detective", "inkType": ["sapphire"], "cardType": "character"},
        {"id": "c1", "canonicalId": "cd", "name": "Mother Knows Best", "version": "", "inkType": ["emerald"], "cardType": "action"},
    ]


def test_exact_normalized_and_name_version_resolution():
    index = build_source_card_index(_records())

    assert resolve_deck_card(RawDeckCard("Ariel - On Human Legs", 4), index).resolved
    assert resolve_deck_card(RawDeckCard("Mickey Mouse – Brave Little Tailor", 1), index).card_id == "b1"
    assert resolve_deck_card(RawDeckCard("Mother Knows Best", 2), index).card_id == "c1"
    assert normalize_card_name("  Ariel — On Human Legs  ") == "ariel - on human legs"


def test_ambiguous_simple_name_does_not_guess_and_not_found_reports():
    index = build_source_card_index(_records())

    ambiguous = resolve_deck_card(RawDeckCard("Mickey Mouse", 1), index)
    missing = resolve_deck_card(RawDeckCard("No Such Card", 1), index)

    assert ambiguous.resolved is False
    assert ambiguous.resolution_error == "ambiguous_name"
    assert set(ambiguous.candidate_ids) == {"b1", "b2"}
    assert missing.resolved is False
    assert missing.resolution_error == "not_found"


def test_reprint_group_resolves_deterministically_and_preserves_count():
    index = build_source_card_index(_records())

    card = resolve_deck_card(RawDeckCard("Ariel - On Human Legs", 4), index)

    assert card.resolution_status == "resolved_reprint_group"
    assert card.card_id == "a2"
    assert card.count == 4
    assert card.candidate_ids == ("a2", "a1")


def test_malicious_mean_and_scary_resolves_without_alias():
    """Regression test: Malicious, Mean, and Scary should resolve without needing a deck alias."""
    import json
    from pathlib import Path

    source_json = Path("data/lorcanito_extracted/cards.normalized.json")
    if not source_json.exists():
        import pytest
        pytest.skip("cards.normalized.json not available")

    cards_data = json.loads(source_json.read_text())["cards"]
    rc1_card = next((c for c in cards_data if c.get("id") == "Rc1"), None)
    assert rc1_card is not None, "Card Rc1 not found in source"

    # Build index with the actual card
    index = build_source_card_index([rc1_card])

    # Test resolution
    resolved = resolve_deck_card(RawDeckCard("Malicious, Mean, and Scary", 4), index)
    assert resolved.resolved, f"Expected resolved, got status: {resolved.resolution_status}, error: {resolved.resolution_error}"
    assert resolved.card_id == "Rc1" or resolved.canonical_id == "ci_Ggc", f"Expected Rc1 or ci_Ggc, got card_id: {resolved.card_id}, canonical: {resolved.canonical_id}"
