from __future__ import annotations

from dataclasses import dataclass

from .events import GameEvent
from .state import MatchState


@dataclass(frozen=True, slots=True)
class TransitionResult:
    state: MatchState
    events: tuple[GameEvent, ...] = ()
    pending: tuple[object, ...] = ()
    accepted: bool = True
    reason: str | None = None
