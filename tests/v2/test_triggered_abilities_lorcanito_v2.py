from lorcana_engine_v2.core.ids import InstanceId, PlayerId
from lorcana_engine_v2.effects.triggered_abilities import (
    flush_triggered_events_to_bag,
    get_next_bag_resolver,
    record_event,
)

from .helpers import resources_for, state_with_play


def test_real_play_trigger_buffers_then_flushes_to_lorcanito_bag_item():
    resources = resources_for({"aladdin": "ZTM"})
    state = state_with_play(resources, p0=("aladdin",))
    state = type(state)(
        G=state.G,
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
    assert len(state.G.triggeredAbilities.pendingEvents) == 1

    state = flush_triggered_events_to_bag(state, resources=resources)

    assert state.G.triggeredAbilities.pendingEvents == ()
    assert len(state.G.triggeredAbilities.bag.items) == 1
    bag_item = state.G.triggeredAbilities.bag.items[0]
    assert bag_item.id == "bag:0:1"
    assert bag_item.type == "bag-effect"
    assert bag_item.kind == "triggered-ability"
    assert bag_item.sourceId == InstanceId("aladdin")
    assert bag_item.controllerId == PlayerId("p0")
    assert bag_item.abilityName == "IMPROVISE"
    assert bag_item.trigger["event"] == "play"
    assert bag_item.effect == {"amount": 1, "target": "EACH_OPPONENT", "type": "lose-lore"}
    assert get_next_bag_resolver(state) == PlayerId("p0")
