from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace

from lorcana_engine_v2.core.ids import PlayerId
from lorcana_engine_v2.core.results import RuntimeValidationResult
from lorcana_engine_v2.core.state import MatchState
from lorcana_engine_v2.effects.triggered_abilities import (
    BagItem,
    can_resolve_bag_effect_by_restrictions,
    flush_triggered_events_to_bag,
    get_next_bag_resolver,
    record_bag_effect_resolution,
    remove_bag_effect,
    set_last_bag_resolver,
)
from lorcana_engine_v2.resolution.action_effect_types import PendingResolutionResult
from lorcana_engine_v2.resolution.action_effects import resolve_action_effect
from lorcana_engine_v2.resolution.pending import _state_of, _write_state


def _find_bag_item(state: MatchState, bag_id: str) -> BagItem | None:
    return next(
        (item for item in state.G.triggeredAbilities.bag.items if isinstance(item, BagItem) and item.id == bag_id),
        None,
    )


def validate_resolve_bag(
    state_or_context: MatchState | object,
    *,
    bag_id: str,
    player_id: PlayerId | str,
) -> RuntimeValidationResult:
    state = _state_of(state_or_context)
    if not bag_id:
        return RuntimeValidationResult.fail("resolveBag requires a valid bag id", "RESOLVE_BAG_ID_REQUIRED")
    bag_item = _find_bag_item(state, bag_id)
    if bag_item is None:
        return RuntimeValidationResult.fail("Bag effect was not found", "RESOLVE_BAG_NOT_FOUND")
    resolver = get_next_bag_resolver(state)
    if resolver != PlayerId(str(player_id)) or bag_item.controllerId != resolver:
        return RuntimeValidationResult.fail("Only the active bag resolver may choose this effect", "RESOLVE_BAG_WRONG_PLAYER")
    return RuntimeValidationResult.ok()


def resolve_bag(
    target: MatchState | object,
    *,
    bag_id: str,
    player_id: PlayerId | str | None = None,
    params: Mapping[str, object] | None = None,
    resources: object | None = None,
) -> PendingResolutionResult:
    state = _state_of(target)
    bag_item = _find_bag_item(state, bag_id)
    if bag_item is None:
        return PendingResolutionResult(status="not-found", state=state)

    if player_id is not None:
        validation = validate_resolve_bag(state, bag_id=bag_id, player_id=player_id)
        if not validation.valid:
            return PendingResolutionResult(status="invalid", state=state, bagItem=bag_item)

    state = set_last_bag_resolver(state, bag_item.controllerId)

    if not can_resolve_bag_effect_by_restrictions(state, bag_item):
        state, _ = remove_bag_effect(state, bag_id)
        state = flush_triggered_events_to_bag(state, resources=resources)
        return PendingResolutionResult(status="cancelled", state=_write_state(target, state), bagItem=bag_item)

    resolution_input = bag_item.resolutionInput.merge(params)
    result = resolve_action_effect(
        state,
        bag_item.cardPlayed,
        bag_item.effect,
        resolution_input,
        {"sourceAbilityIndex": bag_item.abilityIndex} if bag_item.abilityIndex is not None else None,
    )
    next_state = result.state if isinstance(result.state, MatchState) else state

    if result.status == "suspended":
        next_state, _ = remove_bag_effect(next_state, bag_id)
        return replace(result, state=_write_state(target, next_state), bagItem=bag_item)

    next_state = record_bag_effect_resolution(next_state, bag_item)
    next_state, _ = remove_bag_effect(next_state, bag_id)
    next_state = flush_triggered_events_to_bag(next_state, resources=resources)
    return PendingResolutionResult(
        status="resolved",
        state=_write_state(target, next_state),
        bagItem=bag_item,
        resolutionInput=resolution_input,
    )


class BagService:
    validate = staticmethod(validate_resolve_bag)
    resolve = staticmethod(resolve_bag)
    next_resolver = staticmethod(get_next_bag_resolver)


__all__ = [
    "BagItem",
    "BagService",
    "resolve_bag",
    "validate_resolve_bag",
]
