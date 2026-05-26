from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from lorcana_engine_v2.core.ids import PlayerId
from lorcana_engine_v2.core.results import RuntimeValidationResult
from lorcana_engine_v2.core.state import MatchState


@dataclass(frozen=True, slots=True)
class RuntimeIdentity:
    turnOwnerId: PlayerId | None
    priorityHolderId: PlayerId | None
    pendingChoicePlayerId: PlayerId | None


def _status_of(value: MatchState | object):
    if isinstance(value, MatchState):
        return value.ctx.status
    ctx = getattr(value, "ctx", None)
    if ctx is not None and hasattr(ctx, "status"):
        return ctx.status
    status = getattr(value, "status", None)
    if status is not None:
        return status
    framework = getattr(value, "framework", None)
    framework_state = getattr(framework, "state", None)
    return getattr(framework_state, "status", None)


def _priority_of(value: MatchState | object):
    if isinstance(value, MatchState):
        return value.ctx.priority
    ctx = getattr(value, "ctx", None)
    if ctx is not None and hasattr(ctx, "priority"):
        return ctx.priority
    priority = getattr(value, "priority", None)
    if priority is not None:
        return priority
    framework = getattr(value, "framework", None)
    framework_state = getattr(framework, "state", None)
    return getattr(framework_state, "priority", None)


def _player_ids_of(value: MatchState | object) -> tuple[PlayerId, ...]:
    if isinstance(value, MatchState):
        return tuple(value.ctx.playerIds)
    ctx = getattr(value, "ctx", None)
    if ctx is not None and hasattr(ctx, "playerIds"):
        return tuple(PlayerId(str(item)) for item in ctx.playerIds)
    raw = getattr(value, "playerIds", None)
    if raw is not None:
        return tuple(PlayerId(str(item)) for item in raw)
    framework = getattr(value, "framework", None)
    framework_state = getattr(framework, "state", None)
    raw = getattr(framework_state, "playerIds", None)
    if raw is not None:
        return tuple(PlayerId(str(item)) for item in raw)
    return ()


def _game_state_of(value: MatchState | object, explicit_g: object | None = None):
    if explicit_g is not None:
        return explicit_g
    if isinstance(value, MatchState):
        return value.G
    raw = getattr(value, "G", None)
    if raw is not None:
        return raw
    state = getattr(value, "state", None)
    if isinstance(state, MatchState):
        return state.G
    return None


def _player_id_or_none(value: object | None) -> PlayerId | None:
    if value is None:
        return None
    text = str(value)
    return PlayerId(text) if text else None


def resolve_turn_owner_id(state_or_ctx: MatchState | object, G: object | None = None) -> PlayerId | None:
    """Canonical Lorcanito turn-owner resolver.

    Mirrors Lorcanito:
      1. status.turnOwnerId
      2. status.otp + G.turnsCompletedByPlayer rotation
      3. priority.holder only when OTP is unavailable
    """

    status = _status_of(state_or_ctx)
    priority = _priority_of(state_or_ctx)
    player_ids = _player_ids_of(state_or_ctx)
    game_state = _game_state_of(state_or_ctx, G)

    explicit_turn_owner = _player_id_or_none(getattr(status, "turnOwnerId", None))
    if explicit_turn_owner is not None:
        return explicit_turn_owner

    otp = _player_id_or_none(getattr(status, "otp", None))
    if otp is None:
        return _player_id_or_none(getattr(priority, "holder", None))

    if not player_ids:
        return otp

    turns_completed = getattr(game_state, "turnsCompletedByPlayer", None)
    if turns_completed is None:
        turns_completed = {}
    if isinstance(turns_completed, Mapping):
        total_completed_turns = sum(int(value or 0) for value in turns_completed.values())
    else:
        total_completed_turns = 0

    if total_completed_turns == 0:
        return otp

    try:
        otp_index = player_ids.index(otp)
    except ValueError:
        return otp

    offset = total_completed_turns % len(player_ids)
    return player_ids[(otp_index + offset) % len(player_ids)]


def resolve_priority_holder_id(state_or_ctx: MatchState | object) -> PlayerId | None:
    priority = _priority_of(state_or_ctx)
    return _player_id_or_none(getattr(priority, "holder", None))


def resolve_pending_choice_player_id(state_or_ctx: MatchState | object) -> PlayerId | None:
    priority = _priority_of(state_or_ctx)
    pending_choice = getattr(priority, "pendingChoice", None)
    if pending_choice is None:
        return None
    return _player_id_or_none(getattr(pending_choice, "playerID", None))


def resolve_runtime_identity(state_or_ctx: MatchState | object, G: object | None = None) -> RuntimeIdentity:
    return RuntimeIdentity(
        turnOwnerId=resolve_turn_owner_id(state_or_ctx, G),
        priorityHolderId=resolve_priority_holder_id(state_or_ctx),
        pendingChoicePlayerId=resolve_pending_choice_player_id(state_or_ctx),
    )


def resolve_current_player_for_move(state_or_ctx: MatchState | object, G: object | None = None) -> PlayerId | None:
    """Alias for the turn owner.

    This function intentionally does not fall back to the acting player. A missing
    turn owner is malformed runtime state, not permission for the actor to become
    the current player.
    """

    return resolve_turn_owner_id(state_or_ctx, G)


def is_turn_owner(state_or_ctx: MatchState | object, player_id: PlayerId | str, G: object | None = None) -> bool:
    return resolve_turn_owner_id(state_or_ctx, G) == PlayerId(str(player_id))


def is_priority_holder(state_or_ctx: MatchState | object, player_id: PlayerId | str) -> bool:
    return resolve_priority_holder_id(state_or_ctx) == PlayerId(str(player_id))


def require_current_player_for_move(
    state_or_ctx: MatchState | object,
    actor: PlayerId | str,
    G: object | None = None,
) -> RuntimeValidationResult:
    current_player = resolve_current_player_for_move(state_or_ctx, G)
    actor_id = PlayerId(str(actor))
    if current_player is None:
        return RuntimeValidationResult.fail(
            "Current turn player could not be resolved",
            "CURRENT_PLAYER_NOT_RESOLVED",
        )
    if current_player != actor_id:
        return RuntimeValidationResult.fail(
            "Only the current turn player may perform this move",
            "NOT_CURRENT_PLAYER",
        )
    return RuntimeValidationResult.ok()


def require_priority_holder(
    state_or_ctx: MatchState | object,
    actor: PlayerId | str,
) -> RuntimeValidationResult:
    holder = resolve_priority_holder_id(state_or_ctx)
    actor_id = PlayerId(str(actor))
    if holder is None:
        return RuntimeValidationResult.fail(
            "Priority holder could not be resolved",
            "PRIORITY_HOLDER_NOT_RESOLVED",
        )
    if holder != actor_id:
        return RuntimeValidationResult.fail(
            f"Player '{actor_id}' does not currently have priority",
            "NOT_PRIORITY_HOLDER",
        )
    return RuntimeValidationResult.ok()


__all__ = [
    "RuntimeIdentity",
    "is_priority_holder",
    "is_turn_owner",
    "require_current_player_for_move",
    "require_priority_holder",
    "resolve_current_player_for_move",
    "resolve_pending_choice_player_id",
    "resolve_priority_holder_id",
    "resolve_runtime_identity",
    "resolve_turn_owner_id",
]