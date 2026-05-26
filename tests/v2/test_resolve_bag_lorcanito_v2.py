from dataclasses import replace

from lorcana_engine_v2.core.ids import InstanceId, PlayerId
from lorcana_engine_v2.core.state import MatchState
from lorcana_engine_v2.core.zones import move_card_to_zone, scoped_zone
from lorcana_engine_v2.effects.triggered_abilities import flush_triggered_events_to_bag, record_event
from lorcana_engine_v2.resolution.action_effect_types import BagItem
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


def _state_with_bag_item(resources, bag_item):
    state = state_with_play(resources, p0=("source",), p1=("target",))
    state = MatchState(
        G=state.G,
        ctx=state.ctx.with_updates(
            status=state.ctx.status.with_updates(turn=1, turnOwnerId=PlayerId("p0")),
            priority=state.ctx.priority.with_updates(holder=PlayerId("p0")),
        ),
    )
    bag = replace(state.G.triggeredAbilities.bag, items=(bag_item,), nextSeq=2)
    triggered = replace(state.G.triggeredAbilities, bag=bag)
    return MatchState(G=state.G.with_updates(triggeredAbilities=triggered), ctx=state.ctx)


def test_resolve_bag_direct_discard_chooser_exception_allows_targeted_player():
    resources = resources_for(
        {"source": "ZTM", "target": "Y1z", "card": "Y1z"},
        owners={"p0": ("source",), "p1": ("target", "card")},
    )
    bag_item = BagItem.create(
        id="bag:direct-discard",
        abilityId="direct-discard",
        abilityKey="1:source:direct-discard",
        controllerId="p0",
        sourceId="source",
        cardPlayed={"playerId": PlayerId("p0"), "cardId": InstanceId("source"), "cardType": "character"},
        trigger={"event": "play"},
        effect={"type": "discard", "target": "OPPONENT", "from": "hand", "amount": 1, "chosen": True},
        occurrenceIndex=1,
    )
    state = _state_with_bag_item(resources, bag_item)
    zones = move_card_to_zone(state.ctx.zones, card_id="card", destination_zone_key=scoped_zone("hand", "p1"))
    state = MatchState(G=state.G, ctx=state.ctx.with_updates(zones=zones))

    validation = validate_resolve_bag(state, bag_id=bag_item.id, player_id="p1", params={"targets": ["card"]})
    result = resolve_bag(state, bag_id=bag_item.id, player_id="p1", params={"targets": ["card"]})

    assert validation.valid
    assert result.status == "resolved"
    assert InstanceId("card") in result.state.ctx.zones.private.zoneCards[scoped_zone("discard", "p1")]
    assert result.state.G.triggeredAbilities.bag.items == ()


def test_resolve_bag_partial_choice_input_updates_bag_without_resolving():
    resources = resources_for({"source": "ZTM", "target": "Y1z"}, owners={"p0": ("source",), "p1": ("target",)})
    bag_item = BagItem.create(
        id="bag:choice",
        abilityId="choice",
        abilityKey="1:source:choice",
        controllerId="p0",
        sourceId="source",
        cardPlayed={"playerId": PlayerId("p0"), "cardId": InstanceId("source"), "cardType": "character"},
        trigger={"event": "play"},
        effect={
            "type": "choice",
            "options": [
                {"type": "gain-lore", "target": "CONTROLLER", "amount": 1},
                {"type": "banish", "target": "CHOSEN_CHARACTER"},
            ],
        },
        occurrenceIndex=1,
    )
    state = _state_with_bag_item(resources, bag_item)

    result = resolve_bag(state, bag_id=bag_item.id, player_id="p0", params={"choiceIndex": 1})

    assert result.status == "pending"
    stored = result.state.G.triggeredAbilities.bag.items[0]
    assert stored.id == bag_item.id
    assert stored.resolutionInput.choiceIndex == 1
    assert result.state.G.lore[PlayerId("p0")] == 0
