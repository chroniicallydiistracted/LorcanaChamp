from dataclasses import replace

from lorcana_engine_v2.core.bootstrap import initialize_match_state_from_static_resources
from lorcana_engine_v2.core.commands import CommandEnvelope, MoveInput, REDACTED_MOVE_INPUT, sanitize_command
from lorcana_engine_v2.core.ids import PlayerId
from lorcana_engine_v2.core.runtime import MatchRuntime
from lorcana_engine_v2.core.state import MatchState
from lorcana_engine_v2.flow.runtime_flow_config import lorcana_runtime_flow
from lorcana_engine_v2.moves import PUT_CARD_INTO_INKWELL
from lorcana_engine_v2.runtime_game.definition import lorcana_runtime_config

from .helpers import resources_for


def _main_phase_state(state: MatchState) -> MatchState:
    return MatchState(
        G=state.G,
        ctx=state.ctx.with_updates(
            status=state.ctx.status.with_updates(gameSegment="mainGame", phase="main", turn=1),
            priority=state.ctx.priority.with_updates(holder=PlayerId("p0"), windowOpen=True),
        ),
    )


def test_command_envelope_and_move_input_match_lorcanito_shape():
    command = CommandEnvelope(
        commandID="cmd-1",
        move="putCardIntoInkwell",
        input=MoveInput(args={"cardId": "c1"}),
        optimisticHint=True,
        redactInput=True,
    )

    assert command.commandID == "cmd-1"
    assert command.move == "putCardIntoInkwell"
    assert command.input.args == {"cardId": "c1"}
    assert sanitize_command(command).input == REDACTED_MOVE_INPUT


def test_missing_input_returns_lorcanito_missing_input_failure_without_state_change():
    resources = resources_for({"c1": "XGm"})
    state = _main_phase_state(initialize_match_state_from_static_resources(resources))
    runtime = MatchRuntime(resources)
    runtime.load_state(state)

    result = runtime.process_command(
        CommandEnvelope(commandID="cmd-missing-input", move=PUT_CARD_INTO_INKWELL),
        "p0",
        actor_role="player",
    )

    assert result.success is False
    assert result.error == "Move input was not provided"
    assert result.errorCode == "MISSING_INPUT"
    assert result.currentStateID == state.ctx._stateID
    assert runtime.get_state() == state


def test_stale_state_returns_lorcanito_stale_state_failure_without_state_change():
    resources = resources_for({"c1": "XGm"})
    state = _main_phase_state(initialize_match_state_from_static_resources(resources))
    runtime = MatchRuntime(resources)
    runtime.load_state(state)

    result = runtime.process_command(
        CommandEnvelope(
            commandID="cmd-stale",
            move=PUT_CARD_INTO_INKWELL,
            input=MoveInput(args={"cardId": "c1"}),
        ),
        "p0",
        prev_state_id=state.ctx._stateID + 1,
        actor_role="player",
    )

    assert result.success is False
    assert result.error == "State ID mismatch - client state is stale"
    assert result.errorCode == "STALE_STATE"
    assert runtime.get_state() == state


def test_unknown_move_returns_lorcanito_move_not_found():
    resources = resources_for({})
    state = _main_phase_state(initialize_match_state_from_static_resources(resources))
    runtime = MatchRuntime(resources)
    runtime.load_state(state)

    result = runtime.process_command(
        CommandEnvelope(commandID="cmd-unknown", move="unknownMove", input=MoveInput(args={})),
        "p0",
        actor_role="player",
    )

    assert result.success is False
    assert result.error == "Move 'unknownMove' not found"
    assert result.errorCode == "MOVE_NOT_FOUND"


def test_flow_disallowed_returns_lorcanito_flow_disallowed_before_priority_validation():
    resources = resources_for({"c1": "XGm"})
    state = initialize_match_state_from_static_resources(resources)
    runtime = MatchRuntime(resources)
    runtime.load_state(state)

    result = runtime.process_command(
        CommandEnvelope(
            commandID="cmd-flow",
            move=PUT_CARD_INTO_INKWELL,
            input=MoveInput(args={"cardId": "c1"}),
        ),
        "p0",
        actor_role="player",
    )

    assert state.ctx.status.gameSegment == lorcana_runtime_flow.initialGameSegment
    assert result.success is False
    assert result.error == "Move 'putCardIntoInkwell' is not legal in phase 'chooseFirstPlayer'"
    assert result.errorCode == "FLOW_DISALLOWED"


def test_server_only_player_command_returns_lorcanito_server_only_before_flow_validation():
    class ServerOnlyMove:
        serverOnly = True
        ignorePriority = False
        ignoreStaleStateID = False

        def execute(self, context):
            return context.state

    resources = resources_for({})
    state = _main_phase_state(initialize_match_state_from_static_resources(resources))
    runtime = MatchRuntime(
        resources,
        config=replace(lorcana_runtime_config, moves={"serverOnlyMove": ServerOnlyMove()}),
    )
    runtime.load_state(state)

    result = runtime.process_command(
        CommandEnvelope(commandID="cmd-server", move="serverOnlyMove", input=MoveInput(args={})),
        "p0",
        actor_role="player",
    )

    assert result.success is False
    assert result.error == "Move 'serverOnlyMove' is server-only"
    assert result.errorCode == "SERVER_ONLY"
