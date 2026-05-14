import copy

from lorcana_bot.automation.planner import create_automated_action_plan, take_automated_action
from lorcana_bot.automation.strategy_registry import get_strategy


def test_planner_returns_ordered_summaries(engine, state):
    plan = create_automated_action_plan(state, engine, get_strategy("deck-aware-lore-race"))
    assert len(plan.candidates) == len(plan.summaries)
    assert plan.summaries == sorted(plan.summaries, key=lambda s: (s.family_order, -s.score, plan.candidates.index(s.candidate), s.stable_key))


def test_take_automated_action_traces_success(engine, state):
    before = copy.deepcopy(state)
    next_state, trace = take_automated_action(state, engine, get_strategy("deck-aware-lore-race"))
    assert state == before
    assert next_state != state
    assert trace.schema_version == 1
    assert trace.execution_attempts
