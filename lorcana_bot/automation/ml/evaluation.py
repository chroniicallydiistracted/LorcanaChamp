from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from lorcana_bot.engine import GameEngine
from lorcana_bot.cards import CardDatabase

from ..planner import take_automated_action


@dataclass
class EvaluationReport:
    wins: int
    losses: int
    draws_timeouts: int
    winrate: float
    average_turns: float
    average_actions: float
    illegal_move_attempts: int
    fallback_count: int
    blocked_count: int
    average_decision_candidates: float
    average_execution_failures: float


def evaluate_strategy(strategy_a, strategy_b, deck_a, deck_b, seeds: Iterable[int], games_per_side: int = 1, db: CardDatabase | None = None, max_actions: int = 300) -> EvaluationReport:
    if db is None:
        from lorcana_bot.cards import load_demo_database

        db = load_demo_database()
    wins = losses = draws = actions_total = turns_total = fallbacks = blocked = illegal = candidates_total = exec_failures = games = 0
    for seed in seeds:
        for side in range(games_per_side):
            engine = GameEngine(db)
            first = side % 2
            state = engine.setup_game([deck_a, deck_b], seed=seed + side, first_player=first)
            actions = 0
            while state.winner is None and actions < max_actions:
                strategy = strategy_a if state.active_player == 0 else strategy_b
                state, trace = take_automated_action(state, engine, strategy)
                actions += 1
                fallbacks += 1 if trace.fallback_taken else 0
                blocked += 1 if trace.result == "blocked" else 0
                candidates_total += trace.candidate_count
                exec_failures += sum(1 for attempt in trace.execution_attempts if not attempt.get("success"))
                illegal += sum(1 for attempt in trace.execution_attempts if not attempt.get("success") and attempt.get("error_code") == "IllegalActionError")
                if trace.result == "blocked":
                    break
            if state.winner is None:
                draws += 1
            elif state.winner == 0:
                wins += 1
            else:
                losses += 1
            actions_total += actions
            turns_total += state.turn_number
            games += 1
    return EvaluationReport(
        wins=wins,
        losses=losses,
        draws_timeouts=draws,
        winrate=wins / max(1, wins + losses),
        average_turns=turns_total / max(1, games),
        average_actions=actions_total / max(1, games),
        illegal_move_attempts=illegal,
        fallback_count=fallbacks,
        blocked_count=blocked,
        average_decision_candidates=candidates_total / max(1, actions_total),
        average_execution_failures=exec_failures / max(1, actions_total),
    )
