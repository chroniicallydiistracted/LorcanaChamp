from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from .bots import AutomationStrategyBot, GreedyLoreBot, HeuristicBot, LinearPolicyBot, RandomLegalBot
from .cards import load_card_database, make_demo_deck
from .engine import GameEngine, GameResult, GameRunner
from .logging.game_logger import GameLogger
from .automation.planner import take_automated_action
from .automation.strategy_registry import get_strategy, list_strategies
from .traces import ActionTrace, DecisionTrace, observation_to_trace


def build_bot(name: str, seed: int | None = None):
    if name == "random":
        return RandomLegalBot(seed=seed)
    if name == "greedy":
        return GreedyLoreBot()
    if name == "heuristic":
        return HeuristicBot(seed=seed)
    if name == "linear":
        return LinearPolicyBot(seed=seed)
    raise ValueError(f"Unknown bot {name}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a Lorcana Core Bot demo game.")
    parser.add_argument("--bot0", choices=["random", "greedy", "heuristic", "linear"], default="heuristic")
    parser.add_argument("--bot1", choices=["random", "greedy", "heuristic", "linear"], default="greedy")
    parser.add_argument("--automation-strategy", choices=list_strategies(), default=None)
    parser.add_argument("--opponent-strategy", choices=list_strategies(), default=None)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--max-actions", type=int, default=500)
    parser.add_argument("--database", choices=["demo", "imported"], default="demo")
    parser.add_argument("--card-data-path", default="data/cards")
    parser.add_argument("--log-game-jsonl", type=Path, default=None)
    parser.add_argument("--log-decisions-jsonl", type=Path, default=None)
    parser.add_argument("--log-mode", choices=["public", "private", "training", "oracle"], default="public")
    args = parser.parse_args()

    db = load_card_database("demo" if args.database == "demo" else "lorcanito", card_data_path=args.card_data_path)
    engine = GameEngine(db)
    if args.database == "demo":
        deck0 = make_demo_deck(["Amber Recruit", "Amber Guard", "Amber Storyteller", "Amethyst Scholar", "Amethyst Insight"])
        deck1 = make_demo_deck(["Steel Bruiser", "Emerald Scout", "Ruby Charger", "Steel Cannon", "Sapphire Helper"])
    else:
        imported_ids = [card.id for card in db.all_cards() if card.inkable]
        deck0 = (imported_ids[:60] if len(imported_ids) >= 60 else imported_ids) * 1
        deck1 = (imported_ids[60:120] if len(imported_ids) >= 120 else imported_ids[:60]) * 1
    state = engine.setup_game([deck0, deck1], seed=args.seed)
    bot0 = AutomationStrategyBot(args.automation_strategy) if args.automation_strategy else build_bot(args.bot0, args.seed)
    bot1 = AutomationStrategyBot(args.opponent_strategy) if args.opponent_strategy else build_bot(args.bot1, args.seed + 1)
    result = _play_with_logs(
        engine,
        state,
        (bot0, bot1),
        max_actions=args.max_actions,
        game_log_path=args.log_game_jsonl,
        decision_log_path=args.log_decisions_jsonl,
        log_mode=args.log_mode,
        strategy_names=(
            args.automation_strategy or args.bot0,
            args.opponent_strategy or args.bot1,
        ),
        automation_strategy_names=(args.automation_strategy, args.opponent_strategy),
        seed=args.seed,
    )
    print(result)


def _play_with_logs(
    engine: GameEngine,
    state,
    bots,
    *,
    max_actions: int,
    game_log_path: Path | None,
    decision_log_path: Path | None,
    log_mode: str,
    strategy_names: tuple[str | None, str | None],
    automation_strategy_names: tuple[str | None, str | None],
    seed: int,
    game_id: str | None = None,
    log_append: bool = False,
    log_metadata: dict | None = None,
) -> GameResult:
    game_id = game_id or f"cli-seed-{seed}"
    metadata = dict(log_metadata or {})
    game_logger = (
        GameLogger(
            game_log_path,
            game_id=game_id,
            mode=log_mode,
            append=log_append,
            extra_metadata=metadata,
        )
        if game_log_path
        else None
    )
    try:
        if any(automation_strategy_names):
            result, decision_rows = _play_automation_loop(
                engine,
                state,
                strategy_names=automation_strategy_names,
                fallback_bots=bots,
                max_actions=max_actions,
                game_logger=game_logger,
                log_mode=log_mode,
            )
        elif decision_log_path:
            result, decision_rows = _play_generic_logged_loop(
                engine,
                state,
                bots,
                strategy_names=strategy_names,
                max_actions=max_actions,
                game_logger=game_logger,
            )
        else:
            runner = GameRunner(engine, max_actions=max_actions)
            callback = None
            if game_logger is not None:
                callback = lambda payload: game_logger.log_move(engine=engine, **payload)
            result = runner.play(state, bots, on_action=callback, strategy_names=strategy_names)
            decision_rows = []
        if decision_log_path:
            decision_log_path.parent.mkdir(parents=True, exist_ok=True)
            with decision_log_path.open("a" if log_append else "w", encoding="utf-8") as fh:
                for row in decision_rows:
                    enriched = dict(row)
                    enriched.update(metadata)
                    enriched.setdefault("game_id", game_id)
                    fh.write(json.dumps(enriched, sort_keys=True) + "\n")
        return result
    finally:
        if game_logger is not None:
            game_logger.close()


def _play_automation_loop(
    engine: GameEngine,
    state,
    *,
    strategy_names: tuple[str | None, str | None],
    fallback_bots,
    max_actions: int,
    game_logger: GameLogger | None,
    log_mode: str,
) -> tuple[GameResult, list[dict]]:
    strategies = []
    for idx, name in enumerate(strategy_names):
        if name:
            strategy = get_strategy(name)
        else:
            strategy = getattr(fallback_bots[idx], "strategy", None)
        if strategy is None:
            strategy = get_strategy("deck-aware-lore-race")
        strategy.information_policy = "oracle" if log_mode in {"private", "oracle"} else "fair"
        strategies.append(strategy)
    decision_rows: list[dict] = []
    actions_taken = 0
    while state.winner is None and actions_taken < max_actions:
        actor = state.active_player
        before = state
        event_start_index = len(before.event_log)
        state, trace = take_automated_action(state, engine, strategies[actor])
        decision_rows.append(trace.to_dict())
        if trace.result == "blocked" or state is before:
            state.winner = state.opponent(actor)
            state.loss_reason = f"player_{actor}_had_no_executable_action"
            break
        if game_logger is not None and trace.selected_action is not None:
            from .actions import Action

            action = Action(**{key: trace.selected_action.get(key) for key in ("kind", "actor", "source", "card", "target", "choice")})
            game_logger.log_move(
                ply=actions_taken,
                before=before,
                after=state,
                engine=engine,
                action=action,
                strategy_name=trace.strategy_name,
                selected_candidate=trace.selected_candidate,
                fallback_status=trace.fallback_taken or trace.result,
                event_start_index=event_start_index,
            )
        actions_taken += 1
    return _finalize_result(state, actions_taken), decision_rows


def _play_generic_logged_loop(
    engine: GameEngine,
    state,
    bots,
    *,
    strategy_names: tuple[str | None, str | None],
    max_actions: int,
    game_logger: GameLogger | None,
) -> tuple[GameResult, list[dict]]:
    traces: list[DecisionTrace] = []
    actions_taken = 0
    while state.winner is None and actions_taken < max_actions:
        actor = state.active_player
        legal = engine.legal_actions(state, actor)
        if not legal:
            state.winner = state.opponent(actor)
            state.loss_reason = f"player_{actor}_had_no_legal_actions"
            break
        obs = engine.observe(state, actor)
        selected = bots[actor].choose_action(obs, legal, engine)
        if selected < 0 or selected >= len(legal):
            state.winner = state.opponent(actor)
            state.loss_reason = f"player_{actor}_bot_returned_illegal_index"
            break
        legal_traces = [ActionTrace.from_action(idx, action) for idx, action in enumerate(legal)]
        trace = DecisionTrace(
            ply=actions_taken,
            player=actor,
            observation=observation_to_trace(engine, state, actor),
            legal_actions=legal_traces,
            selected_index=selected,
            selected_action=legal_traces[selected],
        )
        traces.append(trace)
        before = state
        event_start_index = len(before.event_log)
        action = legal[selected]
        state = engine.apply_action(state, action)
        if game_logger is not None:
            game_logger.log_move(
                ply=actions_taken,
                before=before,
                after=state,
                engine=engine,
                action=action,
                strategy_name=strategy_names[actor],
                selected_candidate=asdict(legal_traces[selected]),
                fallback_status=None,
                event_start_index=event_start_index,
            )
        actions_taken += 1
    return _finalize_result(state, actions_taken), [asdict(trace) for trace in traces]


def _finalize_result(state, actions_taken: int) -> GameResult:
    if state.winner is None:
        if state.players[0].lore > state.players[1].lore:
            state.winner = 0
            state.loss_reason = "max_actions_lore_tiebreak"
        elif state.players[1].lore > state.players[0].lore:
            state.winner = 1
            state.loss_reason = "max_actions_lore_tiebreak"
        else:
            state.loss_reason = "max_actions_draw"
    return GameResult(
        winner=state.winner,
        turns=state.turn_number,
        final_lore=(state.players[0].lore, state.players[1].lore),
        reason=state.loss_reason,
        action_count=actions_taken,
    )


if __name__ == "__main__":
    main()
