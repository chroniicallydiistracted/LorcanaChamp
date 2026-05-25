from types import SimpleNamespace

from lorcana_engine_v2.core.ids import InstanceId, PlayerId
from lorcana_engine_v2.effects.replacement_effects import (
    apply_replacement_effects,
    register_replacement_effect,
)

from .helpers import resources_for, state_with_play


def test_real_beast_printed_replacement_redirects_damage_to_self():
    resources = resources_for({"beast": "sLs", "ally": "ZTM"}, owners={"p0": ("beast", "ally")})
    state = state_with_play(resources, p0=("beast", "ally"))
    target = SimpleNamespace(state=state, resources=resources)

    replaced = apply_replacement_effects(
        target,
        {
            "kind": "deal-damage",
            "eventId": "damage:1",
            "controllerId": PlayerId("p1"),
            "targetId": InstanceId("ally"),
            "amount": 3,
        },
    )

    assert replaced["targetId"] == InstanceId("beast")
    assert replaced["amount"] == 3


def test_registered_zone_destination_replacement_indexes_by_event_kind_and_applies_once():
    resources = resources_for({"aladdin": "ZTM"})
    state = state_with_play(resources, p0=("aladdin",))
    state = type(state)(
        G=state.G,
        ctx=state.ctx.with_updates(status=state.ctx.status.with_updates(turn=1)),
    )
    state = register_replacement_effect(
        state,
        {"playerId": PlayerId("p0"), "cardId": InstanceId("aladdin")},
        {
            "type": "zone-destination",
            "eventKinds": ["zone-change"],
            "targetRef": "source",
            "toZone": "discard",
            "replacementZone": "deck",
            "replacementPosition": "bottom",
        },
        "this-turn",
        {},
    )

    registration = state.G.replacementEffects.registrations[0]
    assert registration.id == "replacement:1"
    assert state.G.replacementEffects.byEventKind == {"zone-change": ("replacement:1",)}

    replaced = apply_replacement_effects(
        state,
        {
            "kind": "zone-change",
            "eventId": "zone:1",
            "controllerId": PlayerId("p0"),
            "cardId": InstanceId("aladdin"),
            "fromZone": "play",
            "toZone": "discard",
        },
    )

    assert replaced["toZone"] == "deck"
    assert replaced["position"] == "bottom"
