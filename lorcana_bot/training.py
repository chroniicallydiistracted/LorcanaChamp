from __future__ import annotations

import json
import random
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable

from .bots import ActionFeatureEncoder, GreedyLoreBot, HeuristicBot, LinearPolicyBot, RandomLegalBot
from .cards import CardDatabase, make_demo_deck
from .engine import GameEngine, GameRunner


FEATURE_COUNT = 24


@dataclass(slots=True)
class EvaluationResult:
    games: int
    wins: int
    losses: int
    draws: int
    win_rate: float
    average_actions: float


@dataclass(slots=True)
class TrainingResult:
    generations: int
    best_score: float
    weights: list[float]
    evaluation: EvaluationResult


def evaluate_bot(
    db: CardDatabase,
    bot_factory: Callable[[int], object],
    opponent_factory: Callable[[int], object] | None = None,
    *,
    games: int = 20,
    seed: int = 1,
    max_actions: int = 500,
    deck0: list[str] | None = None,
    deck1: list[str] | None = None,
) -> EvaluationResult:
    opponent_factory = opponent_factory or (lambda s: GreedyLoreBot())
    deck0 = deck0 or make_demo_deck(["Amber Recruit", "Amber Guard", "Amber Storyteller", "Amethyst Scholar", "Amethyst Insight"], size=60)
    deck1 = deck1 or make_demo_deck(["Steel Bruiser", "Emerald Scout", "Ruby Charger", "Steel Cannon", "Sapphire Helper"], size=60)
    wins = losses = draws = 0
    total_actions = 0
    for game_idx in range(games):
        engine = GameEngine(db)
        first = game_idx % 2
        state = engine.setup_game([deck0, deck1], seed=seed + game_idx, first_player=first)
        learned_player = 0
        bots = [None, None]
        bots[learned_player] = bot_factory(seed + 10_000 + game_idx)
        bots[1] = opponent_factory(seed + 20_000 + game_idx)
        result = GameRunner(engine, max_actions=max_actions).play(state, (bots[0], bots[1]))
        total_actions += result.action_count
        if result.winner == learned_player:
            wins += 1
        elif result.winner is None:
            draws += 1
        else:
            losses += 1
    return EvaluationResult(games, wins, losses, draws, wins / games if games else 0.0, total_actions / games if games else 0.0)


def train_linear_policy_evolution(
    db: CardDatabase,
    *,
    generations: int = 8,
    population: int = 12,
    games_per_candidate: int = 8,
    seed: int = 1,
    mutation_scale: float = 0.35,
) -> TrainingResult:
    """Tiny evolutionary trainer for the linear action scorer.

    This is intended as a reproducible smoke trainer, not the final strong model.
    Its purpose is to validate the engine/action-mask/training loop before PPO or
    MCTS-guided policy/value training is introduced.
    """

    rng = random.Random(seed)
    best_weights = [0.0] * FEATURE_COUNT
    # Sensible prior: prefer questing/play/challenge over inking/end-turn.
    best_weights[:5] = [0.25, 0.7, 1.4, 0.8, -0.4]
    best_score = -1e9
    best_eval = EvaluationResult(0, 0, 0, 0, 0.0, 0.0)

    opponents = [lambda s: RandomLegalBot(s), lambda s: GreedyLoreBot(), lambda s: HeuristicBot(seed=s)]

    for generation in range(generations):
        candidates = [best_weights]
        for _ in range(population - 1):
            candidates.append([w + rng.normalvariate(0.0, mutation_scale) for w in best_weights])

        for idx, weights in enumerate(candidates):
            opponent_factory = opponents[(generation + idx) % len(opponents)]
            result = evaluate_bot(
                db,
                lambda s, weights=weights: LinearPolicyBot(weights=list(weights), seed=s),
                opponent_factory,
                games=games_per_candidate,
                seed=seed + generation * 1000 + idx * 100,
            )
            score = result.win_rate - 0.001 * result.average_actions
            if score > best_score:
                best_score = score
                best_weights = list(weights)
                best_eval = result

    return TrainingResult(generations, best_score, best_weights, best_eval)


def save_training_result(result: TrainingResult, path: str | Path) -> None:
    payload = asdict(result)
    Path(path).write_text(json.dumps(payload, indent=2), encoding="utf-8")


# Monkey-patch-free explicit feature count helper.
def linear_feature_count() -> int:
    return FEATURE_COUNT
