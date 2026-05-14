from __future__ import annotations

from lorcana_bot.actions import Action
from lorcana_bot.cards import CardDatabase, CardDef, load_demo_database, make_demo_deck
from lorcana_bot.constants import (
    ACTION_CHALLENGE,
    ACTION_MOVE_TO_LOCATION,
    ACTION_PLAY_CARD,
    ACTION_END_TURN,
    CARD_LOCATION,
    EVENT_LOCATION_LORE_GAINED,
    EVENT_MOVED_TO_LOCATION,
    ZONE_HAND,
    ZONE_INKWELL,
    ZONE_PLAY,
)
from lorcana_bot.engine import GameEngine
from tests.conftest import add_ready_ink, put_card


def find_action(actions: list[Action], kind: str, **kwargs) -> Action:
    for action in actions:
        if action.kind != kind:
            continue
        if all(getattr(action, key) == value for key, value in kwargs.items()):
            return action
    raise AssertionError(f"Missing action {kind} {kwargs}; got {[a.compact() for a in actions]}")


def keyword_db() -> CardDatabase:
    cards = load_demo_database().all_cards()
    cards.extend(
        [
            CardDef("test_location", "Training Grounds", "amber", 2, True, "location", willpower=5, lore=1, move_cost=1),
            CardDef("test_location_big", "Fortified Site", "steel", 3, True, "location", willpower=5, lore=2, move_cost=2),
            CardDef("test_ward", "Ward Mouse", "amber", 2, True, "character", 1, 3, 1, keywords=("WARD",)),
            CardDef("test_resist", "Resist Wall", "steel", 2, True, "character", 2, 5, 1, keywords=("RESIST:2",)),
        ]
    )
    return CardDatabase(cards)


def setup_keyword_game() -> tuple[GameEngine, object]:
    db = keyword_db()
    engine = GameEngine(db)
    pool = [
        "Amber Recruit",
        "Amber Guard",
        "Amber Storyteller",
        "Amethyst Scholar",
        "Steel Bruiser",
        "Steel Cannon",
        "Sapphire Helper",
        "Training Grounds",
        "Fortified Site",
        "Ward Mouse",
        "Resist Wall",
    ]
    state = engine.setup_game([make_demo_deck(pool, 50), make_demo_deck(pool, 50)], seed=42)
    return engine, state


def test_character_can_move_to_own_location_by_paying_location_move_cost():
    engine, state = setup_keyword_game()
    character = put_card(state, engine, 0, "Amber Recruit", ZONE_PLAY, exerted=True, drying=False)
    location = put_card(state, engine, 0, "Training Grounds", ZONE_PLAY)
    add_ready_ink(state, engine, 0, 1, exclude=frozenset({character, location}))

    action = find_action(engine.legal_actions(state), ACTION_MOVE_TO_LOCATION, source=character, target=location)
    state = engine.apply_action(state, action)

    assert state.cards[character].location_instance_id == location
    assert state.cards[character].exerted is True
    assert engine.available_ink(state, 0) == 0
    assert any(event.event_type == EVENT_MOVED_TO_LOCATION for event in state.event_log)


def test_location_lore_is_gained_when_that_players_turn_starts():
    engine, state = setup_keyword_game()
    location = put_card(state, engine, 1, "Fortified Site", ZONE_PLAY)
    assert engine.card_def(state, location).card_type == CARD_LOCATION
    assert state.players[1].lore == 0

    state = engine.apply_action(state, find_action(engine.legal_actions(state), ACTION_END_TURN))

    assert state.active_player == 1
    assert state.players[1].lore == 2
    assert any(event.event_type == EVENT_LOCATION_LORE_GAINED and event.actor == 1 for event in state.event_log)


def test_locations_are_challengeable_without_being_exerted_and_do_not_deal_return_damage():
    engine, state = setup_keyword_game()
    source = put_card(state, engine, 0, "Steel Bruiser", ZONE_PLAY, drying=False)
    location = put_card(state, engine, 1, "Training Grounds", ZONE_PLAY, exerted=False)

    action = find_action(engine.legal_actions(state), ACTION_CHALLENGE, source=source, target=location)
    state = engine.apply_action(state, action)

    assert location in state.players[1].play
    assert state.cards[location].damage == 3
    assert state.cards[source].damage == 0


def test_location_is_banished_when_challenge_damage_reaches_willpower():
    engine, state = setup_keyword_game()
    source = put_card(state, engine, 0, "Steel Bruiser", ZONE_PLAY, drying=False)
    location = put_card(state, engine, 1, "Training Grounds", ZONE_PLAY, exerted=False, damage=2)

    action = find_action(engine.legal_actions(state), ACTION_CHALLENGE, source=source, target=location)
    state = engine.apply_action(state, action)

    assert location in state.players[1].discard


def test_bodyguard_blocks_location_challenge_when_bodyguard_is_challengeable():
    engine, state = setup_keyword_game()
    source = put_card(state, engine, 0, "Steel Bruiser", ZONE_PLAY, drying=False)
    guard = put_card(state, engine, 1, "Amber Guard", ZONE_PLAY, exerted=True, drying=False)
    location = put_card(state, engine, 1, "Training Grounds", ZONE_PLAY, exerted=False)

    targets = {a.target for a in engine.legal_actions(state) if a.kind == ACTION_CHALLENGE and a.source == source}

    assert targets == {guard}
    assert location not in targets


def test_ward_prevents_opponent_effect_targeting_but_not_challenges():
    engine, state = setup_keyword_game()
    cannon = put_card(state, engine, 0, "Steel Cannon", ZONE_HAND)
    add_ready_ink(state, engine, 0, 2, exclude=frozenset({cannon}))
    ward = put_card(state, engine, 1, "Ward Mouse", ZONE_PLAY, exerted=True, drying=False)
    challenger = put_card(state, engine, 0, "Steel Bruiser", ZONE_PLAY, drying=False, exclude=frozenset({cannon}))

    actions = engine.legal_actions(state)

    assert not any(a.kind == ACTION_PLAY_CARD and a.card == cannon and a.target == ward for a in actions)
    assert any(a.kind == ACTION_CHALLENGE and a.source == challenger and a.target == ward for a in actions)


def test_resist_reduces_challenge_and_effect_damage():
    engine, state = setup_keyword_game()
    source = put_card(state, engine, 0, "Steel Bruiser", ZONE_PLAY, drying=False)
    resist_target = put_card(state, engine, 1, "Resist Wall", ZONE_PLAY, exerted=True, drying=False)

    state = engine.apply_action(state, find_action(engine.legal_actions(state), ACTION_CHALLENGE, source=source, target=resist_target))

    assert state.cards[resist_target].damage == 1
    assert state.cards[source].damage == 2

    # Reset into a fresh state for action-effect damage.
    engine, state = setup_keyword_game()
    cannon = put_card(state, engine, 0, "Steel Cannon", ZONE_HAND)
    add_ready_ink(state, engine, 0, 2, exclude=frozenset({cannon}))
    resist_target = put_card(state, engine, 1, "Resist Wall", ZONE_PLAY, exerted=True, drying=False)

    state = engine.apply_action(state, find_action(engine.legal_actions(state), ACTION_PLAY_CARD, card=cannon, target=resist_target))

    assert state.cards[resist_target].damage == 0
