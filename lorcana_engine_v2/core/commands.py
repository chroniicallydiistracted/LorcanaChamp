from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any


REDACTED_MOVE_INPUT = "[REDACTED]"


@dataclass(frozen=True, slots=True)
class MoveInput:
    """Lorcanito runtime move input.

    Lorcanito sends command input as ``{ args: ... }``.  The v2 kernel keeps
    the same boundary so move validation and execution read ``ctx.args`` and
    ``ctx.params`` instead of legacy command fields.
    """

    args: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def from_args(cls, **args: Any) -> "MoveInput":
        return cls(args=args)


@dataclass(frozen=True, slots=True)
class CommandEnvelope:
    """External command envelope matching Lorcanito's runtime command shape."""

    commandID: str
    move: str
    input: MoveInput | None = None
    optimisticHint: bool = False
    redactInput: bool = False


@dataclass(frozen=True, slots=True)
class SanitizedCommandEnvelope:
    commandID: str
    move: str
    input: MoveInput | str
    optimisticHint: bool = False
    redactInput: bool = False


def sanitize_command(command: CommandEnvelope) -> SanitizedCommandEnvelope:
    return SanitizedCommandEnvelope(
        commandID=command.commandID,
        move=command.move,
        input=REDACTED_MOVE_INPUT if command.redactInput else (command.input or MoveInput()),
        optimisticHint=command.optimisticHint,
        redactInput=command.redactInput,
    )
