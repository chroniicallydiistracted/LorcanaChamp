from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
import time

from .commands import CommandEnvelope
from .context import (
    RuntimeActorRole,
    UndoAPI,
    build_enumeration_context,
    build_execution_context,
    build_rules_context,
)
from .events import GameEvent
from .ids import PlayerId
from .mutator import advance_state_id_and_expire_reveals
from .results import (
    CommandFailure,
    CommandResult,
    CommandSuccess,
    GameEndResult,
    ProjectedLogEntry,
    PublishedGameEvent,
)
from .state import MatchState
from .static_resources import MatchStaticResources
from .validation import can_player_take_actions, validate_command
from lorcana_engine_v2.flow.runtime_flow import (
    apply_game_end,
    check_game_end_condition,
    is_move_allowed_by_flow,
    resolve_flow_transitions,
)


def _default_runtime_config():
    from lorcana_engine_v2.runtime_game.definition import lorcana_runtime_config

    return lorcana_runtime_config


def _move_flag(move_def: object, name: str, default: bool = False) -> bool:
    return bool(getattr(move_def, name, default))


def _append_logs(
    sink: list[ProjectedLogEntry],
    entry: ProjectedLogEntry | Iterable[ProjectedLogEntry],
) -> None:
    if isinstance(entry, ProjectedLogEntry):
        sink.append(entry)
    else:
        sink.extend(entry)


@dataclass(slots=True)
class CommandExecutionContext:
    state: MatchState
    config: object
    staticResources: MatchStaticResources
    actorRole: RuntimeActorRole
    capturePatches: bool
    gameEnded: bool
    currentStateID: int


@dataclass(frozen=True, slots=True)
class InternalCommandSuccess:
    success: bool
    stateID: int
    state: MatchState
    patches: tuple[object, ...]
    inversePatches: tuple[object, ...]
    pendingGameEvents: tuple[GameEvent, ...]
    moveLogEntries: tuple[ProjectedLogEntry, ...]
    undoable: bool


@dataclass(frozen=True, slots=True)
class CommandExecutionResult:
    result: InternalCommandSuccess | CommandFailure
    newState: MatchState
    gameEnded: bool
    gameEndResult: GameEndResult | None = None


def execute_command(
    command: CommandEnvelope,
    player_id: PlayerId | str,
    prev_state_id: int,
    timestamp: int,
    ctx: CommandExecutionContext,
) -> CommandExecutionResult:
    command_input = command.input
    if command_input is None:
        return CommandExecutionResult(
            result=CommandFailure(
                success=False,
                error="Move input was not provided",
                errorCode="MISSING_INPUT",
                currentStateID=ctx.currentStateID,
            ),
            newState=ctx.state,
            gameEnded=ctx.gameEnded,
        )

    validation = validate_command(
        command,
        player_id,
        prev_state_id,
        state=ctx.state,
        config=ctx.config,
        static_resources=ctx.staticResources,
        actor_role=ctx.actorRole,
        game_ended=ctx.gameEnded,
        current_state_id=ctx.currentStateID,
    )
    if not validation.valid:
        return CommandExecutionResult(
            result=CommandFailure(
                success=False,
                error=validation.reason or "Command validation failed",
                errorCode=validation.code or "VALIDATION_FAILED",
                currentStateID=ctx.currentStateID,
            ),
            newState=ctx.state,
            gameEnded=ctx.gameEnded,
        )

    move_def = validation.moveDef
    acting_player_id = validation.actingPlayerId or PlayerId(str(player_id))
    pending_game_events: list[GameEvent] = []
    move_log_entries: list[ProjectedLogEntry] = []
    undo = UndoAPI()

    try:
        execution_context = build_execution_context(
            state=ctx.state,
            player_id=acting_player_id,
            input=command_input,
            config=ctx.config,
            static_resources=ctx.staticResources,
            game_ended=ctx.gameEnded,
            emit=pending_game_events.append,
            undo=undo,
            move_log_sink=lambda entry: _append_logs(move_log_entries, entry),
        )
        execute = getattr(move_def, "execute")
        returned_state = execute(execution_context)
        new_state = returned_state if isinstance(returned_state, MatchState) else execution_context.state
        new_state = MatchState(
            G=new_state.G,
            ctx=new_state.ctx.with_updates(random=execution_context.framework.random.ctx_random),
        )
        new_state = resolve_flow_transitions(
            new_state,
            ctx.config.flow,
            config=ctx.config,
            static_resources=ctx.staticResources,
            game_ended=ctx.gameEnded,
            emit=pending_game_events.append,
            undo=undo,
            move_log_sink=lambda entry: _append_logs(move_log_entries, entry),
        )
        game_end_result = check_game_end_condition(new_state, ctx.config.flow)
        if game_end_result is not None:
            new_state = apply_game_end(new_state, game_end_result)
        new_state = advance_state_id_and_expire_reveals(new_state)

        pending_game_events.insert(
            0,
            GameEvent(
                kind="MOVE_EXECUTED",
                commandId=command.commandID or f"cmd-{timestamp}",
                move=command.move,
                playerId=acting_player_id,
                inputRedacted=bool(command.redactInput),
                input="[REDACTED]" if command.redactInput else command_input,
            ),
        )

        game_ended = new_state.ctx.status.gameEnded
        if game_ended:
            if game_end_result is None:
                game_end_result = GameEndResult(
                    winner=new_state.ctx.status.winner,
                    reason=new_state.ctx.status.reason or "",
                )
            if not any(event.kind == "GAME_ENDED" for event in pending_game_events):
                pending_game_events.append(
                    GameEvent(
                        kind="GAME_ENDED",
                        winner=game_end_result.winner,
                        reason=game_end_result.reason,
                    )
                )

        return CommandExecutionResult(
            result=InternalCommandSuccess(
                success=True,
                stateID=new_state.ctx._stateID,
                state=new_state,
                patches=(),
                inversePatches=(),
                pendingGameEvents=tuple(pending_game_events),
                moveLogEntries=tuple(move_log_entries),
                undoable=not undo.hasBarrier(),
            ),
            newState=new_state,
            gameEnded=game_ended,
            gameEndResult=game_end_result,
        )
    except Exception as error:
        return CommandExecutionResult(
            result=CommandFailure(
                success=False,
                error=str(error) or "Move execution failed",
                errorCode="EXECUTION_ERROR",
                currentStateID=ctx.currentStateID,
            ),
            newState=ctx.state,
            gameEnded=ctx.gameEnded,
        )


@dataclass(slots=True)
class MatchRuntime:
    """Lorcanito-shaped deterministic runtime shell for v2."""

    resources: MatchStaticResources
    config: object = field(default_factory=_default_runtime_config)
    state: MatchState | None = None
    capturePatches: bool = False
    publishedGameEvents: list[PublishedGameEvent] = field(default_factory=list)
    moveLogHistory: list[ProjectedLogEntry] = field(default_factory=list)
    nextGameEventSeq: int = 0
    gameEnded: bool = False
    gameEndResult: GameEndResult | None = None

    def context(self):
        return build_rules_context(self.resources)

    def load_state(self, state: MatchState) -> None:
        self.state = state
        self.gameEnded = state.ctx.status.gameEnded
        self.gameEndResult = (
            GameEndResult(winner=state.ctx.status.winner, reason=state.ctx.status.reason or "")
            if state.ctx.status.gameEnded
            else None
        )
        self.publishedGameEvents.clear()
        self.moveLogHistory.clear()
        self.nextGameEventSeq = 0

    loadState = load_state

    def get_state(self) -> MatchState:
        if self.state is None:
            raise RuntimeError("MatchRuntime has no loaded state")
        return self.state

    getState = get_state

    def get_current_state_id(self) -> int:
        return self.get_state().ctx._stateID

    getCurrentStateID = get_current_state_id

    def has_game_ended(self) -> bool:
        return self.gameEnded

    hasGameEnded = has_game_ended

    def get_game_end_result(self) -> GameEndResult | None:
        return self.gameEndResult

    getGameEndResult = get_game_end_result

    def get_published_game_events(self) -> tuple[PublishedGameEvent, ...]:
        return tuple(self.publishedGameEvents)

    getPublishedGameEvents = get_published_game_events

    def get_move_log_history(self) -> tuple[ProjectedLogEntry, ...]:
        return tuple(self.moveLogHistory)

    getMoveLogHistory = get_move_log_history

    def get_filtered_view(self, role_ctx):
        player_view = getattr(self.config, "playerView", None)
        if player_view is None:
            return self.get_state()
        return player_view(self.get_state(), role_ctx)

    getFilteredView = get_filtered_view

    def _state_for_call(self, state: MatchState | None = None) -> MatchState:
        if state is not None:
            return state
        return self.get_state()

    def enumerate_moves_for_player(
        self,
        player_id: PlayerId | str,
        actor_role: RuntimeActorRole = "player",
        state: MatchState | None = None,
    ) -> tuple[str, ...]:
        current_state = self._state_for_call(state)
        if self.gameEnded or current_state.ctx.status.gameEnded:
            return ()
        context = build_enumeration_context(
            state=current_state,
            player_id=player_id,
            config=self.config,
            static_resources=self.resources,
            game_ended=self.gameEnded,
        )
        legal_moves: list[str] = []
        for move_id, move_def in self.config.moves.items():
            if actor_role == "player" and _move_flag(move_def, "serverOnly"):
                continue
            if not is_move_allowed_by_flow(
                self.config.flow,
                current_state.ctx.status.phase,
                move_id,
                current_state.ctx.status.gameSegment,
            ):
                continue
            if (
                actor_role != "judge"
                and not _move_flag(move_def, "serverOnly")
                and not _move_flag(move_def, "ignorePriority")
                and not can_player_take_actions(current_state, player_id)
            ):
                continue
            available = getattr(move_def, "available", None)
            if available is not None and not available(context):
                continue
            legal_moves.append(str(move_id))
        return tuple(legal_moves)

    enumerateMovesForPlayer = enumerate_moves_for_player

    def enumerate_moves(self, actor_role: RuntimeActorRole = "player") -> tuple[str, ...]:
        state = self.get_state()
        player_id = state.ctx.priority.holder or (state.ctx.playerIds[0] if state.ctx.playerIds else PlayerId("p0"))
        return self.enumerate_moves_for_player(player_id, actor_role=actor_role)

    enumerateMoves = enumerate_moves

    def legal_moves(self, state: MatchState, player: str | PlayerId) -> tuple[str, ...]:
        return self.enumerate_moves_for_player(player, state=state)

    def validate_command(
        self,
        command: CommandEnvelope,
        player_id: PlayerId | str,
        prev_state_id: int | None = None,
        actor_role: RuntimeActorRole = "player",
    ):
        state = self.get_state()
        return validate_command(
            command,
            player_id,
            state.ctx._stateID if prev_state_id is None else prev_state_id,
            state=state,
            config=self.config,
            static_resources=self.resources,
            actor_role=actor_role,
            game_ended=self.gameEnded,
            current_state_id=state.ctx._stateID,
        )

    validateCommand = validate_command

    def publish_game_events(
        self,
        events: tuple[GameEvent, ...],
        state_id: int,
        timestamp: int,
    ) -> tuple[PublishedGameEvent, ...]:
        published: list[PublishedGameEvent] = []
        for event in events:
            published_event = PublishedGameEvent(
                seq=self.nextGameEventSeq,
                timestamp=timestamp,
                stateId=state_id,
                event=event,
            )
            self.nextGameEventSeq += 1
            published.append(published_event)
        return tuple(published)

    publishGameEvents = publish_game_events

    def process_command(
        self,
        command: CommandEnvelope,
        player_id: PlayerId | str,
        prev_state_id: int | None = None,
        timestamp: int | None = None,
        actor_role: RuntimeActorRole = "judge",
    ) -> CommandResult:
        state = self.get_state()
        resolved_prev_state_id = state.ctx._stateID if prev_state_id is None else prev_state_id
        resolved_timestamp = int(time.time() * 1000) if timestamp is None else timestamp
        exec_result = execute_command(
            command,
            player_id,
            resolved_prev_state_id,
            resolved_timestamp,
            CommandExecutionContext(
                state=state,
                config=self.config,
                staticResources=self.resources,
                actorRole=actor_role,
                capturePatches=self.capturePatches,
                gameEnded=self.gameEnded,
                currentStateID=state.ctx._stateID,
            ),
        )
        self.state = exec_result.newState
        if isinstance(exec_result.result, CommandFailure):
            return exec_result.result

        published = self.publish_game_events(
            exec_result.result.pendingGameEvents,
            exec_result.newState.ctx._stateID,
            resolved_timestamp,
        )
        self.publishedGameEvents.extend(published)
        self.moveLogHistory.extend(exec_result.result.moveLogEntries)
        if exec_result.gameEnded:
            self.gameEnded = True
            self.gameEndResult = exec_result.gameEndResult

        return CommandSuccess(
            success=True,
            stateID=exec_result.result.stateID,
            state=exec_result.result.state,
            patches=exec_result.result.patches,
            gameEvents=published,
            processedCommand=command,
            animations=(),
            undoable=exec_result.result.undoable,
            moveLogs=exec_result.result.moveLogEntries,
        )

    processCommand = process_command

    def submit_player_command(
        self,
        command: CommandEnvelope,
        player_id: PlayerId | str,
        prev_state_id: int | None = None,
    ) -> CommandResult:
        return self.process_command(command, player_id, prev_state_id, actor_role="player")

    submitPlayerCommand = submit_player_command


__all__ = [
    "CommandExecutionContext",
    "CommandExecutionResult",
    "InternalCommandSuccess",
    "MatchRuntime",
    "execute_command",
]
