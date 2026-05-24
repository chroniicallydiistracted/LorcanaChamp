from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class SourceEffect:
    kind: str
    raw: dict[str, Any]

    @property
    def target(self) -> Any:
        return self.raw.get("target")

    @property
    def amount(self) -> Any:
        if "amount" in self.raw:
            return self.raw["amount"]
        if "modifier" in self.raw:
            return self.raw["modifier"]
        if "reduction" in self.raw:
            return self.raw["reduction"]
        return None


@dataclass(frozen=True, slots=True)
class SourceAbility:
    kind: str
    raw: dict[str, Any]
    id: str | None = None
    name: str | None = None
    text: str | None = None
    source_zones: tuple[str, ...] = ()
    effects: tuple[SourceEffect, ...] = ()


@dataclass(frozen=True, slots=True)
class CardDefinition:
    id: str
    name: str
    version: str | None
    full_name: str
    card_type: str
    cost: int
    inkable: bool
    colors: tuple[str, ...] = ()
    classifications: tuple[str, ...] = ()
    strength: int = 0
    willpower: int = 0
    lore: int = 0
    move_cost: int | None = None
    abilities: tuple[SourceAbility, ...] = ()
    raw: dict[str, Any] = field(default_factory=dict)

    def static_abilities(self) -> tuple[SourceAbility, ...]:
        return tuple(ability for ability in self.abilities if ability.kind == "static")
