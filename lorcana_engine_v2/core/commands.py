from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .ids import InstanceId, PlayerId


@dataclass(frozen=True, slots=True)
class Command:
    """External command submitted to MatchRuntime.

    Commands are intentionally generic.  The move registry owns validation and
    application of each command kind.
    """
    kind: str
    actor: PlayerId
    card: InstanceId | None = None
    target: InstanceId | None = None
    payload: dict[str, Any] = field(default_factory=dict)
