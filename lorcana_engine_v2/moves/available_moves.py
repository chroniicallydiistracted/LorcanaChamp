from __future__ import annotations

from dataclasses import dataclass, field

from lorcana_engine_v2.core.commands import Command
from lorcana_engine_v2.core.ids import PlayerId
from lorcana_engine_v2.core.results import TransitionResult
from .ink import PUT_CARD_INTO_INKWELL, PutCardIntoInkwellMove
from .registry import MoveDefinition
from .specs import MoveSpec


def default_move_registry() -> dict[str, MoveDefinition]:
    ink = PutCardIntoInkwellMove()
    return {ink.kind: ink}


@dataclass(slots=True)
class AvailableMoveService:
    """Lorcanito-style move registry/enumeration/application service."""

    registry: dict[str, MoveDefinition] = field(default_factory=default_move_registry)

    def legal_moves(self, state, player: str | PlayerId, ctx) -> tuple[MoveSpec, ...]:
        actor = PlayerId(str(player))
        moves: list[MoveSpec] = []
        for move in self.registry.values():
            moves.extend(move.enumerate(state, actor, ctx))
        return tuple(moves)

    def apply(self, state, command: Command, ctx) -> TransitionResult:
        move = self.registry.get(command.kind)
        if move is None:
            return TransitionResult(
                state=state,
                accepted=False,
                reason=f"Move '{command.kind}' not found",
            )
        validation = move.validate(state, command, ctx)
        if not validation.valid:
            return TransitionResult(state=state, accepted=False, reason=validation.reason)
        return move.execute(state, command, ctx)


__all__ = [
    "AvailableMoveService",
    "PUT_CARD_INTO_INKWELL",
    "PutCardIntoInkwellMove",
    "default_move_registry",
]