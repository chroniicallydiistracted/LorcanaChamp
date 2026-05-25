from lorcana_engine_v2.core.bootstrap import initialize_match_state_from_static_resources
from lorcana_engine_v2.core.commands import CommandEnvelope, MoveInput
from lorcana_engine_v2.core.ids import InstanceId, PlayerId, ZoneId
from lorcana_engine_v2.core.runtime import MatchRuntime
from lorcana_engine_v2.core.state import MatchState
from lorcana_engine_v2.core.zones import move_card_to_zone, scoped_zone
from lorcana_engine_v2.moves import PUT_CARD_INTO_INKWELL

from .helpers import resources_for


def _interim_main_phase_state(state: MatchState, active: PlayerId = PlayerId("p0")) -> MatchState:
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


def _state_with_hand(resources, *, p0=(), p1=()) -> MatchState:
    state = initialize_match_state_from_static_resources(resources)
    zones = state.ctx.zones
    for card_id in p0:
        zones = move_card_to_zone(
            zones,
            card_id=InstanceId(str(card_id)),
            destination_zone_key=scoped_zone("hand", "p0"),
        )
    for card_id in p1:
        zones = move_card_to_zone(
            zones,
            card_id=InstanceId(str(card_id)),
            destination_zone_key=scoped_zone("hand", "p1"),
        )
    return _interim_main_phase_state(MatchState(G=state.G, ctx=state.ctx.with_updates(zones=zones)))


def _runtime_with_state(resources, state: MatchState) -> MatchRuntime:
    runtime = MatchRuntime(resources)
    runtime.load_state(state)
    return runtime


def _ink_command(card_id: str, command_id: str = "cmd-ink") -> CommandEnvelope:
    return CommandEnvelope(
        commandID=command_id,
        move=PUT_CARD_INTO_INKWELL,
        input=MoveInput(args={"cardId": card_id}),
    )


def test_v2_enumerates_real_inkable_hand_card_as_put_card_into_inkwell_move():
    resources = resources_for({"c1": "XGm"})
    state = _state_with_hand(resources, p0=("c1",))
    runtime = _runtime_with_state(resources, state)

    moves = runtime.enumerate_moves_for_player("p0", actor_role="player")

    assert moves == (PUT_CARD_INTO_INKWELL,)


def test_v2_put_card_into_inkwell_moves_real_card_and_records_turn_metadata():
    resources = resources_for({"c1": "XGm"})
    state = _state_with_hand(resources, p0=("c1",))
    runtime = _runtime_with_state(resources, state)

    result = runtime.process_command(_ink_command("c1"), "p0", actor_role="player", timestamp=1000)

    assert result.success is True
    assert result.stateID == state.ctx._stateID + 1
    assert result.gameEvents[0].event.kind == "MOVE_EXECUTED"
    assert result.gameEvents[0].event.commandId == "cmd-ink"
    assert result.gameEvents[0].event.move == PUT_CARD_INTO_INKWELL
    assert result.moveLogs[0].defaultMessage.key == "lorcana.card.inked"
    assert any(event.event.kind == "card.inked" for event in result.gameEvents)

    next_state = result.state
    assert InstanceId("c1") not in next_state.ctx.zones.private.zoneCards[scoped_zone("hand", "p0")]
    assert InstanceId("c1") in next_state.ctx.zones.private.zoneCards[scoped_zone("inkwell", "p0")]
    assert next_state.ctx.zones.private.cardIndex[InstanceId("c1")].zoneKey == ZoneId("inkwell:p0")
    assert next_state.G.turnMetadata.inkedThisTurn == (InstanceId("c1"),)
    assert next_state.G.turnMetadata.cardsPutIntoInkwellThisTurn == (InstanceId("c1"),)

    meta = next_state.ctx.zones.private.cardMeta[InstanceId("c1")]
    assert meta.state == "ready"
    assert meta.publicFaceState == "faceDown"
    assert next_state.ctx.zones.reveals.active[0].cardIDs == (InstanceId("c1"),)
    assert next_state.ctx.zones.reveals.active[0].visibleTo == "all"


def test_v2_put_card_into_inkwell_rejects_second_ink_same_turn():
    resources = resources_for({"c1": "XGm", "c2": "Y1z"})
    state = _state_with_hand(resources, p0=("c1", "c2"))
    runtime = _runtime_with_state(resources, state)

    first = runtime.process_command(_ink_command("c1", "cmd-first"), "p0", actor_role="player")
    assert first.success is True

    assert runtime.enumerate_moves_for_player("p0", actor_role="player") == ()

    second = runtime.process_command(_ink_command("c2", "cmd-second"), "p0", actor_role="player")
    assert second.success is False
    assert second.error == "Already inked this turn"
    assert second.errorCode == "ALREADY_INKED"
    assert InstanceId("c2") in runtime.get_state().ctx.zones.private.zoneCards[scoped_zone("hand", "p0")]


def test_v2_put_card_into_inkwell_rejects_real_non_inkable_card():
    resources = resources_for({"c1": "5XS"})
    state = _state_with_hand(resources, p0=("c1",))
    runtime = _runtime_with_state(resources, state)

    assert resources.cards.get("5XS").inkable is False
    assert runtime.enumerate_moves_for_player("p0", actor_role="player") == ()

    result = runtime.process_command(_ink_command("c1"), "p0", actor_role="player")
    assert result.success is False
    assert result.error == "Card is not inkable"
    assert result.errorCode == "NOT_INKABLE"
    assert InstanceId("c1") in runtime.get_state().ctx.zones.private.zoneCards[scoped_zone("hand", "p0")]


def test_v2_put_card_into_inkwell_rejects_card_not_in_hand():
    resources = resources_for({"c1": "XGm"})
    state = _interim_main_phase_state(initialize_match_state_from_static_resources(resources))
    runtime = _runtime_with_state(resources, state)

    result = runtime.process_command(_ink_command("c1"), "p0", actor_role="player")

    assert result.success is False
    assert result.error == "Card not in hand"
    assert result.errorCode == "CARD_NOT_IN_HAND"


def test_v2_put_card_into_inkwell_rejects_non_priority_player():
    resources = resources_for(
        {"c1": "XGm", "c2": "Y1z"},
        owners={"p0": ("c1",), "p1": ("c2",)},
    )
    state = _state_with_hand(resources, p1=("c2",))
    runtime = _runtime_with_state(resources, state)

    assert state.ctx.priority.holder == PlayerId("p0")
    assert runtime.enumerate_moves_for_player("p1", actor_role="player") == ()

    result = runtime.process_command(_ink_command("c2"), "p1", actor_role="player")
    assert result.success is False
    assert result.error == "Player 'p1' does not currently have priority"
    assert result.errorCode == "NOT_PRIORITY_HOLDER"


def test_v2_put_card_into_inkwell_requires_lorcanito_move_input_args():
    resources = resources_for({"c1": "XGm"})
    state = _state_with_hand(resources, p0=("c1",))
    runtime = _runtime_with_state(resources, state)

    result = runtime.process_command(
        CommandEnvelope(
            commandID="cmd-missing-card",
            move=PUT_CARD_INTO_INKWELL,
            input=MoveInput(args={}),
        ),
        "p0",
        actor_role="player",
    )

    assert result.success is False
    assert result.error == "Card input was not provided"
    assert result.errorCode == "MISSING_CARD"
