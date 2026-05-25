from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace

from lorcana_engine_v2.core.ids import InstanceId, PlayerId
from lorcana_engine_v2.core.state import ContinuousEffectState, MatchState
from lorcana_engine_v2.core.zones import base_zone_from_key
from lorcana_engine_v2.rules.effect_registry import is_effect_expired, resolve_effect_window
from lorcana_engine_v2.resolution.pending import _state_of, _write_state


ContinuousEffectStat = str


@dataclass(frozen=True, slots=True)
class StatModifierContinuousEffectInstance:
    id: str
    kind: str
    sourceId: InstanceId
    targetId: InstanceId
    stat: ContinuousEffectStat
    modifier: int
    duration: str
    createdAtTurn: int
    expiresAtTurn: int
    controllerId: PlayerId | None = None
    condition: object | None = None
    nonStacking: bool = False


def _card_in_play(state: MatchState, card_id: InstanceId | str) -> bool:
    entry = state.ctx.zones.private.cardIndex.get(InstanceId(str(card_id)))
    return entry is not None and str(base_zone_from_key(entry.zoneKey)) == "play"


def _rebuild_by_target(
    instances: tuple[object, ...],
) -> dict[InstanceId, tuple[object, ...]]:
    buckets: dict[InstanceId, list[object]] = {}
    for instance in instances:
        if isinstance(instance, StatModifierContinuousEffectInstance):
            buckets.setdefault(instance.targetId, []).append(instance)
    return {target: tuple(entries) for target, entries in buckets.items()}


def add_stat_modifier_effect(
    target: MatchState | object,
    *,
    source_id: InstanceId | str,
    target_id: InstanceId | str,
    stat: ContinuousEffectStat,
    modifier: int,
    duration: str,
    current_turn: int | None = None,
    controller_id: PlayerId | str | None = None,
    condition: object | None = None,
    non_stacking: bool = False,
) -> tuple[MatchState, StatModifierContinuousEffectInstance]:
    state = _state_of(target)
    turn = current_turn if current_turn is not None else (state.ctx.status.turn or 1)
    current = state.G.continuousEffects
    source = InstanceId(str(source_id))
    target_card = InstanceId(str(target_id))
    instances = tuple(current.instances)
    if non_stacking:
        instances = tuple(
            instance
            for instance in instances
            if not (
                isinstance(instance, StatModifierContinuousEffectInstance)
                and instance.sourceId == source
                and instance.targetId == target_card
                and instance.stat == stat
            )
        )
    window = resolve_effect_window(turn, duration)
    created = StatModifierContinuousEffectInstance(
        id=f"ce_{current.nextSeq}",
        kind="stat-modifier",
        sourceId=source,
        targetId=target_card,
        stat=stat,
        modifier=int(modifier),
        duration=duration,
        createdAtTurn=turn,
        expiresAtTurn=window.expiresAtTurn,
        controllerId=PlayerId(str(controller_id)) if controller_id is not None else None,
        condition=condition,
        nonStacking=non_stacking,
    )
    instances = instances + (created,)
    continuous = ContinuousEffectState(
        nextSeq=current.nextSeq + 1,
        instances=instances,
        byTarget=_rebuild_by_target(instances),
    )
    next_state = MatchState(
        G=state.G.with_updates(
            continuousEffects=continuous,
            staticEffectsVersion=state.G.staticEffectsVersion + 1,
        ),
        ctx=state.ctx,
    )
    return _write_state(target, next_state), created


def _effect_active(
    state: MatchState,
    effect: StatModifierContinuousEffectInstance,
    current_turn: int,
) -> bool:
    return (
        _card_in_play(state, effect.targetId)
        and current_turn <= effect.expiresAtTurn
        and (effect.condition is None)
    )


def get_active_stat_modifier_total(
    state_or_context: MatchState | object,
    card_id: InstanceId | str,
    stat: ContinuousEffectStat,
) -> int:
    state = _state_of(state_or_context)
    current_turn = state.ctx.status.turn or 1
    target_id = InstanceId(str(card_id))
    candidates = state.G.continuousEffects.byTarget.get(target_id, ())
    total = 0
    for candidate in candidates:
        if not isinstance(candidate, StatModifierContinuousEffectInstance):
            continue
        if candidate.stat != stat:
            continue
        if not _effect_active(state, candidate, current_turn):
            continue
        total += candidate.modifier
    return total


def cleanup_expired_continuous_effects(
    target: MatchState | object,
    current_turn: int,
) -> MatchState:
    state = _state_of(target)
    instances = tuple(
        instance
        for instance in state.G.continuousEffects.instances
        if not (
            isinstance(instance, StatModifierContinuousEffectInstance)
            and (is_effect_expired(instance, current_turn) or not _card_in_play(state, instance.targetId))
        )
    )
    if instances == tuple(state.G.continuousEffects.instances):
        return state
    continuous = ContinuousEffectState(
        nextSeq=state.G.continuousEffects.nextSeq,
        instances=instances,
        byTarget=_rebuild_by_target(instances),
    )
    next_state = MatchState(
        G=state.G.with_updates(
            continuousEffects=continuous,
            staticEffectsVersion=state.G.staticEffectsVersion + 1,
        ),
        ctx=state.ctx,
    )
    return _write_state(target, next_state)


cleanup_expired_effects = cleanup_expired_continuous_effects


__all__ = [
    "ContinuousEffectState",
    "ContinuousEffectStat",
    "StatModifierContinuousEffectInstance",
    "add_stat_modifier_effect",
    "cleanup_expired_continuous_effects",
    "cleanup_expired_effects",
    "get_active_stat_modifier_total",
]
