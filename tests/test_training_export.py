import json

from lorcana_bot.automation.ml.training_export import trace_to_training_row
from lorcana_bot.automation.planner import take_automated_action
from lorcana_bot.automation.strategy_registry import get_strategy


def test_training_row_schema(engine, state):
    _, trace = take_automated_action(state, engine, get_strategy("deck-aware-lore-race"))
    row = trace_to_training_row(trace)
    assert row["schema_version"] == 1
    assert row["selected_stable_key"] in {candidate["stable_key"] for candidate in row["candidates"]}
    assert json.dumps(row)
