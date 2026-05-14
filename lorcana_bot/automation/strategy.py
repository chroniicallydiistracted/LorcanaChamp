from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Protocol, Sequence

from lorcana_bot.engine import GameEngine
from lorcana_bot.state import GameState

from .candidates import AutomatedActionCandidate, AutomatedActionCandidateSummary

InformationPolicy = Literal["fair", "oracle"]


@dataclass(frozen=True)
class StrategyContext:
    state: GameState
    engine: GameEngine
    actor: int
    information_policy: str
    actor_observation: Any
    actor_deck_profile: Any | None
    opponent_deck_profile: Any | None
    turn_number: int
    phase: str


class AutomatedActionStrategy(Protocol):
    name: str
    information_policy: str

    def summarize_candidates(
        self,
        context: StrategyContext,
        candidates: Sequence[AutomatedActionCandidate],
    ) -> list[AutomatedActionCandidateSummary]:
        ...
