from lorcana_bot.actions import Action
from lorcana_bot.constants import ACTION_CHALLENGE, ACTION_END_TURN, ACTION_INK_CARD, ACTION_PLAY_CARD, ACTION_QUEST, ZONE_DISCARD, ZONE_HAND, ZONE_PLAY
from lorcana_bot.engine import GameEngine
from tests.conftest import add_ready_ink, put_card


def find_action(actions, kind, **kwargs):
    for action in actions:
        if action.kind != kind:
            continue
        ok = True
        for key, value in kwargs.items():
            if getattr(action, key) != value:
                ok = False
                break
        if ok:
            return action
    raise AssertionError(f"Missing action {kind} {kwargs}; got {[a.compact() for a in actions]}")


def test_setup_draws_initial_hands_and_first_player_skips_only_initial_draw(state):
    assert len(state.players[0].hand) == 7
    assert len(state.players[1].hand) == 7


def test_end_turn_readies_next_player_and_draws(engine, state):
    p1_hand_before = len(state.players[1].hand)
    action = find_action(engine.legal_actions(state), ACTION_END_TURN)
    state = engine.apply_action(state, action)
    assert state.active_player == 1
    assert len(state.players[1].hand) == p1_hand_before + 1


def test_ink_once_per_turn(engine, state):
    card = put_card(state, engine, 0, "Amber Recruit", ZONE_HAND)
    actions = engine.legal_actions(state)
    ink_action = find_action(actions, ACTION_INK_CARD, card=card)
    state = engine.apply_action(state, ink_action)
    assert state.turn_player_has_inked is True
    assert engine.available_ink(state, 0) == 1
    assert not any(action.kind == ACTION_INK_CARD for action in engine.legal_actions(state))


def test_play_character_pays_ink_and_enters_drying(engine, state):
    card = put_card(state, engine, 0, "Amber Storyteller", ZONE_HAND)
    add_ready_ink(state, engine, 0, 3, exclude=frozenset({card}))
    action = find_action(engine.legal_actions(state), ACTION_PLAY_CARD, card=card)
    state = engine.apply_action(state, action)
    assert card in state.players[0].play
    assert state.cards[card].drying is True
    assert engine.available_ink(state, 0) == 0


def test_drying_character_cannot_quest_until_next_turn(engine, state):
    card = put_card(state, engine, 0, "Amber Storyteller", ZONE_PLAY, drying=True)
    assert not any(action.kind == ACTION_QUEST and action.source == card for action in engine.legal_actions(state))
    state = engine.apply_action(state, find_action(engine.legal_actions(state), ACTION_END_TURN))
    state = engine.apply_action(state, find_action(engine.legal_actions(state), ACTION_END_TURN))
    assert state.active_player == 0
    assert state.cards[card].drying is False
    assert find_action(engine.legal_actions(state), ACTION_QUEST, source=card)


def test_quest_adds_lore_and_can_win(db, state):
    engine = GameEngine(db, lore_to_win=20)
    card = put_card(state, engine, 0, "Amber Storyteller", ZONE_PLAY, drying=False)
    state.players[0].lore = 18
    action = find_action(engine.legal_actions(state), ACTION_QUEST, source=card)
    state = engine.apply_action(state, action)
    assert state.players[0].lore == 21
    assert state.winner == 0


def test_challenge_deals_simultaneous_damage_and_banishes(engine, state):
    source = put_card(state, engine, 0, "Steel Bruiser", ZONE_PLAY, drying=False)
    target = put_card(state, engine, 1, "Sapphire Helper", ZONE_PLAY, exerted=True, drying=False)
    action = find_action(engine.legal_actions(state), ACTION_CHALLENGE, source=source, target=target)
    state = engine.apply_action(state, action)
    assert target in state.players[1].discard
    assert source in state.players[0].play
    assert state.cards[source].damage == 1


def test_bodyguard_restricts_challenge_targets(engine, state):
    source = put_card(state, engine, 0, "Steel Bruiser", ZONE_PLAY, drying=False)
    guard = put_card(state, engine, 1, "Amber Guard", ZONE_PLAY, exerted=True, drying=False)
    other = put_card(state, engine, 1, "Ruby Charger", ZONE_PLAY, exerted=True, drying=False)
    actions = [a for a in engine.legal_actions(state) if a.kind == ACTION_CHALLENGE and a.source == source]
    assert actions
    assert {a.target for a in actions} == {guard}
    assert other not in {a.target for a in actions}


def test_evasive_can_only_be_challenged_by_evasive(engine, state):
    non_evasive = put_card(state, engine, 0, "Steel Bruiser", ZONE_PLAY, drying=False)
    evasive_attacker = put_card(state, engine, 0, "Emerald Scout", ZONE_PLAY, drying=False)
    target = put_card(state, engine, 1, "Emerald Scout", ZONE_PLAY, exerted=True, drying=False)
    actions = engine.legal_actions(state)
    assert not any(a.kind == ACTION_CHALLENGE and a.source == non_evasive and a.target == target for a in actions)
    assert any(a.kind == ACTION_CHALLENGE and a.source == evasive_attacker and a.target == target for a in actions)


def test_action_effect_deals_damage_to_target(engine, state):
    cannon = put_card(state, engine, 0, "Steel Cannon", ZONE_HAND)
    add_ready_ink(state, engine, 0, 2, exclude=frozenset({cannon}))
    target = put_card(state, engine, 1, "Sapphire Helper", ZONE_PLAY, exerted=True, drying=False)
    action = find_action(engine.legal_actions(state), ACTION_PLAY_CARD, card=cannon, target=target)
    state = engine.apply_action(state, action)
    assert cannon in state.players[0].discard
    assert target in state.players[1].discard
