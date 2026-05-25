from lorcana_engine_v2.core.bootstrap import initialize_match_state_from_static_resources
from lorcana_engine_v2.core.commands import CommandEnvelope, MoveInput
from lorcana_engine_v2.core.ids import InstanceId, PlayerId
from lorcana_engine_v2.core.runtime import MatchRuntime
from lorcana_engine_v2.core.state import MatchState
from lorcana_engine_v2.core.zones import move_card_to_zone, scoped_zone
from lorcana_engine_v2.moves.ink import (
    PUT_CARD_INTO_INKWELL,
)
from lorcana_engine_v2.resolution.pending import create_pending_action_effect, enqueue_pending_action_effect

from .helpers import resources_for


def _main_state(state: MatchState, active: PlayerId = PlayerId("p0")) -> MatchState:
    return MatchState(
        G=state.G,
        ctx=state.ctx.with_updates(
            status=state.ctx.status.with_updates(
                turn=1,
                gameSegment="mainGame",
                phase="main",
                turnOwnerId=active,
            ),
            priority=state.ctx.priority.with_updates(
                holder=active,
                windowOpen=True,
                passSequence=(),
                stackDepth=0,
            ),
        ),
    )


def _state_with_zones(resources, *, play=(), hand=(), discard=()) -> MatchState:
    state = initialize_match_state_from_static_resources(resources)
    zones = state.ctx.zones
    for card_id in play:
        zones = move_card_to_zone(
            zones,
            card_id=InstanceId(str(card_id)),
            destination_zone_key=scoped_zone("play", "p0"),
        )
    for card_id in hand:
        zones = move_card_to_zone(
            zones,
            card_id=InstanceId(str(card_id)),
            destination_zone_key=scoped_zone("hand", "p0"),
        )
    for card_id in discard:
        zones = move_card_to_zone(
            zones,
            card_id=InstanceId(str(card_id)),
            destination_zone_key=scoped_zone("discard", "p0"),
        )
    return _main_state(MatchState(G=state.G, ctx=state.ctx.with_updates(zones=zones)))


def _runtime(resources, state: MatchState) -> MatchRuntime:
    runtime = MatchRuntime(resources)
    runtime.load_state(state)
    return runtime


def _ink_command(card_id: str, command_id: str = "cmd-ink") -> CommandEnvelope:
    return CommandEnvelope(
        commandID=command_id,
        move=PUT_CARD_INTO_INKWELL,
        input=MoveInput(args={"cardId": card_id}),
    )


def test_authoritative_ink_rejects_pending_action_effect_before_card_validation():
    resources = resources_for({"source": "XGm", "ink": "Y1z"})
    state = _state_with_zones(resources, hand=("source", "ink"))
    pending = create_pending_action_effect(
        state,
        kind="target-selection",
        sourceCardId="source",
        controllerId="p0",
        chooserId="p0",
        cardPlayed={
            "playerId": PlayerId("p0"),
            "cardId": InstanceId("source"),
            "cardType": "character",
            "costType": "free",
        },
        effect={"type": "draw", "amount": 1},
    )
    state = enqueue_pending_action_effect(state, pending)
    runtime = _runtime(resources, state)

    result = runtime.process_command(_ink_command("ink"), "p0", actor_role="player")

    assert result.success is False
    assert result.errorCode == "EFFECT_PENDING"
    assert result.error == "Cannot ink cards while an action effect is pending"


def test_real_belle_static_additional_inkwell_allows_second_ink_this_turn():
    resources = resources_for({"belle": "6qy", "first": "XGm", "second": "Y1z"})
    state = _state_with_zones(resources, play=("belle",), hand=("first", "second"))
    runtime = _runtime(resources, state)

    first = runtime.process_command(_ink_command("first", "cmd-first"), "p0", actor_role="player")
    assert first.success is True

    assert runtime.enumerate_moves_for_player("p0", actor_role="player") == (PUT_CARD_INTO_INKWELL,)

    second = runtime.process_command(_ink_command("second", "cmd-second"), "p0", actor_role="player")

    assert second.success is True
    assert second.state.G.turnMetadata.inkedThisTurn == (InstanceId("first"), InstanceId("second"))
    assert InstanceId("second") in second.state.ctx.zones.private.zoneCards[scoped_zone("inkwell", "p0")]


def test_real_hidden_inkcaster_grants_hand_inkability_to_non_inkable_card():
    resources = resources_for({"inkcaster": "RqX", "non_inkable": "5XS"})
    state = _state_with_zones(resources, play=("inkcaster",), hand=("non_inkable",))
    runtime = _runtime(resources, state)

    assert resources.cards.get("5XS").inkable is False
    assert runtime.enumerate_moves_for_player("p0", actor_role="player") == (PUT_CARD_INTO_INKWELL,)

    result = runtime.process_command(_ink_command("non_inkable"), "p0", actor_role="player")

    assert result.success is True
    assert InstanceId("non_inkable") in result.state.ctx.zones.private.zoneCards[scoped_zone("inkwell", "p0")]


def test_real_moana_grants_discard_inkability_for_normally_inkable_cards():
    resources = resources_for({"moana": "wRv", "discard_card": "XGm"})
    state = _state_with_zones(resources, play=("moana",), discard=("discard_card",))
    runtime = _runtime(resources, state)

    assert runtime.enumerate_moves_for_player("p0", actor_role="player") == (PUT_CARD_INTO_INKWELL,)

    result = runtime.process_command(_ink_command("discard_card"), "p0", actor_role="player")

    assert result.success is True
    assert InstanceId("discard_card") in result.state.ctx.zones.private.zoneCards[scoped_zone("inkwell", "p0")]
    card_inked_events = [event.event for event in result.gameEvents if event.event.kind == "cardInked"]
    assert card_inked_events[0].payload["from"] == "discard:p0"
    assert card_inked_events[0].payload["to"] == "inkwell:p0"


def test_inking_flushes_real_ink_trigger_to_lorcanito_bag():
    resources = resources_for({"tala": "0Rd", "inked": "XGm"})
    state = _state_with_zones(resources, play=("tala",), hand=("inked",))
    runtime = _runtime(resources, state)

    result = runtime.process_command(_ink_command("inked"), "p0", actor_role="player")

    assert result.success is True
    bag_items = result.state.G.triggeredAbilities.bag.items
    assert len(bag_items) == 1
    assert bag_items[0].sourceId == InstanceId("tala")
    assert bag_items[0].abilityName == "DO YOU KNOW WHO YOU ARE?"
    assert bag_items[0].trigger["event"] == "ink"
    assert result.state.ctx.priority.holder == PlayerId("p0")
