from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace

from lorcana_engine_v2.core.ids import PlayerId
from lorcana_engine_v2.core.state import MatchState, PlayFromUnderPermissionsState
from lorcana_engine_v2.rules.effect_registry import is_effect_expired
from lorcana_engine_v2.resolution.pending import _state_of, _write_state


@dataclass(frozen=True, slots=True)
class PlayFromUnderPermission:
    sourceItemId: str
    expiresAtTurn: int
    cardType: str | None = None
    controllerId: PlayerId | None = None
    startsAtTurn: int = 1


def _coerce_permission(raw: object) -> PlayFromUnderPermission | None:
    if isinstance(raw, PlayFromUnderPermission):
        return raw
    if not isinstance(raw, Mapping):
        return None
    source = raw.get("sourceItemId") or raw.get("sourceId")
    expires = raw.get("expiresAtTurn")
    if not isinstance(source, str) or not source or not isinstance(expires, int):
        return None
    return PlayFromUnderPermission(
        sourceItemId=source,
        expiresAtTurn=expires,
        cardType=str(raw["cardType"]) if raw.get("cardType") is not None else None,
        controllerId=PlayerId(str(raw["controllerId"])) if raw.get("controllerId") is not None else None,
        startsAtTurn=int(raw.get("startsAtTurn", 1) or 1),
    )


def get_active_play_from_under_permissions(
    state: PlayFromUnderPermissionsState | None,
    player_id: PlayerId | str,
    current_turn: int,
) -> tuple[PlayFromUnderPermission, ...]:
    if state is None:
        return ()
    raw_permissions = state.permissionsByPlayer.get(PlayerId(str(player_id)), ())
    permissions: list[PlayFromUnderPermission] = []
    for raw in raw_permissions:
        permission = _coerce_permission(raw)
        if permission is None:
            continue
        if current_turn < permission.startsAtTurn:
            continue
        if is_effect_expired(permission, current_turn):
            continue
        permissions.append(permission)
    return tuple(permissions)


def add_play_from_under_permission(
    target: MatchState | object,
    player_id: PlayerId | str,
    permission: PlayFromUnderPermission | Mapping[str, object],
) -> MatchState:
    state = _state_of(target)
    normalized = _coerce_permission(permission)
    if normalized is None:
        return state
    player = PlayerId(str(player_id))
    permissions_by_player = {
        PlayerId(str(pid)): tuple(values)
        for pid, values in state.G.playFromUnderPermissions.permissionsByPlayer.items()
    }
    permissions_by_player[player] = permissions_by_player.get(player, ()) + (normalized,)
    next_state = MatchState(
        G=state.G.with_updates(
            playFromUnderPermissions=PlayFromUnderPermissionsState(
                permissionsByPlayer=permissions_by_player,
            )
        ),
        ctx=state.ctx,
    )
    return _write_state(target, next_state)


def prune_expired_play_from_under_permissions(
    target: MatchState | object,
    current_turn: int,
) -> MatchState:
    state = _state_of(target)
    permissions_by_player: dict[PlayerId, tuple[object, ...]] = {}
    for player_id, raw_permissions in state.G.playFromUnderPermissions.permissionsByPlayer.items():
        active = tuple(
            permission
            for permission in (
                _coerce_permission(raw_permission) for raw_permission in raw_permissions
            )
            if permission is not None
            and permission.startsAtTurn <= current_turn
            and not is_effect_expired(permission, current_turn)
        )
        if active:
            permissions_by_player[PlayerId(str(player_id))] = active
    next_state = MatchState(
        G=state.G.with_updates(
            playFromUnderPermissions=replace(
                state.G.playFromUnderPermissions,
                permissionsByPlayer=permissions_by_player,
            )
        ),
        ctx=state.ctx,
    )
    return _write_state(target, next_state)


__all__ = [
    "PlayFromUnderPermission",
    "add_play_from_under_permission",
    "get_active_play_from_under_permissions",
    "prune_expired_play_from_under_permissions",
]
