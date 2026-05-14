from __future__ import annotations

import json
from pathlib import Path

import pytest

from lorcana_bot.cards import CardDatabase, CardDef, FormatRules, load_official_database, validate_deck
from lorcana_bot.constants import CARD_TYPES, INKS


CARD_DATA_DIR = Path(__file__).resolve().parents[1] / "data" / "cards"


@pytest.fixture(scope="module")
def official_db() -> CardDatabase:
    return load_official_database(CARD_DATA_DIR)


def test_official_loader_reads_every_set_file_and_card(official_db):
    expected_count = 0
    expected_ids = set()
    for path in sorted(CARD_DATA_DIR.glob("setdata.*.json")):
        raw = json.loads(path.read_text(encoding="utf-8"))
        assert isinstance(raw.get("cards"), list), f"{path.name} must contain a cards list"
        expected_count += len(raw["cards"])
        for card in raw["cards"]:
            assert card["id"] not in expected_ids, f"Duplicate official id {card['id']} in {path.name}"
            expected_ids.add(card["id"])

    assert len(official_db) == expected_count == 2966
    assert {card.id for card in official_db.all_cards()} == {str(card_id) for card_id in expected_ids}


def test_all_official_cards_satisfy_import_invariants(official_db):
    for card in official_db.all_cards():
        assert card.id, card.full_name
        assert card.full_name, card.id
        assert card.card_type in CARD_TYPES, card.full_name
        assert all(color in INKS for color in card.colors), card.full_name
        assert card.cost >= 0, card.full_name
        assert isinstance(card.inkable, bool), card.full_name
        assert isinstance(card.allowed_in_formats, dict), card.full_name
        assert card.set_code, card.full_name
        assert card.raw, card.full_name

        if card.card_type == "character":
            assert card.strength is not None, card.full_name
            assert card.willpower is not None, card.full_name
            assert card.lore is not None, card.full_name

        if card.card_type == "location":
            assert card.willpower is not None, card.full_name
            assert card.move_cost is not None, card.full_name


def test_official_card_fields_are_normalized_without_losing_raw_metadata(official_db):
    ariel = official_db.get(1)

    assert ariel.id == "1"
    assert ariel.full_name == "Ariel - On Human Legs"
    assert ariel.name == "Ariel"
    assert ariel.card_type == "character"
    assert ariel.colors == ("amber",)
    assert ariel.ink == "amber"
    assert ariel.cost == 4
    assert ariel.inkable is True
    assert ariel.strength == 3
    assert ariel.willpower == 4
    assert ariel.lore == 2
    assert ariel.subtypes == ("Storyborn", "Hero", "Princess")
    assert ariel.rarity == "uncommon"
    assert ariel.set_code == "1"
    assert ariel.set_name == "The First Chapter"
    assert ariel.collector_number == "1"
    assert ariel.full_identifier == "1/204 • EN • 1"
    assert ariel.rules_text
    assert ariel.abilities and ariel.abilities[0]["type"] == "static"
    assert ariel.images["full"].startswith("https://")
    assert ariel.external_links["tcgPlayerId"] == 494102
    assert ariel.allowed_in_tournaments_from_date == "2023-09-08"
    assert ariel.is_allowed_in_format("Core") is False
    assert ariel.is_allowed_in_format("Infinity") is True
    assert ariel.raw["fullName"] == ariel.full_name


def test_official_loader_preserves_multicolor_and_colorless_cards(official_db):
    rhino = official_db.get(1434)
    anna = official_db.get(914)

    assert rhino.full_name == "Rhino - Motivational Speaker"
    assert rhino.colors == ("amber", "steel")
    assert rhino.ink == "amber"

    assert anna.full_name == "Anna - Ensnared Sister"
    assert anna.colors == ()
    assert anna.ink == ""
    assert anna.keywords == ("EVASIVE",)
    assert anna.is_allowed_in_format("Core") is False


def test_official_loader_preserves_actions_songs_items_locations_and_text_effects(official_db):
    song = official_db.get(25)
    item = official_db.get(32)
    location = official_db.get(2223)

    assert song.card_type == "action"
    assert "Song" in song.subtypes
    assert song.text_effects

    assert item.card_type == "item"
    assert item.abilities[0]["type"] == "activated"

    assert location.card_type == "location"
    assert location.move_cost == 2
    assert location.willpower == 6


def test_official_database_requires_ids_for_ambiguous_full_names(official_db):
    matches = official_db.find_by_full_name("Mickey Mouse - True Friend")
    assert len(matches) >= 2

    with pytest.raises(KeyError, match="Ambiguous card name"):
        official_db.get("Mickey Mouse - True Friend")

    assert official_db.get(matches[0].id).full_name == "Mickey Mouse - True Friend"


def test_official_core_validation_rejects_format_illegal_cards(official_db):
    errors = validate_deck(["1"], official_db, FormatRules(min_cards=1))

    assert any("Ariel - On Human Legs is not legal in Core" in error for error in errors)


def test_official_constructed_validation_counts_all_colors_on_multicolor_cards(official_db):
    rules = FormatRules(min_cards=2, max_copies_by_full_name=99, require_format_legal=False)
    errors = validate_deck(["1434", "1453"], official_db, rules)

    assert any("maximum is 2" in error for error in errors)


def test_official_constructed_validation_honors_special_copy_limits(official_db):
    glass_slipper_errors = validate_deck(
        ["1477", "1477", "1641"],
        official_db,
        FormatRules(min_cards=3, require_format_legal=False),
    )
    assert any("The Glass Slipper; maximum is 2" in error for error in glass_slipper_errors)

    dalmatians = ["436", "437", "438", "439", "440", "1702"]
    assert validate_deck(dalmatians, official_db, FormatRules(min_cards=6)) == []

    microbots = ["1366"] * 10
    assert validate_deck(microbots, official_db, FormatRules(min_cards=10)) == []


def test_card_database_rejects_duplicate_ids_loudly():
    card = CardDef("same", "One", "amber", 1, True, "character", 1, 1, 1)

    with pytest.raises(ValueError, match="Card ids must be unique"):
        CardDatabase([card, card])


def test_expanded_card_schema_round_trips_through_json(tmp_path, official_db):
    path = tmp_path / "official.json"
    official_db.save_json(path)

    restored = CardDatabase.load_json(path)
    assert len(restored) == len(official_db)

    original = official_db.get(1434)
    round_tripped = restored.get(1434)
    assert round_tripped.full_name == original.full_name
    assert round_tripped.colors == original.colors
    assert round_tripped.subtypes == original.subtypes
    assert round_tripped.allowed_in_formats == original.allowed_in_formats
    assert round_tripped.raw["fullName"] == original.full_name
