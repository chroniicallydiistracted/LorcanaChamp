from __future__ import annotations

from dataclasses import dataclass

from lorcana_engine_v2.core.events import GameEvent
from lorcana_engine_v2.core.ids import InstanceId, PlayerId, ZoneId
from lorcana_engine_v2.core.results import LogMessage, LogVisibility, ProjectedLogEntry, RuntimeValidationResult
from lorcana_engine_v2.core.state import MatchState
from lorcana_engine_v2.core.zones import ZoneRef, scoped_zone

from .registry import MoveEnumerationContext, MoveExecutionContext, MoveValidationContext, input_card_id


PUT_CARD_INTO_INKWELL = "putCardIntoInkwell"


def _ink_actions_remaining(context: MoveValidationContext | MoveEnumerationContext | MoveExecutionContext) -> int:
    turn_metadata = context.G.turnMetadata
    base_action = 1
    extra_actions = turn_metadata.additionalInkwellActions
    return base_action + extra_actions - len(turn_metadata.inkedThisTurn)


@dataclass(frozen=True, slots=True)
class PutCardIntoInkwellMove:
    """Core inking move using Lorcanito command contexts."""

    serverOnly: bool = False
    ignorePriority: bool = False
    ignoreStaleStateID: bool = False

    def available(self, context: MoveEnumerationContext) -> bool:
        if _ink_actions_remaining(context) <= 0:
            return False
        current_player = context.framework.state.priority.holder or context.playerId
        hand_cards = context.framework.zones.getCards({"zone": "hand", "playerId": current_player})
        for card_id in hand_cards:
            try:
                runtime_card = context.cards.require(card_id)
            except KeyError:
                continue
            if runtime_card.definition.inkable:
                return True
        return False

    def validate(self, context: MoveValidationContext) -> RuntimeValidationResult:
        current_player = context.framework.state.priority.holder or context.playerId

        if _ink_actions_remaining(context) <= 0:
            return RuntimeValidationResult.fail("Already inked this turn", "ALREADY_INKED")

        raw_card_id = input_card_id(context)
        if context.validationMode == "preflight" and raw_card_id is None:
            return RuntimeValidationResult.ok()
        if raw_card_id is None:
            return RuntimeValidationResult.fail("Card input was not provided", "MISSING_CARD")

        card_id = InstanceId(raw_card_id)
        hand_cards = context.framework.zones.getCards({"zone": "hand", "playerId": current_player})
        if card_id not in hand_cards:
            return RuntimeValidationResult.fail("Card not in hand", "CARD_NOT_IN_HAND")

        try:
            runtime_card = context.cards.require(card_id)
        except KeyError:
            return RuntimeValidationResult.fail("Card definition not found", "CARD_DEFINITION_NOT_FOUND")

        if not runtime_card.definition.inkable:
            return RuntimeValidationResult.fail("Card is not inkable", "NOT_INKABLE")

        return RuntimeValidationResult.ok()

    def execute(self, context: MoveExecutionContext) -> MatchState:
        card_id = InstanceId(input_card_id(context) or "")
        owner_id = PlayerId(str(context.framework.state.priority.holder or context.playerId))
        source_zone = context.framework.zones.getCardZone(card_id) or scoped_zone("hand", owner_id)
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
        context.framework.events.emit(
            GameEvent(
                kind="card.inked",
                actor=owner_id,
                source=card_id,
                payload={
                    "cardId": str(card_id),
                    "fromZone": str(source_zone),
                    "toZone": str(scoped_zone("inkwell", owner_id)),
                },
            )
        )
        context.set_G(
            context.state.G.with_updates(
                turnMetadata=context.state.G.turnMetadata.record_ink(card_id),
            )
        )
        return context.state
