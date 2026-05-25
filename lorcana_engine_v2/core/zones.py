from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Callable, Mapping, Sequence

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
    topPublicCardID: InstanceId | None = None


@dataclass(frozen=True, slots=True)
class ZoneCardIndexEntry:
    zoneKey: ZoneId
    index: int | None
    ownerID: PlayerId
    controllerID: PlayerId


@dataclass(frozen=True, slots=True)
class ZoneRevealWindow:
    revealID: str
    cardIDs: tuple[InstanceId, ...]
    visibleTo: str | tuple[PlayerId, ...]
    expiresAtStateID: int | None = None


@dataclass(frozen=True, slots=True)
class ZoneRef:
    zone: ZoneId
    playerId: PlayerId | None = None


@dataclass(frozen=True, slots=True)
class LorcanaCardMeta:
    state: str | None = None
    damage: int | None = None
    isDrying: bool | None = None
    publicFaceState: str | None = None
    atLocationId: InstanceId | None = None
    cardsUnder: tuple[InstanceId, ...] | None = None
    stackParentId: InstanceId | None = None
    playedViaShift: bool | None = None
    playedCostType: str | None = None
    temporaryKeywords: Mapping[str, int] | None = None
    temporaryKeywordStarts: Mapping[str, int] | None = None
    temporaryKeywordValues: Mapping[str, int] | None = None
    temporaryKeywordPayloads: Mapping[str, object] | None = None
    temporaryLostKeywords: Mapping[str, int] | None = None
    temporaryLostKeywordStarts: Mapping[str, int] | None = None
    temporaryClassifications: Mapping[str, int] | None = None
    temporaryClassificationStarts: Mapping[str, int] | None = None
    temporaryAbilities: Mapping[str, int] | None = None
    temporaryAbilityStarts: Mapping[str, int] | None = None
    temporaryAbilityPayloads: Mapping[str, object] | None = None
    temporaryRestrictions: Mapping[str, int] | None = None
    temporaryRestrictionStarts: Mapping[str, int] | None = None
    temporaryRestrictionPayloads: Mapping[str, object] | None = None
    activatedAbilityUses: Mapping[str, int] | None = None
    activatedAbilityUseTurns: Mapping[str, int] | None = None
    replacementAbilities: tuple[object, ...] | None = None
    afterPlayDestination: str | None = None

    def with_updates(self, **updates: object) -> "LorcanaCardMeta":
        return replace(self, **updates)


CardMeta = LorcanaCardMeta


def create_default_card_meta() -> LorcanaCardMeta:
    return LorcanaCardMeta()


@dataclass(frozen=True, slots=True)
class ZoneRuntimePublicState:
    zoneSummaries: Mapping[ZoneId, PublicZoneSummary]


@dataclass(frozen=True, slots=True)
class ZoneRuntimeRevealState:
    active: tuple[ZoneRevealWindow, ...] = ()
    nextSeq: int = 0


@dataclass(frozen=True, slots=True)
class ZoneRuntimePrivateState:
    zoneCards: Mapping[ZoneId, tuple[InstanceId, ...]]
    cardIndex: Mapping[InstanceId, ZoneCardIndexEntry]
    cardMeta: Mapping[InstanceId, LorcanaCardMeta]


@dataclass(frozen=True, slots=True)
class ZoneRuntimeState:
    public: ZoneRuntimePublicState
    reveals: ZoneRuntimeRevealState
    private: ZoneRuntimePrivateState


ZoneEvent = dict[str, object]


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


def _zone_def_for_key(
    zone_definitions: Mapping[ZoneId, ZoneConfig] | None,
    zone_key: ZoneId,
) -> ZoneConfig | None:
    definitions = zone_definitions or LORCANA_RUNTIME_ZONES
    return definitions.get(zone_key) or definitions.get(base_zone_from_key(zone_key))


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
        public=ZoneRuntimePublicState(
            zoneSummaries={zone_id: PublicZoneSummary() for zone_id in registry},
        ),
        reveals=ZoneRuntimeRevealState(active=(), nextSeq=0),
        private=ZoneRuntimePrivateState(
            zoneCards={zone_id: () for zone_id in registry},
            cardIndex={},
            cardMeta={},
        ),
    )


def resolve_zone_id_from_registry(
    zone: ZoneRef | Mapping[str, object] | str | ZoneId,
    zone_registry: Mapping[ZoneId, ZoneConfig],
    card_index: Mapping[InstanceId, ZoneCardIndexEntry],
) -> ZoneId:
    zone_ref = _coerce_zone_ref(zone)
    zone_id = ZoneId(str(zone_ref.zone))

    if ":" in str(zone_id):
        if zone_ref.playerId and not str(zone_id).endswith(f":{zone_ref.playerId}"):
            raise ValueError(f"Zone player mismatch for {zone_id}")
        if zone_id not in zone_registry:
            raise ValueError(f"Unknown zone: {zone_id}")
        return zone_id

    if zone_ref.playerId is not None:
        scoped = scoped_zone(zone_id, zone_ref.playerId)
        if scoped in zone_registry:
            return scoped

    unscoped_def = zone_registry.get(zone_id)
    if unscoped_def is None:
        raise ValueError(f"Unknown zone: {zone_id}")

    if unscoped_def.owner_scoped:
        player_id = zone_ref.playerId
        if player_id is None:
            raise ValueError(f"Owner-scoped zone requires player id: {zone_id}")
        has_player_cards = any(
            entry.ownerID == player_id or entry.controllerID == player_id
            for entry in card_index.values()
        )
        if not has_player_cards:
            raise ValueError(f"Unknown zone: {zone_id}")

    return zone_id


def _coerce_zone_ref(zone: ZoneRef | Mapping[str, object] | str | ZoneId) -> ZoneRef:
    if isinstance(zone, ZoneRef):
        return zone
    if isinstance(zone, Mapping):
        raw_zone = zone.get("zone")
        if raw_zone is None:
            raise ValueError("Zone ref requires zone")
        raw_player = zone.get("playerId") or zone.get("player_id")
        return ZoneRef(
            zone=ZoneId(str(raw_zone)),
            playerId=PlayerId(str(raw_player)) if raw_player is not None else None,
        )
    return ZoneRef(zone=ZoneId(str(zone)))


def _zone_summary_for_cards(
    existing: PublicZoneSummary | None,
    card_ids: tuple[InstanceId, ...],
    zone_def: ZoneConfig | None = None,
) -> PublicZoneSummary:
    revision = (existing.revision if existing else 0) + 1
    top = (
        card_ids[-1]
        if zone_def is not None
        and zone_def.visibility == "public"
        and not zone_def.face_down
        and card_ids
        else None
    )
    return PublicZoneSummary(revision=revision, count=len(card_ids), topPublicCardID=top)


def _reindex_zone(
    *,
    zone_cards: dict[ZoneId, tuple[InstanceId, ...]],
    card_index: dict[InstanceId, ZoneCardIndexEntry],
    zone_summaries: dict[ZoneId, PublicZoneSummary],
    previous_state: ZoneRuntimeState,
    zone_key: ZoneId,
    zone_definitions: Mapping[ZoneId, ZoneConfig] | None = None,
    ordered_index: bool = True,
) -> None:
    cards = tuple(zone_cards.get(zone_key, ()))
    for index, card_id in enumerate(cards):
        previous_entry = card_index.get(card_id)
        owner_id = previous_entry.ownerID if previous_entry else zone_owner_from_key(zone_key)
        if owner_id is None:
            owner_id = PlayerId("unknown")
        controller_id = previous_entry.controllerID if previous_entry else owner_id
        card_index[card_id] = ZoneCardIndexEntry(
            zoneKey=zone_key,
            index=index if ordered_index else None,
            ownerID=owner_id,
            controllerID=controller_id,
        )
    zone_summaries[zone_key] = _zone_summary_for_cards(
        previous_state.public.zoneSummaries.get(zone_key),
        cards,
        _zone_def_for_key(zone_definitions, zone_key),
    )


def remove_card_from_current_zone(
    zone_state: ZoneRuntimeState,
    card_id: InstanceId | str,
    *,
    zone_definitions: Mapping[ZoneId, ZoneConfig] | None = None,
) -> ZoneRuntimeState:
    cid = InstanceId(str(card_id))
    index_entry = zone_state.private.cardIndex.get(cid)
    if index_entry is None:
        return zone_state

    zone_key = index_entry.zoneKey
    current_cards = tuple(zone_state.private.zoneCards.get(zone_key, ()))
    remaining = tuple(item for item in current_cards if item != cid)

    zone_cards = {key: tuple(value) for key, value in zone_state.private.zoneCards.items()}
    card_index = dict(zone_state.private.cardIndex)
    card_meta = dict(zone_state.private.cardMeta)
    zone_summaries = dict(zone_state.public.zoneSummaries)

    zone_cards[zone_key] = remaining
    card_index.pop(cid, None)
    _reindex_zone(
        zone_cards=zone_cards,
        card_index=card_index,
        zone_summaries=zone_summaries,
        previous_state=zone_state,
        zone_key=zone_key,
        zone_definitions=zone_definitions,
    )

    return ZoneRuntimeState(
        public=ZoneRuntimePublicState(zoneSummaries=zone_summaries),
        reveals=zone_state.reveals,
        private=ZoneRuntimePrivateState(
            zoneCards=zone_cards,
            cardIndex=card_index,
            cardMeta=card_meta,
        ),
    )


def put_cards_in_zone(
    zone_state: ZoneRuntimeState,
    *,
    zone_key: ZoneId,
    card_ids: tuple[InstanceId, ...],
    owner_id: PlayerId,
    controller_id: PlayerId | None = None,
    index: int | None = None,
    zone_definitions: Mapping[ZoneId, ZoneConfig] | None = None,
) -> ZoneRuntimeState:
    controller = controller_id if controller_id is not None else owner_id
    zone_cards = {key: tuple(value) for key, value in zone_state.private.zoneCards.items()}
    card_index = dict(zone_state.private.cardIndex)
    card_meta = dict(zone_state.private.cardMeta)
    zone_summaries = dict(zone_state.public.zoneSummaries)

    if zone_key not in zone_cards:
        raise KeyError(f"ZONE_NOT_REGISTERED: {zone_key}")

    current = list(zone_cards.get(zone_key, ()))
    insert_at = index
    for raw_card_id in card_ids:
        card_id = InstanceId(str(raw_card_id))
        existing = card_index.get(card_id)
        if existing is not None:
            existing_cards = list(zone_cards.get(existing.zoneKey, ()))
            existing_cards = [item for item in existing_cards if item != card_id]
            zone_cards[existing.zoneKey] = tuple(existing_cards)
            card_index.pop(card_id, None)
            _reindex_zone(
                zone_cards=zone_cards,
                card_index=card_index,
                zone_summaries=zone_summaries,
                previous_state=zone_state,
                zone_key=existing.zoneKey,
                zone_definitions=zone_definitions,
            )
        if insert_at is not None and 0 <= insert_at <= len(current):
            current.insert(insert_at, card_id)
            inserted_index = insert_at
            insert_at += 1
        else:
            current.append(card_id)
            inserted_index = len(current) - 1
        card_index[card_id] = ZoneCardIndexEntry(
            zoneKey=zone_key,
            index=inserted_index,
            ownerID=owner_id,
            controllerID=controller,
        )
        card_meta.setdefault(card_id, create_default_card_meta())

    zone_cards[zone_key] = tuple(current)
    _reindex_zone(
        zone_cards=zone_cards,
        card_index=card_index,
        zone_summaries=zone_summaries,
        previous_state=zone_state,
        zone_key=zone_key,
        zone_definitions=zone_definitions,
    )
    return ZoneRuntimeState(
        public=ZoneRuntimePublicState(zoneSummaries=zone_summaries),
        reveals=zone_state.reveals,
        private=ZoneRuntimePrivateState(
            zoneCards=zone_cards,
            cardIndex=card_index,
            cardMeta=card_meta,
        ),
    )


def move_card_to_zone(
    zone_state: ZoneRuntimeState,
    *,
    card_id: InstanceId | str,
    destination_zone_key: ZoneId,
    owner_id: PlayerId | None = None,
    controller_id: PlayerId | None = None,
    index: int | None = None,
    zone_definitions: Mapping[ZoneId, ZoneConfig] | None = None,
) -> ZoneRuntimeState:
    cid = InstanceId(str(card_id))
    if destination_zone_key not in zone_state.private.zoneCards:
        raise KeyError(f"ZONE_NOT_REGISTERED: {destination_zone_key}")
    previous = zone_state.private.cardIndex.get(cid)
    resolved_owner = owner_id or (previous.ownerID if previous else zone_owner_from_key(destination_zone_key))
    if resolved_owner is None:
        raise ValueError(f"ZONE_OWNER_REQUIRED: {destination_zone_key}")
    resolved_controller = controller_id or (previous.controllerID if previous else resolved_owner)
    without = remove_card_from_current_zone(zone_state, cid, zone_definitions=zone_definitions)
    return put_cards_in_zone(
        without,
        zone_key=destination_zone_key,
        card_ids=(cid,),
        owner_id=resolved_owner,
        controller_id=resolved_controller,
        index=index,
        zone_definitions=zone_definitions,
    )


def patch_card_meta(
    zone_state: ZoneRuntimeState,
    card_id: InstanceId | str,
    meta: LorcanaCardMeta,
) -> ZoneRuntimeState:
    cid = InstanceId(str(card_id))
    card_meta = dict(zone_state.private.cardMeta)
    card_meta[cid] = meta
    return ZoneRuntimeState(
        public=zone_state.public,
        reveals=zone_state.reveals,
        private=ZoneRuntimePrivateState(
            zoneCards=zone_state.private.zoneCards,
            cardIndex=zone_state.private.cardIndex,
            cardMeta=card_meta,
        ),
    )


def card_is_in_zone(
    zone_state: ZoneRuntimeState,
    *,
    card_id: InstanceId | str,
    zone_key: ZoneId,
) -> bool:
    cid = InstanceId(str(card_id))
    return cid in zone_state.private.zoneCards.get(zone_key, ())


def get_cards(zone_state: ZoneRuntimeState, zone_key: ZoneId | str) -> tuple[InstanceId, ...]:
    return tuple(zone_state.private.zoneCards.get(ZoneId(str(zone_key)), ()))


def get_card_count(zone_state: ZoneRuntimeState, zone_key: ZoneId | str) -> int:
    return len(get_cards(zone_state, zone_key))


def get_top_card(zone_state: ZoneRuntimeState, zone_key: ZoneId | str) -> InstanceId | None:
    cards = get_cards(zone_state, zone_key)
    return cards[-1] if cards else None


def get_bottom_card(zone_state: ZoneRuntimeState, zone_key: ZoneId | str) -> InstanceId | None:
    cards = get_cards(zone_state, zone_key)
    return cards[0] if cards else None


def draw_cards(
    zone_state: ZoneRuntimeState,
    *,
    from_zone_key: ZoneId,
    to_zone_key: ZoneId,
    count: int,
    owner_id: PlayerId | None = None,
    controller_id: PlayerId | None = None,
    zone_definitions: Mapping[ZoneId, ZoneConfig] | None = None,
) -> tuple[ZoneRuntimeState, tuple[InstanceId, ...]]:
    source_cards = list(zone_state.private.zoneCards.get(from_zone_key, ()))
    candidate_cards = list(reversed(source_cards))
    if owner_id is not None:
        candidate_cards = [
            card_id
            for card_id in candidate_cards
            if zone_state.private.cardIndex.get(card_id, None)
            and zone_state.private.cardIndex[card_id].ownerID == owner_id
        ]
    drawn = tuple(candidate_cards[: max(0, min(count, len(candidate_cards)))])

    next_zones = zone_state
    for card_id in drawn:
        previous = next_zones.private.cardIndex.get(card_id)
        next_zones = move_card_to_zone(
            next_zones,
            card_id=card_id,
            destination_zone_key=to_zone_key,
            owner_id=owner_id or (previous.ownerID if previous else zone_owner_from_key(to_zone_key)),
            controller_id=controller_id or (previous.controllerID if previous else owner_id),
            zone_definitions=zone_definitions,
        )
    return next_zones, drawn


def draw_specific_card(
    zone_state: ZoneRuntimeState,
    *,
    card_id: InstanceId | str,
    from_zone_key: ZoneId,
    to_zone_key: ZoneId,
    owner_id: PlayerId | None = None,
    controller_id: PlayerId | None = None,
    zone_definitions: Mapping[ZoneId, ZoneConfig] | None = None,
) -> tuple[ZoneRuntimeState, bool]:
    cid = InstanceId(str(card_id))
    if cid not in zone_state.private.zoneCards.get(from_zone_key, ()):
        return zone_state, False
    previous = zone_state.private.cardIndex.get(cid)
    next_zones = move_card_to_zone(
        zone_state,
        card_id=cid,
        destination_zone_key=to_zone_key,
        owner_id=owner_id or (previous.ownerID if previous else zone_owner_from_key(to_zone_key)),
        controller_id=controller_id or (previous.controllerID if previous else owner_id),
        zone_definitions=zone_definitions,
    )
    return next_zones, True


def mill_cards(
    zone_state: ZoneRuntimeState,
    *,
    from_zone_key: ZoneId,
    to_zone_key: ZoneId,
    count: int,
    owner_id: PlayerId | None = None,
    zone_definitions: Mapping[ZoneId, ZoneConfig] | None = None,
) -> tuple[ZoneRuntimeState, tuple[InstanceId, ...]]:
    return draw_cards(
        zone_state,
        from_zone_key=from_zone_key,
        to_zone_key=to_zone_key,
        count=count,
        owner_id=owner_id,
        controller_id=owner_id,
        zone_definitions=zone_definitions,
    )


def shuffle_zone(
    zone_state: ZoneRuntimeState,
    *,
    zone_key: ZoneId,
    random_float: Callable[[], float],
    owner_id: PlayerId | None = None,
    zone_definitions: Mapping[ZoneId, ZoneConfig] | None = None,
) -> ZoneRuntimeState:
    cards = list(zone_state.private.zoneCards.get(zone_key, ()))
    zone_cards = {key: tuple(value) for key, value in zone_state.private.zoneCards.items()}
    card_index = dict(zone_state.private.cardIndex)
    card_meta = dict(zone_state.private.cardMeta)
    zone_summaries = dict(zone_state.public.zoneSummaries)

    if owner_id is not None:
        owned_indexes: list[int] = []
        owned_cards: list[InstanceId] = []
        for idx, card_id in enumerate(cards):
            if card_index.get(card_id) and card_index[card_id].ownerID == owner_id:
                owned_indexes.append(idx)
                owned_cards.append(card_id)
        _shuffle_list_in_place(owned_cards, random_float)
        for idx, card_id in zip(owned_indexes, owned_cards, strict=False):
            cards[idx] = card_id
    else:
        _shuffle_list_in_place(cards, random_float)

    zone_cards[zone_key] = tuple(cards)
    _reindex_zone(
        zone_cards=zone_cards,
        card_index=card_index,
        zone_summaries=zone_summaries,
        previous_state=zone_state,
        zone_key=zone_key,
        zone_definitions=zone_definitions,
    )
    return ZoneRuntimeState(
        public=ZoneRuntimePublicState(zoneSummaries=zone_summaries),
        reveals=zone_state.reveals,
        private=ZoneRuntimePrivateState(zoneCards=zone_cards, cardIndex=card_index, cardMeta=card_meta),
    )


def shuffle_bottom(
    zone_state: ZoneRuntimeState,
    *,
    zone_key: ZoneId,
    count: int,
    random_float: Callable[[], float],
    zone_definitions: Mapping[ZoneId, ZoneConfig] | None = None,
) -> ZoneRuntimeState:
    cards = list(zone_state.private.zoneCards.get(zone_key, ()))
    bottom_count = min(max(count, 0), len(cards))
    bottom_cards = cards[:bottom_count]
    _shuffle_list_in_place(bottom_cards, random_float)
    cards[:bottom_count] = bottom_cards

    zone_cards = {key: tuple(value) for key, value in zone_state.private.zoneCards.items()}
    card_index = dict(zone_state.private.cardIndex)
    card_meta = dict(zone_state.private.cardMeta)
    zone_summaries = dict(zone_state.public.zoneSummaries)
    zone_cards[zone_key] = tuple(cards)
    _reindex_zone(
        zone_cards=zone_cards,
        card_index=card_index,
        zone_summaries=zone_summaries,
        previous_state=zone_state,
        zone_key=zone_key,
        zone_definitions=zone_definitions,
    )
    return ZoneRuntimeState(
        public=ZoneRuntimePublicState(zoneSummaries=zone_summaries),
        reveals=zone_state.reveals,
        private=ZoneRuntimePrivateState(zoneCards=zone_cards, cardIndex=card_index, cardMeta=card_meta),
    )


def _shuffle_list_in_place(items: list[InstanceId], random_float: Callable[[], float]) -> None:
    for idx in range(len(items) - 1, 0, -1):
        swap_idx = int(random_float() * (idx + 1))
        items[idx], items[swap_idx] = items[swap_idx], items[idx]


def reveal_cards(
    zone_state: ZoneRuntimeState,
    card_ids: Sequence[InstanceId | str],
    visible_to: str | Sequence[PlayerId | str],
    *,
    expires_at_state_id: int | None = None,
) -> tuple[ZoneRuntimeState, str]:
    next_seq = zone_state.reveals.nextSeq
    reveal_id = f"reveal-{next_seq}"
    visible: str | tuple[PlayerId, ...]
    if visible_to == "all":
        visible = "all"
    else:
        visible = tuple(PlayerId(str(player_id)) for player_id in visible_to)
    reveal = ZoneRevealWindow(
        revealID=reveal_id,
        cardIDs=tuple(InstanceId(str(card_id)) for card_id in card_ids),
        visibleTo=visible,
        expiresAtStateID=expires_at_state_id,
    )
    return (
        ZoneRuntimeState(
            public=zone_state.public,
            reveals=ZoneRuntimeRevealState(
                active=zone_state.reveals.active + (reveal,),
                nextSeq=next_seq + 1,
            ),
            private=zone_state.private,
        ),
        reveal_id,
    )


def reveal_top(
    zone_state: ZoneRuntimeState,
    *,
    zone_key: ZoneId,
    count: int,
    visible_to: str | Sequence[PlayerId | str],
) -> tuple[ZoneRuntimeState, tuple[InstanceId, ...], str]:
    cards = get_cards(zone_state, zone_key)
    revealed = tuple(reversed(cards[-min(max(count, 0), len(cards)) :])) if count > 0 else ()
    next_zones, reveal_id = reveal_cards(zone_state, revealed, visible_to)
    return next_zones, revealed, reveal_id


def clear_reveal(zone_state: ZoneRuntimeState, reveal_id: str) -> ZoneRuntimeState:
    return ZoneRuntimeState(
        public=zone_state.public,
        reveals=ZoneRuntimeRevealState(
            active=tuple(reveal for reveal in zone_state.reveals.active if reveal.revealID != reveal_id),
            nextSeq=zone_state.reveals.nextSeq,
        ),
        private=zone_state.private,
    )


def clear_reveals_by_zone(
    zone_state: ZoneRuntimeState,
    *,
    zone_key: ZoneId,
    current_state_id: int | None = None,
    respect_expiry: bool = False,
) -> ZoneRuntimeState:
    zone_cards = set(zone_state.private.zoneCards.get(zone_key, ()))
    active: list[ZoneRevealWindow] = []
    for reveal in zone_state.reveals.active:
        touches_zone = any(card_id in zone_cards for card_id in reveal.cardIDs)
        if not touches_zone:
            active.append(reveal)
            continue
        if (
            respect_expiry
            and current_state_id is not None
            and reveal.expiresAtStateID is not None
            and reveal.expiresAtStateID > current_state_id
        ):
            active.append(reveal)
    return ZoneRuntimeState(
        public=zone_state.public,
        reveals=ZoneRuntimeRevealState(active=tuple(active), nextSeq=zone_state.reveals.nextSeq),
        private=zone_state.private,
    )


def expire_reveals(zone_state: ZoneRuntimeState, *, current_state_id: int) -> ZoneRuntimeState:
    return ZoneRuntimeState(
        public=zone_state.public,
        reveals=ZoneRuntimeRevealState(
            active=tuple(
                reveal
                for reveal in zone_state.reveals.active
                if reveal.expiresAtStateID is None or reveal.expiresAtStateID > current_state_id
            ),
            nextSeq=zone_state.reveals.nextSeq,
        ),
        private=zone_state.private,
    )


class ZoneOperations:
    def __init__(
        self,
        zone_state: ZoneRuntimeState,
        zone_registry: Mapping[ZoneId, ZoneConfig],
        *,
        emit_event: Callable[[ZoneEvent], None] | None = None,
        random_float: Callable[[], float] | None = None,
        current_state_id: int = 0,
    ) -> None:
        self.zones = zone_state
        self.zone_registry = zone_registry
        self.emit_event = emit_event
        self.random_float = random_float or (lambda: 0.5)
        self.current_state_id = current_state_id

    def _emit(self, event: ZoneEvent) -> None:
        if self.emit_event is not None:
            self.emit_event(event)

    def _resolve(self, zone: ZoneRef | Mapping[str, object] | str | ZoneId) -> ZoneId:
        return resolve_zone_id_from_registry(zone, self.zone_registry, self.zones.private.cardIndex)

    def move_card(
        self,
        card_id: InstanceId | str,
        to_zone: ZoneRef | Mapping[str, object] | str | ZoneId,
        *,
        index: int | None = None,
        face_down: bool | None = None,
    ) -> None:
        cid = InstanceId(str(card_id))
        to_zone_id = self._resolve(to_zone)
        previous = self.zones.private.cardIndex.get(cid)
        from_zone = previous.zoneKey if previous else None
        owner_id = previous.ownerID if previous else zone_owner_from_key(to_zone_id)
        if owner_id is None:
            owner_id = PlayerId("unknown")
        controller_id = previous.controllerID if previous else owner_id
        self.zones = move_card_to_zone(
            self.zones,
            card_id=cid,
            destination_zone_key=to_zone_id,
            owner_id=owner_id,
            controller_id=controller_id,
            index=index,
            zone_definitions=self.zone_registry,
        )
        if from_zone is not None:
            self._emit({"kind": "CARD_LEFT_ZONE", "cardId": cid, "fromZone": from_zone})
        self._emit(
            {
                "kind": "CARD_MOVED",
                "cardId": cid,
                "fromZone": from_zone,
                "toZone": to_zone_id,
                "index": index,
                "faceDown": face_down,
            }
        )
        self._emit(
            {
                "kind": "CARD_ENTERED_ZONE",
                "cardId": cid,
                "toZone": to_zone_id,
                "controllerId": controller_id,
                "ownerId": owner_id,
            }
        )

    def move_cards(
        self,
        card_ids: Sequence[InstanceId | str],
        to_zone: ZoneRef | Mapping[str, object] | str | ZoneId,
        *,
        index: int | None = None,
    ) -> None:
        to_zone_id = self._resolve(to_zone)
        start_index = index if index is not None else len(self.zones.private.zoneCards.get(to_zone_id, ()))
        for offset, card_id in enumerate(card_ids):
            self.move_card(card_id, to_zone_id, index=start_index + offset)

    def draw_cards(
        self,
        *,
        from_zone: ZoneRef | Mapping[str, object] | str | ZoneId,
        to_zone: ZoneRef | Mapping[str, object] | str | ZoneId,
        count: int,
    ) -> tuple[InstanceId, ...]:
        from_ref = _coerce_zone_ref(from_zone)
        to_ref = _coerce_zone_ref(to_zone)
        from_zone_id = self._resolve(from_ref)
        to_zone_id = self._resolve(to_ref)
        source_cards = list(reversed(self.zones.private.zoneCards.get(from_zone_id, ())))
        if from_ref.playerId is not None:
            source_cards = [
                card_id
                for card_id in source_cards
                if self.zones.private.cardIndex.get(card_id)
                and self.zones.private.cardIndex[card_id].ownerID == from_ref.playerId
            ]
        drawn = tuple(source_cards[: max(0, min(count, len(source_cards)))])
        for card_id in drawn:
            self.move_card(card_id, ZoneRef(zone=to_zone_id, playerId=to_ref.playerId))
        self._emit(
            {
                "kind": "CARDS_DRAWN",
                "cardIds": drawn,
                "fromZone": from_zone_id,
                "toZone": to_zone_id,
                "playerId": from_ref.playerId,
            }
        )
        return drawn

    def draw_specific_card(
        self,
        card_id: InstanceId | str,
        *,
        from_zone: ZoneRef | Mapping[str, object] | str | ZoneId,
        to_zone: ZoneRef | Mapping[str, object] | str | ZoneId,
    ) -> bool:
        cid = InstanceId(str(card_id))
        from_zone_id = self._resolve(from_zone)
        if cid not in self.zones.private.zoneCards.get(from_zone_id, ()):
            return False
        self.move_card(cid, to_zone)
        return True

    def mill(
        self,
        *,
        from_zone: ZoneRef | Mapping[str, object] | str | ZoneId,
        to_zone: ZoneRef | Mapping[str, object] | str | ZoneId,
        count: int,
    ) -> tuple[InstanceId, ...]:
        from_ref = _coerce_zone_ref(from_zone)
        to_ref = _coerce_zone_ref(to_zone)
        from_zone_id = self._resolve(from_ref)
        to_zone_id = self._resolve(to_ref)
        source_cards = list(reversed(self.zones.private.zoneCards.get(from_zone_id, ())))
        if from_ref.playerId is not None:
            source_cards = [
                card_id
                for card_id in source_cards
                if self.zones.private.cardIndex.get(card_id)
                and self.zones.private.cardIndex[card_id].ownerID == from_ref.playerId
            ]
        milled = tuple(source_cards[: max(0, min(count, len(source_cards)))])
        for card_id in milled:
            self.move_card(card_id, ZoneRef(zone=to_zone_id, playerId=to_ref.playerId))
        self._emit(
            {
                "kind": "CARDS_MILLED",
                "cardIds": milled,
                "fromZone": from_zone_id,
                "toZone": to_zone_id,
                "playerId": from_ref.playerId,
            }
        )
        return milled

    def shuffle(self, zone: ZoneRef | Mapping[str, object] | str | ZoneId) -> None:
        zone_ref = _coerce_zone_ref(zone)
        zone_id = self._resolve(zone_ref)
        self.zones = shuffle_zone(
            self.zones,
            zone_key=zone_id,
            owner_id=zone_ref.playerId,
            random_float=self.random_float,
            zone_definitions=self.zone_registry,
        )
        self._emit({"kind": "ZONE_SHUFFLED", "zoneId": zone_id, "playerId": zone_ref.playerId})

    def shuffle_bottom(self, zone: ZoneRef | Mapping[str, object] | str | ZoneId, count: int) -> None:
        zone_id = self._resolve(zone)
        self.zones = shuffle_bottom(
            self.zones,
            zone_key=zone_id,
            count=count,
            random_float=self.random_float,
            zone_definitions=self.zone_registry,
        )
        self._emit({"kind": "ZONE_BOTTOM_SHUFFLED", "zoneId": zone_id, "count": count})

    def reveal(
        self,
        card_ids: Sequence[InstanceId | str],
        visible_to: str | Sequence[PlayerId | str],
        *,
        state_id: int | None = None,
    ) -> str:
        self.zones, reveal_id = reveal_cards(
            self.zones,
            card_ids,
            visible_to,
            expires_at_state_id=state_id,
        )
        reveal = self.zones.reveals.active[-1]
        self._emit(
            {
                "kind": "REVEAL_CREATED",
                "revealId": reveal_id,
                "cardIds": reveal.cardIDs,
                "visibleTo": reveal.visibleTo,
            }
        )
        return reveal_id

    def reveal_top(
        self,
        zone: ZoneRef | Mapping[str, object] | str | ZoneId,
        count: int,
        visible_to: str | Sequence[PlayerId | str],
    ) -> tuple[InstanceId, ...]:
        zone_id = self._resolve(zone)
        self.zones, revealed, _ = reveal_top(
            self.zones,
            zone_key=zone_id,
            count=count,
            visible_to=visible_to,
        )
        reveal = self.zones.reveals.active[-1]
        self._emit(
            {
                "kind": "REVEAL_CREATED",
                "revealId": reveal.revealID,
                "cardIds": reveal.cardIDs,
                "visibleTo": reveal.visibleTo,
            }
        )
        return revealed

    def clear_reveal(self, reveal_id: str) -> None:
        before = len(self.zones.reveals.active)
        self.zones = clear_reveal(self.zones, reveal_id)
        if len(self.zones.reveals.active) != before:
            self._emit({"kind": "REVEAL_CLEARED", "revealId": reveal_id})

    def clear_reveals_by_zone(
        self,
        zone: ZoneRef | Mapping[str, object] | str | ZoneId,
        *,
        respect_expiry: bool = False,
    ) -> None:
        zone_id = self._resolve(zone)
        before = {reveal.revealID for reveal in self.zones.reveals.active}
        self.zones = clear_reveals_by_zone(
            self.zones,
            zone_key=zone_id,
            current_state_id=self.current_state_id,
            respect_expiry=respect_expiry,
        )
        after = {reveal.revealID for reveal in self.zones.reveals.active}
        for reveal_id in sorted(before - after):
            self._emit({"kind": "REVEAL_CLEARED", "revealId": reveal_id})

    def get_cards(self, zone: ZoneRef | Mapping[str, object] | str | ZoneId) -> tuple[InstanceId, ...]:
        return get_cards(self.zones, self._resolve(zone))

    def get_card_count(self, zone: ZoneRef | Mapping[str, object] | str | ZoneId) -> int:
        return get_card_count(self.zones, self._resolve(zone))

    def get_top_card(self, zone: ZoneRef | Mapping[str, object] | str | ZoneId) -> InstanceId | None:
        return get_top_card(self.zones, self._resolve(zone))

    def get_bottom_card(self, zone: ZoneRef | Mapping[str, object] | str | ZoneId) -> InstanceId | None:
        return get_bottom_card(self.zones, self._resolve(zone))

    def get_card_zone(self, card_id: InstanceId | str) -> ZoneId | None:
        entry = self.zones.private.cardIndex.get(InstanceId(str(card_id)))
        return entry.zoneKey if entry else None

    def get_card_owner(self, card_id: InstanceId | str) -> PlayerId | None:
        entry = self.zones.private.cardIndex.get(InstanceId(str(card_id)))
        return entry.ownerID if entry else None

    def get_card_controller(self, card_id: InstanceId | str) -> PlayerId | None:
        entry = self.zones.private.cardIndex.get(InstanceId(str(card_id)))
        return entry.controllerID if entry else None

    def is_ordered(self, zone: ZoneRef | Mapping[str, object] | str | ZoneId) -> bool:
        return self.zone_registry[self._resolve(zone)].ordered

    def is_owner_scoped(self, zone: ZoneRef | Mapping[str, object] | str | ZoneId) -> bool:
        return self.zone_registry[self._resolve(zone)].owner_scoped

    def get_visibility(self, zone: ZoneRef | Mapping[str, object] | str | ZoneId) -> str:
        return self.zone_registry[self._resolve(zone)].visibility


ZoneOperations.moveCard = ZoneOperations.move_card
ZoneOperations.moveCards = ZoneOperations.move_cards
ZoneOperations.drawCards = ZoneOperations.draw_cards
ZoneOperations.drawSpecificCard = ZoneOperations.draw_specific_card
ZoneOperations.shuffleBottom = ZoneOperations.shuffle_bottom
ZoneOperations.revealTop = ZoneOperations.reveal_top
ZoneOperations.clearReveal = ZoneOperations.clear_reveal
ZoneOperations.clearRevealsByZone = ZoneOperations.clear_reveals_by_zone
ZoneOperations.getCards = ZoneOperations.get_cards
ZoneOperations.getCardCount = ZoneOperations.get_card_count
ZoneOperations.getTopCard = ZoneOperations.get_top_card
ZoneOperations.getBottomCard = ZoneOperations.get_bottom_card
ZoneOperations.getCardZone = ZoneOperations.get_card_zone
ZoneOperations.getCardOwner = ZoneOperations.get_card_owner
ZoneOperations.getCardController = ZoneOperations.get_card_controller
ZoneOperations.isOrdered = ZoneOperations.is_ordered
ZoneOperations.isOwnerScoped = ZoneOperations.is_owner_scoped
ZoneOperations.getVisibility = ZoneOperations.get_visibility


def create_zone_operations(
    zone_state: ZoneRuntimeState,
    zone_registry: Mapping[ZoneId, ZoneConfig],
    *,
    emit_event: Callable[[ZoneEvent], None] | None = None,
    random_float: Callable[[], float] | None = None,
    current_state_id: int = 0,
) -> ZoneOperations:
    return ZoneOperations(
        zone_state,
        zone_registry,
        emit_event=emit_event,
        random_float=random_float,
        current_state_id=current_state_id,
    )
