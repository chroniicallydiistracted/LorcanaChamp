from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class Action:
    """A fully specified legal move candidate.

    The engine returns concrete Action objects. Bots choose an index from that
    list. Bots do not create arbitrary moves.
    """

    kind: str
    actor: int
    source: int | None = None
    card: int | None = None
    target: int | None = None
    choice: Any | None = None

    def compact(self) -> str:
        parts = [self.kind, f"p{self.actor}"]
        if self.card is not None:
            parts.append(f"card={self.card}")
        if self.source is not None:
            parts.append(f"source={self.source}")
        if self.target is not None:
            parts.append(f"target={self.target}")
        if self.choice is not None:
            parts.append(f"choice={self.choice}")
        return " ".join(parts)
