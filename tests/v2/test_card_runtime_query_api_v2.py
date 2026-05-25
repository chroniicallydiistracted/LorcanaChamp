from lorcana_engine_v2.core.zones import CardMeta, ZoneRuntimePrivateState, put_cards_in_zone, scoped_zone

from .helpers import context_for, resources_for
from lorcana_engine_v2.core.bootstrap import initialize_match_state_from_static_resources
from lorcana_engine_v2.core.ids import InstanceId, PlayerId


def test_runtime_card_api_resolves_instance_to_definition_through_static_resources():
    resources = resources_for({"c1": "XGm"})
    ctx = context_for(resources)
    state = initialize_match_state_from_static_resources(resources)

    runtime_card = ctx.query.runtime_card(state, "c1")
    assert runtime_card.instanceId == "c1"
    assert runtime_card.definitionId == "XGm"
    assert runtime_card.ownerID == "p0"
    assert runtime_card.controllerID == "p0"
    assert runtime_card.definition.full_name == "Chi-Fu - Imperial Advisor"
    assert runtime_card.zoneID == scoped_zone("deck", "p0")
    assert runtime_card.zoneIndex == 0
    assert runtime_card.fullName == "Chi-Fu - Imperial Advisor"
    assert runtime_card.strength == 0
    assert runtime_card.willpower == 5
    assert runtime_card.lore == 1


def test_runtime_card_api_reads_zone_and_meta_state_without_card_definition_in_state():
    resources = resources_for({"c1": "XGm"})
    ctx = context_for(resources)
    state = initialize_match_state_from_static_resources(resources)
    zones = put_cards_in_zone(
        state.ctx.zones,
        zone_key=scoped_zone("play", "p0"),
        card_ids=(InstanceId("c1"),),
        owner_id=PlayerId("p0"),
        controller_id=PlayerId("p0"),
    )
    meta = dict(zones.private.cardMeta)
    meta[InstanceId("c1")] = CardMeta(damage=2, state="exerted")
    zones = type(zones)(
        public=zones.public,
        reveals=zones.reveals,
        private=ZoneRuntimePrivateState(
            zoneCards=zones.private.zoneCards,
            cardIndex=zones.private.cardIndex,
            cardMeta=meta,
        ),
    )
    state = type(state)(G=state.G, ctx=state.ctx.with_updates(zones=zones))

    runtime_card = ctx.query.runtime_card(state, "c1")
    assert runtime_card.zoneID == scoped_zone("play", "p0")
    assert runtime_card.meta.damage == 2
    assert runtime_card.meta.state == "exerted"
    assert runtime_card.damage == 2
    assert runtime_card.exerted is True
    assert ctx.query.public_in_play_ids(state) == ("c1",)
    assert ctx.query.characters_in_play(state, "p0") == ("c1",)
