from lorcana_bot.cards import DEMO_FEATURE_CARD_IDS, load_demo_database
from lorcana_bot.engine import GameEngine
from lorcana_bot.play_modes import get_shift_rules, is_song_card


def test_demo_database_contains_curated_feature_pool():
    db = load_demo_database()

    for feature, card_id in DEMO_FEATURE_CARD_IDS.items():
        card = db.get(card_id)
        assert card.id == card_id, feature


def test_demo_database_has_core_targeting_card_types_and_keywords():
    db = load_demo_database()

    assert db.get(DEMO_FEATURE_CARD_IDS["basic_character"]).card_type == "character"
    assert "BODYGUARD" in db.get(DEMO_FEATURE_CARD_IDS["bodyguard_character"]).keywords
    assert "EVASIVE" in db.get(DEMO_FEATURE_CARD_IDS["evasive_character"]).keywords
    assert "WARD" in db.get(DEMO_FEATURE_CARD_IDS["ward_character"]).keywords
    assert "RUSH" in db.get(DEMO_FEATURE_CARD_IDS["rush_character"]).keywords
    assert any(keyword.startswith("CHALLENGER") for keyword in db.get(DEMO_FEATURE_CARD_IDS["challenger_character"]).keywords)
    assert any(keyword.startswith("RESIST") for keyword in db.get(DEMO_FEATURE_CARD_IDS["resist_character"]).keywords)
    assert "SINGER" in db.get(DEMO_FEATURE_CARD_IDS["singer_character"]).keywords
    assert db.get(DEMO_FEATURE_CARD_IDS["item"]).card_type == "item"
    assert db.get(DEMO_FEATURE_CARD_IDS["location"]).card_type == "location"


def test_demo_database_has_target_action_cards_for_microfix_10():
    db = load_demo_database()

    assert db.get(DEMO_FEATURE_CARD_IDS["target_character_action"]).effects[0].target == "chosen_character"
    assert db.get(DEMO_FEATURE_CARD_IDS["target_item_action"]).effects[0].target == "chosen_item"
    assert db.get(DEMO_FEATURE_CARD_IDS["target_location_action"]).effects[0].target == "chosen_location"
    assert db.get(DEMO_FEATURE_CARD_IDS["target_player_action"]).effects[0].target == "chosen_player"
    assert db.get(DEMO_FEATURE_CARD_IDS["target_player_action"]).effects[0].kind == "gain_lore"
    assert db.get(DEMO_FEATURE_CARD_IDS["target_damaged_action"]).effects[0].target == "chosen_damaged_character"
    assert db.get(DEMO_FEATURE_CARD_IDS["fixed_opponent_action"]).effects[0].target == "opponent"


def test_demo_database_song_is_detected_by_play_mode_helper():
    db = load_demo_database()
    engine = GameEngine(db)

    song = db.get(DEMO_FEATURE_CARD_IDS["song"])
    assert song.card_type == "action"
    assert song.action_subtype == "song"
    assert is_song_card(engine, song.id)


def test_demo_database_shift_cards_cover_supported_modes_and_unsupported_cost():
    db = load_demo_database()

    same_name = get_shift_rules(db.get(DEMO_FEATURE_CARD_IDS["shift_same_name"]))
    classification = get_shift_rules(db.get(DEMO_FEATURE_CARD_IDS["shift_classification"]))
    universal = get_shift_rules(db.get(DEMO_FEATURE_CARD_IDS["shift_universal"]))
    non_ink = get_shift_rules(db.get(DEMO_FEATURE_CARD_IDS["shift_non_ink_cost"]))

    assert same_name is not None
    assert same_name.ink_cost == 2
    assert same_name.target_mode.type == "name"
    assert same_name.target_mode.name == "Demo Hero"

    assert classification is not None
    assert classification.ink_cost == 3
    assert classification.target_mode.type == "classification"
    assert classification.target_mode.classification == "Sorcerer"

    assert universal is not None
    assert universal.ink_cost == 3
    assert universal.target_mode.type == "universal"

    assert non_ink is not None
    assert non_ink.ink_cost is None
    assert non_ink.discard_cost is not None
    assert non_ink.unsupported_reason is not None
