from lorcana_bot.automation.planner import create_automated_action_plan
from lorcana_bot.automation.strategies.ml_ranked_strategy import MLRankedStrategy


def test_ml_ranked_scores_all_candidates_with_fallback(engine, state):
    plan = create_automated_action_plan(state, engine, MLRankedStrategy())
    assert len(plan.summaries) == len(plan.candidates)
    assert all(any(c.name == "model_unavailable_fallback" for c in s.contributors) for s in plan.summaries)


def test_ml_ranked_never_invents_candidates(engine, state):
    plan = create_automated_action_plan(state, engine, MLRankedStrategy())
    assert {c.stable_key for c in plan.candidates} == {s.stable_key for s in plan.summaries}
