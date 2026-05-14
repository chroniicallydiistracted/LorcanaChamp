from __future__ import annotations

import json

from lorcana_bot.bots import GreedyLoreBot, HeuristicBot
from lorcana_bot.cards import make_demo_deck
from lorcana_bot.engine import GameEngine
from lorcana_bot.traces import export_traces_jsonl, rollout_with_traces


def test_rollout_with_traces_records_legal_candidates_and_selection(db):
    engine = GameEngine(db)
    state = engine.setup_game([make_demo_deck(size=50), make_demo_deck(size=50)], seed=7)

    result = rollout_with_traces(engine, state, (HeuristicBot(seed=1), GreedyLoreBot()), max_actions=30)

    assert result.traces
    first = result.traces[0]
    assert first.legal_actions
    assert 0 <= first.selected_index < len(first.legal_actions)
    assert first.selected_action == first.legal_actions[first.selected_index]
    assert result.game.action_count == len(result.traces)


def test_trace_observation_does_not_export_opponent_hand_card_ids(db):
    engine = GameEngine(db)
    state = engine.setup_game([make_demo_deck(size=50), make_demo_deck(size=50)], seed=7)

    result = rollout_with_traces(engine, state, (HeuristicBot(seed=1), GreedyLoreBot()), max_actions=1)
    trace = result.traces[0]

    for card in trace.observation.public_cards.values():
        assert not (card["zone"] == "hand" and card["controller"] != trace.player)
    assert trace.observation.opponent_hand_count == 7


def test_export_traces_jsonl(tmp_path, db):
    engine = GameEngine(db)
    state = engine.setup_game([make_demo_deck(size=50), make_demo_deck(size=50)], seed=7)
    result = rollout_with_traces(engine, state, (HeuristicBot(seed=1), GreedyLoreBot()), max_actions=3)
    out = tmp_path / "traces.jsonl"

    export_traces_jsonl(result.traces, out)

    rows = [json.loads(line) for line in out.read_text(encoding="utf-8").splitlines()]
    assert len(rows) == len(result.traces)
    assert rows[0]["legal_actions"]
    assert rows[0]["selected_action"] == rows[0]["legal_actions"][rows[0]["selected_index"]]
