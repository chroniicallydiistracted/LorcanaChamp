from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, TypeAlias

from .commands import CommandEnvelope
from .events import GameEvent
from .ids import PlayerId
from .state import MatchState


@dataclass(frozen=True, slots=True)
class GameEndResult:
    reason: str
    winner: PlayerId | None = None
    metadata: Mapping[str, object] | None = None


@dataclass(frozen=True, slots=True)
class RuntimeValidationResult:
    valid: bool
    error: str | None = None
    errorCode: str | None = None

    @staticmethod
    def ok() -> "RuntimeValidationResult":
        return RuntimeValidationResult(valid=True)

    @staticmethod
    def fail(error: str, error_code: str | None = None) -> "RuntimeValidationResult":
        return RuntimeValidationResult(valid=False, error=error, errorCode=error_code)


@dataclass(frozen=True, slots=True)
class LogMessage:
    key: str
    values: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class LogVisibility:
    mode: str
    visibleTo: tuple[str, ...] = ()
    overrides: Mapping[str, LogMessage] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ProjectedLogEntry:
    category: str
    visibility: LogVisibility
    defaultMessage: LogMessage | None = None
    typedEntry: object | None = None


@dataclass(frozen=True, slots=True)
class PublishedGameEvent:
    seq: int
    timestamp: int
    stateId: int
    event: GameEvent


@dataclass(frozen=True, slots=True)
class PacketAnimation:
    id: str
    kind: str
    payload: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class CommandSuccess:
    success: bool
    stateID: int
    state: MatchState
    patches: tuple[object, ...]
    gameEvents: tuple[PublishedGameEvent, ...]
    processedCommand: CommandEnvelope
    animations: tuple[PacketAnimation, ...] = ()
    undoable: bool = True
    moveLogs: tuple[ProjectedLogEntry, ...] = ()


@dataclass(frozen=True, slots=True)
class CommandFailure:
    success: bool
    error: str
    errorCode: str
    currentStateID: int


CommandResult: TypeAlias = CommandSuccess | CommandFailure
