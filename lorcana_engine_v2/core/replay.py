from __future__ import annotations

from dataclasses import dataclass

from .commands import Command


@dataclass(frozen=True, slots=True)
class ReplayRecord:
    seed: str
    commands: tuple[Command, ...]
