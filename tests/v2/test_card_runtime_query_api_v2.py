from lorcana_engine_v2.core.zones import CardMeta, put_cards_in_zone, scoped_zone

from .helpers import context_for, resources_for
from lorcana_engine_v2.core.bootstrap import initialize_match_state_from_static_resources
from lorcana_engine_v2.core.ids import InstanceId, PlayerId


def test_runtime_card_api_resolves_instance_to_definition_through_static_resources():
    resources = resources_for({"c1": "XGm"})
    ctx = context_for(resources)
    state = initialize_match_state_from_static_resources(resources)

    runtime_card = ctx.query.runtime_card(state, "c1")
    assert runtime_card.instance_id == "c1"
    assert runtime_card.definition_id == "XGm"
    assert runtime_card.owner_id == "p0"
    assert runtime_card.controller_id == "p0"
    assert runtime_card.definition.full_name == "Chi-Fu - Imperial Advisor"
    assert runtime_card.zone_id == scoped_zone("deck", "p0")
    assert runtime_card.zone_index == 0


def test_runtime_card_api_reads_zone_and_meta_state_without_card_definition_in_state():
    resources = resources_for({"c1": "XGm"})
    ctx = context_for(resources)
    state = initialize_match_state_from_static_resources(resources)
    zones = put_cards_in_zone(
        state.framework.zones,
        zone_key=scoped_zone("play", "p0"),
        card_ids=(InstanceId("c1"),),
        owner_id=PlayerId("p0"),
        controller_id=PlayerId("p0"),
    )
    meta = dict(zones.card_meta)
    meta[InstanceId("c1")] = CardMeta(damage=2, exerted=True)
    zones = type(zones)(
        zone_cards=zones.zone_cards,
        card_index=zones.card_index,
        card_meta=meta,
        zone_summaries=zones.zone_summaries,
    )
    state = type(state)(framework=state.framework.with_updates(zones=zones), game=state.game)

    runtime_card = ctx.query.runtime_card(state, "c1")
    assert runtime_card.zone_id == scoped_zone("play", "p0")
    assert runtime_card.meta.damage == 2
    assert runtime_card.meta.exerted is True
    assert ctx.query.public_in_play_ids(state) == ("c1",)
    assert ctx.query.characters_in_play(state, "p0") == ("c1",)
