from __future__ import annotations

from lorcana_engine_v2.core.ids import PlayerId
from lorcana_engine_v2.core.results import RuntimeValidationResult
from lorcana_engine_v2.core.state import MatchState


def _state_of(value: MatchState | object) -> MatchState | None:
    if isinstance(value, MatchState):
        return value
    state = getattr(value, "state", None)
    if isinstance(state, MatchState):
        return state
    framework = getattr(value, "framework", None)
    framework_state = getattr(framework, "state", None)
    if framework_state is not None:
        # Framework snapshots do not carry G, so callers that pass only a move
        # context are handled by the direct `state` branch above. This branch is
        # intentionally not reconstructing MatchState from a snapshot.
        return None
    return None


def resolve_turn_owner_id(state: MatchState | object) -> PlayerId | None:
    match_state = _state_of(state)
    if match_state is not None:
        return match_state.ctx.status.turnOwnerId
    status = getattr(state, "status", None)
    raw = getattr(status, "turnOwnerId", None)
    return PlayerId(str(raw)) if raw is not None else None


def resolve_current_player_for_move(
    state: MatchState | object,
    fallback_actor: PlayerId | str | None = None,
) -> PlayerId | None:
    match_state = _state_of(state)
    if match_state is not None:
        return (
            match_state.ctx.status.turnOwnerId
            or getattr(match_state.ctx, "currentPlayer", None)
            or fallback_actor
        )
    status = getattr(state, "status", None)
    raw = getattr(status, "turnOwnerId", None)
    if raw is None:
        raw = getattr(state, "currentPlayer", None)
    if raw is None:
        raw = fallback_actor
    return PlayerId(str(raw)) if raw is not None else None


def require_current_player_for_move(
    state: MatchState | object,
    actor: PlayerId | str,
) -> RuntimeValidationResult:
    current_player = resolve_current_player_for_move(state, fallback_actor=actor)
    actor_id = PlayerId(str(actor))
    if current_player is None:
        return RuntimeValidationResult.fail("Current turn player could not be resolved", "CURRENT_PLAYER_NOT_RESOLVED")
    if current_player != actor_id:
        return RuntimeValidationResult.fail("Only the current turn player may perform this move", "NOT_CURRENT_PLAYER")
    return RuntimeValidationResult.ok()


__all__ = [
    "require_current_player_for_move",
    "resolve_current_player_for_move",
    "resolve_turn_owner_id",
]
