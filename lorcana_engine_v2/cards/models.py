from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping


@dataclass(frozen=True, slots=True)
class SourceEffect:
    """Preserved Lorcanito source effect shape.

    v2 intentionally keeps the raw Lorcanito-derived object available.  Runtime
    support will be added by mapping these source shapes into typed executable
    specs, not by mutating the card definition or losing source fidelity.
    """
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
    """Preserved Lorcanito source ability shape."""
    kind: str
    raw: dict[str, Any]
    id: str | None = None
    name: str | None = None
    text: str | None = None
    source_zones: tuple[str, ...] = ()
    effects: tuple[SourceEffect, ...] = ()


@dataclass(frozen=True, slots=True)
class CardDefinition:
    """Immutable card definition loaded from Lorcanito-derived card data.

    This is v2's equivalent of Lorcanito's BaseCardDefinition / typed card
    object.  It must remain immutable and must not contain per-match mutable
    state such as zone, damage, exertion, controller, or cards-under data.
    """
    id: str
    name: str
    version: str | None
    full_name: str
    card_type: str
    cost: int
    inkable: bool
    canonical_id: str | None = None
    reprints: tuple[str, ...] = ()
    colors: tuple[str, ...] = ()
    classifications: tuple[str, ...] = ()
    strength: int = 0
    willpower: int = 0
    lore: int = 0
    move_cost: int | None = None
    abilities: tuple[SourceAbility, ...] = ()
    raw: Mapping[str, Any] = field(default_factory=dict)

    def static_abilities(self) -> tuple[SourceAbility, ...]:
        return tuple(ability for ability in self.abilities if ability.kind == "static")

