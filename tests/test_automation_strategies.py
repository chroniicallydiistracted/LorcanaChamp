from lorcana_bot.automation.candidates import AutomatedActionFamily
from lorcana_bot.automation.planner import create_automated_action_plan
from lorcana_bot.automation.strategy_registry import get_strategy
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


def test_concede_always_last(engine, state):
    plan = create_automated_action_plan(state, engine, get_strategy("deck-aware-lore-race"))
    assert plan.summaries[-1].family == AutomatedActionFamily.CONCEDE
    assert all(summary.contributors for summary in plan.summaries)


def test_quest_only_ranks_quest_first(engine, state):
    cid = put_card(state, engine, 0, "Amber Recruit", ZONE_PLAY, drying=False)
    state.cards[cid].exerted = False
    plan = create_automated_action_plan(state, engine, get_strategy("quest-only-test"))
    assert plan.summaries[0].family == AutomatedActionFamily.QUEST


def test_challenge_only_ranks_challenge_first(engine, state):
    attacker = put_card(state, engine, 0, "Ruby Charger", ZONE_PLAY, drying=False)
    defender = put_card(state, engine, 1, "Amber Storyteller", ZONE_PLAY, exerted=True)
    plan = create_automated_action_plan(state, engine, get_strategy("challenge-only-test"))
    assert plan.summaries[0].family == AutomatedActionFamily.CHALLENGE
