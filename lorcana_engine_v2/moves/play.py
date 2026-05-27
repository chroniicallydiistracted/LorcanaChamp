from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace

from lorcana_engine_v2.cards.models import CardDefinition
from lorcana_engine_v2.core.ids import InstanceId, PlayerId
from lorcana_engine_v2.core.results import LogMessage, LogVisibility, ProjectedLogEntry, RuntimeValidationResult
from lorcana_engine_v2.core.state import MatchState
from lorcana_engine_v2.core.turn_owner import require_current_player_for_move, resolve_current_player_for_move
from lorcana_engine_v2.core.zones import CardMeta, ZoneId, ZoneRef, base_zone_from_key, scoped_zone
from lorcana_engine_v2.effects.win_condition_effects import recompute_lore_to_win
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
from lorcana_engine_v2.resolution.action_card_resolver import resolve_action_card_effects
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
from lorcana_engine_v2.rules.derived_state import (
    CostReductionApplication,
    consume_applied_cost_reductions,
    get_applied_cost_reductions,
    get_static_cost_increase_amount,
)
from lorcana_engine_v2.rules.move_registry_cache import get_or_build_move_registry
from lorcana_engine_v2.rules.static_ability_utils import (
    evaluate_static_condition,
    has_opponent_static_play_restriction,
    has_static_card_restriction,
)
from lorcana_engine_v2.targeting.runtime.target_analysis import (
    TargetAnalysis,
    analyze_effect_targets,
    validate_and_normalize_target_selection,
)
from lorcana_engine_v2.targeting.slotted_targets import flatten_slotted_targets, is_slotted_target_input
from lorcana_engine_v2.runtime_game.turn_metrics import (
    record_card_played_this_turn,
    record_discard_exit_this_turn,
    record_shift_played_this_turn,
)

from .registry import MoveEnumerationContext, MoveExecutionContext, MoveValidationContext, input_card_id


PLAY_CARD = "playCard"


def _current_player(context: MoveValidationContext | MoveEnumerationContext | MoveExecutionContext) -> PlayerId:
    resolved = resolve_current_player_for_move(context, context.G)
    if resolved is None:
        raise RuntimeError("playCard could not resolve the current turn player")
    return resolved


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


def _static_registry(context: MoveValidationContext | MoveEnumerationContext | MoveExecutionContext):
    return get_or_build_move_registry(context)


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


def _compute_cost_reduction(
    context: MoveValidationContext | MoveExecutionContext,
    card_def: CardDefinition,
    play_method: str | None,
) -> tuple[int, tuple[CostReductionApplication, ...]]:
    return get_applied_cost_reductions(
        state=_state_from_context(context),
        player_id=_current_player(context),
        definition=card_def,
        play_method=play_method,
        registry=_static_registry(context),
    )


def _compute_cost_increase(
    context: MoveValidationContext | MoveExecutionContext,
    card_def: CardDefinition,
    play_method: str | None,
) -> int:
    return get_static_cost_increase_amount(
        state=_state_from_context(context),
        player_id=_current_player(context),
        definition=card_def,
        play_method=play_method,
        registry=_static_registry(context),
    )


def _standard_play_basic_cost(
    context: MoveValidationContext | MoveExecutionContext,
    card_def: CardDefinition,
) -> BasicCost:
    reduction_amount, _ = _compute_cost_reduction(context, card_def, "standard")
    increase_amount = _compute_cost_increase(context, card_def, "standard")
    return BasicCost(ink=max(0, int(card_def.cost) - reduction_amount + increase_amount))


def _shift_play_basic_cost(
    context: MoveValidationContext | MoveExecutionContext,
    card_def: CardDefinition,
) -> BasicCost:
    rules = get_shift_rules(card_def)
    reduction_amount, _ = _compute_cost_reduction(context, card_def, "shift")
    return BasicCost(
        ink=max(0, int(rules.inkCost or 0) - reduction_amount)
        if rules is not None and rules.inkCost is not None
        else 0
    )


def _consume_applied_cost_reductions(
    context: MoveExecutionContext,
    player_id: PlayerId,
    card_def: CardDefinition,
    play_method: str | None,
) -> None:
    _, applications = _compute_cost_reduction(context, card_def, play_method)
    if not any(app.source == "pending" and app.consumeOnUse for app in applications):
        return
    next_state = consume_applied_cost_reductions(context.state, player_id, applications)
    context._draft.set_state(next_state)


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
    return has_opponent_static_play_restriction(
        state=_state_from_context(context),
        playerId=player_id,
        restriction=restriction,
        cardDef=card_def,
        registry=_static_registry(context),
    )


def _has_static_card_restriction(context, card_id: InstanceId, restriction: str) -> bool:
    return has_static_card_restriction(
        state=_state_from_context(context),
        cardId=card_id,
        restriction=restriction,
        registry=_static_registry(context),
    )


def _self_play_condition_error(
    context: MoveValidationContext,
    player_id: PlayerId,
    card_id: InstanceId,
    card_def: CardDefinition,
) -> RuntimeValidationResult | None:
    for ability in card_def.abilities:
        if ability.kind != "static":
            continue
        effect = ability.raw.get("effect")
        if not isinstance(effect, Mapping) or effect.get("type") != "self-play-condition":
            continue
        condition = ability.raw.get("condition")
        if condition is None:
            continue
        if not evaluate_static_condition(
            condition=condition,
            state=_state_from_context(context),
            controllerId=player_id,
            sourceId=card_id,
            getDefinitionByInstanceId=lambda candidate_id: _card_definition(context, candidate_id),
        ):
            return RuntimeValidationResult.fail(
                "Card cannot be played: play condition not met",
                "SELF_PLAY_CONDITION_NOT_MET",
            )
    return None


def _can_use_shift_ability(
    context: MoveValidationContext,
    player_id: PlayerId,
    card_id: InstanceId,
    card_def: CardDefinition,
) -> bool:
    shift_ability = next(
        (
            ability
            for ability in card_def.abilities
            if ability.kind == "keyword"
            and ability.raw.get("keyword") == "Shift"
            and ability.raw.get("condition") is not None
        ),
        None,
    )
    if shift_ability is None:
        return True
    return evaluate_static_condition(
        condition=shift_ability.raw.get("condition"),
        state=_state_from_context(context),
        controllerId=player_id,
        sourceId=card_id,
        getDefinitionByInstanceId=lambda candidate_id: _card_definition(context, candidate_id),
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


def _action_target_input(context: MoveValidationContext | MoveExecutionContext) -> object | None:
    if "targets" in context.args:
        return context.args.get("targets")
    if "slottedTargets" in context.args:
        return context.args.get("slottedTargets")
    return None


def _flat_action_target_input(targets: object | None) -> object | None:
    if is_slotted_target_input(targets):
        return flatten_slotted_targets(targets)
    return targets


def _merge_target_analysis(left: TargetAnalysis, right: TargetAnalysis) -> TargetAnalysis:
    return TargetAnalysis(
        targetDsl=tuple((*left.targetDsl, *right.targetDsl)),
        cardCandidates=tuple(dict.fromkeys((*left.cardCandidates, *right.cardCandidates))),
        playerCandidates=tuple(dict.fromkeys((*left.playerCandidates, *right.playerCandidates))),
        allowedZones=tuple(dict.fromkeys((*left.allowedZones, *right.allowedZones))),
        minSelections=max(left.minSelections, right.minSelections),
        maxSelections=max(left.maxSelections, right.maxSelections),
        declaredMaxSelections=max(left.declaredMaxSelections or 0, right.declaredMaxSelections or 0),
        requiresExplicitSelection=left.requiresExplicitSelection or right.requiresExplicitSelection,
        allowsDeferredResolutionWithoutInitialSelection=(
            left.allowsDeferredResolutionWithoutInitialSelection
            or right.allowsDeferredResolutionWithoutInitialSelection
        ),
        allowDuplicateTargets=left.allowDuplicateTargets or right.allowDuplicateTargets,
    )


def _combined_action_target_analysis(
    context: MoveValidationContext | MoveExecutionContext,
    player_id: PlayerId,
    card_id: InstanceId,
    card_def: CardDefinition,
) -> TargetAnalysis:
    card_played = {
        "playerId": player_id,
        "cardId": card_id,
        "cardType": card_def.card_type,
        "costType": _cost(context),
    }
    combined = TargetAnalysis()
    for ability in card_def.abilities:
        if ability.kind != "action":
            continue
        combined = _merge_target_analysis(
            combined,
            analyze_effect_targets(ability.raw.get("effect"), context, card_played),
        )
    return combined


def _validate_action_targets(
    context: MoveValidationContext,
    player_id: PlayerId,
    card_id: InstanceId,
    card_def: CardDefinition,
) -> RuntimeValidationResult:
    if card_def.card_type != "action":
        return RuntimeValidationResult.ok()
    if "targets" not in context.args and "slottedTargets" not in context.args:
        return RuntimeValidationResult.ok()
    analysis = _combined_action_target_analysis(context, player_id, card_id, card_def)
    selection = validate_and_normalize_target_selection(
        _flat_action_target_input(_action_target_input(context)),
        analysis,
        {"currentPlayer": player_id, "ctx": context},
    )
    if getattr(selection, "valid", False):
        return RuntimeValidationResult.ok()
    if isinstance(selection, RuntimeValidationResult):
        return selection
    return RuntimeValidationResult.fail(
        getattr(selection, "error", None) or "Action target selection is invalid",
        getattr(selection, "errorCode", None) or "INVALID_ACTION_TARGETS",
    )


def _validate_cost(context: MoveValidationContext, card_id: InstanceId, card_def: CardDefinition) -> RuntimeValidationResult:
    player_id = _current_player(context)
    cost = _cost(context)
    characters = _controlled_characters_in_play(context, player_id)

    if cost == "standard":
        return validate_basic_cost(context, _standard_play_basic_cost(context, card_def))

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
            cost_validation = validate_basic_cost(context, _shift_play_basic_cost(context, card_def))
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
    record_card_played_this_turn(context, card_id)
    if shifted:
        record_shift_played_this_turn(context, card_id)
    context.set_G(context.state.G.with_updates(staticEffectsVersion=context.state.G.staticEffectsVersion + 1))


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
            "slottedTargets": context.args.get("slottedTargets"),
            "amount": context.args.get("amount"),
            "choiceIndex": context.args.get("choiceIndex"),
            "resolveOptional": context.args.get("resolveOptional"),
            "namedCard": context.args.get("namedCard"),
            "destinations": context.args.get("destinations"),
            "eventSnapshot": context.args.get("eventSnapshot"),
            "preventAutoResolveTriggeredEffects": context.args.get("preventAutoResolveTriggeredEffects"),
        }
    )
    resolve_action_card_effects(context, card_played, card_def, resolution_input)


@dataclass(frozen=True, slots=True)
class PlayCardMove:
    serverOnly: bool = False
    ignorePriority: bool = True
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
        current_player_validation = require_current_player_for_move(context, context.playerId, context.G)
        if not current_player_validation.valid:
            return current_player_validation
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
        action_params = _validate_action_params(context, card_def)
        if not action_params.valid:
            return action_params
        return _validate_action_targets(context, player_id, card_id, card_def)

    def execute(self, context: MoveExecutionContext) -> MatchState:
        card_id = InstanceId(input_card_id(context) or "")
        player_id = _current_player(context)
        cost = _cost(context)
        card_def = context.cards.require(card_id).definition
        ink_paid = 0
        singer_ids: tuple[InstanceId, ...] = ()

        if cost == "standard":
            paid = pay_basic_cost(context, _standard_play_basic_cost(context, card_def))
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
                paid = pay_basic_cost(context, _shift_play_basic_cost(context, card_def))
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
            record_discard_exit_this_turn(context)
        else:
            raise RuntimeError(f"playCard execute: unrecognized or missing cost type: {cost!r}")

        if cost in {"standard", "shift"}:
            _consume_applied_cost_reductions(context, player_id, card_def, cost)
        _detach_from_parent_if_playing_from_under(context, card_id)
        context.framework.zones.moveCard(card_id, ZoneRef(zone=ZoneId("play"), playerId=player_id))
        recompute_lore_to_win(context)
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
