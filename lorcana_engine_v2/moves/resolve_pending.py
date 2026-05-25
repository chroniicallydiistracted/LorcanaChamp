from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from lorcana_engine_v2.core.ids import InstanceId, PlayerId
from lorcana_engine_v2.core.results import RuntimeValidationResult
from lorcana_engine_v2.core.state import MatchState
from lorcana_engine_v2.effects.triggered_abilities import flush_triggered_events_to_bag
from lorcana_engine_v2.resolution.action_effect_types import PendingActionEffect
from lorcana_engine_v2.resolution.action_effects import resolve_action_effect
from lorcana_engine_v2.resolution.pending import (
    finalize_resolved_action_card,
    has_pending_action_effect_resolution,
    resolve_pending_action_effect,
)

from .registry import MoveEnumerationContext, MoveExecutionContext, MoveValidationContext


RESOLVE_EFFECT = "resolveEffect"


def _state_from_context(context: MoveValidationContext | MoveExecutionContext) -> MatchState:
    state = getattr(context, "state", None)
    if isinstance(state, MatchState):
        return state
    getter = getattr(context.cards, "_state_getter", None)
    if callable(getter):
        found = getter()
        if isinstance(found, MatchState):
            return found
    raise TypeError("resolveEffect requires a Lorcanito runtime state context")


def _effect_id(context: MoveValidationContext | MoveExecutionContext) -> str | None:
    raw = context.args.get("effectId")
    return str(raw) if isinstance(raw, str) and raw else None


def _params(context: MoveValidationContext | MoveExecutionContext) -> Mapping[str, object] | None:
    value = context.args.get("params")
    return value if isinstance(value, Mapping) else None


def _pending_effect(context: MoveValidationContext | MoveExecutionContext, effect_id: str) -> PendingActionEffect | None:
    for effect in context.G.pendingEffects:
        if isinstance(effect, PendingActionEffect) and effect.id == effect_id:
            return effect
    return None


def _targets(value: object) -> tuple[InstanceId, ...]:
    if isinstance(value, str):
        return (InstanceId(value),) if value else ()
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return tuple(InstanceId(str(item)) for item in value if isinstance(item, str) and item)
    return ()


def _card_type(context: MoveValidationContext | MoveExecutionContext, card_id: InstanceId) -> str | None:
    try:
        return context.cards.require(card_id).definition.card_type
    except Exception:
        return None


def _validate_params_shape(params: object) -> RuntimeValidationResult:
    if not isinstance(params, Mapping):
        return RuntimeValidationResult.fail("resolveEffect params must be an object", "RESOLVE_EFFECT_PARAMS_REQUIRED")
    allowed = {
        "targets",
        "slottedTargets",
        "currentTargets",
        "amount",
        "choiceIndex",
        "resolveOptional",
        "enterPlayExerted",
        "destinations",
        "namedCard",
        "eventSnapshot",
    }
    unknown = tuple(key for key in params if key not in allowed)
    if unknown:
        return RuntimeValidationResult.fail("resolveEffect params contain unsupported fields", "RESOLVE_EFFECT_INVALID_PARAMS")
    targets = params.get("targets")
    if targets is not None:
        if isinstance(targets, str):
            if not targets:
                return RuntimeValidationResult.fail("resolveEffect targets must be non-empty", "INVALID_PENDING_TARGETS")
        elif not isinstance(targets, (list, tuple)):
            return RuntimeValidationResult.fail("resolveEffect targets must be a card id or array of card ids", "INVALID_PENDING_TARGETS")
        elif not all(isinstance(target, str) and target for target in targets):
            return RuntimeValidationResult.fail("resolveEffect targets must be card ids", "INVALID_PENDING_TARGETS")
    amount = params.get("amount")
    if amount is not None and not isinstance(amount, (int, str, Mapping)):
        return RuntimeValidationResult.fail("resolveEffect amount must be a valid amount", "INVALID_PENDING_AMOUNT")
    choice_index = params.get("choiceIndex")
    if choice_index is not None and (not isinstance(choice_index, int) or choice_index < 0):
        return RuntimeValidationResult.fail("resolveEffect choiceIndex must be a non-negative integer", "INVALID_PENDING_CHOICE")
    resolve_optional = params.get("resolveOptional")
    if resolve_optional is not None and not isinstance(resolve_optional, bool):
        return RuntimeValidationResult.fail("resolveEffect resolveOptional must be a boolean", "INVALID_PENDING_OPTIONAL")
    enter_play_exerted = params.get("enterPlayExerted")
    if enter_play_exerted is not None and not isinstance(enter_play_exerted, bool):
        return RuntimeValidationResult.fail("resolveEffect enterPlayExerted must be a boolean", "INVALID_PENDING_ENTER_PLAY_EXERTED")
    destinations = params.get("destinations")
    if destinations is not None and not isinstance(destinations, (list, tuple)):
        return RuntimeValidationResult.fail("resolveEffect destinations must be an array", "INVALID_PENDING_DESTINATIONS")
    named_card = params.get("namedCard")
    if named_card is not None and (not isinstance(named_card, str) or not named_card.strip()):
        return RuntimeValidationResult.fail("resolveEffect namedCard must be a non-empty string", "INVALID_PENDING_NAMED_CARD")
    return RuntimeValidationResult.ok()


def _validate_target_legality(
    context: MoveValidationContext | MoveExecutionContext,
    pending: PendingActionEffect,
    params: Mapping[str, object],
) -> RuntimeValidationResult:
    selected = _targets(params.get("targets"))
    if pending.kind == "discard-choice":
        if not selected:
            return RuntimeValidationResult.fail("resolveEffect requires discard targets", "RESOLVE_EFFECT_TARGETS_REQUIRED")
        state = _state_from_context(context)
        effect = pending.effect if isinstance(pending.effect, Mapping) else {}
        source_zone = str(effect.get("from") or "hand")
        target_players = (
            tuple(player_id for player_id in state.ctx.playerIds if player_id != pending.controllerId)
            if str(effect.get("target") or "").upper() in {"OPPONENT", "EACH_OPPONENT", "OPPONENTS"}
            else (pending.chooserId,)
        )
        legal = set()
        for player_id in target_players:
            legal.update(state.ctx.zones.private.zoneCards.get(f"{source_zone}:{player_id}", ()))
        if any(card_id not in legal for card_id in selected):
            return RuntimeValidationResult.fail("resolveEffect discard target is illegal", "INVALID_PENDING_TARGETS")
        return RuntimeValidationResult.ok()

    if pending.kind == "target-selection":
        if params.get("resolveOptional") is False:
            return RuntimeValidationResult.ok()
        if not selected:
            return RuntimeValidationResult.fail("resolveEffect requires targets for this pending effect", "RESOLVE_EFFECT_TARGETS_REQUIRED")
        state = _state_from_context(context)
        effect = pending.effect if isinstance(pending.effect, Mapping) else {}
        raw_target = effect.get("target")
        for card_id in selected:
            entry = state.ctx.zones.private.cardIndex.get(card_id)
            if entry is None:
                return RuntimeValidationResult.fail("resolveEffect target was not found", "INVALID_PENDING_TARGETS")
            normalized = str(raw_target or "").upper()
            if "CHARACTER" in normalized and _card_type(context, card_id) != "character":
                return RuntimeValidationResult.fail("resolveEffect target must be a character", "INVALID_PENDING_TARGETS")
            if "OPPOSING" in normalized and entry.controllerID == pending.controllerId:
                return RuntimeValidationResult.fail("resolveEffect target must be opposing", "INVALID_PENDING_TARGETS")
            if isinstance(raw_target, Mapping):
                card_types = raw_target.get("cardTypes") or raw_target.get("card_types")
                if isinstance(card_types, Sequence) and not isinstance(card_types, (str, bytes, bytearray)):
                    allowed_types = {str(item) for item in card_types}
                    if "card" not in allowed_types and _card_type(context, card_id) not in allowed_types:
                        return RuntimeValidationResult.fail("resolveEffect target has wrong card type", "INVALID_PENDING_TARGETS")
                owner = raw_target.get("owner")
                if owner == "you" and entry.controllerID != pending.controllerId:
                    return RuntimeValidationResult.fail("resolveEffect target must be yours", "INVALID_PENDING_TARGETS")
                if owner == "opponent" and entry.controllerID == pending.controllerId:
                    return RuntimeValidationResult.fail("resolveEffect target must be opposing", "INVALID_PENDING_TARGETS")
        return RuntimeValidationResult.ok()

    return RuntimeValidationResult.ok()


@dataclass(frozen=True, slots=True)
class ResolveEffectMove:
    serverOnly: bool = False
    ignorePriority: bool = True
    ignoreStaleStateID: bool = False

    def available(self, context: MoveEnumerationContext) -> bool:
        pending_choice = context.framework.state.priority.pendingChoice
        if pending_choice is None or pending_choice.type != "action-effect":
            return False
        pending = next(
            (effect for effect in context.G.pendingEffects if isinstance(effect, PendingActionEffect) and effect.id == pending_choice.requestID),
            None,
        )
        return pending is not None and pending.chooserId == context.playerId

    def validate(self, context: MoveValidationContext) -> RuntimeValidationResult:
        effect_id = _effect_id(context)
        if effect_id is None:
            return RuntimeValidationResult.fail("resolveEffect requires a valid effect id", "RESOLVE_EFFECT_ID_REQUIRED")
        pending_choice = context.framework.state.priority.pendingChoice
        if pending_choice is None or pending_choice.type != "action-effect" or pending_choice.requestID != effect_id:
            return RuntimeValidationResult.fail("No matching pending effect is available to resolve", "RESOLVE_EFFECT_NOT_PENDING")
        pending = _pending_effect(context, effect_id)
        if pending is None:
            return RuntimeValidationResult.fail("Pending effect payload was not found", "RESOLVE_EFFECT_NOT_FOUND")
        if pending.chooserId != context.playerId:
            return RuntimeValidationResult.fail("Only the pending chooser may resolve this effect", "RESOLVE_EFFECT_WRONG_PLAYER")
        if context.validationMode == "preflight" and context.args.get("params") is None:
            return RuntimeValidationResult.ok()
        params = _params(context)
        shape = _validate_params_shape(context.args.get("params"))
        if not shape.valid:
            return shape
        assert params is not None
        if pending.kind == "choice-selection" and params.get("choiceIndex") is None:
            return RuntimeValidationResult.fail("resolveEffect requires choiceIndex for this pending effect", "RESOLVE_EFFECT_CHOICE_REQUIRED")
        if pending.kind == "optional-selection" and params.get("resolveOptional") is None:
            return RuntimeValidationResult.fail("resolveEffect requires resolveOptional for this pending effect", "RESOLVE_EFFECT_OPTIONAL_REQUIRED")
        if pending.kind == "scry-selection" and params.get("destinations") is None:
            return RuntimeValidationResult.fail("resolveEffect requires destinations for this pending effect", "RESOLVE_EFFECT_DESTINATIONS_REQUIRED")
        if pending.kind == "name-card-selection" and params.get("namedCard") is None:
            return RuntimeValidationResult.fail("resolveEffect requires namedCard for this pending effect", "RESOLVE_EFFECT_NAMED_CARD_REQUIRED")
        return _validate_target_legality(context, pending, params)

    def execute(self, context: MoveExecutionContext) -> MatchState:
        effect_id = _effect_id(context)
        if effect_id is None:
            raise RuntimeError("resolveEffect execute called without a valid effectId")
        params = _params(context)
        if params is None:
            raise RuntimeError("resolveEffect execute called without Lorcanito args.params")

        result = resolve_pending_action_effect(
            context,
            effect_id=effect_id,
            player_id=context.playerId,
            params=params,
            resolver=lambda _state, pending_effect, resolution_input: resolve_action_effect(
                context,
                pending_effect.cardPlayed,
                pending_effect.effect,
                resolution_input,
                {"sourceAbilityIndex": pending_effect.abilityIndex}
                if pending_effect.abilityIndex is not None
                else None,
            ),
        )
        if result.status not in {"resolved", "suspended"}:
            raise RuntimeError(f"Failed to resolve pending action effect: {result.status}")
        if result.status == "resolved" and result.pendingEffect is not None:
            continuation = result.pendingEffect.continuation
            remaining = ()
            if isinstance(continuation, Mapping):
                raw_remaining = continuation.get("remainingEffects")
                if isinstance(raw_remaining, Sequence) and not isinstance(raw_remaining, (str, bytes, bytearray)):
                    remaining = tuple(raw_remaining)
            if remaining:
                continued = resolve_action_effect(
                    context,
                    result.pendingEffect.cardPlayed,
                    {"type": "sequence", "effects": remaining},
                    result.resolutionInput,
                    {"sourceAbilityIndex": result.pendingEffect.abilityIndex}
                    if result.pendingEffect.abilityIndex is not None
                    else None,
                )
                if continued.status not in {"resolved", "suspended"}:
                    raise RuntimeError(f"Failed to resolve pending action effect continuation: {continued.status}")
        if not has_pending_action_effect_resolution(context.state):
            card_played = result.pendingEffect.cardPlayed if result.pendingEffect is not None else {}
            finalize_resolved_action_card(context, card_played)
            flush_triggered_events_to_bag(context)
        return context.state


Move = ResolveEffectMove


__all__ = ["RESOLVE_EFFECT", "ResolveEffectMove", "Move"]
