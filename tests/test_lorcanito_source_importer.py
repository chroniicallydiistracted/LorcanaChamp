import json

from lorcana_bot.importers.lorcanito_source_importer import import_lorcanito_source_cards
from lorcana_bot.importers.lorcanito_source_mapper import _get_amount_shape


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

def test_lore_value_of_amount_shape_accepts_string_target_alias():
    assert (
        _get_amount_shape(
            {
                "type": "lore-value-of",
                "target": "CHOSEN_OPPOSING_CHARACTER",
            }
        )
        == "lore_value_of_target"
    )


def test_import_runtime_card_with_lore_value_of_string_target_alias(tmp_path):
    payload = {
        "schema_version": 1,
        "cards": [
            {
                "id": "Ath",
                "canonicalId": "ci_Ath",
                "cardType": "character",
                "name": "Abu",
                "version": "Illusory Pachyderm",
                "inkType": ["amethyst", "steel"],
                "set": "008",
                "cardNumber": 50,
                "rarity": "uncommon",
                "cost": 6,
                "inkable": True,
                "strength": 3,
                "willpower": 7,
                "lore": 1,
                "classifications": ["Dreamborn", "Ally", "Illusion"],
                "text": [
                    {"title": "Vanish"},
                    {
                        "title": "GRASPING TRUNK",
                        "description": "Whenever this character quests, gain lore equal to the {L} of chosen opposing character.",
                    },
                ],
                "abilities": [
                    {
                        "keyword": "Vanish",
                        "text": "Vanish",
                        "type": "keyword",
                    },
                    {
                        "id": "Ath-2",
                        "name": "GRASPING TRUNK",
                        "text": "GRASPING TRUNK Whenever this character quests, gain lore equal to the {L} of chosen opposing character.",
                        "type": "triggered",
                        "trigger": {
                            "event": "quest",
                            "on": "SELF",
                            "timing": "whenever",
                        },
                        "effect": {
                            "type": "gain-lore",
                            "target": "CONTROLLER",
                            "amount": {
                                "type": "lore-value-of",
                                "target": "CHOSEN_OPPOSING_CHARACTER",
                            },
                        },
                    },
                ],
            }
        ],
    }

    path = tmp_path / "cards.normalized.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    db, report = import_lorcanito_source_cards(path)

    assert report.errors == []
    card = db.get("Ath")
    assert card.id == "Ath"
    assert len(card.source_abilities) == 2
    assert len(card.triggers) == 1
    assert card.triggers[0].event == "quest"
    assert card.triggers[0].effects[0].kind == "gain_lore"
    assert card.triggers[0].effects[0].raw["raw"]["amount"] == {
        "type": "lore-value-of",
        "target": "CHOSEN_OPPOSING_CHARACTER",
    }