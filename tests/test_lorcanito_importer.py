from __future__ import annotations

import json
from pathlib import Path

import pytest

from lorcana_bot.constants import CARD_ACTION, CARD_CHARACTER, CARD_ITEM, CARD_LOCATION
from lorcana_bot.importers.lorcanito_importer import import_lorcanito_cards, load_lorcanito_database


CARD_DATA_DIR = Path(__file__).resolve().parents[1] / "data" / "cards"


@pytest.fixture(scope="module")
def import_result():
    return import_lorcanito_cards(CARD_DATA_DIR)


def test_lorcanito_importer_loads_all_setdata_files_and_cards(import_result):
    expected_files = sorted(CARD_DATA_DIR.glob("setdata.*.json"))
    expected_count = sum(len(json.loads(path.read_text(encoding="utf-8"))["cards"]) for path in expected_files)

    assert import_result.report.is_valid
    assert import_result.report.files_loaded == len(expected_files) == 14
    assert import_result.report.cards_loaded == expected_count == 2966
    assert len(import_result.cards) == expected_count


def test_every_card_gets_stable_internal_id_matching_source_id(import_result):
    source_ids = set()
    for path in CARD_DATA_DIR.glob("setdata.*.json"):
        for raw in json.loads(path.read_text(encoding="utf-8"))["cards"]:
            source_ids.add(str(raw["id"]))

    imported_ids = {card.id for card in import_result.cards}

    assert imported_ids == source_ids
    assert len(imported_ids) == len(import_result.cards)
    assert not import_result.report.duplicate_ids


def test_importer_normalizes_representative_character_action_item_location(import_result):
    db = import_result.to_database()
    character = db.get(1)
    action = db.get(25)
    item = db.get(32)
    location = db.get(2223)

    assert character.card_type == CARD_CHARACTER
    assert character.full_name == "Ariel - On Human Legs"
    assert character.ink == "amber"
    assert character.cost == 4
    assert character.inkable is True
    assert character.strength == 3
    assert character.willpower == 4
    assert character.lore == 2

    assert action.card_type == CARD_ACTION
    assert action.full_name == "Be Our Guest"
    assert "Song" in action.subtypes
    assert action.text_effects
    assert any(record["source"] == "effects" for record in action.unsupported_abilities)

    assert item.card_type == CARD_ITEM
    assert item.full_name == "Dinglehopper"
    assert item.abilities[0]["type"] == "activated"
    assert item.unsupported_abilities[0]["type"] == "activated"

    assert location.card_type == CARD_LOCATION
    assert location.full_name == "Duckburg - Funso's Funzone"
    assert location.lore == 0
    assert location.willpower == 6
    assert location.move_cost == 2


def test_keyword_import_covers_core_keyword_set(import_result):
    db = import_result.to_database()

    assert "WARD" in db.get(69).keywords
    assert "RESIST" in db.get(2365).keywords
    assert "BODYGUARD" in db.get(4).keywords
    assert "EVASIVE" in db.get(46).keywords
    assert "RUSH" in db.get(43).keywords

    for keyword in ("WARD", "RESIST", "BODYGUARD", "EVASIVE", "RUSH"):
        assert import_result.report.keyword_counts[keyword] > 0


def test_locations_preserve_lore_willpower_and_move_cost(import_result):
    locations = [card for card in import_result.cards if card.card_type == CARD_LOCATION]

    assert locations
    assert all(location.lore is not None for location in locations)
    assert all(location.willpower is not None for location in locations)
    assert all(location.move_cost is not None for location in locations)
    assert import_result.to_database().get(2223).move_cost == 2


def test_unknown_ability_text_is_preserved_as_structured_unsupported_records(import_result):
    db = import_result.to_database()
    goofy = db.get(4)

    assert goofy.unsupported_abilities
    record = goofy.unsupported_abilities[0]
    assert record["source"] == "ability"
    assert record["type"] == "triggered"
    assert record["name"] == "AND TWO FOR TEA!"
    assert "remove up to 2 damage" in record["effect"]
    assert record["raw"]["fullText"] == record["full_text"]


def test_load_lorcanito_database_returns_card_database(import_result):
    db = load_lorcanito_database(CARD_DATA_DIR)

    assert len(db) == import_result.report.cards_loaded
    assert db.get(1).full_name == "Ariel - On Human Legs"
