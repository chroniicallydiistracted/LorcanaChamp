from __future__ import annotations

from dataclasses import dataclass

from lorcana_engine_v2.core.commands import Command
from lorcana_engine_v2.core.events import GameEvent
from lorcana_engine_v2.core.ids import InstanceId, PlayerId, ZoneId
from lorcana_engine_v2.core.results import TransitionResult
from lorcana_engine_v2.core.state import MatchState
from lorcana_engine_v2.core.zones import (
    CardMeta,
    card_is_in_zone,
    move_card_to_zone,
    patch_card_meta,
    scoped_zone,
)
from .registry import MoveValidationResult, command_card_id
from .specs import MoveSpec


PUT_CARD_INTO_INKWELL = "putCardIntoInkwell"


@dataclass(frozen=True, slots=True)
class PutCardIntoInkwellMove:
    """Lorcanito-aligned implementation of the core inking move.

    This mirrors the early behavior of Lorcanito's `putCardIntoInkwell` move:
    validate priority/turn/card-zone/inkability, then move the selected card to
    the player's inkwell and record that the player inked this turn.
    """

    kind: str = PUT_CARD_INTO_INKWELL

    def enumerate(self, state: MatchState, player: PlayerId, ctx) -> tuple[MoveSpec, ...]:
        actor = PlayerId(str(player))
        if actor != state.framework.active_player:
            return ()
        if state.game.turn_metadata.inked_this_turn:
            return ()

        hand_zone = scoped_zone("hand", actor)
        moves: list[MoveSpec] = []
        for card_id in state.framework.zones.zone_cards.get(hand_zone, ()):
            try:
                runtime_card = ctx.query.runtime_card(state, card_id)
            except KeyError:
                continue
            if not runtime_card.definition.inkable:
                continue
            moves.append(MoveSpec(kind=self.kind, actor=actor, card=card_id))
        return tuple(moves)

    def validate(self, state: MatchState, command: Command, ctx) -> MoveValidationResult:
        actor = PlayerId(str(command.actor))
        if actor != state.framework.active_player:
            return MoveValidationResult.fail(
                f"Player '{actor}' does not currently have priority",
                "NOT_PRIORITY_HOLDER",
            )

        if state.game.turn_metadata.inked_this_turn:
            return MoveValidationResult.fail("Already inked this turn", "ALREADY_INKED")

        raw_card_id = command_card_id(command)
        if raw_card_id is None:
            return MoveValidationResult.fail("Card input was not provided", "MISSING_CARD")
        card_id = InstanceId(raw_card_id)

        hand_zone = scoped_zone("hand", actor)
        if not card_is_in_zone(state.framework.zones, card_id=card_id, zone_key=hand_zone):
            return MoveValidationResult.fail("Card not in hand", "CARD_NOT_IN_HAND")

        try:
            runtime_card = ctx.query.runtime_card(state, card_id)
        except KeyError:
            return MoveValidationResult.fail("Card definition not found", "CARD_DEFINITION_NOT_FOUND")

        if not runtime_card.definition.inkable:
            return MoveValidationResult.fail("Card is not inkable", "NOT_INKABLE")

        return MoveValidationResult.ok()

    def execute(self, state: MatchState, command: Command, ctx) -> TransitionResult:
        validation = self.validate(state, command, ctx)
        if not validation.valid:
            return TransitionResult(state=state, accepted=False, reason=validation.reason)

        actor = PlayerId(str(command.actor))
        card_id = InstanceId(command_card_id(command) or "")
        source_zone = state.framework.zones.card_index[card_id].zone_key
        destination_zone = scoped_zone("inkwell", actor)

        zones = move_card_to_zone(
            state.framework.zones,
            card_id=card_id,
            destination_zone_key=destination_zone,
            owner_id=ctx.query.owner(state, card_id),
            controller_id=actor,
        )

        current_meta = zones.card_meta.get(card_id, CardMeta())
        flags = dict(current_meta.flags)
        flags["state"] = "ready"
        flags["publicFaceState"] = "faceDown"
        flags["lastMovedBy"] = self.kind
        zones = patch_card_meta(
            zones,
            card_id,
            current_meta.with_updates(exerted=False, drying=False, flags=flags),
        )

        event = GameEvent(
            kind="card.inked",
            actor=actor,
            source=card_id,
            payload={
                "cardId": str(card_id),
                "fromZone": str(source_zone),
                "toZone": str(destination_zone),
            },
        )

        next_framework = state.framework.with_updates(
            zones=zones,
            state_id=state.framework.state_id + 1,
        )
        next_game = state.game.with_updates(
            turn_metadata=state.game.turn_metadata.record_ink(card_id),
            event_log=state.game.event_log + (event,),
        )
        next_state = MatchState(framework=next_framework, game=next_game)
        return TransitionResult(state=next_state, events=(event,), accepted=True)