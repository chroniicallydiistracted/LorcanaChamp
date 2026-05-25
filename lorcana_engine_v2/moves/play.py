from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace

from lorcana_engine_v2.cards.models import CardDefinition
from lorcana_engine_v2.core.ids import InstanceId, PlayerId
from lorcana_engine_v2.core.results import LogMessage, LogVisibility, ProjectedLogEntry, RuntimeValidationResult
from lorcana_engine_v2.core.state import MatchState
from lorcana_engine_v2.core.zones import CardMeta, ZoneId, ZoneRef, base_zone_from_key, scoped_zone
from lorcana_engine_v2.effects.play_from_under_permissions import get_active_play_from_under_permissions
from lorcana_engine_v2.effects.temporary_effects import (
    has_temporary_player_restriction,
    has_temporary_restriction,
)
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
    ShiftDiscardCost,
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
from lorcana_engine_v2.registries.static_registry import StaticRegistry

from .registry import MoveEnumerationContext, MoveExecutionContext, MoveValidationContext, input_card_id


PLAY_CARD = "playCard"


def _current_player(context: MoveValidationContext | MoveEnumerationContext | MoveExecutionContext) -> PlayerId:
    return PlayerId(str(context.framework.state.priority.holder or context.playerId))


def _state_from_context(context: MoveValidationContext | MoveEnumerationContext | MoveExecutionContext) -> MatchState:
    state = getattr(context, "state", None)
    if isinstance(state, MatchState):
        return state
    getter = getattr(context.cards, "_state_getter", None)
    if callable(getter):
        found = getter()
        if isinstance(found, MatchState):
            return found
    raise TypeError("playCard requires a Lorcanito runtime state context")


def _resources_from_context(context) -> object | None:
    query = getattr(context.cards, "_query", None)
    return getattr(query, "resources", None)


def _static_registry(context: MoveValidationContext | MoveEnumerationContext | MoveExecutionContext):
    query = getattr(context.cards, "_query", None)
    if query is None:
        return None
    return StaticRegistry().build(_state_from_context(context), query)


def _current_turn(context: MoveValidationContext | MoveEnumerationContext | MoveExecutionContext) -> int:
    turn = context.framework.state.status.turn
    return turn if isinstance(turn, int) and turn > 0 else 1


def _card_type(card_def: CardDefinition | None) -> str | None:
    return card_def.card_type if card_def is not None else None


def _cost(context: MoveValidationContext | MoveExecutionContext) -> str:
    return str(context.args.get("cost") or "standard")


def _card_definition(context, card_id: InstanceId | str) -> CardDefinition | None:
    try:
        return context.cards.require(card_id).definition
    except KeyError:
        return None


def _card_zone_base(context, card_id: InstanceId | str) -> str | None:
    try:
        zone_id = context.framework.zones.getCardZone(card_id)
    except Exception:
        return None
    return str(base_zone_from_key(zone_id)) if zone_id is not None else None


def _card_owner(context, card_id: InstanceId | str) -> PlayerId | None:
    try:
        return PlayerId(str(context.framework.zones.getCardOwner(card_id)))
    except Exception:
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


def _shift_cost(card_def: CardDefinition, reduction: int = 0) -> BasicCost:
    rules = get_shift_rules(card_def)
    return BasicCost(ink=max(0, int(rules.inkCost or 0) - reduction) if rules is not None else 0)


def _pending_cost_reductions(context, player_id: PlayerId, card_def: CardDefinition, play_method: str | None) -> tuple[int, tuple[int, ...]]:
    entries = tuple(context.G.turnMetadata.pendingCostReductionsByPlayer.get(player_id, ()))
    current_turn = _current_turn(context)
    total = 0
    consume_indexes: list[int] = []
    for index, raw in enumerate(entries):
        if not isinstance(raw, Mapping):
            continue
        expires = raw.get("expiresAtTurn")
        if isinstance(expires, int) and expires < current_turn:
            continue
        card_type = raw.get("cardType")
        if card_type is not None:
            allowed = {str(item) for item in card_type} if isinstance(card_type, Sequence) and not isinstance(card_type, (str, bytes, bytearray)) else {str(card_type)}
            is_song = is_song_card(card_def)
            if card_def.card_type not in allowed and not (is_song and "song" in allowed):
                continue
        classification = raw.get("classification")
        if classification and not any(str(item).lower() == str(classification).lower() for item in card_def.classifications):
            continue
        entry_method = raw.get("playMethod")
        if entry_method not in {None, "either", play_method}:
            continue
        amount = raw.get("amount")
        if isinstance(amount, int):
            total += max(0, amount)
            if raw.get("consumeOnUse") is True:
                consume_indexes.append(index)
    return total, tuple(consume_indexes)


def _static_cost_delta(context, card_id: InstanceId, card_def: CardDefinition, play_method: str | None) -> tuple[int, int]:
    registry = _static_registry(context)
    reduction = 0
    increase = 0
    if registry is not None:
        for effect in registry.get_effects_for_player(_current_player(context), kind="cost-reduction"):
            payload = getattr(effect, "payload", {})
            if not isinstance(payload, Mapping):
                continue
            effect_method = payload.get("playMethod")
            if effect_method not in {None, "either", play_method}:
                continue
            card_type = payload.get("cardType")
            if card_type is not None:
                allowed = {str(item) for item in card_type} if isinstance(card_type, Sequence) and not isinstance(card_type, (str, bytes, bytearray)) else {str(card_type)}
                if card_def.card_type not in allowed and not (is_song_card(card_def) and "song" in allowed):
                    continue
            classification = payload.get("classification")
            if classification and not any(str(item).lower() == str(classification).lower() for item in card_def.classifications):
                continue
            card_name = payload.get("cardName")
            if card_name and str(card_name).lower() not in {card_def.name.lower(), card_def.full_name.lower()}:
                continue
            amount = payload.get("amount", payload.get("reduction", 0))
            if isinstance(amount, int):
                reduction += max(0, amount)
        for effect in registry.globalEffects:
            if getattr(effect, "kind", None) != "cost-increase":
                continue
            payload = getattr(effect, "payload", {})
            if not isinstance(payload, Mapping):
                continue
            card_type = payload.get("cardType")
            if card_type is not None:
                allowed = {str(item) for item in card_type} if isinstance(card_type, Sequence) and not isinstance(card_type, (str, bytes, bytearray)) else {str(card_type)}
                if card_def.card_type not in allowed and not (is_song_card(card_def) and "song" in allowed):
                    continue
            amount = payload.get("amount", 0)
            if isinstance(amount, int):
                increase += max(0, amount)
    pending_reduction, _ = _pending_cost_reductions(context, _current_player(context), card_def, play_method)
    _ = card_id
    return reduction + pending_reduction, increase


def _effective_standard_cost(context, card_id: InstanceId, card_def: CardDefinition) -> BasicCost:
    reduction, increase = _static_cost_delta(context, card_id, card_def, "standard")
    return BasicCost(ink=max(0, int(card_def.cost) - reduction + increase))


def _consume_pending_cost_reductions(context: MoveExecutionContext, player_id: PlayerId, card_def: CardDefinition, play_method: str | None) -> None:
    _, consume_indexes = _pending_cost_reductions(context, player_id, card_def, play_method)
    if not consume_indexes:
        return
    current_turn = _current_turn(context)
    consume_set = set(consume_indexes)
    current = tuple(context.state.G.turnMetadata.pendingCostReductionsByPlayer.get(player_id, ()))
    remaining = tuple(
        entry
        for index, entry in enumerate(current)
        if index not in consume_set
        and not (isinstance(entry, Mapping) and isinstance(entry.get("expiresAtTurn"), int) and entry.get("expiresAtTurn") < current_turn)
    )
    pending_by_player = dict(context.state.G.turnMetadata.pendingCostReductionsByPlayer)
    pending_by_player[player_id] = remaining
    context.set_G(
        context.state.G.with_updates(
            turnMetadata=replace(
                context.state.G.turnMetadata,
                pendingCostReductionsByPlayer=pending_by_player,
            )
        )
    )


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


def _source_is_playable(context: MoveValidationContext, card_id: InstanceId, player_id: PlayerId, card_def: CardDefinition) -> RuntimeValidationResult:
    if card_id in _hand_cards(context, player_id):
        return RuntimeValidationResult.ok()
    if _card_zone_base(context, card_id) != "limbo":
        return RuntimeValidationResult.fail("Card not in hand", "CARD_NOT_IN_HAND")
    if _card_owner(context, card_id) != player_id:
        return RuntimeValidationResult.fail("Card not in hand", "CARD_NOT_IN_HAND")
    meta = context.cards.require(card_id).meta
    source_item_id = getattr(meta, "stackParentId", None)
    if source_item_id is None:
        return RuntimeValidationResult.fail("Card not in hand", "CARD_NOT_IN_HAND")
    permissions = get_active_play_from_under_permissions(
        context.G.playFromUnderPermissions,
        player_id,
        _current_turn(context),
    )
    permission = next((item for item in permissions if item.sourceItemId == str(source_item_id)), None)
    if permission is None:
        return RuntimeValidationResult.fail("Card not in hand", "CARD_NOT_IN_HAND")
    if permission.cardType and permission.cardType != card_def.card_type:
        return RuntimeValidationResult.fail("Card type not allowed by play-from-under permission", "CARD_NOT_IN_HAND")
    return RuntimeValidationResult.ok()


def _has_static_player_restriction(context, player_id: PlayerId, restriction: str, card_def: CardDefinition) -> bool:
    registry = _static_registry(context)
    if registry is None:
        return False
    for effect in registry.get_effects_for_player(player_id, kind="restriction"):
        payload = getattr(effect, "payload", {})
        if isinstance(payload, Mapping) and payload.get("restriction") == restriction:
            min_cost = payload.get("minCost")
            if isinstance(min_cost, int) and card_def.cost < min_cost:
                continue
            card_type = payload.get("cardType")
            if card_type is not None:
                allowed = {str(item) for item in card_type} if isinstance(card_type, Sequence) and not isinstance(card_type, (str, bytes, bytearray)) else {str(card_type)}
                if card_def.card_type not in allowed and not (is_song_card(card_def) and "song" in allowed):
                    continue
            return True
    for effect in registry.globalEffects:
        if getattr(effect, "kind", None) != "restriction":
            continue
        payload = getattr(effect, "payload", {})
        if not isinstance(payload, Mapping) or payload.get("restriction") != restriction:
            continue
        card_type = payload.get("cardType")
        if card_type is None:
            return True
        allowed = {str(item) for item in card_type} if isinstance(card_type, Sequence) and not isinstance(card_type, (str, bytes, bytearray)) else {str(card_type)}
        if card_def.card_type in allowed or (is_song_card(card_def) and "song" in allowed):
            return True
    return False


def _has_static_card_restriction(context, card_id: InstanceId, restriction: str) -> bool:
    registry = _static_registry(context)
    if registry is None:
        return False
    return any(
        getattr(effect, "kind", None) == "restriction"
        and isinstance(getattr(effect, "payload", {}), Mapping)
        and getattr(effect, "payload", {}).get("restriction") == restriction
        for effect in registry.get_effects_for_card(card_id, kind="restriction")
    )


def _self_play_condition_error(context: MoveValidationContext, player_id: PlayerId, card_id: InstanceId, card_def: CardDefinition) -> RuntimeValidationResult | None:
    resources = _resources_from_context(context)
    if resources is None:
        return None
    from lorcana_engine_v2.core.context import build_rules_context
    from lorcana_engine_v2.rules.condition_evaluator import ConditionContext, ConditionEvaluator

    rules_ctx = build_rules_context(resources)
    for ability in card_def.abilities:
        if ability.kind != "static":
            continue
        effect = ability.raw.get("effect")
        if not isinstance(effect, Mapping) or effect.get("type") != "self-play-condition":
            continue
        condition = ability.raw.get("condition")
        if condition is None:
            continue
        if not ConditionEvaluator().evaluate(
            _state_from_context(context),
            rules_ctx,
            condition,
            ConditionContext(actor=player_id, source_id=card_id),
        ):
            return RuntimeValidationResult.fail("Card cannot be played: play condition not met", "SELF_PLAY_CONDITION_NOT_MET")
    return None


def _can_use_shift_ability(context: MoveValidationContext, player_id: PlayerId, card_id: InstanceId, card_def: CardDefinition) -> bool:
    shift_ability = next(
        (
            ability
            for ability in card_def.abilities
            if ability.kind == "keyword" and ability.raw.get("keyword") == "Shift" and ability.raw.get("condition") is not None
        ),
        None,
    )
    if shift_ability is None:
        return True
    resources = _resources_from_context(context)
    if resources is None:
        return False
    from lorcana_engine_v2.core.context import build_rules_context
    from lorcana_engine_v2.rules.condition_evaluator import ConditionContext, ConditionEvaluator

    return ConditionEvaluator().evaluate(
        _state_from_context(context),
        build_rules_context(resources),
        shift_ability.raw.get("condition"),
        ConditionContext(actor=player_id, source_id=card_id),
    )


def _validate_play_restrictions(context: MoveValidationContext, player_id: PlayerId, card_id: InstanceId, card_def: CardDefinition) -> RuntimeValidationResult:
    current_turn = _current_turn(context)
    restrictions = context.G.temporaryPlayerRestrictions
    if has_temporary_player_restriction(restrictions, player_id, current_turn, "cant-play"):
        return RuntimeValidationResult.fail("Player cannot play cards due to an active restriction", "PLAYER_PLAY_RESTRICTED")
    typed_restrictions = {
        "action": "cant-play-actions",
        "item": "cant-play-items",
        "character": "cant-play-characters",
    }
    restriction = typed_restrictions.get(card_def.card_type)
    if restriction and has_temporary_player_restriction(restrictions, player_id, current_turn, restriction):
        return RuntimeValidationResult.fail("Player cannot play this card type due to an active restriction", "PLAYER_PLAY_RESTRICTED")
    if restriction and _has_static_player_restriction(context, player_id, restriction, card_def):
        return RuntimeValidationResult.fail("Player cannot play this card type due to a static restriction", "PLAYER_PLAY_RESTRICTED")
    self_condition = _self_play_condition_error(context, player_id, card_id, card_def)
    if self_condition is not None:
        return self_condition
    return RuntimeValidationResult.ok()


def _action_alternative_cost_ability(card_def: CardDefinition, alternative_cost: str):
    return next(
        (
            ability
            for ability in card_def.abilities
            if ability.kind == "action" and ability.raw.get("alternativeCost") == alternative_cost
        ),
        None,
    )


def _discard_cards_for_shift(context: MoveValidationContext | MoveExecutionContext) -> tuple[InstanceId, ...]:
    return _input_instance_tuple(context, "discardCards")


def _validate_shift_discard_cost(
    context: MoveValidationContext,
    discard_cost: ShiftDiscardCost,
    player_id: PlayerId,
) -> RuntimeValidationResult:
    discard_cards = _discard_cards_for_shift(context)
    if context.validationMode == "preflight" and not discard_cards:
        return RuntimeValidationResult.ok()
    if len(discard_cards) < discard_cost.discardCards:
        return RuntimeValidationResult.fail(
            f"Shift requires discarding {discard_cost.discardCards} card(s)",
            "SHIFT_DISCARD_REQUIRED",
        )
    hand = set(_hand_cards(context, player_id))
    for discard_card in discard_cards[: discard_cost.discardCards]:
        if discard_card not in hand:
            return RuntimeValidationResult.fail("Discard card is not in hand", "SHIFT_DISCARD_NOT_IN_HAND")
        if discard_cost.discardCardType:
            discard_def = _card_definition(context, discard_card)
            matches = is_song_card(discard_def) if discard_cost.discardCardType == "song" else _card_type(discard_def) == discard_cost.discardCardType
            if not matches:
                return RuntimeValidationResult.fail(
                    f"Shift requires discarding a {discard_cost.discardCardType} card",
                    "SHIFT_DISCARD_WRONG_TYPE",
                )
    return RuntimeValidationResult.ok()


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
        return validate_basic_cost(context, _effective_standard_cost(context, card_id, card_def))

    if cost == "shift":
        rules = get_shift_rules(card_def)
        if rules is None:
            return RuntimeValidationResult.fail("Card does not have Shift", "NO_SHIFT_ABILITY")
        if not _can_use_shift_ability(context, player_id, card_id, card_def):
            return RuntimeValidationResult.fail("Shift condition is not met", "NO_SHIFT_ABILITY")
        if rules.unsupportedReason:
            return RuntimeValidationResult.fail(rules.unsupportedReason, "UNSUPPORTED_SHIFT_COST")
        if rules.discardCost is not None:
            discard_validation = _validate_shift_discard_cost(context, rules.discardCost, player_id)
            if not discard_validation.valid:
                return discard_validation
        else:
            if rules.inkCost is None:
                return RuntimeValidationResult.fail("Shift cost could not be resolved", "INVALID_SHIFT_COST")
            shift_reduction, _ = _static_cost_delta(context, card_id, card_def, "shift")
            cost_validation = validate_basic_cost(context, _shift_cost(card_def, shift_reduction))
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
        if _has_static_card_restriction(context, singer, "cant-sing") or has_temporary_restriction(
            context.cards.require(singer).meta,
            _current_turn(context),
            "cant-sing",
        ):
            return RuntimeValidationResult.fail("Singer has cant-sing restriction", "CANT_SING_RESTRICTION")
        validation = validate_basic_cost(context, _sing_cost(singer, singer_def))
        if not validation.valid:
            return validation
        threshold = get_singer_threshold_for_instance(
            framework=context.framework,
            singerId=singer,
            singerDef=singer_def,
            getDefinitionByInstanceId=lambda candidate_id: _card_definition(context, candidate_id),
            G=context.G,
            registry=_static_registry(context),
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
            if _has_static_card_restriction(context, singer, "cant-sing") or has_temporary_restriction(
                context.cards.require(singer).meta,
                _current_turn(context),
                "cant-sing",
            ):
                return RuntimeValidationResult.fail(f"Singer {singer} has cant-sing restriction", "CANT_SING_RESTRICTION")
            singer_threshold = get_singer_threshold_for_instance(
                framework=context.framework,
                singerId=singer,
                singerDef=singer_def,
                getDefinitionByInstanceId=lambda candidate_id: _card_definition(context, candidate_id),
                G=context.G,
                registry=_static_registry(context),
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

    if cost == "sacrifice":
        if _action_alternative_cost_ability(card_def, "sacrifice-item") is None:
            return RuntimeValidationResult.fail("Card does not have a sacrifice alternative cost ability", "NO_SACRIFICE_ABILITY")
        sacrifice_target = _input_instance(context, "sacrificeTarget")
        if sacrifice_target is None:
            return RuntimeValidationResult.fail("Sacrifice cost requires a valid sacrificeTarget", "MISSING_SACRIFICE_TARGET")
        sacrifice_def = _card_definition(context, sacrifice_target)
        if _card_type(sacrifice_def) != "item":
            return RuntimeValidationResult.fail("Sacrifice target must be an item", "SACRIFICE_TARGET_NOT_ITEM")
        if _card_zone_base(context, sacrifice_target) != "play" or _card_owner(context, sacrifice_target) != player_id:
            return RuntimeValidationResult.fail("Sacrifice target must be an item you control in play", "SACRIFICE_TARGET_NOT_IN_PLAY")
        return RuntimeValidationResult.ok()

    if cost == "exert-items":
        if _action_alternative_cost_ability(card_def, "exert-4-items") is None:
            return RuntimeValidationResult.fail("Card does not have an exert-items alternative cost ability", "NO_EXERT_ITEMS_ABILITY")
        exert_targets = _input_instance_tuple(context, "exertTargets")
        if len(exert_targets) != 4 or len(set(exert_targets)) != 4:
            return RuntimeValidationResult.fail("Exert cost requires exactly 4 unique exertTargets", "INVALID_EXERT_TARGETS_COUNT")
        for exert_target in exert_targets:
            exert_def = _card_definition(context, exert_target)
            if _card_type(exert_def) != "item":
                return RuntimeValidationResult.fail("Exert target must be an item", "EXERT_TARGET_NOT_ITEM")
            if _card_zone_base(context, exert_target) != "play" or _card_owner(context, exert_target) != player_id:
                return RuntimeValidationResult.fail("Exert target must be an item you control in play", "EXERT_TARGET_NOT_IN_PLAY")
            if context.cards.require(exert_target).meta.state == "exerted":
                return RuntimeValidationResult.fail("Exert target must be a ready item", "EXERT_TARGET_MUST_BE_READY")
        return RuntimeValidationResult.ok()

    if cost == "put-on-deck-bottom":
        if _action_alternative_cost_ability(card_def, "put-toy-character-on-deck-bottom") is None:
            return RuntimeValidationResult.fail("Card does not have a put-on-deck-bottom alternative cost ability", "NO_PUT_ON_DECK_BOTTOM_ABILITY")
        deck_bottom_target = _input_instance(context, "deckBottomTarget")
        if deck_bottom_target is None:
            return RuntimeValidationResult.fail("Put-on-deck-bottom cost requires a valid deckBottomTarget", "MISSING_DECK_BOTTOM_TARGET")
        target_def = _card_definition(context, deck_bottom_target)
        if _card_type(target_def) != "character":
            return RuntimeValidationResult.fail("Put-on-deck-bottom target must be a character card", "PUT_ON_DECK_BOTTOM_TARGET_NOT_CHARACTER")
        if target_def is None or not any(item == "Toy" for item in target_def.classifications):
            return RuntimeValidationResult.fail("Put-on-deck-bottom target must be a Toy character card", "PUT_ON_DECK_BOTTOM_TARGET_NOT_TOY")
        if _card_zone_base(context, deck_bottom_target) != "discard" or _card_owner(context, deck_bottom_target) != player_id:
            return RuntimeValidationResult.fail("Put-on-deck-bottom target must be in your discard", "PUT_ON_DECK_BOTTOM_TARGET_NOT_IN_DISCARD")
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


def _enters_with_damage_amount(card_def: CardDefinition) -> int:
    if card_def.card_type != "character":
        return 0
    total = 0
    for ability in card_def.abilities:
        effect = ability.raw.get("effect")
        if not isinstance(effect, Mapping) or effect.get("type") != "enters-with-damage":
            continue
        amount = effect.get("amount")
        if isinstance(amount, int):
            total += max(0, amount)
    return total


def _detach_from_parent_if_playing_from_under(context: MoveExecutionContext, card_id: InstanceId) -> None:
    meta = context.cards.getMeta(card_id)
    parent_id = meta.stackParentId
    if parent_id is None:
        return
    parent_meta = context.cards.getMeta(parent_id)
    cards_under = tuple(item for item in (parent_meta.cardsUnder or ()) if item != card_id)
    context.cards.patchMeta(parent_id, {"cardsUnder": cards_under or None})
    context.cards.patchMeta(card_id, {"stackParentId": None})


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
        condition = ability.raw.get("condition")
        if condition is not None:
            resources = _resources_from_context(context)
            if resources is not None:
                from lorcana_engine_v2.core.context import build_rules_context
                from lorcana_engine_v2.rules.condition_evaluator import ConditionContext, ConditionEvaluator

                if not ConditionEvaluator().evaluate(
                    context.state,
                    build_rules_context(resources),
                    condition,
                    ConditionContext(
                        actor=PlayerId(str(card_played.get("playerId", context.playerId))),
                        source_id=InstanceId(str(card_played.get("cardId", ""))),
                        event_payload={"eventSnapshot": dict(resolution_input.eventSnapshot)},
                    ),
                ):
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
                        registry=_static_registry(context),
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
        card_def = _card_definition(context, card_id)
        if card_def is None:
            return RuntimeValidationResult.fail("Card definition not found", "CARD_NOT_FOUND")
        source_validation = _source_is_playable(context, card_id, player_id, card_def)
        if not source_validation.valid:
            return source_validation
        restrictions = _validate_play_restrictions(context, player_id, card_id, card_def)
        if not restrictions.valid:
            return restrictions
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
            paid = pay_basic_cost(context, _effective_standard_cost(context, card_id, card_def))
            if not paid.success:
                raise RuntimeError(f"Failed to pay play cost: {paid.error} ({paid.errorCode})")
            ink_paid = paid.inkPaid
        elif cost == "shift":
            rules = get_shift_rules(card_def)
            if rules is None or rules.unsupportedReason:
                raise RuntimeError(rules.unsupportedReason if rules else "Card does not have Shift")
            if rules.discardCost is not None:
                discard_cards = _discard_cards_for_shift(context)[: rules.discardCost.discardCards]
                for discard_id in discard_cards:
                    context.framework.zones.moveCard(discard_id, ZoneRef(zone=ZoneId("discard"), playerId=player_id))
                ink_paid = 0
            else:
                shift_reduction, _ = _static_cost_delta(context, card_id, card_def, "shift")
                paid = pay_basic_cost(context, _shift_cost(card_def, shift_reduction))
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
        elif cost == "sacrifice":
            sacrifice_target = _input_instance(context, "sacrificeTarget")
            if sacrifice_target is None:
                raise RuntimeError("Sacrifice cost requires sacrificeTarget")
            context.framework.zones.moveCard(sacrifice_target, ZoneRef(zone=ZoneId("discard"), playerId=player_id))
            context.cards.clearMeta(sacrifice_target)
        elif cost == "exert-items":
            for exert_target in _input_instance_tuple(context, "exertTargets"):
                context.cards.patchMeta(exert_target, {"state": "exerted"})
        elif cost == "put-on-deck-bottom":
            deck_bottom_target = _input_instance(context, "deckBottomTarget")
            if deck_bottom_target is None:
                raise RuntimeError("Put-on-deck-bottom cost requires deckBottomTarget")
            context.framework.zones.moveCard(
                deck_bottom_target,
                ZoneRef(zone=ZoneId("deck"), playerId=player_id),
                index=0,
            )
        else:
            raise RuntimeError(f"playCard execute: unrecognized or missing cost type: {cost!r}")

        if cost in {"standard", "shift"}:
            _consume_pending_cost_reductions(context, player_id, card_def, cost)
        _detach_from_parent_if_playing_from_under(context, card_id)
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
                if execute_shift_play(context, card_id, shift_target, player_id, card_def):
                    return context.state
        elif card_def.card_type == "character":
            context.cards.setMeta(
                card_id,
                CardMeta(
                    state="ready",
                    damage=_enters_with_damage_amount(card_def),
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
