from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from lorcana_engine_v2.core.ids import InstanceId, PlayerId, ZoneId
from lorcana_engine_v2.core.results import LogMessage, LogVisibility, ProjectedLogEntry, RuntimeValidationResult
from lorcana_engine_v2.core.state import MatchState, TurnMetadata
from lorcana_engine_v2.core.turn_owner import resolve_priority_holder_id
from lorcana_engine_v2.core.zones import ZoneRef, base_zone_from_key, scoped_zone
from lorcana_engine_v2.effects.triggered_abilities import (
    emit_triggered_lorcana_event,
    flush_triggered_events_to_bag,
)
from lorcana_engine_v2.resolution.pending import has_any_pending_effects, validate_no_pending_effects

from .registry import MoveEnumerationContext, MoveExecutionContext, MoveValidationContext, input_card_id


PUT_CARD_INTO_INKWELL = "putCardIntoInkwell"
BASE_TURN_ACTION_INK_LIMIT = 1
INKWELL_CANDIDATE_QUERY_DSL = {
    "selector": "chosen",
    "count": 1,
    "owner": "you",
    "zones": ("hand", "discard"),
}


def _current_player(
    context: MoveValidationContext | MoveEnumerationContext | MoveExecutionContext,
) -> PlayerId:
    resolved = resolve_priority_holder_id(context)
    if resolved is not None:
        return resolved
    return PlayerId(str(context.playerId))


def _zone_is_play(zone_key: object) -> bool:
    if zone_key is None:
        return False
    return base_zone_from_key(str(zone_key)) == ZoneId("play")


def _normalize_allowance(value: object) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return max(0, value)
    if isinstance(value, float):
        return max(0, int(value))
    return 0


def build_turn_action_ink_state(
    context: MoveValidationContext | MoveEnumerationContext | MoveExecutionContext | MatchState,
):
    """Return the Lorcanito-shaped minimal state used by turn-action ink helpers."""

    if isinstance(context, MatchState):
        return {
            "G": context.G,
            "ctx": {
                "priority": context.ctx.priority,
                "zones": {"private": context.ctx.zones.private},
            },
        }
    return {
        "G": context.G,
        "ctx": {
            "priority": context.framework.state.priority,
            "zones": {"private": context.framework.state._zonesPrivate},
        },
    }


def get_temporary_additional_turn_action_ink_allowance(
    context: MoveValidationContext | MoveEnumerationContext | MoveExecutionContext | MatchState,
) -> int:
    state = context if isinstance(context, MatchState) else None
    turn_metadata = state.G.turnMetadata if state is not None else context.G.turnMetadata
    return _normalize_allowance(turn_metadata.additionalInkwellActions)


def get_static_additional_turn_action_ink_allowance(
    context: MoveValidationContext | MoveEnumerationContext | MoveExecutionContext,
    *,
    player_id: PlayerId | str | None = None,
    get_definition_by_instance_id: Callable[[InstanceId], object | None] | None = None,
) -> int:
    resolved_player = PlayerId(str(player_id)) if player_id is not None else _current_player(context)
    definition_getter = get_definition_by_instance_id or (lambda card_id: context.cards.getDefinition(card_id))
    allowance = 0

    for card_id, entry in context.framework.state._zonesPrivate.cardIndex.items():
        if entry.controllerID != resolved_player or not _zone_is_play(entry.zoneKey):
            continue
        definition = definition_getter(InstanceId(str(card_id)))
        if definition is None:
            continue
        for ability in getattr(definition, "abilities", ()) or ():
            raw = getattr(ability, "raw", {})
            effect = raw.get("effect") if isinstance(raw, dict) else None
            if getattr(ability, "kind", None) == "static" and isinstance(effect, dict) and effect.get("type") == "additional-inkwell":
                allowance += _normalize_allowance(effect.get("amount", 1))

    return allowance


def get_additional_turn_action_ink_allowance(
    context: MoveValidationContext | MoveEnumerationContext | MoveExecutionContext,
    *,
    player_id: PlayerId | str | None = None,
) -> int:
    return get_temporary_additional_turn_action_ink_allowance(context) + get_static_additional_turn_action_ink_allowance(
        context,
        player_id=player_id,
    )


def get_turn_action_ink_limit(
    context: MoveValidationContext | MoveEnumerationContext | MoveExecutionContext,
    *,
    player_id: PlayerId | str | None = None,
) -> int:
    return BASE_TURN_ACTION_INK_LIMIT + get_additional_turn_action_ink_allowance(context, player_id=player_id)


def can_ink_this_turn(
    context: MoveValidationContext | MoveEnumerationContext | MoveExecutionContext,
    *,
    player_id: PlayerId | str | None = None,
) -> bool:
    turn_metadata = context.G.turnMetadata
    return len(turn_metadata.inkedThisTurn) < get_turn_action_ink_limit(context, player_id=player_id)


def record_card_put_into_inkwell_this_turn(
    turn_metadata: TurnMetadata,
    card_id: InstanceId | str,
) -> TurnMetadata:
    return turn_metadata.record_ink(card_id)


def _candidate_cards(
    context: MoveValidationContext | MoveEnumerationContext | MoveExecutionContext,
    player_id: PlayerId,
) -> tuple[InstanceId, ...]:
    hand_cards = context.framework.zones.getCards({"zone": "hand", "playerId": player_id})
    discard_cards = context.framework.zones.getCards({"zone": "discard", "playerId": player_id})
    return tuple(hand_cards) + tuple(discard_cards)


@dataclass(frozen=True, slots=True)
class PutCardIntoInkwellMove:
    """Authoritative Lorcanito resource turn action for putting a card into the inkwell."""

    serverOnly: bool = False
    ignorePriority: bool = False
    ignoreStaleStateID: bool = False

    def available(self, context: MoveEnumerationContext) -> bool:
        if has_any_pending_effects(context):
            return False

        current_player = _current_player(context)
        if not can_ink_this_turn(context, player_id=current_player):
            return False

        for card_id in _candidate_cards(context, current_player):
            try:
                runtime_card = context.cards.require(card_id)
            except KeyError:
                continue
            if runtime_card.canBePutInInkwell:
                return True
        return False

    def validate(self, context: MoveValidationContext) -> RuntimeValidationResult:
        pending_failure = validate_no_pending_effects(context, action_label="ink cards")
        if not pending_failure.valid:
            return pending_failure

        current_player = _current_player(context)

        if not can_ink_this_turn(context, player_id=current_player):
            return RuntimeValidationResult.fail("Already inked this turn", "ALREADY_INKED")

        raw_card_id = input_card_id(context)
        if context.validationMode == "preflight" and raw_card_id is None:
            return RuntimeValidationResult.ok()
        if raw_card_id is None:
            return RuntimeValidationResult.fail("Card input was not provided", "MISSING_CARD")

        card_id = InstanceId(raw_card_id)
        if card_id not in _candidate_cards(context, current_player):
            return RuntimeValidationResult.fail("Card not in hand", "CARD_NOT_IN_HAND")

        try:
            runtime_card = context.cards.require(card_id)
        except KeyError:
            return RuntimeValidationResult.fail("Card definition not found", "CARD_DEFINITION_NOT_FOUND")

        if not runtime_card.canBePutInInkwell:
            return RuntimeValidationResult.fail("Card is not inkable", "NOT_INKABLE")

        return RuntimeValidationResult.ok()

    def execute(self, context: MoveExecutionContext) -> MatchState:
        card_id = InstanceId(input_card_id(context) or "")
        owner_id = _current_player(context)
        discard_cards = context.framework.zones.getCards({"zone": "discard", "playerId": owner_id})
        source_zone = "discard" if card_id in discard_cards else "hand"
        reveal_until_state_id = context.framework.state.stateID + 3

        context.framework.zones.moveCard(card_id, ZoneRef(zone=ZoneId("inkwell"), playerId=owner_id))
        context.cards.patchMeta(card_id, {"state": "ready", "publicFaceState": "faceDown"})
        context.framework.zones.reveal([card_id], "all", stateID=reveal_until_state_id)
        context.framework.log(
            ProjectedLogEntry(
                category="action",
                visibility=LogVisibility(mode="PUBLIC"),
                defaultMessage=LogMessage(
                    key="lorcana.card.inked",
                    values={"playerId": str(owner_id), "cardId": str(card_id)},
                ),
            )
        )

        context.set_G(
            context.state.G.with_updates(
                turnMetadata=record_card_put_into_inkwell_this_turn(
                    context.state.G.turnMetadata,
                    card_id,
                ),
            )
        )

        emit_triggered_lorcana_event(
            context,
            "cardInked",
            {
                "playerId": owner_id,
                "cardId": card_id,
                "from": str(scoped_zone(source_zone, owner_id)),
                "to": str(scoped_zone("inkwell", owner_id)),
            },
            {
                "event": "ink",
                "playerId": owner_id,
                "subjectCardId": card_id,
            },
        )
        flush_triggered_events_to_bag(context)
        return context.state


__all__ = [
    "BASE_TURN_ACTION_INK_LIMIT",
    "INKWELL_CANDIDATE_QUERY_DSL",
    "PUT_CARD_INTO_INKWELL",
    "PutCardIntoInkwellMove",
    "build_turn_action_ink_state",
    "can_ink_this_turn",
    "get_additional_turn_action_ink_allowance",
    "get_static_additional_turn_action_ink_allowance",
    "get_temporary_additional_turn_action_ink_allowance",
    "get_turn_action_ink_limit",
    "record_card_put_into_inkwell_this_turn",
]