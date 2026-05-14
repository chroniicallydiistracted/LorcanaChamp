from __future__ import annotations

from dataclasses import dataclass

from .actions import Action
from .bots import RandomLegalBot
from .cards import CardDatabase, make_demo_deck
from .engine import GameEngine, GameState, Observation


@dataclass(slots=True)
class StepResult:
    observation: Observation
    reward: float
    terminated: bool
    info: dict


class LorcanaSelfPlayEnv:
    """Gym-like environment without a hard dependency on gymnasium.

    `step(action_index)` applies the selected action for the active player. This
    wrapper is intentionally thin; the engine remains the source of legality.
    """

    def __init__(self, db: CardDatabase, deck0: list[str] | None = None, deck1: list[str] | None = None, seed: int | None = None):
        self.db = db
        self.engine = GameEngine(db)
        self.deck0 = deck0 or make_demo_deck()
        self.deck1 = deck1 or make_demo_deck()
        self.seed = seed
        self.state: GameState | None = None

    def reset(self, seed: int | None = None) -> Observation:
        self.seed = self.seed if seed is None else seed
        self.state = self.engine.setup_game([self.deck0, self.deck1], seed=self.seed)
        return self.engine.observe(self.state, self.state.active_player)

    def legal_actions(self) -> list[Action]:
        if self.state is None:
            raise RuntimeError("Call reset before legal_actions")
        return self.engine.legal_actions(self.state, self.state.active_player)

    def step(self, action_index: int) -> StepResult:
        if self.state is None:
            raise RuntimeError("Call reset before step")
        player_before = self.state.active_player
        legal = self.legal_actions()
        action = legal[action_index]
        self.state = self.engine.apply_action(self.state, action)
        terminated = self.state.winner is not None
        if terminated:
            reward = 1.0 if self.state.winner == player_before else -1.0
        else:
            reward = 0.0
        obs = self.engine.observe(self.state, self.state.active_player)
        return StepResult(obs, reward, terminated, {"action": action, "winner": self.state.winner, "reason": self.state.loss_reason})

    def rollout_random(self, max_actions: int = 250, seed: int | None = None) -> int | None:
        bot = RandomLegalBot(seed=seed)
        self.reset(seed=seed)
        assert self.state is not None
        for _ in range(max_actions):
            if self.state.winner is not None:
                return self.state.winner
            legal = self.legal_actions()
            obs = self.engine.observe(self.state, self.state.active_player)
            idx = bot.choose_action(obs, legal, self.engine)
            self.step(idx)
        return self.state.winner
