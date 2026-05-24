from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Mapping

from .ids import InstanceId, PlayerId, ZoneId


@dataclass(frozen=True, slots=True)
class ZoneConfig:
    id: ZoneId
    name: str
    visibility: str
    ordered: bool
    owner_scoped: bool
    face_down: bool = False
    max_size: int | None = None


@dataclass(frozen=True, slots=True)
class PublicZoneSummary:
    revision: int = 0
    count: int = 0
    top_public_card_id: InstanceId | None = None


@dataclass(frozen=True, slots=True)
class ZoneCardIndexEntry:
    zone_key: ZoneId
    index: int | None
    owner_id: PlayerId
    controller_id: PlayerId


@dataclass(frozen=True, slots=True)
class CardMeta:
    damage: int = 0
    exerted: bool = False
    drying: bool = False
    location_instance_id: InstanceId | None = None
    stack_parent_id: InstanceId | None = None
    cards_under: tuple[InstanceId, ...] = ()
    flags: Mapping[str, object] = field(default_factory=dict)

    def with_updates(self, **updates: object) -> "CardMeta":
        return replace(self, **updates)


@dataclass(frozen=True, slots=True)
class ZoneRuntimeState:
    zone_cards: Mapping[ZoneId, tuple[InstanceId, ...]]
    card_index: Mapping[InstanceId, ZoneCardIndexEntry]
    card_meta: Mapping[InstanceId, CardMeta]
    zone_summaries: Mapping[ZoneId, PublicZoneSummary]


LORCANA_RUNTIME_ZONES: dict[ZoneId, ZoneConfig] = {
    ZoneId("deck"): ZoneConfig(ZoneId("deck"), "Deck", "secret", ordered=True, owner_scoped=True, face_down=True),
    ZoneId("hand"): ZoneConfig(ZoneId("hand"), "Hand", "private", ordered=False, owner_scoped=True),
    ZoneId("play"): ZoneConfig(ZoneId("play"), "Play", "public", ordered=False, owner_scoped=True),
    ZoneId("discard"): ZoneConfig(ZoneId("discard"), "Discard", "public", ordered=True, owner_scoped=True),
    ZoneId("inkwell"): ZoneConfig(ZoneId("inkwell"), "Inkwell", "public", ordered=False, owner_scoped=True, face_down=True),
    ZoneId("limbo"): ZoneConfig(ZoneId("limbo"), "Limbo", "public", ordered=True, owner_scoped=True),
}


def scoped_zone(base_zone: str | ZoneId, player_id: str | PlayerId) -> ZoneId:
    return ZoneId(f"{base_zone}:{player_id}")


def zone_owner_from_key(zone_key: str | ZoneId) -> PlayerId | None:
    parts = str(zone_key).split(":")
    if len(parts) <= 1:
        return None
    return PlayerId(parts[-1])


def base_zone_from_key(zone_key: str | ZoneId) -> ZoneId:
    return ZoneId(str(zone_key).split(":", 1)[0])


def build_zone_registry(
    zone_definitions: Mapping[ZoneId, ZoneConfig],
    player_ids: tuple[PlayerId, ...],
) -> dict[ZoneId, ZoneConfig]:
    registry: dict[ZoneId, ZoneConfig] = {}
    for zone_id, zone_def in zone_definitions.items():
        registry[zone_id] = zone_def
        if not zone_def.owner_scoped:
            continue
        for player_id in player_ids:
            key = scoped_zone(zone_id, player_id)
            registry[key] = replace(zone_def, id=key)
    return registry


def initialize_zone_state_from_registry(registry: Mapping[ZoneId, ZoneConfig]) -> ZoneRuntimeState:
    return ZoneRuntimeState(
        zone_cards={zone_id: () for zone_id in registry},
        card_index={},
        card_meta={},
        zone_summaries={zone_id: PublicZoneSummary() for zone_id in registry},
    )


def put_cards_in_zone(
    zone_state: ZoneRuntimeState,
    *,
    zone_key: ZoneId,
    card_ids: tuple[InstanceId, ...],
    owner_id: PlayerId,
    controller_id: PlayerId | None = None,
) -> ZoneRuntimeState:
    controller = controller_id if controller_id is not None else owner_id
    zone_cards = {key: tuple(value) for key, value in zone_state.zone_cards.items()}
    card_index = dict(zone_state.card_index)
    card_meta = dict(zone_state.card_meta)
    zone_summaries = dict(zone_state.zone_summaries)

    current = list(zone_cards.get(zone_key, ()))
    for card_id in card_ids:
        current.append(card_id)
        card_index[card_id] = ZoneCardIndexEntry(
            zone_key=zone_key,
            index=len(current) - 1,
            owner_id=owner_id,
            controller_id=controller,
        )
        card_meta.setdefault(card_id, CardMeta())
    zone_cards[zone_key] = tuple(current)
    zone_summaries[zone_key] = PublicZoneSummary(revision=1, count=len(current))
    return ZoneRuntimeState(
        zone_cards=zone_cards,
        card_index=card_index,
        card_meta=card_meta,
        zone_summaries=zone_summaries,
    )
