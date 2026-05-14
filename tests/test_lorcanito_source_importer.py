import json

from lorcana_bot.importers.lorcanito_source_importer import import_lorcanito_source_cards


def test_source_importer_loads_generated_cards_and_preserves_raw():
    db, report = import_lorcanito_source_cards("data/lorcanito_extracted/cards.normalized.json")
    assert report.schema_version == 1
    assert report.cards_loaded == len(db.all_cards())
    card = next(card for card in db.all_cards() if card.source_abilities)
    assert card.raw_lorcanito_source
    assert card.source_abilities
    assert card.abilities


def test_unknown_fields_and_abilities_are_not_discarded(tmp_path):
    payload = {
        "schema_version": 1,
        "cards": [
            {
                "id": "x",
                "name": "Test",
                "cardType": "action",
                "inkType": ["amber"],
                "cost": 1,
                "inkable": True,
                "customField": {"kept": True},
                "abilities": [{"type": "unknown-new-type", "custom": 1}],
            }
        ],
    }
    path = tmp_path / "cards.normalized.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    db, report = import_lorcanito_source_cards(path)
    card = db.get("x")
    assert card.raw_lorcanito_source["customField"] == {"kept": True}
    assert card.source_abilities[0].raw["custom"] == 1
    assert report.ability_records_loaded == 1


def test_malicious_mean_and_scary_imports_with_correct_full_name():
    """Regression test: Malicious, Mean, and Scary should import with full name containing commas."""
    db, report = import_lorcanito_source_cards("data/lorcanito_extracted/cards.normalized.json")
    card = db.get("Rc1")
    assert card is not None, "Card Rc1 not found in imported database"
    assert card.full_name == "Malicious, Mean, and Scary", f"Expected full name with commas, got: {card.full_name}"
    assert card.name == "Malicious, Mean, and Scary", f"Expected name with commas, got: {card.name}"
    assert card.card_type == "action"
    # Verify ability/effect structure is preserved
    assert card.effects or card.unsupported_abilities or card.source_abilities

