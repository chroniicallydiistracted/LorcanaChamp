from __future__ import annotations

import copy
import json

from lorcana_bot.bots import HeuristicBot
from lorcana_bot.cards import make_demo_deck
from lorcana_bot.cli import _play_with_logs
from lorcana_bot.engine import GameEngine, GameRunner
from lorcana_bot.logging.game_logger import GameLogger, build_game_log_row, state_summary


def _rows(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_game_log_file_created_with_one_row_per_executed_move(tmp_path, db):
    engine = GameEngine(db)
    state = engine.setup_game([make_demo_deck(size=50), make_demo_deck(size=50)], seed=7)
    path = tmp_path / "game.jsonl"
    with GameLogger(path, game_id="test-game") as logger:
        result = GameRunner(engine, max_actions=5).play(
            state,
            (HeuristicBot(seed=1), HeuristicBot(seed=2)),
            on_action=lambda payload: logger.log_move(engine=engine, **payload),
            strategy_names=("heuristic", "heuristic"),
        )

    rows = _rows(path)
    assert path.exists()
    assert len(rows) == result.action_count
    assert all(row["schema_version"] == 1 for row in rows)
    assert rows[0]["selected_action"]["kind"]
    assert "before_summary" in rows[0]
    assert "after_summary" in rows[0]
    assert "new_events_emitted" in rows[0]


def test_public_logs_hide_opponent_private_hand_and_deck(db):
    engine = GameEngine(db)
    state = engine.setup_game([make_demo_deck(size=50), make_demo_deck(size=50)], seed=7)
    action = engine.legal_actions(state, state.active_player)[0]
    next_state = engine.apply_action(state, action)

    row = build_game_log_row(
        game_id="public",
        ply=0,
        before=state,
        after=next_state,
        engine=engine,
        action=action,
        strategy_name="test",
        mode="public",
    )

    opponent = state.opponent(action.actor)
    opponent_summary = row["before_summary"]["players"][opponent]
    assert "hand" not in opponent_summary
    assert "deck" not in opponent_summary
    assert opponent_summary["hand_count"] == 7
    assert opponent_summary["deck_count"] == 43


def test_private_logs_include_reconstructable_state_data(db):
    engine = GameEngine(db)
    state = engine.setup_game([make_demo_deck(size=50), make_demo_deck(size=50)], seed=7)

    summary = state_summary(state, engine, actor=0, mode="private")

    assert "cards" in summary
    assert len(summary["cards"]) == len(state.cards)
    assert "deck" in summary["players"][1]
    assert "hand" in summary["players"][1]
    assert summary["players"][1]["deck"][0]["card_id"]
    assert summary["seed"] == state.seed


def test_decision_trace_and_game_move_logs_can_be_emitted_together(tmp_path, db):
    engine = GameEngine(db)
    state = engine.setup_game([make_demo_deck(size=50), make_demo_deck(size=50)], seed=9)
    game_path = tmp_path / "game.jsonl"
    decision_path = tmp_path / "decisions.jsonl"

    result = _play_with_logs(
        engine,
        state,
        (HeuristicBot(seed=1), HeuristicBot(seed=2)),
        max_actions=4,
        game_log_path=game_path,
        decision_log_path=decision_path,
        log_mode="public",
        strategy_names=("heuristic", "heuristic"),
        automation_strategy_names=(None, None),
        seed=9,
    )

    game_rows = _rows(game_path)
    decision_rows = _rows(decision_path)
    assert len(game_rows) == result.action_count
    assert len(decision_rows) == result.action_count
    assert game_rows[0]["selected_action"]
    assert decision_rows[0]["selected_action"]


def test_logging_does_not_mutate_game_state(db):
    engine = GameEngine(db)
    state = engine.setup_game([make_demo_deck(size=50), make_demo_deck(size=50)], seed=7)
    before = copy.deepcopy(state)

    state_summary(state, engine, actor=0, mode="public")

    assert state == before
