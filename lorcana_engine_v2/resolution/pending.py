from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import replace
from typing import Any

from lorcana_engine_v2.core.ids import InstanceId, PlayerId, ZoneId
from lorcana_engine_v2.core.results import RuntimeValidationResult
from lorcana_engine_v2.core.state import CtxPriority, MatchState, PendingChoice
from lorcana_engine_v2.core.zones import (
    CardMeta,
    ZoneRuntimePrivateState,
    ZoneRuntimeState,
    base_zone_from_key,
    move_card_to_zone,
    patch_card_meta,
    scoped_zone,
)
from lorcana_engine_v2.resolution.action_effect_types import (
    ActionResolutionInput,
    PendingActionEffect,
    PendingResolutionResult,
)
from lorcana_engine_v2.runtime_game.turn_metrics import (
    is_discard_zone_key,
    record_card_put_into_discard_this_turn,
)


EFFECT_PENDING_ERROR_CODE = "EFFECT_PENDING"


def _state_of(target: MatchState | object) -> MatchState:
    if isinstance(target, MatchState):
        return target
    state = getattr(target, "state", None)
    if isinstance(state, MatchState):
        return state
    draft = getattr(target, "_draft", None)
    draft_state = getattr(draft, "state", None)
    if isinstance(draft_state, MatchState):
        return draft_state
    raise TypeError("Expected MatchState or runtime context with state")


def _write_state(target: MatchState | object, state: MatchState) -> MatchState:
    if isinstance(target, MatchState):
        return state
    draft = getattr(target, "_draft", None)
    if draft is not None and hasattr(draft, "set_state"):
        draft.set_state(state)
    elif hasattr(target, "set_state"):
        target.set_state(state)
    if hasattr(target, "G"):
        target.G = state.G
    return state


def _pending_effect_id(
    state: MatchState,
    source_card_id: InstanceId | str,
    chooser_id: PlayerId | str,
) -> str:
    next_index = len(state.G.pendingEffects) + 1
    return f"pending-action:{state.ctx._stateID}:{source_card_id}:{chooser_id}:{next_index}"


def create_pending_action_effect(
    state: MatchState,
    *,
    kind: str,
    sourceCardId: InstanceId | str,
    controllerId: PlayerId | str,
    chooserId: PlayerId | str,
    cardPlayed: Mapping[str, object] | None,
    effect: object,
    resolutionInput: object | None = None,
    abilityIndex: int | None = None,
    continuation: object | None = None,
    selectionContext: object | None = None,
    allowSuspendWithZeroTargetCandidates: bool = False,
) -> PendingActionEffect:
    return PendingActionEffect.create(
        id=_pending_effect_id(state, sourceCardId, chooserId),
        kind=kind,
        sourceCardId=sourceCardId,
        controllerId=controllerId,
        chooserId=chooserId,
        cardPlayed=cardPlayed,
        effect=effect,
        resolutionInput=resolutionInput,
        abilityIndex=abilityIndex,
        continuation=continuation,
        selectionContext=selectionContext,
        allowSuspendWithZeroTargetCandidates=allowSuspendWithZeroTargetCandidates,
    )


def enqueue_pending_action_effect(
    target: MatchState | object,
    pending_effect: PendingActionEffect,
) -> MatchState:
    state = _state_of(target)
    pending = tuple(
        effect for effect in state.G.pendingEffects if getattr(effect, "id", None) != pending_effect.id
    ) + (pending_effect,)
    next_state = MatchState(
        G=state.G.with_updates(pendingEffects=pending),
        ctx=state.ctx.with_updates(
            priority=state.ctx.priority.with_updates(
                pendingChoice=PendingChoice(
                    type="action-effect",
                    playerID=pending_effect.chooserId,
                    requestID=pending_effect.id,
                )
            )
        ),
    )
    return _write_state(target, next_state)


def clear_pending_action_choice(target: MatchState | object) -> MatchState:
    state = _state_of(target)
    next_state = MatchState(
        G=state.G,
        ctx=state.ctx.with_updates(
            priority=state.ctx.priority.with_updates(pendingChoice=None)
        ),
    )
    return _write_state(target, next_state)


def remove_pending_action_effect(
    target: MatchState | object,
    effect_id: str,
) -> tuple[MatchState, PendingActionEffect | None]:
    state = _state_of(target)
    matched = next(
        (effect for effect in state.G.pendingEffects if getattr(effect, "id", None) == effect_id),
        None,
    )
    if not isinstance(matched, PendingActionEffect):
        return state, None

    remaining = tuple(
        effect for effect in state.G.pendingEffects if getattr(effect, "id", None) != effect_id
    )
    pending_choice = state.ctx.priority.pendingChoice
    should_clear_choice = (
        pending_choice is not None
        and pending_choice.type == "action-effect"
        and pending_choice.requestID == effect_id
    )
    next_priority: CtxPriority = state.ctx.priority.with_updates(
        pendingChoice=None if should_clear_choice and not remaining else pending_choice
    )
    next_state = MatchState(
        G=state.G.with_updates(pendingEffects=remaining),
        ctx=state.ctx.with_updates(priority=next_priority),
    )
    return _write_state(target, next_state), matched


def has_pending_action_effect_resolution(state_or_context: MatchState | object) -> bool:
    if isinstance(state_or_context, MatchState):
        pending_effects = state_or_context.G.pendingEffects
        pending_choice = state_or_context.ctx.priority.pendingChoice
    elif hasattr(state_or_context, "G") and hasattr(state_or_context, "framework"):
        pending_effects = getattr(state_or_context.G, "pendingEffects", ())
        pending_choice = getattr(state_or_context.framework.state.priority, "pendingChoice", None)
    else:
        state = _state_of(state_or_context)
        pending_effects = state.G.pendingEffects
        pending_choice = state.ctx.priority.pendingChoice
    return bool(pending_effects) or (
        pending_choice is not None and pending_choice.type == "action-effect"
    )


def has_any_pending_effects(state_or_context: MatchState | object) -> bool:
    if isinstance(state_or_context, MatchState):
        pending_effects = state_or_context.G.pendingEffects
        bag_items = state_or_context.G.triggeredAbilities.bag.items
    elif hasattr(state_or_context, "G"):
        pending_effects = getattr(state_or_context.G, "pendingEffects", ())
        triggered = getattr(state_or_context.G, "triggeredAbilities", None)
        bag = getattr(triggered, "bag", None)
        bag_items = getattr(bag, "items", ())
    else:
        state = _state_of(state_or_context)
        pending_effects = state.G.pendingEffects
        bag_items = state.G.triggeredAbilities.bag.items
    return bool(pending_effects) or bool(bag_items)


def validate_no_pending_effects(
    state_or_context: MatchState | object,
    *,
    action_label: str = "act",
) -> RuntimeValidationResult:
    if has_pending_action_effect_resolution(state_or_context):
        return RuntimeValidationResult.fail(
            f"Cannot {action_label} while an action effect is pending",
            EFFECT_PENDING_ERROR_CODE,
        )
    if isinstance(state_or_context, MatchState):
        bag_items = state_or_context.G.triggeredAbilities.bag.items
    elif hasattr(state_or_context, "G"):
        triggered = getattr(state_or_context.G, "triggeredAbilities", None)
        bag_items = getattr(getattr(triggered, "bag", None), "items", ())
    else:
        bag_items = _state_of(state_or_context).G.triggeredAbilities.bag.items
    if bag_items:
        return RuntimeValidationResult.fail(
            f"Cannot {action_label} while bag effects are pending",
            "BAG_PENDING",
        )
    return RuntimeValidationResult.ok()


def validate_pending_choice_input(
    state_or_context: MatchState | object,
    *,
    player_id: PlayerId | str,
    effect_id: str,
    params: Mapping[str, object] | None = None,
) -> RuntimeValidationResult:
    state = _state_of(state_or_context)
    pending_choice = state.ctx.priority.pendingChoice
    if pending_choice is None or pending_choice.type != "action-effect":
        return RuntimeValidationResult.fail("No action effect is pending", "NO_PENDING_EFFECT")
    if pending_choice.requestID != effect_id:
        return RuntimeValidationResult.fail("Pending effect id does not match", "PENDING_EFFECT_MISMATCH")
    if pending_choice.playerID != PlayerId(str(player_id)):
        return RuntimeValidationResult.fail("Only the pending chooser may resolve this effect", "WRONG_PENDING_EFFECT_PLAYER")
    if not any(getattr(effect, "id", None) == effect_id for effect in state.G.pendingEffects):
        return RuntimeValidationResult.fail("Pending effect was not found", "PENDING_EFFECT_NOT_FOUND")

    if params is not None:
        targets = params.get("targets")
        if targets is not None:
            if isinstance(targets, str):
                if not targets:
                    return RuntimeValidationResult.fail("Invalid target selection", "INVALID_PENDING_TARGETS")
            elif not isinstance(targets, (list, tuple)):
                return RuntimeValidationResult.fail("Invalid target selection", "INVALID_PENDING_TARGETS")
            elif not all(isinstance(target, str) and target for target in targets):
                return RuntimeValidationResult.fail("Invalid target selection", "INVALID_PENDING_TARGETS")

    return RuntimeValidationResult.ok()


def resolve_pending_action_effect(
    target: MatchState | object,
    *,
    effect_id: str,
    player_id: PlayerId | str | None = None,
    params: Mapping[str, object] | ActionResolutionInput | None = None,
    resolver: Callable[[MatchState, PendingActionEffect, ActionResolutionInput], PendingResolutionResult | MatchState | None] | None = None,
) -> PendingResolutionResult:
    state = _state_of(target)
    pending = next(
        (effect for effect in state.G.pendingEffects if getattr(effect, "id", None) == effect_id),
        None,
    )
    if not isinstance(pending, PendingActionEffect):
        return PendingResolutionResult(status="not-found", state=state)

    if player_id is not None:
        validation = validate_pending_choice_input(
            state,
            player_id=player_id,
            effect_id=effect_id,
            params=params.to_mapping() if isinstance(params, ActionResolutionInput) else params,
        )
        if not validation.valid:
            return PendingResolutionResult(
                status="invalid",
                state=state,
                pendingEffect=pending,
                resolutionInput=pending.resolutionInput,
            )

    resolution_input = pending.resolutionInput.merge(params)
    state_without_pending, removed = remove_pending_action_effect(target, effect_id)
    if removed is None:
        return PendingResolutionResult(status="not-found", state=state_without_pending)

    if resolver is None:
        return PendingResolutionResult(
            status="resolved",
            state=_write_state(target, state_without_pending),
            pendingEffect=removed,
            resolutionInput=resolution_input,
        )

    resolved = resolver(state_without_pending, removed, resolution_input)
    if isinstance(resolved, PendingResolutionResult):
        next_state = _write_state(target, resolved.state) if isinstance(resolved.state, MatchState) else state_without_pending
        return replace(
            resolved,
            state=next_state,
            pendingEffect=resolved.pendingEffect if resolved.pendingEffect is not None else removed,
        )
    if isinstance(resolved, MatchState):
        return PendingResolutionResult(
            status="resolved",
            state=_write_state(target, resolved),
            pendingEffect=removed,
            resolutionInput=resolution_input,
        )
    return PendingResolutionResult(
        status="resolved",
        state=_write_state(target, state_without_pending),
        pendingEffect=removed,
        resolutionInput=resolution_input,
    )


def move_suspended_action_card_to_limbo(
    target: MatchState | object,
    card_played: Mapping[str, object],
) -> MatchState:
    if card_played.get("cardType") != "action":
        return _state_of(target)

    state = _state_of(target)
    card_id = InstanceId(str(card_played.get("cardId", "")))
    player_id = PlayerId(str(card_played.get("playerId", "")))
    if not card_id or not player_id:
        return state

    current = state.ctx.zones.private.cardIndex.get(card_id)
    if current is None or not str(current.zoneKey).startswith("play"):
        return state

    zones = move_card_to_zone(
        state.ctx.zones,
        card_id=card_id,
        destination_zone_key=scoped_zone("limbo", player_id),
    )
    meta = zones.private.cardMeta.get(card_id, CardMeta())
    zones = patch_card_meta(zones, card_id, meta.with_updates(publicFaceState="faceUp"))
    next_state = MatchState(G=state.G, ctx=state.ctx.with_updates(zones=zones))
    return _write_state(target, next_state)


def finalize_resolved_action_card(
    target: MatchState | object,
    card_played: Mapping[str, object],
) -> MatchState:
    if card_played.get("cardType") != "action":
        return _state_of(target)

    state = _state_of(target)
    card_id = InstanceId(str(card_played.get("cardId", "")))
    player_id = PlayerId(str(card_played.get("playerId", "")))
    current = state.ctx.zones.private.cardIndex.get(card_id)
    if current is None:
        return state
    if not (str(current.zoneKey).startswith("play") or str(current.zoneKey).startswith("limbo")):
        return state

    from_zone = str(base_zone_from_key(current.zoneKey))
    destination_zone = "discard"
    destination_index: int | None = None
    meta = state.ctx.zones.private.cardMeta.get(card_id, CardMeta())
    if meta.afterPlayDestination == "bottom-of-deck":
        destination_zone = "deck"
        destination_index = 0

    from lorcana_engine_v2.effects.replacement_effects import apply_replacement_effects

    replacement = apply_replacement_effects(
        target,
        {
            "kind": "zone-change",
            "eventId": f"finalize-action:{card_id}",
            "cardId": card_id,
            "sourceId": card_id,
            "controllerId": player_id,
            "fromZone": from_zone,
            "toZone": destination_zone,
        },
    )
    destination_zone = str(replacement.get("toZone") or destination_zone)
    replacement_position = replacement.get("position")
    if replacement_position in {"bottom", "deck-bottom"}:
        destination_index = 0
    elif replacement_position in {"top", "deck-top"}:
        destination_index = None

    destination = scoped_zone(destination_zone, player_id)

    zones = move_card_to_zone(
        state.ctx.zones,
        card_id=card_id,
        destination_zone_key=destination,
        index=destination_index,
    )
    card_meta = dict(zones.private.cardMeta)
    card_meta.pop(card_id, None)
    zones = ZoneRuntimeState(
        public=zones.public,
        reveals=zones.reveals,
        private=ZoneRuntimePrivateState(
            zoneCards=zones.private.zoneCards,
            cardIndex=zones.private.cardIndex,
            cardMeta=card_meta,
        ),
    )
    next_state = MatchState(G=state.G, ctx=state.ctx.with_updates(zones=zones))
    if is_discard_zone_key(destination_zone):
        next_state = record_card_put_into_discard_this_turn(next_state, player_id)
    return _write_state(target, next_state)


class PendingService:
    create = staticmethod(create_pending_action_effect)
    enqueue = staticmethod(enqueue_pending_action_effect)
    resolve = staticmethod(resolve_pending_action_effect)
    validate = staticmethod(validate_pending_choice_input)
    has_any = staticmethod(has_any_pending_effects)
    validate_empty = staticmethod(validate_no_pending_effects)


__all__ = [
    "EFFECT_PENDING_ERROR_CODE",
    "PendingActionEffect",
    "PendingService",
    "clear_pending_action_choice",
    "create_pending_action_effect",
    "enqueue_pending_action_effect",
    "finalize_resolved_action_card",
    "has_any_pending_effects",
    "has_pending_action_effect_resolution",
    "move_suspended_action_card_to_limbo",
    "remove_pending_action_effect",
    "resolve_pending_action_effect",
    "validate_no_pending_effects",
    "validate_pending_choice_input",
]
