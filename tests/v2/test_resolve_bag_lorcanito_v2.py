from lorcana_engine_v2.core.ids import InstanceId, PlayerId
from lorcana_engine_v2.effects.triggered_abilities import flush_triggered_events_to_bag, record_event
from lorcana_engine_v2.resolution.bag import resolve_bag, validate_resolve_bag

from .helpers import resources_for, state_with_play


def _state_with_aladdin_bag(resources):
    state = state_with_play(resources, p0=("aladdin",))
    state = type(state)(
        G=state.G.with_updates(lore={PlayerId("p0"): 0, PlayerId("p1"): 3}),
        ctx=state.ctx.with_updates(
            status=state.ctx.status.with_updates(turn=1, turnOwnerId=PlayerId("p0")),
            priority=state.ctx.priority.with_updates(holder=PlayerId("p0")),
        ),
    )
    state = record_event(
        state,
        {
            "event": "play",
            "subjectCardId": InstanceId("aladdin"),
            "triggerSourceCardId": InstanceId("aladdin"),
            "playerId": PlayerId("p0"),
        },
    )
    return flush_triggered_events_to_bag(state, resources=resources)


def test_resolve_bag_executes_real_lorcanito_trigger_effect_and_clears_bag():
    resources = resources_for({"aladdin": "ZTM"})
    state = _state_with_aladdin_bag(resources)
    bag_item = state.G.triggeredAbilities.bag.items[0]

    result = resolve_bag(state, bag_id=bag_item.id, player_id="p0", resources=resources)

    assert result.status == "resolved"
    assert result.state.G.lore[PlayerId("p1")] == 2
    assert result.state.G.triggeredAbilities.bag.items == ()
    assert result.state.G.triggeredAbilities.bag.lastResolvedPlayerId is None


def test_resolve_bag_rejects_non_resolver_like_lorcanito_priority_gate():
    resources = resources_for({"aladdin": "ZTM"})
    state = _state_with_aladdin_bag(resources)
    bag_item = state.G.triggeredAbilities.bag.items[0]

    validation = validate_resolve_bag(state, bag_id=bag_item.id, player_id="p1")

    assert not validation.valid
    assert validation.errorCode == "RESOLVE_BAG_WRONG_PLAYER"
