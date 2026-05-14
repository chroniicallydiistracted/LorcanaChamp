from __future__ import annotations

import pytest

from lorcana_bot.actions import Action
from lorcana_bot.constants import (
    ACTION_CONCEDE,
    ACTION_END_TURN,
    ACTION_INK_CARD,
    ACTION_KEEP_HAND,
    ACTION_MULLIGAN,
    ACTION_PLAY_CARD,
    ACTION_QUEST,
    EVENT_CONCEDED,
    EVENT_KEPT_HAND,
    EVENT_MULLIGANED,
    EVENT_TURN_START,
    PHASE_GAME_OVER,
    PHASE_MAIN,
    PHASE_MULLIGAN,
    ZONE_HAND,
    ZONE_PLAY,
)
from lorcana_bot.engine import IllegalActionError
from tests.conftest import add_ready_ink, put_card
from tests.test_engine_core import find_action


def test_setup_can_enter_explicit_mulligan_phase(engine, db):
    state = engine.setup_game([["Amber Recruit"] * 20, ["Amber Guard"] * 20], seed=7, enable_mulligan=True)

    assert state.phase == PHASE_MULLIGAN
    assert state.active_player == state.first_player == 0
    assert len(state.players[0].hand) == 7
    assert len(state.players[1].hand) == 7
    assert state.players[0].has_kept_opening_hand is False
    assert state.players[1].has_kept_opening_hand is False

    actions = engine.legal_actions(state)
    assert len([action for action in actions if action.kind == ACTION_MULLIGAN]) == 127
    assert find_action(actions, ACTION_KEEP_HAND)
    assert find_action(actions, ACTION_CONCEDE)


def test_keep_hand_advances_mulligan_priority_and_starts_game(engine):
    state = engine.setup_game([["Amber Recruit"] * 20, ["Amber Guard"] * 20], seed=7, enable_mulligan=True)

    state = engine.apply_action(state, find_action(engine.legal_actions(state), ACTION_KEEP_HAND))
    assert state.phase == PHASE_MULLIGAN
    assert state.active_player == 1
    assert state.players[0].has_kept_opening_hand is True
    assert state.event_log[-1].event_type == EVENT_KEPT_HAND

    state = engine.apply_action(state, find_action(engine.legal_actions(state), ACTION_KEEP_HAND))
    assert state.phase == PHASE_MAIN
    assert state.active_player == 0
    assert [entry.action.kind for entry in state.action_log] == [ACTION_KEEP_HAND, ACTION_KEEP_HAND]
    assert state.event_log[-1].event_type == EVENT_TURN_START


def test_mulligan_replaces_selected_cards_and_is_logged(engine):
    state = engine.setup_game([["Amber Recruit"] * 20, ["Amber Guard"] * 20], seed=11, enable_mulligan=True)
    selected = tuple(state.players[0].hand[:3])
    action = find_action(engine.legal_actions(state), ACTION_MULLIGAN, choice=selected)

    state = engine.apply_action(state, action)

    assert state.active_player == 1
    assert len(state.players[0].hand) == 7
    assert not any(cid in state.players[0].hand for cid in selected)
    assert state.players[0].has_mulliganed is True
    assert state.players[0].has_kept_opening_hand is True
    assert state.players[0].mulliganed_card_ids == list(selected)
    assert state.event_log[-1].event_type == EVENT_MULLIGANED
    assert state.action_log[-1].action == action


def test_mulligan_is_deterministic_for_same_seed(engine):
    decks = [["Amber Recruit", "Amber Guard", "Amber Storyteller", "Amethyst Scholar"] * 10] * 2
    first = engine.setup_game(decks, seed=99, enable_mulligan=True)
    second = engine.setup_game(decks, seed=99, enable_mulligan=True)

    first_selected = tuple(first.players[0].hand[:2])
    second_selected = tuple(second.players[0].hand[:2])
    assert first_selected == second_selected

    first = engine.apply_action(first, find_action(engine.legal_actions(first), ACTION_MULLIGAN, choice=first_selected))
    second = engine.apply_action(second, find_action(engine.legal_actions(second), ACTION_MULLIGAN, choice=second_selected))

    assert first.players[0].hand == second.players[0].hand
    assert first.players[0].deck == second.players[0].deck


def test_mulligan_rejects_duplicate_or_non_hand_choices(engine, state):
    hand_card = state.players[0].hand[0]
    deck_card = state.players[0].deck[0]
    state.phase = PHASE_MULLIGAN
    state.players[0].has_kept_opening_hand = False

    with pytest.raises(IllegalActionError, match="Illegal action"):
        engine.apply_action(state, Action(ACTION_MULLIGAN, actor=0, choice=(hand_card, hand_card)))

    with pytest.raises(IllegalActionError, match="Illegal action"):
        engine.apply_action(state, Action(ACTION_MULLIGAN, actor=0, choice=(deck_card,)))


def test_concede_sets_winner_logs_event_and_ends_game(engine, state):
    action = find_action(engine.legal_actions(state), ACTION_CONCEDE)
    state = engine.apply_action(state, action)

    assert state.winner == 1
    assert state.loss_reason == "player_0_conceded"
    assert state.phase == PHASE_GAME_OVER
    assert state.event_log[-1].event_type == EVENT_CONCEDED
    assert state.action_log[-1].action == action
    assert engine.legal_actions(state) == []


def test_card_turn_flags_are_set_and_cleared_on_owner_next_turn(engine, state):
    ink_card = put_card(state, engine, 0, "Amber Recruit", ZONE_HAND)
    ink_action = find_action(engine.legal_actions(state), ACTION_INK_CARD, card=ink_card)
    state = engine.apply_action(state, ink_action)
    assert state.cards[ink_card].added_to_ink_this_turn is True
    assert state.players[0].turn_flags.played_ink is True

    character = put_card(state, engine, 0, "Amber Storyteller", ZONE_HAND)
    add_ready_ink(state, engine, 0, 3, exclude=frozenset({ink_card, character}))
    state = engine.apply_action(state, find_action(engine.legal_actions(state), ACTION_PLAY_CARD, card=character))
    assert state.cards[character].just_played is True

    state.cards[character].drying = False
    state = engine.apply_action(state, find_action(engine.legal_actions(state), ACTION_QUEST, source=character))
    assert state.cards[character].has_quested_this_turn is True

    state = engine.apply_action(state, find_action(engine.legal_actions(state), ACTION_END_TURN))
    state = engine.apply_action(state, find_action(engine.legal_actions(state), ACTION_END_TURN))

    assert state.active_player == 0
    assert state.cards[ink_card].added_to_ink_this_turn is False
    assert state.cards[character].just_played is False
    assert state.cards[character].has_quested_this_turn is False
    assert state.players[0].turn_flags.played_ink is False


def test_challenge_records_damage_source_flags(engine, state):
    source = put_card(state, engine, 0, "Steel Bruiser", ZONE_PLAY, drying=False)
    target = put_card(state, engine, 1, "Amber Guard", ZONE_PLAY, exerted=True, drying=False)

    state = engine.apply_action(state, find_action(engine.legal_actions(state), "CHALLENGE", source=source, target=target))

    assert state.cards[target].last_damage_source == source
    assert state.cards[target].last_damage_was_challenge is True
    assert state.cards[target].was_challenged_this_turn is True
    assert state.cards[source].last_damage_source == target
    assert state.cards[source].last_damage_was_challenge is True
