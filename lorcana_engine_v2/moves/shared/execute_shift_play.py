from __future__ import annotations

from lorcana_engine_v2.cards.models import CardDefinition
from lorcana_engine_v2.core.ids import InstanceId, PlayerId
from lorcana_engine_v2.core.zones import CardMeta


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


def execute_shift_play(
    context,
    card_id: InstanceId | str,
    shift_target: InstanceId | str,
    player_id: PlayerId | str,
    card_def: CardDefinition,
    *,
    enters_exerted: bool = False,
) -> bool:
    _ = card_def
    attach_shift_stack(context, card_id, shift_target, player_id, context.cards.getMeta(shift_target))
    shifted_meta = context.cards.getMeta(card_id)
    context.cards.setMeta(
        card_id,
        shifted_meta.with_updates(
            state="exerted" if enters_exerted else shifted_meta.state,
            playedViaShift=True,
            playedCostType="shift",
        ),
    )
    return False


__all__ = ["attach_shift_stack", "execute_shift_play"]
