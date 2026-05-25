from __future__ import annotations

from dataclasses import dataclass

from .commands import CommandEnvelope


@dataclass(frozen=True, slots=True)
class ReplayRecord:
    seed: str
    commands: tuple[CommandEnvelope, ...]
