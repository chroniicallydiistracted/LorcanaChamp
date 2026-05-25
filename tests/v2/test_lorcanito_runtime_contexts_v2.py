from lorcana_engine_v2.core.bootstrap import initialize_match_state_from_static_resources
from lorcana_engine_v2.core.commands import MoveInput
from lorcana_engine_v2.core.context import (
    UndoAPI,
    build_enumeration_context,
    build_execution_context,
    build_validation_context,
    create_framework_state_snapshot,
)
from lorcana_engine_v2.core.ids import InstanceId, PlayerId
from lorcana_engine_v2.core.results import LogMessage, LogVisibility, ProjectedLogEntry
from lorcana_engine_v2.core.state import MatchState
from lorcana_engine_v2.core.zones import move_card_to_zone, scoped_zone
from lorcana_engine_v2.runtime_game.definition import lorcana_runtime_config

from .helpers import resources_for


def _state_with_hand(resources) -> MatchState:
    state = initialize_match_state_from_static_resources(resources)
    zones = move_card_to_zone(
        state.ctx.zones,
        card_id=InstanceId("c1"),
        destination_zone_key=scoped_zone("hand", "p0"),
    )
    return MatchState(
        G=state.G,
        ctx=state.ctx.with_updates(
            zones=zones,
            status=state.ctx.status.with_updates(gameSegment="mainGame", phase="main", turn=1),
            priority=state.ctx.priority.with_updates(holder=PlayerId("p0"), windowOpen=True),
        ),
    )


def test_framework_state_snapshot_matches_lorcanito_runtime_shape():
    resources = resources_for({"c1": "XGm"})
    state = _state_with_hand(resources)

    snapshot = create_framework_state_snapshot(state)

    assert snapshot.priority == state.ctx.priority
    assert snapshot.status == state.ctx.status
    assert snapshot._zonesPrivate == state.ctx.zones.private
    assert snapshot._zonesPublic == state.ctx.zones.public
    assert snapshot.playerIds == state.ctx.playerIds
    assert snapshot.turn == 1
    assert snapshot.phase == "main"
    assert snapshot.gameSegment == "mainGame"
    assert snapshot.currentPlayer == PlayerId("p0")
    assert snapshot.stateID == state.ctx._stateID
    assert snapshot.matchID == state.ctx.matchID
    assert snapshot.gameID == state.ctx.gameID
    assert snapshot.gameEnded is False


def test_validation_context_exposes_input_args_params_and_read_apis():
    resources = resources_for({"c1": "XGm"})
    state = _state_with_hand(resources)

    context = build_validation_context(
        state=state,
        player_id="p0",
        input=MoveInput(args={"cardId": "c1"}),
        config=lorcana_runtime_config,
        static_resources=resources,
        validation_mode="final",
    )

    assert context.input.args == {"cardId": "c1"}
    assert context.args == {"cardId": "c1"}
    assert context.params == {"cardId": "c1"}
    assert context.playerId == PlayerId("p0")
    assert context.validationMode == "final"
    assert context.framework.zones.getCards({"zone": "hand", "playerId": "p0"}) == (InstanceId("c1"),)
    assert context.cards.require("c1").definitionId == "XGm"


def test_enumeration_context_omits_move_input_and_uses_read_framework_api():
    resources = resources_for({"c1": "XGm"})
    state = _state_with_hand(resources)

    context = build_enumeration_context(
        state=state,
        player_id="p0",
        config=lorcana_runtime_config,
        static_resources=resources,
    )

    assert not hasattr(context, "input")
    assert context.framework.state.stateID == state.ctx._stateID
    assert context.framework.zones.getCardZone("c1") == scoped_zone("hand", "p0")


def test_execution_context_write_apis_update_draft_state_and_buffer_outputs():
    resources = resources_for({"c1": "XGm"})
    state = _state_with_hand(resources)
    events = []
    logs = []
    undo = UndoAPI()

    context = build_execution_context(
        state=state,
        player_id="p0",
        input=MoveInput(args={"cardId": "c1"}),
        config=lorcana_runtime_config,
        static_resources=resources,
        game_ended=False,
        emit=events.append,
        undo=undo,
        move_log_sink=lambda entry: logs.append(entry),
    )

    context.framework.status.setStep("afterWrite")
    context.framework.priority.closeWindow()
    context.framework.zones.moveCard("c1", {"zone": "inkwell", "playerId": "p0"})
    context.cards.patchMeta("c1", {"state": "ready"})
    context.framework.events.emit({"kind": "CUSTOM_TEST_EVENT", "playerId": "p0"})
    context.framework.log(
        ProjectedLogEntry(
            category="action",
            visibility=LogVisibility(mode="PUBLIC"),
            defaultMessage=LogMessage(key="test.log", values={}),
        )
    )
    context.framework.undo.markBarrier("reveal")

    assert context.state.ctx.status.step == "afterWrite"
    assert context.state.ctx.priority.windowOpen is False
    assert context.state.ctx.zones.private.cardIndex[InstanceId("c1")].zoneKey == scoped_zone("inkwell", "p0")
    assert context.state.ctx.zones.private.cardMeta[InstanceId("c1")].state == "ready"
    assert events[-1].kind == "CUSTOM_TEST_EVENT"
    assert logs[0].defaultMessage.key == "test.log"
    assert undo.hasBarrier() is True
