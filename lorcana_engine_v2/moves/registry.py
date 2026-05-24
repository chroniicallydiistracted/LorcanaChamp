from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from lorcana_engine_v2.core.commands import Command
from lorcana_engine_v2.core.results import TransitionResult
from lorcana_engine_v2.core.state import MatchState
from lorcana_engine_v2.core.context import RulesContext
from lorcana_engine_v2.core.ids import PlayerId
from .specs import MoveSpec


@dataclass(frozen=True, slots=True)
class MoveValidationResult:
    valid: bool
    reason: str | None = None
    code: str | None = None

    @staticmethod
    def ok() -> "MoveValidationResult":
        return MoveValidationResult(valid=True)

    @staticmethod
    def fail(reason: str, code: str) -> "MoveValidationResult":
        return MoveValidationResult(valid=False, reason=reason, code=code)


class MoveDefinition(Protocol):
    """Protocol for Lorcanito-style v2 move handlers."""

    kind: str

    def enumerate(self, state: MatchState, player: PlayerId, ctx: RulesContext) -> tuple[MoveSpec, ...]:
        ...

    def validate(self, state: MatchState, command: Command, ctx: RulesContext) -> MoveValidationResult:
        ...

    def execute(self, state: MatchState, command: Command, ctx: RulesContext) -> TransitionResult:
        ...


def command_card_id(command: Command) -> str | None:
    if command.card is not None:
        return str(command.card)
    raw = command.payload.get("cardId") or command.payload.get("card_id")
    if raw is None:
        return None
    return str(raw)