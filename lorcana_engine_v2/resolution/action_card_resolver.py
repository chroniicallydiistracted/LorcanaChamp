from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from lorcana_engine_v2.cards.models import CardDefinition
from lorcana_engine_v2.core.ids import InstanceId, PlayerId
from lorcana_engine_v2.effects.be_chosen import emit_be_chosen_events
from lorcana_engine_v2.effects.triggered_abilities import flush_triggered_events_to_bag
from lorcana_engine_v2.resolution.action_effect_types import ActionResolutionInput
from lorcana_engine_v2.resolution.action_effects import resolve_action_effect
from lorcana_engine_v2.resolution.pending import (
    finalize_resolved_action_card,
    has_pending_action_effect_resolution,
    move_suspended_action_card_to_limbo,
)


@dataclass(frozen=True, slots=True)
class ActionCardResolutionResult:
    status: str
    resolutionInput: ActionResolutionInput


def _resources_from_context(context) -> object | None:
    return getattr(getattr(context.cards, "_query", None), "resources", None)


def _condition_true(context, card_played: Mapping[str, object], condition: object, resolution_input: ActionResolutionInput) -> bool:
    if condition is None:
        return True
    resources = _resources_from_context(context)
    if resources is None:
        return False
    from lorcana_engine_v2.core.context import build_rules_context
    from lorcana_engine_v2.rules.condition_evaluator import ConditionContext, ConditionEvaluator

    return ConditionEvaluator().evaluate(
        context.state,
        build_rules_context(resources),
        condition,
        ConditionContext(
            actor=PlayerId(str(card_played.get("playerId", context.playerId))),
            source_id=InstanceId(str(card_played.get("cardId", ""))),
            event_payload={"eventSnapshot": dict(resolution_input.eventSnapshot)},
        ),
    )


def resolve_action_card_effects(
    context,
    card_played: Mapping[str, object],
    action_card: CardDefinition,
    resolution_input: ActionResolutionInput,
) -> ActionCardResolutionResult:
    if resolution_input.targets is not None or resolution_input.slottedTargets is not None:
        emit_be_chosen_events(
            context,
            player_id=PlayerId(str(card_played.get("playerId", context.playerId))),
            source_card_id=InstanceId(str(card_played.get("cardId", ""))),
            source_card_type=str(card_played.get("cardType", action_card.card_type)),
            selected_targets=resolution_input.slottedTargets if resolution_input.slottedTargets is not None else resolution_input.targets,
            event_snapshot=resolution_input.eventSnapshot,
        )

    for index, ability in enumerate(action_card.abilities):
        if ability.kind != "action":
            continue
        if not _condition_true(context, card_played, ability.raw.get("condition"), resolution_input):
            continue
        result = resolve_action_effect(
            context,
            card_played,
            ability.raw.get("effect"),
            resolution_input,
            {"sourceAbilityIndex": index},
        )
        resolution_input = result.resolutionInput
        if result.status == "suspended" or has_pending_action_effect_resolution(context):
            move_suspended_action_card_to_limbo(context, card_played)
            return ActionCardResolutionResult("suspended", resolution_input)

    finalize_resolved_action_card(context, card_played)
    flush_triggered_events_to_bag(context)
    return ActionCardResolutionResult("resolved", resolution_input)


resolveActionCardEffects = resolve_action_card_effects


__all__ = ["ActionCardResolutionResult", "resolveActionCardEffects", "resolve_action_card_effects"]
