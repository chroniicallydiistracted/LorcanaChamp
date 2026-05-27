from __future__ import annotations

from collections.abc import Callable

from lorcana_engine_v2.core.ids import InstanceId, PlayerId, ZoneId
from lorcana_engine_v2.core.zones import (
    CardMeta,
    ZoneRef,
    ZoneRuntimePrivateState,
    ZoneRuntimeState,
    move_card_to_zone,
    scoped_zone,
)


def _cards_under(meta: CardMeta | None) -> tuple[InstanceId, ...]:
    return tuple(getattr(meta, "cardsUnder", None) or ())


def stacked_card_ids_from_zones(zones, card_id: InstanceId | str) -> tuple[InstanceId, ...]:
    cid = InstanceId(str(card_id))
    meta = zones.private.cardMeta.get(cid, CardMeta())
    ordered: list[InstanceId] = []
    seen: set[InstanceId] = set()

    for raw_id in (cid,) + _cards_under(meta):
        stacked_id = InstanceId(str(raw_id))
        if stacked_id in seen:
            continue
        seen.add(stacked_id)
        ordered.append(stacked_id)

    return tuple(ordered)


def stacked_card_ids_from_context(context, card_id: InstanceId | str) -> tuple[InstanceId, ...]:
    cid = InstanceId(str(card_id))
    meta = context.cards.getMeta(cid)
    return (cid,) + _cards_under(meta)


def clear_stack_meta_from_zones(zones, card_ids: tuple[InstanceId, ...]):
    card_meta = dict(zones.private.cardMeta)
    for card_id in card_ids:
        card_meta.pop(InstanceId(str(card_id)), None)

    return ZoneRuntimeState(
        public=zones.public,
        reveals=zones.reveals,
        private=ZoneRuntimePrivateState(
            zoneCards=zones.private.zoneCards,
            cardIndex=zones.private.cardIndex,
            cardMeta=card_meta,
        ),
    )


def clear_stack_meta_from_context(context, card_ids: tuple[InstanceId, ...]) -> None:
    for card_id in card_ids:
        context.cards.clearMeta(card_id)


def _replace_card_meta_map(zones, card_meta):
    return ZoneRuntimeState(
        public=zones.public,
        reveals=zones.reveals,
        private=ZoneRuntimePrivateState(
            zoneCards=zones.private.zoneCards,
            cardIndex=zones.private.cardIndex,
            cardMeta=card_meta,
        ),
    )


def evacuate_characters_from_leaving_locations_in_zones(
    zones,
    leaving_card_ids: tuple[InstanceId, ...],
    *,
    is_location_card: Callable[[InstanceId], bool],
    is_character_card: Callable[[InstanceId], bool],
):
    leaving_locations = {
        InstanceId(str(card_id))
        for card_id in leaving_card_ids
        if is_location_card(InstanceId(str(card_id)))
    }
    if not leaving_locations:
        return zones

    card_meta = dict(zones.private.cardMeta)
    changed = False

    for card_id, meta in tuple(card_meta.items()):
        if meta.atLocationId in leaving_locations and is_character_card(InstanceId(str(card_id))):
            card_meta[card_id] = meta.with_updates(atLocationId=None)
            changed = True

    if not changed:
        return zones

    return _replace_card_meta_map(zones, card_meta)


def move_card_out_of_play_with_stack_zones(
    zones,
    card_id: InstanceId | str,
    *,
    destination_zone: str,
    destination_player_id: PlayerId | str,
    index: int | None = None,
    is_location_card: Callable[[InstanceId], bool] | None = None,
    is_character_card: Callable[[InstanceId], bool] | None = None,
) -> tuple[object, tuple[InstanceId, ...]]:
    cid = InstanceId(str(card_id))
    player = PlayerId(str(destination_player_id))
    moved_card_ids = stacked_card_ids_from_zones(zones, cid)

    if is_location_card is not None and is_character_card is not None:
        zones = evacuate_characters_from_leaving_locations_in_zones(
            zones,
            moved_card_ids,
            is_location_card=is_location_card,
            is_character_card=is_character_card,
        )

    for offset, moved_id in enumerate(moved_card_ids):
        move_index = None if index is None else index + offset
        zones = move_card_to_zone(
            zones,
            card_id=moved_id,
            destination_zone_key=scoped_zone(destination_zone, player),
            index=move_index,
        )

    zones = clear_stack_meta_from_zones(zones, moved_card_ids)
    return zones, moved_card_ids


def move_card_out_of_play_with_stack_context(
    context,
    card_id: InstanceId | str,
    destination_zone_ref: ZoneRef | dict[str, object],
    *,
    index: int | None = None,
) -> tuple[InstanceId, ...]:
    cid = InstanceId(str(card_id))
    moved_card_ids = stacked_card_ids_from_context(context, cid)

    destination_zone = destination_zone_ref.zone if isinstance(destination_zone_ref, ZoneRef) else destination_zone_ref.get("zone")
    destination_player = (
        destination_zone_ref.playerId
        if isinstance(destination_zone_ref, ZoneRef)
        else destination_zone_ref.get("playerId") or destination_zone_ref.get("player_id")
    )

    for offset, moved_id in enumerate(moved_card_ids):
        move_index = None if index is None else index + offset
        context.framework.zones.moveCard(
            moved_id,
            ZoneRef(zone=ZoneId(str(destination_zone)), playerId=PlayerId(str(destination_player))),
            index=move_index,
        )

    clear_stack_meta_from_context(context, moved_card_ids)
    return moved_card_ids


__all__ = [
    "clear_stack_meta_from_context",
    "clear_stack_meta_from_zones",
    "move_card_out_of_play_with_stack_context",
    "move_card_out_of_play_with_stack_zones",
    "stacked_card_ids_from_context",
    "stacked_card_ids_from_zones",
]