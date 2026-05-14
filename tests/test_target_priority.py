import copy

from lorcana_bot.automation.target_priority import score_challenge_target, score_target_for_effect
from lorcana_bot.constants import ZONE_PLAY


def put_card(state, engine, player, full_name, zone, *, exerted=False, drying=False, damage=0):
    for cid in state.players[player].deck + state.players[player].hand + state.players[player].play + state.players[player].discard + state.players[player].inkwell:
        if engine.card_def(state, cid).full_name == full_name:
            state.move_card(cid, zone, controller=player)
            state.cards[cid].exerted = exerted
            state.cards[cid].drying = drying
            state.cards[cid].damage = damage
            return cid
    raise AssertionError(full_name)


def test_harmful_prefers_opponent_threat(engine, state):
    own = put_card(state, engine, 0, "Amber Recruit", ZONE_PLAY)
    opp = put_card(state, engine, 1, "Amber Storyteller", ZONE_PLAY)
    assert score_target_for_effect(state, engine, 0, None, opp, "harmful") > score_target_for_effect(state, engine, 0, None, own, "harmful")


def test_beneficial_prefers_own_target(engine, state):
    own = put_card(state, engine, 0, "Amber Recruit", ZONE_PLAY, damage=1)
    opp = put_card(state, engine, 1, "Amber Storyteller", ZONE_PLAY)
    assert score_target_for_effect(state, engine, 0, None, own, "beneficial") > score_target_for_effect(state, engine, 0, None, opp, "beneficial")


def test_challenge_priority_no_mutation(engine, state):
    attacker = put_card(state, engine, 0, "Ruby Charger", ZONE_PLAY, drying=False)
    defender = put_card(state, engine, 1, "Amber Storyteller", ZONE_PLAY, exerted=True)
    before = copy.deepcopy(state)
    assert score_challenge_target(state, engine, attacker, defender) > 0
    assert state == before
