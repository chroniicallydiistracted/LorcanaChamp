from __future__ import annotations

from dataclasses import dataclass

from lorcana_engine_v2.core.results import TransitionResult


@dataclass(slots=True)
class AvailableMoveService:
    """Move enumeration/application scaffold."""

    def legal_moves(self, state, player: int, ctx) -> tuple[object, ...]:
        return ()

    def apply(self, state, command, ctx) -> TransitionResult:
        return TransitionResult(state=state, accepted=False, reason="v2_move_application_not_implemented")
