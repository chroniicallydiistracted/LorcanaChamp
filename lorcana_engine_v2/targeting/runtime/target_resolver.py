from __future__ import annotations

from collections.abc import Mapping, Sequence

from lorcana_engine_v2.core.turn_owner import resolve_turn_owner_id
from lorcana_engine_v2.core.ids import InstanceId, PlayerId
from lorcana_engine_v2.core.state import MatchState
from lorcana_engine_v2.core.zones import base_zone_from_key
from lorcana_engine_v2.rules.target_resolver import (
    TargetQueryContext,
    TargetResolver,
    normalize_target_descriptor,
)


def _state(context: MatchState | object) -> MatchState:
    if isinstance(context, MatchState):
        return context
    state = getattr(context, "state", None)
    if isinstance(state, MatchState):
        return state
    getter = getattr(getattr(context, "cards", None), "_state_getter", None)
    if callable(getter):
        found = getter()
        if isinstance(found, MatchState):
            return found
    raise TypeError("target resolver requires MatchState or runtime context")


def _rules_context(context: object):
    query = getattr(getattr(context, "cards", None), "_query", None)
    if query is None:
        query = getattr(context, "query", None)
    return type("TargetRuntimeContext", (), {"query": query})()


def resolve_candidate_targets(
    context: MatchState | object,
    card_played: Mapping[str, object] | None,
    target: object,
    selected_targets: object | None = None,
    event_snapshot: Mapping[str, object] | None = None,
) -> tuple[InstanceId, ...]:
    state = _state(context)
    controller = PlayerId(str((card_played or {}).get("playerId") or getattr(context, "playerId", state.ctx.priority.holder or state.ctx.playerIds[0])))
    source_id = (card_played or {}).get("cardId")
    return TargetResolver().resolve(
        state,
        _rules_context(context),
        target,
        TargetQueryContext(
            actor=controller,
            source_id=InstanceId(str(source_id)) if source_id is not None else None,
            event_payload=event_snapshot,
            strict_unknown_filters=False,
        ),
    )


def _is_player_target_descriptor(target: object) -> bool:
    if isinstance(target, str):
        return target.upper() in {"CHOSEN_PLAYER", "ANY_PLAYER", "EACH_PLAYER", "ALL_PLAYERS", "OPPONENT", "OPPONENTS", "EACH_OPPONENT", "CONTROLLER", "SELF", "YOU"}
    return isinstance(target, Mapping) and target.get("selector") == "chosen-player"


def resolve_effect_targets(
    context: MatchState | object,
    card_played: Mapping[str, object] | None,
    target: object,
    selected_targets: object | None = None,
    event_snapshot: Mapping[str, object] | None = None,
) -> tuple[InstanceId, ...]:
    selected = _normalize_card_targets(selected_targets)
    return selected or resolve_candidate_targets(context, card_played, target, selected_targets, event_snapshot)


def resolve_target_player_ids(
    context: MatchState | object,
    card_played: Mapping[str, object] | None,
    target: object,
    selected_player_ids: object | None = None,
) -> tuple[PlayerId, ...]:
    state = _state(context)
    selected = tuple(PlayerId(str(item)) for item in _normalize_string_targets(selected_player_ids) if PlayerId(str(item)) in state.ctx.playerIds)
    if selected:
        return selected
    controller = PlayerId(str((card_played or {}).get("playerId") or state.ctx.priority.holder or state.ctx.playerIds[0]))
    normalized = str(target or "CONTROLLER").upper()
    if normalized == "CHOSEN_PLAYER":
        return state.ctx.playerIds
    if normalized in {"SELF", "YOU", "CONTROLLER", "CARD_OWNER"}:
        return (controller,)
    if normalized == "OPPONENT":
        return tuple(player for player in state.ctx.playerIds if player != controller)[:1]
    if normalized in {"OPPONENTS", "EACH_OPPONENT"}:
        return tuple(player for player in state.ctx.playerIds if player != controller)
    if normalized in {"ALL_PLAYERS", "EACH_PLAYER", "ANY_PLAYER"}:
        return state.ctx.playerIds
    if normalized == "CURRENT_TURN":
        return (resolve_turn_owner_id(state) or controller,)
    return ()


def target_allows_player_selection(target: object) -> bool:
    return _is_player_target_descriptor(target)


def _normalize_string_targets(value: object | None) -> tuple[str, ...]:
    if isinstance(value, str):
        return (value,) if value else ()
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return tuple(str(item) for item in value if isinstance(item, str) and item)
    return ()


def _normalize_card_targets(value: object | None) -> tuple[InstanceId, ...]:
    return tuple(InstanceId(item) for item in _normalize_string_targets(value))


normalizeTargetDescriptor = normalize_target_descriptor
resolveCandidateTargets = resolve_candidate_targets
resolveEffectTargets = resolve_effect_targets
resolveTargetPlayerIds = resolve_target_player_ids


__all__ = [
    "normalizeTargetDescriptor",
    "normalize_target_descriptor",
    "resolveCandidateTargets",
    "resolveEffectTargets",
    "resolveTargetPlayerIds",
    "resolve_candidate_targets",
    "resolve_effect_targets",
    "resolve_target_player_ids",
    "target_allows_player_selection",
]
