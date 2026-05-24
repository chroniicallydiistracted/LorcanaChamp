from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class MoveSpec:
    kind: str
    actor: int
    card: int | None = None
    target: int | None = None
    payload: dict[str, Any] = field(default_factory=dict)
