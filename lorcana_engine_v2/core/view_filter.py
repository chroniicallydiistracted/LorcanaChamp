from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Mapping, Sequence

from .ids import InstanceId, PlayerId, ZoneId
from .state import CtxPriority, CtxRandom, CtxStatus, LorcanaG, MatchState, NoTimeContext
from .zones import (
    LorcanaCardMeta,
    PublicZoneSummary,
    ZoneCardIndexEntry,
    ZoneConfig,
    ZoneRevealWindow,
    ZoneRuntimePrivateState,
    ZoneRuntimePublicState,
    ZoneRuntimeState,
    base_zone_from_key,
    zone_owner_from_key,
)


Role = Literal["player", "spectator", "judge"]


@dataclass(frozen=True, slots=True)
class ViewRoleContext:
    role: Role
    playerID: PlayerId | None = None


@dataclass(frozen=True, slots=True)
class FilteredCtxRandom:
    seed: str
    draws: int
    state: object | None = None


@dataclass(frozen=True, slots=True)
class FilteredZoneRuntimeRevealState:
    active: tuple[ZoneRevealWindow, ...]


@dataclass(frozen=True, slots=True)
class FilteredZoneRuntimeState:
    public: ZoneRuntimePublicState
    reveals: FilteredZoneRuntimeRevealState
    private: ZoneRuntimePrivateState


@dataclass(frozen=True, slots=True)
class FilteredTCGCtx:
    matchID: str
    gameID: str
    rulesetHash: str
    playerIds: tuple[PlayerId, ...]
    zones: FilteredZoneRuntimeState
    random: FilteredCtxRandom
    protocolVersion: int
    _stateID: int
    status: CtxStatus
    priority: CtxPriority
    time: NoTimeContext


@dataclass(frozen=True, slots=True)
class FilteredMatchView:
    G: LorcanaG
    ctx: FilteredTCGCtx


@dataclass(frozen=True, slots=True)
class PublicZoneViewSummary:
    count: int
    revision: int
    topCardID: InstanceId | None = None


@dataclass(frozen=True, slots=True)
class SecretLeakageCheck:
    valid: bool
    violations: tuple[str, ...] = ()


def filter_match_view(
    state: MatchState,
    role_ctx: ViewRoleContext,
    zone_registry: Mapping[ZoneId, ZoneConfig],
) -> FilteredMatchView:
    filtered_ctx = FilteredTCGCtx(
        matchID=state.ctx.matchID,
        gameID=state.ctx.gameID,
        rulesetHash=state.ctx.rulesetHash,
        playerIds=state.ctx.playerIds,
        zones=filter_zones(
            state.ctx.zones,
            zone_registry,
            role_ctx.role,
            role_ctx.playerID,
        ),
        random=filter_random(state.ctx.random),
        protocolVersion=state.ctx.protocolVersion,
        _stateID=state.ctx._stateID,
        status=state.ctx.status,
        priority=state.ctx.priority,
        time=state.ctx.time,
    )
    return FilteredMatchView(G=state.G, ctx=filtered_ctx)


def filter_zones(
    zones: ZoneRuntimeState,
    zone_registry: Mapping[ZoneId, ZoneConfig],
    role: Role,
    player_id: PlayerId | None = None,
) -> FilteredZoneRuntimeState:
    filtered_public = ZoneRuntimePublicState(zoneSummaries=dict(zones.public.zoneSummaries))
    filtered_reveals = filter_reveals(zones.reveals.active, role, player_id)

    filtered_private = (
        filter_public_zone_cards(zones, zone_registry)
        if role == "player"
        else ZoneRuntimePrivateState(zoneCards={}, cardIndex={}, cardMeta={})
    )

    if role == "judge":
        filtered_private = zones.private
    elif role == "player" and player_id is not None:
        filtered_private = _merge_private_views(
            filtered_private,
            filter_private_zones_for_player(zones, zone_registry, player_id),
        )

    filtered_zone_cards = dict(filtered_private.zoneCards)
    filtered_card_index = dict(filtered_private.cardIndex)
    filtered_card_meta = dict(filtered_private.cardMeta)
    _add_visible_reveals(
        filtered_card_index,
        filtered_card_meta,
        zones,
        filtered_reveals,
    )

    return FilteredZoneRuntimeState(
        public=filtered_public,
        reveals=FilteredZoneRuntimeRevealState(active=filtered_reveals),
        private=ZoneRuntimePrivateState(
            zoneCards=filtered_zone_cards,
            cardIndex=filtered_card_index,
            cardMeta=filtered_card_meta,
        ),
    )


def filter_private_zones_for_player(
    zones: ZoneRuntimeState,
    zone_registry: Mapping[ZoneId, ZoneConfig],
    player_id: PlayerId,
) -> ZoneRuntimePrivateState:
    filtered_zone_cards: dict[ZoneId, tuple[InstanceId, ...]] = {}
    filtered_card_index: dict[InstanceId, ZoneCardIndexEntry] = {}
    filtered_card_meta: dict[InstanceId, LorcanaCardMeta] = {}

    for zone_id, card_ids in zones.private.zoneCards.items():
        zone_def = _zone_def(zone_registry, zone_id)
        if zone_def is None:
            continue

        if zone_def.visibility == "public":
            filtered_zone_cards[zone_id] = tuple(card_ids)
            _copy_cards_into_private_view(
                card_ids,
                zones,
                filtered_card_index,
                filtered_card_meta,
            )
        elif zone_def.visibility == "private":
            owner_id = zone_owner_from_key(zone_id) if zone_def.owner_scoped else None
            is_owner_zone = not zone_def.owner_scoped or owner_id is None or owner_id == player_id
            if not is_owner_zone:
                continue

            visible_cards = tuple(
                card_id
                for card_id in card_ids
                if zones.private.cardIndex.get(card_id)
                and zones.private.cardIndex[card_id].ownerID == player_id
            )
            filtered_zone_cards[zone_id] = visible_cards
            _copy_cards_into_private_view(
                visible_cards,
                zones,
                filtered_card_index,
                filtered_card_meta,
            )
        elif zone_def.visibility == "secret" and zone_def.owner_scoped:
            owner_id = zone_owner_from_key(zone_id)
            if owner_id == player_id:
                filtered_zone_cards[zone_id] = ()
                _copy_cards_into_private_view(
                    card_ids,
                    zones,
                    filtered_card_index,
                    filtered_card_meta,
                )

    return ZoneRuntimePrivateState(
        zoneCards=filtered_zone_cards,
        cardIndex=filtered_card_index,
        cardMeta=filtered_card_meta,
    )


def filter_public_zone_cards(
    zones: ZoneRuntimeState,
    zone_registry: Mapping[ZoneId, ZoneConfig],
) -> ZoneRuntimePrivateState:
    filtered_zone_cards: dict[ZoneId, tuple[InstanceId, ...]] = {}
    filtered_card_index: dict[InstanceId, ZoneCardIndexEntry] = {}
    filtered_card_meta: dict[InstanceId, LorcanaCardMeta] = {}

    for zone_id, card_ids in zones.private.zoneCards.items():
        zone_def = _zone_def(zone_registry, zone_id)
        if zone_def is None or zone_def.visibility != "public":
            continue
        filtered_zone_cards[zone_id] = tuple(card_ids)
        _copy_cards_into_private_view(
            card_ids,
            zones,
            filtered_card_index,
            filtered_card_meta,
        )

    return ZoneRuntimePrivateState(
        zoneCards=filtered_zone_cards,
        cardIndex=filtered_card_index,
        cardMeta=filtered_card_meta,
    )


def filter_reveals(
    reveals: Sequence[ZoneRevealWindow],
    role: Role,
    player_id: PlayerId | None = None,
) -> tuple[ZoneRevealWindow, ...]:
    visible: list[ZoneRevealWindow] = []
    for reveal in reveals:
        if reveal.visibleTo == "all":
            visible.append(reveal)
            continue
        if role == "judge":
            visible.append(reveal)
            continue
        if role == "player" and player_id is not None and player_id in reveal.visibleTo:
            visible.append(reveal)
    return tuple(visible)


def filter_random(random: CtxRandom) -> FilteredCtxRandom:
    return FilteredCtxRandom(seed=random.seed, draws=random.draws, state=None)


def get_public_zone_summary(
    zones: ZoneRuntimeState,
    zone_registry: Mapping[ZoneId, ZoneConfig],
    zone_id: ZoneId | str,
) -> PublicZoneViewSummary:
    resolved_zone_id = ZoneId(str(zone_id))
    zone_def = _zone_def(zone_registry, resolved_zone_id)
    summary = zones.public.zoneSummaries.get(resolved_zone_id)
    if zone_def is None or summary is None:
        return PublicZoneViewSummary(count=0, revision=0)
    return PublicZoneViewSummary(
        count=summary.count,
        revision=summary.revision,
        topCardID=summary.topPublicCardID,
    )


def verify_no_secret_leakage(
    original_state: MatchState,
    filtered_state: FilteredMatchView,
    role_ctx: ViewRoleContext,
    zone_registry: Mapping[ZoneId, ZoneConfig],
) -> SecretLeakageCheck:
    violations: list[str] = []
    role = role_ctx.role
    player_id = role_ctx.playerID

    if role == "player" and player_id is not None:
        for zone_id, zone_def in zone_registry.items():
            if zone_def.visibility != "private" or not zone_def.owner_scoped:
                continue
            original_cards = tuple(original_state.ctx.zones.private.zoneCards.get(zone_id, ()))
            opponent_cards = tuple(
                card_id
                for card_id in original_cards
                if original_state.ctx.zones.private.cardIndex.get(card_id)
                and original_state.ctx.zones.private.cardIndex[card_id].ownerID != player_id
            )
            visible_reveals = filter_reveals(
                original_state.ctx.zones.reveals.active,
                role,
                player_id,
            )
            revealed_card_ids = {
                card_id
                for reveal in visible_reveals
                for card_id in reveal.cardIDs
            }
            filtered_cards = tuple(filtered_state.ctx.zones.private.zoneCards.get(zone_id, ()))
            for card_id in opponent_cards:
                if card_id in filtered_cards and card_id not in revealed_card_ids:
                    violations.append(f"Opponent card {card_id} leaked in zone {zone_id}")

    for zone_id, zone_def in zone_registry.items():
        if zone_def.visibility != "secret":
            continue
        filtered_cards = tuple(filtered_state.ctx.zones.private.zoneCards.get(zone_id, ()))
        if filtered_cards:
            violations.append(f"Secret zone {zone_id} contents leaked")

    if filtered_state.ctx.random.state is not None:
        violations.append("RNG state leaked in filtered view")

    return SecretLeakageCheck(valid=not violations, violations=tuple(violations))


def _zone_def(
    zone_registry: Mapping[ZoneId, ZoneConfig],
    zone_id: ZoneId,
) -> ZoneConfig | None:
    return zone_registry.get(zone_id) or zone_registry.get(base_zone_from_key(zone_id))


def _merge_private_views(
    base: ZoneRuntimePrivateState,
    extra: ZoneRuntimePrivateState,
) -> ZoneRuntimePrivateState:
    return ZoneRuntimePrivateState(
        zoneCards={**base.zoneCards, **extra.zoneCards},
        cardIndex={**base.cardIndex, **extra.cardIndex},
        cardMeta={**base.cardMeta, **extra.cardMeta},
    )


def _copy_cards_into_private_view(
    card_ids: Sequence[InstanceId],
    zones: ZoneRuntimeState,
    card_index: dict[InstanceId, ZoneCardIndexEntry],
    card_meta: dict[InstanceId, LorcanaCardMeta],
) -> None:
    for card_id in card_ids:
        index_entry = zones.private.cardIndex.get(card_id)
        if index_entry is not None:
            card_index[card_id] = index_entry
        meta = zones.private.cardMeta.get(card_id)
        if meta is not None:
            card_meta[card_id] = meta


def _add_visible_reveals(
    target_card_index: dict[InstanceId, ZoneCardIndexEntry],
    target_card_meta: dict[InstanceId, LorcanaCardMeta],
    zones: ZoneRuntimeState,
    reveals: Sequence[ZoneRevealWindow],
) -> None:
    for reveal in reveals:
        for card_id in reveal.cardIDs:
            index_entry = zones.private.cardIndex.get(card_id)
            if index_entry is not None and card_id not in target_card_index:
                target_card_index[card_id] = index_entry
            meta = zones.private.cardMeta.get(card_id)
            if meta is not None and card_id not in target_card_meta:
                target_card_meta[card_id] = meta
