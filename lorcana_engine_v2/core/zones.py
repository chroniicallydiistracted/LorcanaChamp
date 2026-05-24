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


def _zone_summary_for_cards(
    existing: PublicZoneSummary | None,
    card_ids: tuple[InstanceId, ...],
) -> PublicZoneSummary:
    revision = (existing.revision if existing else 0) + 1
    top = card_ids[-1] if card_ids else None
    return PublicZoneSummary(revision=revision, count=len(card_ids), top_public_card_id=top)


def _with_reindexed_zone(
    *,
    zone_cards: dict[ZoneId, tuple[InstanceId, ...]],
    card_index: dict[InstanceId, ZoneCardIndexEntry],
    zone_summaries: dict[ZoneId, PublicZoneSummary],
    previous_state: ZoneRuntimeState,
    zone_key: ZoneId,
    owner_id: PlayerId,
    controller_id: PlayerId,
    ordered_index: bool = True,
) -> None:
    cards = tuple(zone_cards.get(zone_key, ()))
    for index, card_id in enumerate(cards):
        card_index[card_id] = ZoneCardIndexEntry(
            zone_key=zone_key,
            index=index if ordered_index else None,
            owner_id=owner_id,
            controller_id=controller_id,
        )
    zone_summaries[zone_key] = _zone_summary_for_cards(
        previous_state.zone_summaries.get(zone_key),
        cards,
    )


def remove_card_from_current_zone(
    zone_state: ZoneRuntimeState,
    card_id: InstanceId | str,
) -> ZoneRuntimeState:
    cid = InstanceId(str(card_id))
    index_entry = zone_state.card_index.get(cid)
    if index_entry is None:
        return zone_state

    zone_key = index_entry.zone_key
    current_cards = tuple(zone_state.zone_cards.get(zone_key, ()))
    remaining = tuple(item for item in current_cards if item != cid)

    zone_cards = {key: tuple(value) for key, value in zone_state.zone_cards.items()}
    card_index = dict(zone_state.card_index)
    card_meta = dict(zone_state.card_meta)
    zone_summaries = dict(zone_state.zone_summaries)

    zone_cards[zone_key] = remaining
    card_index.pop(cid, None)
    _with_reindexed_zone(
        zone_cards=zone_cards,
        card_index=card_index,
        zone_summaries=zone_summaries,
        previous_state=zone_state,
        zone_key=zone_key,
        owner_id=index_entry.owner_id,
        controller_id=index_entry.controller_id,
    )

    return ZoneRuntimeState(
        zone_cards=zone_cards,
        card_index=card_index,
        card_meta=card_meta,
        zone_summaries=zone_summaries,
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

    if zone_key not in zone_cards:
        raise KeyError(f"ZONE_NOT_REGISTERED: {zone_key}")

    current = list(zone_cards.get(zone_key, ()))
    for raw_card_id in card_ids:
        card_id = InstanceId(str(raw_card_id))
        # Ensure a card cannot exist in two zones.  This mirrors Lorcanito's
        # zone operation invariant where a card has one current zone index.
        existing = card_index.get(card_id)
        if existing is not None:
            existing_cards = list(zone_cards.get(existing.zone_key, ()))
            existing_cards = [item for item in existing_cards if item != card_id]
            zone_cards[existing.zone_key] = tuple(existing_cards)
            card_index.pop(card_id, None)
            _with_reindexed_zone(
                zone_cards=zone_cards,
                card_index=card_index,
                zone_summaries=zone_summaries,
                previous_state=zone_state,
                zone_key=existing.zone_key,
                owner_id=existing.owner_id,
                controller_id=existing.controller_id,
            )
        current.append(card_id)
        card_index[card_id] = ZoneCardIndexEntry(
            zone_key=zone_key,
            index=len(current) - 1,
            owner_id=owner_id,
            controller_id=controller,
        )
        card_meta.setdefault(card_id, CardMeta())

    zone_cards[zone_key] = tuple(current)
    zone_summaries[zone_key] = _zone_summary_for_cards(
        zone_summaries.get(zone_key),
        tuple(current),
    )
    return ZoneRuntimeState(
        zone_cards=zone_cards,
        card_index=card_index,
        card_meta=card_meta,
        zone_summaries=zone_summaries,
    )


def move_card_to_zone(
    zone_state: ZoneRuntimeState,
    *,
    card_id: InstanceId | str,
    destination_zone_key: ZoneId,
    owner_id: PlayerId | None = None,
    controller_id: PlayerId | None = None,
) -> ZoneRuntimeState:
    cid = InstanceId(str(card_id))
    if destination_zone_key not in zone_state.zone_cards:
        raise KeyError(f"ZONE_NOT_REGISTERED: {destination_zone_key}")
    previous = zone_state.card_index.get(cid)
    resolved_owner = owner_id or (previous.owner_id if previous else zone_owner_from_key(destination_zone_key))
    if resolved_owner is None:
        raise ValueError(f"ZONE_OWNER_REQUIRED: {destination_zone_key}")
    resolved_controller = controller_id or (previous.controller_id if previous else resolved_owner)
    without = remove_card_from_current_zone(zone_state, cid)
    return put_cards_in_zone(
        without,
        zone_key=destination_zone_key,
        card_ids=(cid,),
        owner_id=resolved_owner,
        controller_id=resolved_controller,
    )


def patch_card_meta(
    zone_state: ZoneRuntimeState,
    card_id: InstanceId | str,
    meta: CardMeta,
) -> ZoneRuntimeState:
    cid = InstanceId(str(card_id))
    card_meta = dict(zone_state.card_meta)
    card_meta[cid] = meta
    return ZoneRuntimeState(
        zone_cards=zone_state.zone_cards,
        card_index=zone_state.card_index,
        card_meta=card_meta,
        zone_summaries=zone_state.zone_summaries,
    )


def card_is_in_zone(
    zone_state: ZoneRuntimeState,
    *,
    card_id: InstanceId | str,
    zone_key: ZoneId,
) -> bool:
    cid = InstanceId(str(card_id))
    return cid in zone_state.zone_cards.get(zone_key, ())