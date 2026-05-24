from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .ids import InstanceId, PlayerId


@dataclass(frozen=True, slots=True)
class GameEvent:
    kind: str
    actor: PlayerId | None = None
    source: InstanceId | None = None
    target: InstanceId | None = None
    payload: dict[str, Any] = field(default_factory=dict)
