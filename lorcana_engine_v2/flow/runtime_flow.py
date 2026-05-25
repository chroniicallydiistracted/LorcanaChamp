from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import replace

from lorcana_engine_v2.core.context import UndoAPI, build_lifecycle_context
from lorcana_engine_v2.core.events import GameEvent
from lorcana_engine_v2.core.results import GameEndResult, ProjectedLogEntry
from lorcana_engine_v2.core.runtime_config import (
    MatchRuntimeConfig,
    RuntimeFlowDefinition,
    RuntimePhaseDefinition,
)
from lorcana_engine_v2.core.state import MatchState
from lorcana_engine_v2.core.static_resources import MatchStaticResources


MoveLogSink = Callable[[ProjectedLogEntry | Iterable[ProjectedLogEntry]], None]
EventSink = Callable[[GameEvent], None]


def get_current_phase_definition(
    flow: RuntimeFlowDefinition | None,
    current_phase_id: str | None,
    current_game_segment_id: str | None = None,
) -> RuntimePhaseDefinition | None:
    if flow is None or current_phase_id is None:
        return None
    segment_id = current_game_segment_id or flow.initialGameSegment
    segment = flow.gameSegments.get(segment_id) if segment_id is not None else None
    if segment is None or segment.turn is None:
        return None
    return segment.turn.phases.get(current_phase_id)


def is_move_allowed_by_flow(
    flow: RuntimeFlowDefinition | None,
    current_phase_id: str | None,
    move_id: str,
    current_game_segment_id: str | None = None,
) -> bool:
    current_phase = get_current_phase_definition(flow, current_phase_id, current_game_segment_id)
    if current_phase is None or not current_phase.validMoves:
        return True
    return move_id in current_phase.validMoves


def get_flow_disallow_reason(
    flow: RuntimeFlowDefinition | None,
    current_phase_id: str | None,
    move_id: str,
    current_game_segment_id: str | None = None,
) -> str:
    current_phase = get_current_phase_definition(flow, current_phase_id, current_game_segment_id)
    if current_phase is None or not current_phase.validMoves:
        return f"Move '{move_id}' is not legal in the current flow state"
    return f"Move '{move_id}' is not legal in phase '{current_phase.id}'"


def _invoke_lifecycle_hook(
    state: MatchState,
    hook: Callable[..., object] | None,
    *,
    config: MatchRuntimeConfig,
    static_resources: MatchStaticResources,
    game_ended: bool,
    emit: EventSink,
    undo: UndoAPI,
    move_log_sink: MoveLogSink,
    player_id: str | None = None,
) -> MatchState:
    if hook is None:
        return state
    lifecycle = build_lifecycle_context(
        state=state,
        player_id=player_id,
        config=config,
        static_resources=static_resources,
        game_ended=game_ended,
        emit=emit,
        undo=undo,
        move_log_sink=move_log_sink,
    )
    returned_state = hook(lifecycle)
    next_state = returned_state if isinstance(returned_state, MatchState) else lifecycle.state
    return MatchState(
        G=next_state.G,
        ctx=next_state.ctx.with_updates(random=lifecycle.framework.random.ctx_random),
    )


def resolve_flow_transitions(
    state: MatchState,
    flow: RuntimeFlowDefinition | None,
    *,
    config: MatchRuntimeConfig,
    static_resources: MatchStaticResources,
    game_ended: bool,
    emit: EventSink,
    undo: UndoAPI,
    move_log_sink: MoveLogSink,
    bootstrap: bool = False,
) -> MatchState:
    if flow is None or not flow.gameSegments:
        return state

    max_transitions = 20
    next_state = state
    resolved_game_ended = game_ended or next_state.ctx.status.gameEnded

    def current_segment_id() -> str | None:
        return next_state.ctx.status.gameSegment or flow.initialGameSegment

    def current_segment(segment_id: str | None):
        return flow.gameSegments.get(segment_id) if segment_id is not None else None

    def current_turn(segment_id: str | None):
        segment = current_segment(segment_id)
        return segment.turn if segment is not None else None

    def current_phase(segment_id: str | None, phase_id: str | None):
        turn = current_turn(segment_id)
        return turn.phases.get(phase_id or "") if turn is not None else None

    def invoke(hook: Callable[..., object] | None, player_id: str | None = None) -> None:
        nonlocal next_state, resolved_game_ended
        resolved_game_ended = resolved_game_ended or next_state.ctx.status.gameEnded
        next_state = _invoke_lifecycle_hook(
            next_state,
            hook,
            config=config,
            static_resources=static_resources,
            game_ended=resolved_game_ended,
            emit=emit,
            undo=undo,
            move_log_sink=move_log_sink,
            player_id=player_id,
        )

    if bootstrap:
        segment_id = current_segment_id()
        segment = current_segment(segment_id)
        turn = current_turn(segment_id)
        phase = current_phase(segment_id, next_state.ctx.status.phase)
        invoke(segment.onEnter if segment is not None else None)
        invoke(turn.onBegin if turn is not None else None)
        invoke(phase.onEnter if phase is not None else None)

    for _ in range(max_transitions):
        segment_id = current_segment_id()
        segment = current_segment(segment_id)
        turn = current_turn(segment_id)
        phase_id = next_state.ctx.status.phase
        phase = current_phase(segment_id, phase_id)

        if phase is None or phase.endIf is None:
            return next_state

        resolved_game_ended = resolved_game_ended or next_state.ctx.status.gameEnded
        should_end = phase.endIf(next_state)
        if not should_end:
            return next_state

        next_phase = phase.nextPhase(next_state) if callable(phase.nextPhase) else phase.nextPhase
        if next_phase:
            invoke(phase.onExit)
            next_state = MatchState(
                G=next_state.G,
                ctx=next_state.ctx.with_updates(status=next_state.ctx.status.with_updates(phase=next_phase)),
            )
            next_phase_def = current_phase(segment_id, next_phase)
            invoke(next_phase_def.onEnter if next_phase_def is not None else None)
            continue

        if segment is not None and segment.next:
            next_segment_id = segment.next
            next_segment = flow.gameSegments.get(next_segment_id)
            next_initial_phase = next_segment.turn.initialPhase if next_segment is not None and next_segment.turn else None
            if next_segment_id and next_initial_phase:
                invoke(phase.onExit)
                invoke(turn.onEnd if turn is not None else None)
                invoke(segment.onExit)
                next_state = MatchState(
                    G=next_state.G,
                    ctx=next_state.ctx.with_updates(
                        status=next_state.ctx.status.with_updates(
                            gameSegment=next_segment_id,
                            phase=next_initial_phase,
                        )
                    ),
                )
                invoke(next_segment.onEnter if next_segment is not None else None)
                invoke(next_segment.turn.onBegin if next_segment is not None and next_segment.turn else None)
                next_phase_def = (
                    next_segment.turn.phases.get(next_initial_phase)
                    if next_segment is not None and next_segment.turn
                    else None
                )
                invoke(next_phase_def.onEnter if next_phase_def is not None else None)
                continue

        return next_state

    raise RuntimeError("Flow transition resolution exceeded the maximum number of transitions")


def check_game_end_condition(
    state: MatchState,
    flow: RuntimeFlowDefinition | None,
) -> GameEndResult | None:
    if flow is None:
        return None
    segment_id = state.ctx.status.gameSegment or flow.initialGameSegment
    segment = flow.gameSegments.get(segment_id) if segment_id is not None else None
    if segment is None or segment.endIf is None:
        return None
    result = segment.endIf(state)
    return result if isinstance(result, GameEndResult) else None


def apply_game_end(state: MatchState, result: GameEndResult) -> MatchState:
    return replace(
        state,
        ctx=state.ctx.with_updates(
            status=state.ctx.status.with_updates(
                gameEnded=True,
                winner=result.winner,
                reason=result.reason,
            )
        ),
    )


__all__ = [
    "apply_game_end",
    "check_game_end_condition",
    "get_current_phase_definition",
    "get_flow_disallow_reason",
    "is_move_allowed_by_flow",
    "resolve_flow_transitions",
]
