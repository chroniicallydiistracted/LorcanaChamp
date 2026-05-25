from __future__ import annotations

from dataclasses import dataclass

from .commands import CommandEnvelope, MoveInput
from .context import RuntimeActorRole, build_validation_context
from .ids import PlayerId
from .results import RuntimeValidationResult
from .state import MatchState
from .static_resources import MatchStaticResources
from lorcana_engine_v2.flow.runtime_flow import get_flow_disallow_reason, is_move_allowed_by_flow


@dataclass(frozen=True, slots=True)
class ValidatedCommand:
    valid: bool
    reason: str | None = None
    code: str | None = None
    moveDef: object | None = None
    actingPlayerId: PlayerId | None = None


def can_player_take_actions(state: MatchState, player_id: PlayerId | str) -> bool:
    return state.ctx.priority.windowOpen and state.ctx.priority.holder == PlayerId(str(player_id))


def _move_flag(move_def: object, name: str, default: bool = False) -> bool:
    return bool(getattr(move_def, name, default))


def _run_move_validation(move_def: object, context) -> RuntimeValidationResult:
    validate = getattr(move_def, "validate", None)
    if validate is None:
        return RuntimeValidationResult.ok()
    result = validate(context)
    if isinstance(result, RuntimeValidationResult):
        return result
    if result is True or result is None:
        return RuntimeValidationResult.ok()
    if result is False:
        return RuntimeValidationResult.fail("Move validation failed", "VALIDATION_FAILED")
    return result


def validate_command(
    command: CommandEnvelope,
    player_id: PlayerId | str,
    prev_state_id: int,
    *,
    state: MatchState,
    config,
    static_resources: MatchStaticResources,
    actor_role: RuntimeActorRole,
    game_ended: bool,
    current_state_id: int,
) -> ValidatedCommand:
    command_input = command.input
    if command_input is None:
        return ValidatedCommand(False, "Move input was not provided", "MISSING_INPUT")

    if prev_state_id != current_state_id:
        return ValidatedCommand(False, "State ID mismatch - client state is stale", "STALE_STATE")

    if game_ended or state.ctx.status.gameEnded:
        return ValidatedCommand(False, "Game has already ended", "GAME_ENDED")

    move_def = config.moves.get(command.move)
    if move_def is None:
        return ValidatedCommand(False, f"Move '{command.move}' not found", "MOVE_NOT_FOUND")

    if _move_flag(move_def, "serverOnly") and actor_role == "player":
        return ValidatedCommand(False, f"Move '{command.move}' is server-only", "SERVER_ONLY")

    if not is_move_allowed_by_flow(
        config.flow,
        state.ctx.status.phase,
        command.move,
        state.ctx.status.gameSegment,
    ):
        return ValidatedCommand(
            False,
            get_flow_disallow_reason(config.flow, state.ctx.status.phase, command.move, state.ctx.status.gameSegment),
            "FLOW_DISALLOWED",
        )

    actor = PlayerId(str(player_id)) if actor_role == "player" else state.ctx.priority.holder
    if actor is None and state.ctx.playerIds:
        actor = state.ctx.playerIds[0]

    if not _move_flag(move_def, "serverOnly"):
        if actor is None:
            return ValidatedCommand(False, "Non-server-only moves require an explicit acting player", "ACTING_PLAYER_REQUIRED")
        if not _move_flag(move_def, "ignorePriority") and not can_player_take_actions(state, actor):
            return ValidatedCommand(False, f"Player '{actor}' does not currently have priority", "NOT_PRIORITY_HOLDER")

    validation = _run_move_validation(
        move_def,
        build_validation_context(
            state=state,
            player_id=actor or PlayerId(str(player_id)),
            input=command_input if isinstance(command_input, MoveInput) else MoveInput(),
            config=config,
            static_resources=static_resources,
            game_ended=game_ended,
            validation_mode="final",
        ),
    )
    if not validation.valid:
        return ValidatedCommand(
            False,
            validation.error or "Move validation failed",
            validation.errorCode or "VALIDATION_FAILED",
        )

    return ValidatedCommand(True, moveDef=move_def, actingPlayerId=actor or PlayerId(str(player_id)))
