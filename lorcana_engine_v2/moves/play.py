from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from lorcana_engine_v2.cards.models import CardDefinition
from lorcana_engine_v2.core.ids import InstanceId, PlayerId
from lorcana_engine_v2.core.results import LogMessage, LogVisibility, ProjectedLogEntry, RuntimeValidationResult
from lorcana_engine_v2.core.state import MatchState
from lorcana_engine_v2.core.zones import CardMeta, ZoneId, ZoneRef, scoped_zone
from lorcana_engine_v2.effects.triggered_abilities import (
    emit_triggered_lorcana_event,
    flush_triggered_events_to_bag,
)
from lorcana_engine_v2.moves.shared.execute_shift_play import execute_shift_play
from lorcana_engine_v2.resolution.action_effect_types import ActionResolutionInput
from lorcana_engine_v2.resolution.action_effects import resolve_action_effect
from lorcana_engine_v2.resolution.pending import (
    finalize_resolved_action_card,
    has_pending_action_effect_resolution,
    move_suspended_action_card_to_limbo,
    validate_no_pending_effects,
)
from lorcana_engine_v2.rules.play_card_rules import (
    BasicCost,
    ExertCostCard,
    get_available_ink,
    get_shift_rules,
    get_sing_together_threshold,
    get_singer_threshold_for_instance,
    is_ready_and_not_drying,
    is_song_card,
    pay_basic_cost,
    resolve_shift_target_candidates,
    validate_basic_cost,
)

from .registry import MoveEnumerationContext, MoveExecutionContext, MoveValidationContext, input_card_id


PLAY_CARD = "playCard"


def _current_player(context: MoveValidationContext | MoveEnumerationContext | MoveExecutionContext) -> PlayerId:
    return PlayerId(str(context.framework.state.priority.holder or context.playerId))


def _card_type(card_def: CardDefinition | None) -> str | None:
    return card_def.card_type if card_def is not None else None


def _cost(context: MoveValidationContext | MoveExecutionContext) -> str:
    return str(context.args.get("cost") or "standard")


def _card_definition(context, card_id: InstanceId | str) -> CardDefinition | None:
    try:
        return context.cards.require(card_id).definition
    except KeyError:
        return None


def _hand_cards(context, player_id: PlayerId) -> tuple[InstanceId, ...]:
    return tuple(context.framework.zones.getCards({"zone": "hand", "playerId": player_id}))


def _play_cards(context, player_id: PlayerId) -> tuple[InstanceId, ...]:
    return tuple(context.framework.zones.getCards({"zone": "play", "playerId": player_id}))


def _controlled_characters_in_play(context, player_id: PlayerId) -> tuple[InstanceId, ...]:
    return tuple(
        card_id
        for card_id in _play_cards(context, player_id)
        if _card_type(_card_definition(context, card_id)) == "character"
    )


def _standard_cost(card_def: CardDefinition) -> BasicCost:
    return BasicCost(ink=max(0, int(card_def.cost)))


def _shift_cost(card_def: CardDefinition) -> BasicCost:
    rules = get_shift_rules(card_def)
    return BasicCost(ink=max(0, int(rules.inkCost or 0)) if rules is not None else 0)


def _sing_cost(singer: InstanceId, singer_def: CardDefinition | None) -> BasicCost:
    return BasicCost(
        exertCards=(
            ExertCostCard(
                cardId=singer,
                cardType=_card_type(singer_def),
                subject="Singer",
                exhaustedErrorCode="SINGER_EXERTED",
                dryingErrorCode="SINGER_DRYING",
            ),
        )
    )


def _sing_together_cost(singers: tuple[InstanceId, ...], context) -> BasicCost:
    return BasicCost(
        exertCards=tuple(
            ExertCostCard(
                cardId=singer,
                cardType=_card_type(_card_definition(context, singer)),
                subject=f"Singer {singer}",
                exhaustedErrorCode="SINGER_EXERTED",
                dryingErrorCode="SINGER_DRYING",
            )
            for singer in singers
        )
    )


def _input_instance(context: MoveValidationContext | MoveExecutionContext, key: str) -> InstanceId | None:
    value = context.args.get(key)
    return InstanceId(str(value)) if value is not None else None


def _input_instance_tuple(context: MoveValidationContext | MoveExecutionContext, key: str) -> tuple[InstanceId, ...]:
    value = context.args.get(key)
    if value is None:
        return ()
    if isinstance(value, (list, tuple)):
        return tuple(InstanceId(str(item)) for item in value)
    return (InstanceId(str(value)),)


def _validate_action_params(context: MoveValidationContext, card_def: CardDefinition) -> RuntimeValidationResult:
    if _card_type(card_def) != "action":
        if context.args.get("preventAutoResolveTriggeredEffects") is not None:
            return RuntimeValidationResult.fail(
                "preventAutoResolveTriggeredEffects is only supported when playing an action",
                "INVALID_AUTO_RESOLVE_TRIGGERED_EFFECTS",
            )
        return RuntimeValidationResult.ok()
    if context.args.get("preventAutoResolveTriggeredEffects") is not None and not isinstance(
        context.args.get("preventAutoResolveTriggeredEffects"), bool
    ):
        return RuntimeValidationResult.fail(
            "preventAutoResolveTriggeredEffects must be a boolean when provided",
            "INVALID_AUTO_RESOLVE_TRIGGERED_EFFECTS",
        )
    if context.args.get("resolveOptional") is not None and not isinstance(context.args.get("resolveOptional"), bool):
        return RuntimeValidationResult.fail(
            "resolveOptional must be a boolean when provided",
            "INVALID_OPTIONAL_SELECTION",
        )
    choice_index = context.args.get("choiceIndex")
    if choice_index is not None and (not isinstance(choice_index, int) or choice_index < 0):
        return RuntimeValidationResult.fail(
            "choiceIndex must be a non-negative integer when provided",
            "INVALID_CHOICE_INDEX",
        )
    return RuntimeValidationResult.ok()


def _validate_cost(context: MoveValidationContext, card_id: InstanceId, card_def: CardDefinition) -> RuntimeValidationResult:
    player_id = _current_player(context)
    cost = _cost(context)
    characters = _controlled_characters_in_play(context, player_id)

    if cost == "standard":
        return validate_basic_cost(context, _standard_cost(card_def))

    if cost == "shift":
        rules = get_shift_rules(card_def)
        if rules is None:
            return RuntimeValidationResult.fail("Card does not have Shift", "NO_SHIFT_ABILITY")
        if rules.unsupportedReason:
            return RuntimeValidationResult.fail(rules.unsupportedReason, "UNSUPPORTED_SHIFT_COST")
        if rules.inkCost is None:
            return RuntimeValidationResult.fail("Shift cost could not be resolved", "INVALID_SHIFT_COST")
        cost_validation = validate_basic_cost(context, _shift_cost(card_def))
        if not cost_validation.valid:
            return cost_validation
        shift_target = _input_instance(context, "shiftTarget")
        if context.validationMode == "preflight" and shift_target is None:
            return RuntimeValidationResult.ok()
        if shift_target is None:
            return RuntimeValidationResult.fail("Invalid Shift target", "INVALID_SHIFT_TARGET")
        candidates = resolve_shift_target_candidates(
            rules,
            characters,
            lambda candidate_id: _card_definition(context, candidate_id),
        )
        if shift_target not in candidates:
            return RuntimeValidationResult.fail("Invalid Shift target", "INVALID_SHIFT_TARGET")
        return RuntimeValidationResult.ok()

    if cost == "sing":
        if not is_song_card(card_def):
            return RuntimeValidationResult.fail("Can only sing song cards", "NOT_A_SONG")
        singer = _input_instance(context, "singer")
        if context.validationMode == "preflight" and singer is None:
            return RuntimeValidationResult.ok()
        if singer is None or singer not in characters:
            return RuntimeValidationResult.fail("Singer not in play", "SINGER_NOT_IN_PLAY")
        singer_def = _card_definition(context, singer)
        if _card_type(singer_def) != "character":
            return RuntimeValidationResult.fail("Singer must be a character", "INVALID_SINGER")
        validation = validate_basic_cost(context, _sing_cost(singer, singer_def))
        if not validation.valid:
            return validation
        threshold = get_singer_threshold_for_instance(
            framework=context.framework,
            singerId=singer,
            singerDef=singer_def,
            getDefinitionByInstanceId=lambda candidate_id: _card_definition(context, candidate_id),
            G=context.G,
        )
        if threshold is None or threshold < card_def.cost:
            return RuntimeValidationResult.fail(
                f"Singer threshold {threshold or 0} is below song cost {card_def.cost}",
                "INSUFFICIENT_SINGER_THRESHOLD",
            )
        return RuntimeValidationResult.ok()

    if cost == "singTogether":
        if not is_song_card(card_def):
            return RuntimeValidationResult.fail("Can only sing song cards", "NOT_A_SONG")
        threshold = get_sing_together_threshold(card_def)
        if threshold is None:
            return RuntimeValidationResult.fail("Song does not have Sing Together", "NOT_SING_TOGETHER_SONG")
        singers = _input_instance_tuple(context, "singers")
        if context.validationMode == "preflight" and not singers:
            return RuntimeValidationResult.ok()
        if not singers:
            return RuntimeValidationResult.fail("At least one singer is required", "NO_SINGERS_SELECTED")
        if len(set(singers)) != len(singers):
            return RuntimeValidationResult.fail("Singers must be unique", "DUPLICATE_SINGERS")
        total = 0
        for singer in singers:
            if singer not in characters:
                return RuntimeValidationResult.fail(f"Singer {singer} not in play", "SINGER_NOT_IN_PLAY")
            singer_def = _card_definition(context, singer)
            singer_threshold = get_singer_threshold_for_instance(
                framework=context.framework,
                singerId=singer,
                singerDef=singer_def,
                getDefinitionByInstanceId=lambda candidate_id: _card_definition(context, candidate_id),
                G=context.G,
            )
            if singer_threshold is None:
                return RuntimeValidationResult.fail(f"Singer {singer} has no sing threshold", "INVALID_SINGER")
            total += singer_threshold
        validation = validate_basic_cost(context, _sing_together_cost(singers, context))
        if not validation.valid:
            return validation
        if total < threshold:
            return RuntimeValidationResult.fail(
                f"Singers total {total} but require {threshold}",
                "INSUFFICIENT_SING_TOGETHER_TOTAL",
            )
        return RuntimeValidationResult.ok()

    if cost == "free":
        if card_def.cost > 0:
            return RuntimeValidationResult.fail("Card cannot currently be played for free", "FREE_PLAY_NOT_AVAILABLE")
        return RuntimeValidationResult.ok()

    return RuntimeValidationResult.fail(f"Unrecognized or missing cost type: {cost!r}", "INVALID_COST_TYPE")


def _record_card_played(context: MoveExecutionContext, card_id: InstanceId, *, shifted: bool = False) -> None:
    turn_metadata = context.state.G.turnMetadata
    cards_played = turn_metadata.cardsPlayedThisTurn
    if card_id not in cards_played:
        cards_played = cards_played + (card_id,)
    shift_played = turn_metadata.shiftPlayedThisTurn
    if shifted and card_id not in shift_played:
        shift_played = shift_played + (card_id,)
    context.set_G(
        context.state.G.with_updates(
            turnMetadata=turn_metadata.__class__(
                cardsPlayedThisTurn=cards_played,
                charactersQuesting=turn_metadata.charactersQuesting,
                inkedThisTurn=turn_metadata.inkedThisTurn,
                cardsPutIntoInkwellThisTurn=turn_metadata.cardsPutIntoInkwellThisTurn,
                additionalInkwellActions=turn_metadata.additionalInkwellActions,
                shiftPlayedThisTurn=shift_played,
                challengesByPlayerThisTurn=turn_metadata.challengesByPlayerThisTurn,
                damagedCharactersByOwnerThisTurn=turn_metadata.damagedCharactersByOwnerThisTurn,
                damageRemovedByPlayerThisTurn=turn_metadata.damageRemovedByPlayerThisTurn,
                challengedCharactersThisTurn=turn_metadata.challengedCharactersThisTurn,
                banishedCharactersThisTurn=turn_metadata.banishedCharactersThisTurn,
                banishedCharactersInChallengeByOwnerThisTurn=turn_metadata.banishedCharactersInChallengeByOwnerThisTurn,
                discardCardsLeftThisTurn=turn_metadata.discardCardsLeftThisTurn,
                cardsPutIntoDiscardThisTurnByOwner=turn_metadata.cardsPutIntoDiscardThisTurnByOwner,
                pendingCostReductionsByPlayer=turn_metadata.pendingCostReductionsByPlayer,
                cardsDrawnThisTurnByPlayer=turn_metadata.cardsDrawnThisTurnByPlayer,
                cardsUnderThisTurn=turn_metadata.cardsUnderThisTurn,
            ),
            staticEffectsVersion=context.state.G.staticEffectsVersion + 1,
        )
    )


def _card_played_payload(player_id: PlayerId, card_id: InstanceId, card_def: CardDefinition, cost: str, **extra) -> dict[str, object]:
    payload: dict[str, object] = {
        "playerId": player_id,
        "cardId": card_id,
        "cardType": card_def.card_type,
        "costType": cost,
    }
    payload.update(extra)
    return payload


def _resolve_action_card(context: MoveExecutionContext, card_played: Mapping[str, object], card_def: CardDefinition) -> None:
    resolution_input = ActionResolutionInput.from_value(
        {
            "targets": context.args.get("targets"),
            "amount": context.args.get("amount"),
            "choiceIndex": context.args.get("choiceIndex"),
            "resolveOptional": context.args.get("resolveOptional"),
            "namedCard": context.args.get("namedCard"),
            "destinations": context.args.get("destinations"),
            "eventSnapshot": context.args.get("eventSnapshot"),
        }
    )
    for index, ability in enumerate(card_def.abilities):
        if ability.kind != "action":
            continue
        resolve_action_effect(
            context,
            card_played,
            ability.raw.get("effect"),
            resolution_input,
            {"sourceAbilityIndex": index},
        )
        if has_pending_action_effect_resolution(context):
            break
    if has_pending_action_effect_resolution(context):
        move_suspended_action_card_to_limbo(context, card_played)
    else:
        finalize_resolved_action_card(context, card_played)
        flush_triggered_events_to_bag(context)


@dataclass(frozen=True, slots=True)
class PlayCardMove:
    serverOnly: bool = False
    ignorePriority: bool = False
    ignoreStaleStateID: bool = False

    def available(self, context: MoveEnumerationContext) -> bool:
        if not validate_no_pending_effects(context, action_label="play cards").valid:
            return False
        player_id = _current_player(context)
        hand_cards = _hand_cards(context, player_id)
        characters = _controlled_characters_in_play(context, player_id)
        ready_singers = tuple(
            card_id for card_id in characters if is_ready_and_not_drying(context.cards.require(card_id).meta)
        )
        available_ink = get_available_ink(context, player_id)
        for card_id in hand_cards:
            card_def = _card_definition(context, card_id)
            if card_def is None:
                continue
            if available_ink >= max(0, int(card_def.cost)):
                return True
            rules = get_shift_rules(card_def)
            if rules and rules.unsupportedReason is None and rules.inkCost is not None and available_ink >= rules.inkCost:
                if resolve_shift_target_candidates(rules, characters, lambda candidate_id: _card_definition(context, candidate_id)):
                    return True
            if is_song_card(card_def):
                if any(
                    (get_singer_threshold_for_instance(
                        framework=context.framework,
                        singerId=singer,
                        singerDef=_card_definition(context, singer),
                        getDefinitionByInstanceId=lambda candidate_id: _card_definition(context, candidate_id),
                        G=context.G,
                    ) or 0) >= card_def.cost
                    for singer in ready_singers
                ):
                    return True
                if get_sing_together_threshold(card_def) is not None and ready_singers:
                    return True
        return False

    def validate(self, context: MoveValidationContext) -> RuntimeValidationResult:
        pending = validate_no_pending_effects(context, action_label="play cards")
        if not pending.valid:
            return pending
        raw_card_id = input_card_id(context)
        if context.validationMode == "preflight" and raw_card_id is None:
            return RuntimeValidationResult.ok()
        if raw_card_id is None:
            return RuntimeValidationResult.fail("Card input was not provided", "MISSING_CARD")
        player_id = _current_player(context)
        card_id = InstanceId(raw_card_id)
        if card_id not in _hand_cards(context, player_id):
            return RuntimeValidationResult.fail("Card not in hand", "CARD_NOT_IN_HAND")
        card_def = _card_definition(context, card_id)
        if card_def is None:
            return RuntimeValidationResult.fail("Card definition not found", "CARD_NOT_FOUND")
        cost_validation = _validate_cost(context, card_id, card_def)
        if not cost_validation.valid:
            return cost_validation
        return _validate_action_params(context, card_def)

    def execute(self, context: MoveExecutionContext) -> MatchState:
        card_id = InstanceId(input_card_id(context) or "")
        player_id = _current_player(context)
        cost = _cost(context)
        card_def = context.cards.require(card_id).definition
        ink_paid = 0
        singer_ids: tuple[InstanceId, ...] = ()

        if cost == "standard":
            paid = pay_basic_cost(context, _standard_cost(card_def))
            if not paid.success:
                raise RuntimeError(f"Failed to pay play cost: {paid.error} ({paid.errorCode})")
            ink_paid = paid.inkPaid
        elif cost == "shift":
            paid = pay_basic_cost(context, _shift_cost(card_def))
            if not paid.success:
                raise RuntimeError(f"Failed to pay play cost: {paid.error} ({paid.errorCode})")
            ink_paid = paid.inkPaid
        elif cost == "sing":
            singer = _input_instance(context, "singer")
            singer_ids = (singer,) if singer is not None else ()
            paid = pay_basic_cost(context, _sing_cost(singer_ids[0], _card_definition(context, singer_ids[0])))
            if not paid.success:
                raise RuntimeError(f"Failed to pay play cost: {paid.error} ({paid.errorCode})")
        elif cost == "singTogether":
            singer_ids = _input_instance_tuple(context, "singers")
            paid = pay_basic_cost(context, _sing_together_cost(singer_ids, context))
            if not paid.success:
                raise RuntimeError(f"Failed to pay play cost: {paid.error} ({paid.errorCode})")
        elif cost == "free":
            pass
        else:
            raise RuntimeError(f"playCard execute: unrecognized or missing cost type: {cost!r}")

        context.framework.zones.moveCard(card_id, ZoneRef(zone=ZoneId("play"), playerId=player_id))
        context.framework.log(
            ProjectedLogEntry(
                category="action",
                visibility=LogVisibility(mode="PUBLIC"),
                defaultMessage=LogMessage(
                    key="lorcana.move.playCard.shift"
                    if cost == "shift"
                    else "lorcana.move.playCard.sing"
                    if singer_ids
                    else "lorcana.move.playCard",
                    values={"playerId": str(player_id), "cardId": str(card_id)},
                ),
            )
        )
        _record_card_played(context, card_id, shifted=cost == "shift")
        payload_extra: dict[str, object] = {}
        if cost in {"standard", "shift"}:
            payload_extra["inkPaid"] = ink_paid
        if cost == "shift":
            shift_target = _input_instance(context, "shiftTarget")
            payload_extra.update({"shiftTargetId": shift_target, "usedShift": True})
        if singer_ids:
            payload_extra["singerIds"] = singer_ids
        card_played = _card_played_payload(player_id, card_id, card_def, cost, **payload_extra)

        if card_def.card_type == "action":
            emit_triggered_lorcana_event(
                context,
                "cardPlayed",
                card_played,
                {
                    "event": "play",
                    "playerId": player_id,
                    "subjectCardId": card_id,
                    "triggerSourceCardId": card_id,
                },
            )
            for singer_id in singer_ids:
                emit_triggered_lorcana_event(
                    context,
                    "cardPlayed",
                    card_played,
                    {
                        "event": "sing",
                        "playerId": player_id,
                        "subjectCardId": singer_id,
                        "triggerSourceCardId": card_id,
                    },
                )
                emit_triggered_lorcana_event(
                    context,
                    "cardPlayed",
                    card_played,
                    {"event": "exert", "playerId": player_id, "subjectCardId": singer_id},
                )
            _resolve_action_card(context, card_played, card_def)
            return context.state

        if cost == "shift":
            shift_target = _input_instance(context, "shiftTarget")
            if shift_target is not None:
                execute_shift_play(context, card_id, shift_target, player_id, card_def)
        elif card_def.card_type == "character":
            context.cards.setMeta(
                card_id,
                CardMeta(
                    state="ready",
                    damage=0,
                    isDrying=True,
                    publicFaceState=None,
                    atLocationId=None,
                    cardsUnder=None,
                    stackParentId=None,
                    playedViaShift=False,
                    playedCostType=cost,
                ),
            )
        else:
            context.cards.setMeta(
                card_id,
                CardMeta(
                    state=None,
                    damage=None,
                    isDrying=None,
                    publicFaceState=None,
                    atLocationId=None,
                    cardsUnder=None,
                    stackParentId=None,
                    playedViaShift=False,
                    playedCostType=cost,
                ),
            )

        emit_triggered_lorcana_event(
            context,
            "cardPlayed",
            card_played,
            {
                "event": "play",
                "playerId": player_id,
                "subjectCardId": card_id,
                "triggerSourceCardId": card_id,
            },
        )
        for singer_id in singer_ids:
            emit_triggered_lorcana_event(
                context,
                "cardPlayed",
                card_played,
                {
                    "event": "sing",
                    "playerId": player_id,
                    "subjectCardId": singer_id,
                    "triggerSourceCardId": card_id,
                },
            )
            emit_triggered_lorcana_event(
                context,
                "cardPlayed",
                card_played,
                {"event": "exert", "playerId": player_id, "subjectCardId": singer_id},
            )
        flush_triggered_events_to_bag(context)
        return context.state


__all__ = [
    "PLAY_CARD",
    "PlayCardMove",
]
