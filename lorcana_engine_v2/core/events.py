from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from .ids import InstanceId, PlayerId


@dataclass(frozen=True, slots=True)
class GameEvent:
    """Headless runtime game event.

    Lorcanito models game events as discriminated objects with a ``kind`` plus
    event-specific fields.  Python keeps a small common field set for the core
    command events and stores operation-specific details in ``payload``.
    """

    kind: str
    commandId: str | None = None
    move: str | None = None
    playerId: PlayerId | None = None
    inputRedacted: bool | None = None
    input: object | None = None
    actor: PlayerId | None = None
    source: InstanceId | None = None
    target: InstanceId | None = None
    winner: PlayerId | None = None
    reason: str | None = None
    payload: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, raw: Mapping[str, object]) -> "GameEvent":
        payload = dict(raw)
        kind = str(payload.pop("kind"))
        command_id = payload.pop("commandId", payload.pop("commandID", None))
        move = payload.pop("move", None)
        player_id = payload.pop("playerId", payload.pop("playerID", None))
        actor = payload.pop("actor", None)
        source = payload.pop("source", payload.pop("cardId", None))
        target = payload.pop("target", None)
        winner = payload.pop("winner", None)
        reason = payload.pop("reason", None)
        input_redacted = payload.pop("inputRedacted", None)
        input_value = payload.pop("input", None)
        return cls(
            kind=kind,
            commandId=str(command_id) if command_id is not None else None,
            move=str(move) if move is not None else None,
            playerId=PlayerId(str(player_id)) if player_id is not None else None,
            inputRedacted=bool(input_redacted) if input_redacted is not None else None,
            input=input_value,
            actor=PlayerId(str(actor)) if actor is not None else None,
            source=InstanceId(str(source)) if source is not None else None,
            target=InstanceId(str(target)) if target is not None else None,
            winner=PlayerId(str(winner)) if winner is not None else None,
            reason=str(reason) if reason is not None else None,
            payload=payload,
        )
