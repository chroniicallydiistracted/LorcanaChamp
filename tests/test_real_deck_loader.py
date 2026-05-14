import json

import pytest

from lorcana_bot.decks.deck_loader import load_raw_deck, load_raw_deck_dir


def test_loads_real_core_decks_ignoring_manifest():
    decks = load_raw_deck_dir("data/decks/real_core")

    assert len(decks) == 12
    assert [deck.id for deck in decks] == sorted(deck.id for deck in decks)
    assert all(deck.id != "real_core_deck_suite_12" for deck in decks)
    assert decks[0].cards
    assert decks[0].cards[0].name
    assert decks[0].cards[0].count > 0


def test_loader_rejects_malformed_deck_with_path(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text(json.dumps({"id": "bad"}), encoding="utf-8")

    with pytest.raises(ValueError, match="bad.json"):
        load_raw_deck(path)
