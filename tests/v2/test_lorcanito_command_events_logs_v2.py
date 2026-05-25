from dataclasses import replace

from lorcana_engine_v2.core.bootstrap import initialize_match_state_from_static_resources
from lorcana_engine_v2.core.commands import CommandEnvelope, MoveInput
from lorcana_engine_v2.core.ids import InstanceId, PlayerId
from lorcana_engine_v2.core.results import LogMessage, LogVisibility, ProjectedLogEntry, RuntimeValidationResult
from lorcana_engine_v2.core.runtime import MatchRuntime
from lorcana_engine_v2.core.runtime_config import (
    RuntimeFlowDefinition,
    RuntimeGameSegment,
    RuntimePhaseDefinition,
    RuntimeTurnDefinition,
)
from lorcana_engine_v2.core.state import MatchState
from lorcana_engine_v2.core.zones import reveal_cards
from lorcana_engine_v2.runtime_game.definition import lorcana_runtime_config

from .helpers import resources_for


class RecordMove:
    serverOnly = False
    ignorePriority = False
    ignoreStaleStateID = False

    def available(self, context):
        return True

    def validate(self, context):
        if context.args.get("reject"):
            return RuntimeValidationResult.fail("Rejected by record move", "RECORD_REJECTED")
        return RuntimeValidationResult.ok()

    def execute(self, context):
        context.framework.status.setStep("recorded")
        context.framework.events.emit({"kind": "CUSTOM_RECORDED", "playerId": context.playerId})
        context.framework.log(
            ProjectedLogEntry(
                category="action",
                visibility=LogVisibility(mode="PUBLIC"),
                defaultMessage=LogMessage(key="test.recorded", values={"playerId": str(context.playerId)}),
            )
        )
        return context.state


class EndGameMove:
    serverOnly = False
    ignorePriority = False
    ignoreStaleStateID = False

    def execute(self, context):
        context.framework.events.endGame({"winner": str(context.playerId), "reason": "test-end"})
        return context.state


def _phase5_flow() -> RuntimeFlowDefinition:
    return RuntimeFlowDefinition(
        initialGameSegment="mainGame",
        gameSegments={
            "mainGame": RuntimeGameSegment(
                id="mainGame",
                name="Main Game",
                order=1,
                turn=RuntimeTurnDefinition(
                    initialPhase="main",
                    phases={
                        "main": RuntimePhaseDefinition(
                            id="main",
                            name="Main",
                            order=1,
                            validMoves=("recordMove", "endGameMove"),
                        )
                    },
                ),
            )
        },
    )


def _runtime_with_phase5_config(resources, state, moves=None) -> MatchRuntime:
    runtime = MatchRuntime(
        resources,
        config=replace(
            lorcana_runtime_config,
            moves=moves or {"recordMove": RecordMove(), "endGameMove": EndGameMove()},
            flow=_phase5_flow(),
        ),
    )
    runtime.load_state(state)
    return runtime


def _main_state(resources) -> MatchState:
    state = initialize_match_state_from_static_resources(resources)
    return MatchState(
        G=state.G,
        ctx=state.ctx.with_updates(
            status=state.ctx.status.with_updates(gameSegment="mainGame", phase="main", turn=1),
            priority=state.ctx.priority.with_updates(holder=PlayerId("p0"), windowOpen=True),
        ),
    )


def test_successful_command_increments_state_id_publishes_move_event_and_logs():
    resources = resources_for({})
    state = _main_state(resources)
    runtime = _runtime_with_phase5_config(resources, state)

    result = runtime.process_command(
        CommandEnvelope(commandID="cmd-record", move="recordMove", input=MoveInput(args={})),
        "p0",
        actor_role="player",
        timestamp=1234,
    )

    assert result.success is True
    assert result.stateID == state.ctx._stateID + 1
    assert result.state.ctx.status.step == "recorded"
    assert result.gameEvents[0].seq == 0
    assert result.gameEvents[0].timestamp == 1234
    assert result.gameEvents[0].stateId == result.stateID
    assert result.gameEvents[0].event.kind == "MOVE_EXECUTED"
    assert result.gameEvents[0].event.commandId == "cmd-record"
    assert result.gameEvents[1].event.kind == "CUSTOM_RECORDED"
    assert result.moveLogs[0].defaultMessage.key == "test.recorded"
    assert runtime.get_published_game_events() == result.gameEvents
    assert runtime.get_move_log_history() == result.moveLogs


def test_failed_move_validation_leaves_old_state_events_and_logs_unchanged():
    resources = resources_for({})
    state = _main_state(resources)
    runtime = _runtime_with_phase5_config(resources, state)

    result = runtime.process_command(
        CommandEnvelope(commandID="cmd-reject", move="recordMove", input=MoveInput(args={"reject": True})),
        "p0",
        actor_role="player",
        timestamp=1234,
    )

    assert result.success is False
    assert result.error == "Rejected by record move"
    assert result.errorCode == "RECORD_REJECTED"
    assert runtime.get_state() == state
    assert runtime.get_published_game_events() == ()
    assert runtime.get_move_log_history() == ()


def test_successful_command_expires_reveals_at_new_state_id():
    resources = resources_for({"c1": "XGm"})
    state = _main_state(resources)
    zones, reveal_id = reveal_cards(
        state.ctx.zones,
        (InstanceId("c1"),),
        "all",
        expires_at_state_id=state.ctx._stateID + 1,
    )
    state = MatchState(G=state.G, ctx=state.ctx.with_updates(zones=zones))
    runtime = _runtime_with_phase5_config(resources, state)

    result = runtime.process_command(
        CommandEnvelope(commandID="cmd-record", move="recordMove", input=MoveInput(args={})),
        "p0",
        actor_role="player",
    )

    assert result.success is True
    assert reveal_id == "reveal-0"
    assert result.state.ctx._stateID == state.ctx._stateID + 1
    assert result.state.ctx.zones.reveals.active == ()


def test_end_game_event_and_runtime_game_end_result_are_recorded():
    resources = resources_for({})
    state = _main_state(resources)
    runtime = _runtime_with_phase5_config(resources, state)

    result = runtime.process_command(
        CommandEnvelope(commandID="cmd-end", move="endGameMove", input=MoveInput(args={})),
        "p0",
        actor_role="player",
    )

    assert result.success is True
    assert result.state.ctx.status.gameEnded is True
    assert result.state.ctx.status.winner == PlayerId("p0")
    assert result.state.ctx.status.reason == "test-end"
    assert result.gameEvents[-1].event.kind == "GAME_ENDED"
    assert runtime.has_game_ended() is True
    assert runtime.get_game_end_result().winner == PlayerId("p0")
