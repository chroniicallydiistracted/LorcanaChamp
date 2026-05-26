from __future__ import annotations

from collections.abc import Mapping, Sequence

from lorcana_engine_v2.core.ids import InstanceId, PlayerId
from lorcana_engine_v2.core.zones import base_zone_from_key
from lorcana_engine_v2.effects.triggered_abilities import (
    emit_triggered_lorcana_event,
    snapshot_triggered_candidates_for_card,
)
from lorcana_engine_v2.resolution.action_effect_types import ActionResolutionInput
from lorcana_engine_v2.targeting.slotted_targets import flatten_slotted_targets, is_slotted_target_input


def _targets(value: object | None) -> tuple[str, ...]:
    if is_slotted_target_input(value):
        return flatten_slotted_targets(value)
    if isinstance(value, str):
        return (value,) if value else ()
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return tuple(str(item) for item in value if isinstance(item, str) and item)
    return ()


def collect_be_chosen_targets_from_selection(selection: object | None) -> tuple[str, ...]:
    return _targets(selection)


def emit_be_chosen_events(
    context,
    *,
    player_id: PlayerId | str,
    source_card_id: InstanceId | str,
    source_card_type: str | None = None,
    selected_targets: object | None,
    event_snapshot: Mapping[str, object] | None = None,
) -> None:
    state = context.state
    source = InstanceId(str(source_card_id))
    for target in collect_be_chosen_targets_from_selection(selected_targets):
        target_id = InstanceId(target)
        index_entry = state.ctx.zones.private.cardIndex.get(target_id)
        if index_entry is not None:
            owner_id = index_entry.ownerID
            trigger_candidates = snapshot_triggered_candidates_for_card(context, target_id)
            source_type = source_card_type
            if source_type is None:
                definition = context.cards.getDefinition(source)
                source_type = definition.card_type if definition is not None else None
            emit_triggered_lorcana_event(
                context,
                "beChosen",
                {
                    "playerId": owner_id,
                    "subjectCardId": target_id,
                    "triggerSourceCardId": source,
                    "sourceCardType": source_type,
                    "sourceId": source,
                    "selectedTarget": target_id,
                    "targetZone": str(base_zone_from_key(index_entry.zoneKey)),
                    "eventSnapshot": dict(event_snapshot or {}),
                },
                {
                    "event": "be-chosen",
                    "playerId": owner_id,
                    "subjectCardId": target_id,
                    "triggerSourceCardId": source,
                    "sourceCardType": source_type,
                    "selectedTarget": target_id,
                    "eventSnapshot": dict(event_snapshot or {}),
                    "triggerCandidates": trigger_candidates,
                },
            )
        elif PlayerId(target) in state.ctx.playerIds:
            emit_triggered_lorcana_event(
                context,
                "beChosen",
                {
                    "playerId": PlayerId(target),
                    "subjectCardId": None,
                    "triggerSourceCardId": source,
                    "sourceCardType": source_card_type,
                    "sourceId": source,
                    "selectedTarget": PlayerId(target),
                    "eventSnapshot": dict(event_snapshot or {}),
                },
                {
                    "event": "be-chosen",
                    "playerId": PlayerId(target),
                    "subjectCardId": None,
                    "triggerSourceCardId": source,
                    "sourceCardType": source_card_type,
                    "selectedTarget": PlayerId(target),
                    "eventSnapshot": dict(event_snapshot or {}),
                },
            )


def emit_be_chosen_events_for_pending_selection(
    context,
    pending_effect,
    resolution_input: ActionResolutionInput,
) -> None:
    emit_be_chosen_events(
        context,
        player_id=pending_effect.controllerId,
        source_card_id=pending_effect.sourceCardId,
        source_card_type=pending_effect.cardPlayed.get("cardType") if isinstance(pending_effect.cardPlayed, Mapping) else None,
        selected_targets=resolution_input.currentTargets if resolution_input.currentTargets is not None else resolution_input.targets,
        event_snapshot=resolution_input.eventSnapshot,
    )


__all__ = [
    "collect_be_chosen_targets_from_selection",
    "emit_be_chosen_events",
    "emit_be_chosen_events_for_pending_selection",
]
