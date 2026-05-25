from __future__ import annotations

from dataclasses import dataclass

from lorcana_engine_v2.core.results import RuntimeValidationResult
from lorcana_engine_v2.core.state import MatchState
from lorcana_engine_v2.effects.triggered_abilities import flush_triggered_events_to_bag
from lorcana_engine_v2.resolution.action_effects import resolve_action_effect
from lorcana_engine_v2.resolution.pending import (
    finalize_resolved_action_card,
    has_pending_action_effect_resolution,
    resolve_pending_action_effect,
)

from .registry import MoveEnumerationContext, MoveExecutionContext, MoveValidationContext


RESOLVE_EFFECT = "resolveEffect"


def _effect_id(context: MoveValidationContext | MoveExecutionContext) -> str | None:
    raw = context.args.get("effectId") or context.args.get("effectID") or context.args.get("requestId") or context.args.get("requestID")
    if raw is not None:
        return str(raw)
    pending_choice = (
        context.state.ctx.priority.pendingChoice
        if hasattr(context, "state")
        else context.framework.state.priority.pendingChoice
    )
    if pending_choice is not None and pending_choice.type == "action-effect":
        return str(pending_choice.requestID)
    pending = context.G.pendingEffects
    if len(pending) == 1:
        return str(getattr(pending[0], "id", ""))
    return None


@dataclass(frozen=True, slots=True)
class ResolveEffectMove:
    serverOnly: bool = False
    ignorePriority: bool = True
    ignoreStaleStateID: bool = False

    def available(self, context: MoveEnumerationContext) -> bool:
        return has_pending_action_effect_resolution(context)

    def validate(self, context: MoveValidationContext) -> RuntimeValidationResult:
        effect_id = _effect_id(context)
        if effect_id is None:
            return RuntimeValidationResult.fail("No action effect is pending", "NO_PENDING_EFFECT")
        pending_choice = context.framework.state.priority.pendingChoice
        if pending_choice is None or pending_choice.type != "action-effect":
            return RuntimeValidationResult.fail("No action effect is pending", "NO_PENDING_EFFECT")
        if pending_choice.requestID != effect_id:
            return RuntimeValidationResult.fail("Pending effect id does not match", "PENDING_EFFECT_MISMATCH")
        if pending_choice.playerID != context.playerId:
            return RuntimeValidationResult.fail("Only the pending chooser may resolve this effect", "WRONG_PENDING_EFFECT_PLAYER")
        if not any(getattr(effect, "id", None) == effect_id for effect in context.G.pendingEffects):
            return RuntimeValidationResult.fail("Pending effect was not found", "PENDING_EFFECT_NOT_FOUND")
        targets = context.args.get("targets")
        if targets is not None:
            if isinstance(targets, str):
                if not targets:
                    return RuntimeValidationResult.fail("Invalid target selection", "INVALID_PENDING_TARGETS")
            elif not isinstance(targets, (list, tuple)):
                return RuntimeValidationResult.fail("Invalid target selection", "INVALID_PENDING_TARGETS")
            elif not all(isinstance(target, str) and target for target in targets):
                return RuntimeValidationResult.fail("Invalid target selection", "INVALID_PENDING_TARGETS")
        return RuntimeValidationResult.ok()

    def execute(self, context: MoveExecutionContext) -> MatchState:
        effect_id = _effect_id(context)
        if effect_id is None:
            raise RuntimeError("resolveEffect execute called without a pending effect")

        result = resolve_pending_action_effect(
            context,
            effect_id=effect_id,
            player_id=context.playerId,
            params=context.args,
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
        if not has_pending_action_effect_resolution(context.state):
            card_played = result.pendingEffect.cardPlayed if result.pendingEffect is not None else {}
            finalize_resolved_action_card(context, card_played)
            flush_triggered_events_to_bag(context)
        return context.state


Move = ResolveEffectMove


__all__ = ["RESOLVE_EFFECT", "ResolveEffectMove", "Move"]
