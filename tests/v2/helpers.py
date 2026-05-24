from pathlib import Path

from lorcana_engine_v2.cards import CardCatalog
from lorcana_engine_v2.core.bootstrap import initialize_match_state_from_static_resources
from lorcana_engine_v2.core.context import build_rules_context
from lorcana_engine_v2.core.ids import CardId, InstanceId, PlayerId
from lorcana_engine_v2.core.static_resources import CardsMaps, create_match_static_resources_from_cards_maps
from lorcana_engine_v2.core.zones import (
    LORCANA_RUNTIME_ZONES,
    CardMeta,
    ZoneRuntimePrivateState,
    put_cards_in_zone,
    scoped_zone,
)


def real_catalog() -> CardCatalog:
    return CardCatalog.from_lorcanito_normalized_json(Path("data/lorcanito_runtime_extracted/cards.normalized.json"))


def resources_for(card_instances: dict[str, str], owners: dict[str, tuple[str, ...]] | None = None):
    if owners is None:
        owners = {"p0": tuple(card_instances)}
    cards_maps = CardsMaps(
        card_instances={InstanceId(iid): CardId(cid) for iid, cid in card_instances.items()},
        owners={PlayerId(pid): tuple(InstanceId(iid) for iid in ids) for pid, ids in owners.items()},
    )
    return create_match_static_resources_from_cards_maps(cards_maps, real_catalog(), LORCANA_RUNTIME_ZONES)


def state_with_play(resources, p0: tuple[str, ...] = (), p1: tuple[str, ...] = (), meta: dict[str, CardMeta] | None = None):
    state = initialize_match_state_from_static_resources(resources)
    zones = state.ctx.zones
    zones = put_cards_in_zone(zones, zone_key=scoped_zone("play", "p0"), card_ids=tuple(InstanceId(i) for i in p0), owner_id=PlayerId("p0"), controller_id=PlayerId("p0"))
    zones = put_cards_in_zone(zones, zone_key=scoped_zone("play", "p1"), card_ids=tuple(InstanceId(i) for i in p1), owner_id=PlayerId("p1"), controller_id=PlayerId("p1"))
    if meta:
        card_meta = dict(zones.private.cardMeta)
        for key, value in meta.items():
            card_meta[InstanceId(key)] = value
        zones = type(zones)(
            public=zones.public,
            reveals=zones.reveals,
            private=ZoneRuntimePrivateState(
                zoneCards=zones.private.zoneCards,
                cardIndex=zones.private.cardIndex,
                cardMeta=card_meta,
            ),
        )
    return type(state)(G=state.G, ctx=state.ctx.with_updates(zones=zones))


def context_for(resources):
    return build_rules_context(resources)
