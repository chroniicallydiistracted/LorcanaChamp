from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json
from typing import Any, Iterable, Mapping

from .models import CardDefinition, SourceAbility, SourceEffect


@dataclass(frozen=True, slots=True)
class CardCatalog:
    """Immutable card catalog, equivalent to Lorcanito's CardCatalog.

    The catalog stores static card definitions only.  Runtime instance identity
    lives in MatchStaticResources.instances, not inside MatchState.
    """
    cards: Mapping[str, CardDefinition]
    ref: str = "lorcana:cards"

    def get(self, card_id: str) -> CardDefinition:
        try:
            return self.cards[card_id]
        except KeyError as exc:
            raise KeyError(f"Unknown card id: {card_id}") from exc

    def has(self, card_id: str) -> bool:
        return card_id in self.cards

    def all_cards(self) -> tuple[CardDefinition, ...]:
        return tuple(self.cards.values())

    @classmethod
    def from_lorcanito_normalized_json(
        cls,
        path: str | Path,
        *,
        ref: str = "lorcana:cards",
    ) -> "CardCatalog":
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        records = payload.get("cards", payload if isinstance(payload, list) else [])
        cards: dict[str, CardDefinition] = {}
        for record in records:
            if not isinstance(record, dict) or not record.get("id"):
                continue
            card = _parse_card(record)
            cards[card.id] = card
        return cls(cards=cards, ref=ref)


def _parse_card(raw: dict[str, Any]) -> CardDefinition:
    abilities = tuple(_parse_ability(item) for item in raw.get("abilities", ()) if isinstance(item, dict))
    name = str(raw.get("name") or "")
    version = raw.get("version")
    full_name = str(raw.get("fullName") or raw.get("full_name") or (f"{name} - {version}" if version else name))
    colors = raw.get("inkType") or raw.get("colors") or raw.get("ink") or ()
    if isinstance(colors, str):
        colors = (colors,)
    reprints = raw.get("reprints") or ()
    if isinstance(reprints, str):
        reprints = (reprints,)
    return CardDefinition(
        id=str(raw["id"]),
        canonical_id=str(raw.get("canonicalId") or raw.get("canonical_id")) if raw.get("canonicalId") or raw.get("canonical_id") else None,
        reprints=tuple(str(item) for item in reprints),
        name=name,
        version=str(version) if version is not None else None,
        full_name=full_name,
        card_type=str(raw.get("cardType") or raw.get("card_type") or "card"),
        cost=int(raw.get("cost") or 0),
        inkable=bool(raw.get("inkable", False)),
        colors=tuple(str(item).lower() for item in colors),
        classifications=tuple(str(item) for item in raw.get("classifications", ()) or ()),
        strength=int(raw.get("strength") or 0),
        willpower=int(raw.get("willpower") or 0),
        lore=int(raw.get("lore") or 0),
        move_cost=int(raw["moveCost"]) if raw.get("moveCost") is not None else None,
        abilities=abilities,
        raw=dict(raw),
    )


def _parse_ability(raw: dict[str, Any]) -> SourceAbility:
    source_zones = raw.get("sourceZones") or raw.get("source_zones") or ()
    if isinstance(source_zones, str):
        source_zones = (source_zones,)
    effects = tuple(_parse_effects(raw.get("effect")))
    return SourceAbility(
        kind=str(raw.get("type") or raw.get("kind") or "unknown"),
        raw=dict(raw),
        id=str(raw.get("id")) if raw.get("id") is not None else None,
        name=str(raw.get("name")) if raw.get("name") is not None else None,
        text=str(raw.get("text")) if raw.get("text") is not None else None,
        source_zones=tuple(str(zone) for zone in source_zones),
        effects=effects,
    )


def _parse_effects(value: Any) -> Iterable[SourceEffect]:
    if isinstance(value, list):
        for item in value:
            yield from _parse_effects(item)
        return
    if isinstance(value, dict):
        kind = str(value.get("type") or value.get("kind") or "unknown")
        yield SourceEffect(kind=kind, raw=dict(value))

