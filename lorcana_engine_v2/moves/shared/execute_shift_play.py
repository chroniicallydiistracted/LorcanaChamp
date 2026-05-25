from __future__ import annotations

from dataclasses import replace

from lorcana_engine_v2.cards.models import CardDefinition
from lorcana_engine_v2.core.ids import InstanceId, PlayerId
from lorcana_engine_v2.core.state import ContinuousEffectState
from lorcana_engine_v2.core.zones import CardMeta, ZoneId, ZoneRef
from lorcana_engine_v2.effects.triggered_abilities import (
    emit_triggered_lorcana_event,
    flush_triggered_events_to_bag,
)


def _cards_under(meta: CardMeta | None) -> tuple[InstanceId, ...]:
    return tuple(getattr(meta, "cardsUnder", None) or ())


def attach_shift_stack(
    context,
    new_top_id: InstanceId | str,
    old_top_id: InstanceId | str,
    owner_id: PlayerId | str,
    inherited_meta: CardMeta | None = None,
) -> None:
    new_id = InstanceId(str(new_top_id))
    old_id = InstanceId(str(old_top_id))
    player = PlayerId(str(owner_id))
    old_meta = context.cards.getMeta(old_id)
    inherited = inherited_meta or old_meta
    cards_under = (old_id,) + _cards_under(old_meta)

    context.framework.zones.moveCard(old_id, {"zone": "limbo", "playerId": player})
    context.cards.setMeta(
        new_id,
        CardMeta(
            state=inherited.state,
            damage=inherited.damage,
            isDrying=inherited.isDrying,
            publicFaceState=inherited.publicFaceState,
            atLocationId=inherited.atLocationId,
            cardsUnder=cards_under,
            stackParentId=None,
            temporaryKeywords=inherited.temporaryKeywords,
            temporaryKeywordStarts=inherited.temporaryKeywordStarts,
            temporaryKeywordValues=inherited.temporaryKeywordValues,
            temporaryKeywordPayloads=inherited.temporaryKeywordPayloads,
            temporaryLostKeywords=inherited.temporaryLostKeywords,
            temporaryLostKeywordStarts=inherited.temporaryLostKeywordStarts,
            temporaryClassifications=inherited.temporaryClassifications,
            temporaryClassificationStarts=inherited.temporaryClassificationStarts,
            temporaryAbilities=inherited.temporaryAbilities,
            temporaryAbilityStarts=inherited.temporaryAbilityStarts,
            temporaryAbilityPayloads=inherited.temporaryAbilityPayloads,
            temporaryRestrictions=inherited.temporaryRestrictions,
            temporaryRestrictionStarts=inherited.temporaryRestrictionStarts,
            temporaryRestrictionPayloads=inherited.temporaryRestrictionPayloads,
            replacementAbilities=inherited.replacementAbilities,
        ),
    )
    for under_id in cards_under:
        context.cards.setMeta(
            under_id,
            CardMeta(stackParentId=new_id),
        )


def _enters_with_damage_amount(card_def: CardDefinition) -> int:
    if card_def.card_type != "character":
        return 0
    total = 0
    for ability in card_def.abilities:
        effect = ability.raw.get("effect")
        if not isinstance(effect, dict) or effect.get("type") != "enters-with-damage":
            continue
        amount = effect.get("amount")
        if isinstance(amount, int):
            total += max(0, amount)
    return total


def _rebuild_continuous_by_target(instances: tuple[object, ...]):
    buckets: dict[InstanceId, list[object]] = {}
    for instance in instances:
        target_id = getattr(instance, "targetId", None)
        if target_id is not None:
            buckets.setdefault(InstanceId(str(target_id)), []).append(instance)
    return {target_id: tuple(values) for target_id, values in buckets.items()}


def _retarget_continuous_effects(context, old_top_id: InstanceId, new_top_id: InstanceId) -> None:
    continuous = context.state.G.continuousEffects
    changed = False
    instances: list[object] = []
    for instance in continuous.instances:
        if getattr(instance, "targetId", None) == old_top_id:
            instances.append(replace(instance, targetId=new_top_id))
            changed = True
        else:
            instances.append(instance)
    if not changed:
        return
    next_instances = tuple(instances)
    context.set_G(
        context.state.G.with_updates(
            continuousEffects=ContinuousEffectState(
                nextSeq=continuous.nextSeq,
                instances=next_instances,
                byTarget=_rebuild_continuous_by_target(next_instances),
            ),
            staticEffectsVersion=context.state.G.staticEffectsVersion + 1,
        )
    )


def _stacked_card_ids(context, card_id: InstanceId) -> tuple[InstanceId, ...]:
    meta = context.cards.getMeta(card_id)
    return (card_id,) + tuple(meta.cardsUnder or ())


def _move_stack_to_discard(context, card_id: InstanceId, player_id: PlayerId) -> None:
    for stacked_id in _stacked_card_ids(context, card_id):
        context.framework.zones.moveCard(stacked_id, ZoneRef(zone=ZoneId("discard"), playerId=player_id))
    for stacked_id in _stacked_card_ids(context, card_id):
        context.cards.clearMeta(stacked_id)


def _record_banished_character(context, card_id: InstanceId) -> None:
    turn_metadata = context.state.G.turnMetadata
    banished = turn_metadata.banishedCharactersThisTurn
    if card_id not in banished:
        banished = banished + (card_id,)
    context.set_G(
        context.state.G.with_updates(
            turnMetadata=turn_metadata.__class__(
                cardsPlayedThisTurn=turn_metadata.cardsPlayedThisTurn,
                charactersQuesting=turn_metadata.charactersQuesting,
                inkedThisTurn=turn_metadata.inkedThisTurn,
                cardsPutIntoInkwellThisTurn=turn_metadata.cardsPutIntoInkwellThisTurn,
                additionalInkwellActions=turn_metadata.additionalInkwellActions,
                shiftPlayedThisTurn=turn_metadata.shiftPlayedThisTurn,
                challengesByPlayerThisTurn=turn_metadata.challengesByPlayerThisTurn,
                damagedCharactersByOwnerThisTurn=turn_metadata.damagedCharactersByOwnerThisTurn,
                damageRemovedByPlayerThisTurn=turn_metadata.damageRemovedByPlayerThisTurn,
                challengedCharactersThisTurn=turn_metadata.challengedCharactersThisTurn,
                banishedCharactersThisTurn=banished,
                banishedCharactersInChallengeByOwnerThisTurn=turn_metadata.banishedCharactersInChallengeByOwnerThisTurn,
                discardCardsLeftThisTurn=turn_metadata.discardCardsLeftThisTurn,
                cardsPutIntoDiscardThisTurnByOwner=turn_metadata.cardsPutIntoDiscardThisTurnByOwner,
                pendingCostReductionsByPlayer=turn_metadata.pendingCostReductionsByPlayer,
                cardsDrawnThisTurnByPlayer=turn_metadata.cardsDrawnThisTurnByPlayer,
                cardsUnderThisTurn=turn_metadata.cardsUnderThisTurn,
            )
        )
    )


def execute_shift_play(
    context,
    card_id: InstanceId | str,
    shift_target: InstanceId | str,
    player_id: PlayerId | str,
    card_def: CardDefinition,
    *,
    enters_exerted: bool = False,
) -> bool:
    new_id = InstanceId(str(card_id))
    old_id = InstanceId(str(shift_target))
    player = PlayerId(str(player_id))
    attach_shift_stack(context, new_id, old_id, player, context.cards.getMeta(old_id))
    _retarget_continuous_effects(context, old_id, new_id)
    shifted_meta = context.cards.getMeta(new_id)
    inherited_damage = int(shifted_meta.damage or 0) + _enters_with_damage_amount(card_def)
    context.cards.setMeta(
        new_id,
        shifted_meta.with_updates(
            state="exerted" if enters_exerted else shifted_meta.state,
            damage=inherited_damage,
            playedViaShift=True,
            playedCostType="shift",
        ),
    )
    query = getattr(context.cards, "_query", None)
    resources = getattr(query, "resources", None)
    if resources is not None:
        from lorcana_engine_v2.rules.queries import QueryService

        effective_willpower = QueryService(resources, actorPlayerId=player, cacheViews=False).runtime_card(context.state, new_id).willpower
    else:
        effective_willpower = int(card_def.willpower or 0)
    if effective_willpower > 0 and inherited_damage >= effective_willpower:
        _move_stack_to_discard(context, new_id, player)
        emit_triggered_lorcana_event(
            context,
            "cardBanished",
            {"cardId": new_id, "sourceId": None, "reason": "lethal damage"},
            {
                "event": "banish",
                "playerId": player,
                "subjectCardId": new_id,
                "triggerSourceCardId": new_id,
            },
        )
        _record_banished_character(context, new_id)
        flush_triggered_events_to_bag(context)
        return True
    return False


__all__ = ["attach_shift_stack", "execute_shift_play"]
