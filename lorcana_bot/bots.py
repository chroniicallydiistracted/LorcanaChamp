from __future__ import annotations

import math
import random
from dataclasses import dataclass, field

from .actions import Action
from .constants import (
    ACTION_CHALLENGE,
    ACTION_CONCEDE,
    ACTION_END_TURN,
    ACTION_INK_CARD,
    ACTION_MOVE_TO_LOCATION,
    ACTION_PLAY_CARD,
    ACTION_QUEST,
    CARD_ACTION,
    CARD_CHARACTER,
    CARD_LOCATION,
)
from .engine import GameEngine, Observation
from .automation.planner import create_automated_action_plan
from .automation.move_adapter import candidate_to_action
from .automation.strategy_registry import get_strategy


class RandomLegalBot:
    def __init__(self, seed: int | None = None):
        self.rng = random.Random(seed)

    def choose_action(self, observation: Observation, legal_actions: list[Action], engine: GameEngine) -> int:
        return self.rng.randrange(len(legal_actions))


class GreedyLoreBot:
    """Deterministic baseline: maximize immediate lore, then board development."""

    def choose_action(self, observation: Observation, legal_actions: list[Action], engine: GameEngine) -> int:
        scores = [self.score_action(observation, action, engine) for action in legal_actions]
        return max(range(len(legal_actions)), key=lambda i: (scores[i], -i))

    def score_action(self, obs: Observation, action: Action, engine: GameEngine) -> float:
        if action.kind == ACTION_QUEST and action.source is not None:
            public = obs.cards_public.get(action.source, {})
            card_name = public.get("name")
            if card_name:
                cdef = engine.db.get(card_name)
                if obs.own_lore + int(cdef.lore or 0) >= engine.lore_to_win:
                    return 10_000
                return 100 + 12 * int(cdef.lore or 0)
            return 100
        if action.kind == ACTION_PLAY_CARD and action.card is not None:
            try:
                cdef = engine.db.get(obs.cards_public[action.card]["name"])
            except Exception:
                cdef = None
            if cdef is None:
                return 20
            score = 20 + 4 * cdef.cost
            if cdef.card_type == CARD_CHARACTER:
                score += 4 * int(cdef.lore or 0) + 2 * int(cdef.strength or 0) + int(cdef.willpower or 0)
            elif cdef.card_type == CARD_ACTION:
                score += 2
            elif cdef.card_type == CARD_LOCATION:
                score += 8 * int(cdef.lore or 0) + 2 * int(cdef.willpower or 0)
            return score
        if action.kind == ACTION_CHALLENGE:
            return 50
        if action.kind == ACTION_MOVE_TO_LOCATION:
            return 35
        if action.kind == ACTION_INK_CARD:
            return 10
        if action.kind == ACTION_END_TURN:
            return -10
        if action.kind == ACTION_CONCEDE:
            return -1_000_000
        return 0


class HeuristicBot:
    """State-aware baseline using one-ply simulation when available."""

    def __init__(self, exploration: float = 0.0, seed: int | None = None):
        self.exploration = exploration
        self.rng = random.Random(seed)

    def choose_action(self, observation: Observation, legal_actions: list[Action], engine: GameEngine) -> int:
        if self.exploration and self.rng.random() < self.exploration:
            return self.rng.randrange(len(legal_actions))
        scores = [self.static_score(observation, action, engine) for action in legal_actions]
        return max(range(len(legal_actions)), key=lambda i: (scores[i], -i))

    def static_score(self, obs: Observation, action: Action, engine: GameEngine) -> float:
        if action.kind == ACTION_END_TURN:
            return -50
        if action.kind == ACTION_CONCEDE:
            return -1_000_000

        if action.kind == ACTION_QUEST and action.source is not None:
            public = obs.cards_public.get(action.source, {})
            cdef = engine.db.get(public["name"])
            lore = int(cdef.lore or 0)
            if obs.own_lore + lore >= engine.lore_to_win:
                return 1_000_000
            return 500 + 100 * lore

        if action.kind == ACTION_CHALLENGE and action.source is not None and action.target is not None:
            source = engine.db.get(obs.cards_public[action.source]["name"])
            target = engine.db.get(obs.cards_public[action.target]["name"])
            source_damage = obs.cards_public[action.source].get("damage", 0)
            target_damage = obs.cards_public[action.target].get("damage", 0)
            kills_target = target_damage + int(source.strength or 0) >= int(target.willpower or 0)
            loses_source = source_damage + int(target.strength or 0) >= int(source.willpower or 0)
            score = 150
            if kills_target:
                score += 80 + 12 * target.cost + 25 * int(target.lore or 0)
            if loses_source:
                score -= 30 + 10 * source.cost + 25 * int(source.lore or 0)
            return score

        if action.kind == ACTION_PLAY_CARD and action.card is not None:
            # The action card is hidden to observers, but the engine passes full observation only
            # for the acting player. Use instance id through legal action on the live engine only
            # when the action was public; otherwise use a generic curve score. The runner never
            # exposes private cards to the opponent bot.
            try:
                # This will work in training wrappers that add private-card metadata.
                public = obs.cards_public.get(action.card)
                cdef = engine.db.get(public["name"]) if public else None
            except Exception:
                cdef = None
            if cdef is None:
                return 240
            if cdef.card_type == CARD_CHARACTER:
                return 250 + 12 * cdef.cost + 20 * int(cdef.lore or 0) + 4 * int(cdef.strength or 0) + 2 * int(cdef.willpower or 0)
            if cdef.card_type == CARD_LOCATION:
                return 230 + 10 * cdef.cost + 70 * int(cdef.lore or 0) + 3 * int(cdef.willpower or 0)
            return 220 + 8 * cdef.cost

        if action.kind == ACTION_MOVE_TO_LOCATION and action.source is not None and action.target is not None:
            target = engine.db.get(obs.cards_public[action.target]["name"])
            source = engine.db.get(obs.cards_public[action.source]["name"])
            return 180 + 40 * int(target.lore or 0) - 5 * int(target.move_cost or 0) + 5 * int(source.lore or 0)

        if action.kind == ACTION_INK_CARD:
            # Prefer inking before ending, but below developing board/questing.
            return 100

        return 0


@dataclass
class ActionFeatureEncoder:
    """Small numeric encoder for supervised/RL experiments.

    This is intentionally lightweight and dependency-free. Replace with a card
    embedding model when full card data is available.
    """

    action_order: tuple[str, ...] = (
        ACTION_INK_CARD,
        ACTION_PLAY_CARD,
        ACTION_QUEST,
        ACTION_CHALLENGE,
        ACTION_MOVE_TO_LOCATION,
        ACTION_END_TURN,
        ACTION_CONCEDE,
    )

    def encode(self, obs: Observation, action: Action, engine: GameEngine) -> list[float]:
        features = [1.0 if action.kind == kind else 0.0 for kind in self.action_order]
        features.extend(
            [
                obs.own_lore / engine.lore_to_win,
                obs.opponent_lore / engine.lore_to_win,
                obs.own_available_ink / 20.0,
                obs.own_ink_count / 20.0,
                obs.opponent_ink_count / 20.0,
                obs.own_deck_count / 60.0,
                obs.opponent_deck_count / 60.0,
                len(obs.own_play) / 20.0,
                len(obs.opponent_play) / 20.0,
            ]
        )
        if action.source is not None and action.source in obs.cards_public:
            cdef = engine.db.get(obs.cards_public[action.source]["name"])
            features.extend([cdef.cost / 10.0, (cdef.lore or 0) / 5.0, (cdef.strength or 0) / 10.0, (cdef.willpower or 0) / 10.0])
        else:
            features.extend([0.0, 0.0, 0.0, 0.0])
        if action.target is not None and action.target in obs.cards_public:
            cdef = engine.db.get(obs.cards_public[action.target]["name"])
            features.extend([cdef.cost / 10.0, (cdef.lore or 0) / 5.0, (cdef.strength or 0) / 10.0, (cdef.willpower or 0) / 10.0])
        else:
            features.extend([0.0, 0.0, 0.0, 0.0])
        return features


@dataclass
class LinearPolicyBot:
    """Trainable action scorer using a linear feature policy.

    This is a baseline ML-compatible bot, not a strong model. It exists so the
    engine has a stable action-scoring API before neural training is added.
    """

    weights: list[float] = field(default_factory=list)
    temperature: float = 0.0
    seed: int | None = None
    encoder: ActionFeatureEncoder = field(default_factory=ActionFeatureEncoder)

    def __post_init__(self) -> None:
        self.rng = random.Random(self.seed)

    def choose_action(self, observation: Observation, legal_actions: list[Action], engine: GameEngine) -> int:
        encoded = [self.encoder.encode(observation, action, engine) for action in legal_actions]
        if not self.weights:
            self.weights = [0.0] * len(encoded[0])
        scores = [sum(w * x for w, x in zip(self.weights, feats)) for feats in encoded]
        if len(legal_actions) > 1:
            for idx, action in enumerate(legal_actions):
                if action.kind == ACTION_CONCEDE:
                    scores[idx] = -1_000_000
        if self.temperature <= 0:
            return max(range(len(scores)), key=lambda i: (scores[i], -i))
        return self._sample_softmax(scores)

    def _sample_softmax(self, scores: list[float]) -> int:
        max_score = max(scores)
        exps = [math.exp((score - max_score) / self.temperature) for score in scores]
        total = sum(exps)
        pick = self.rng.random() * total
        running = 0.0
        for idx, value in enumerate(exps):
            running += value
            if running >= pick:
                return idx
        return len(scores) - 1


class AutomationStrategyBot:
    """Compatibility adapter from the old bot index API to automation strategies."""

    def __init__(self, strategy_name: str = "deck-aware-lore-race"):
        self.strategy = get_strategy(strategy_name)

    def choose_action(self, observation: Observation, legal_actions: list[Action], engine: GameEngine) -> int:
        state = getattr(engine, "_automation_live_state", None)
        if state is None:
            return HeuristicBot().choose_action(observation, legal_actions, engine)
        plan = create_automated_action_plan(state, engine, self.strategy)
        for summary in plan.summaries:
            try:
                action = candidate_to_action(summary.candidate)
            except Exception:
                continue
            if action in legal_actions:
                return legal_actions.index(action)
        return 0
