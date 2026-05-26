from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace

from lorcana_engine_v2.core.ids import InstanceId, PlayerId
from lorcana_engine_v2.core.results import RuntimeValidationResult
from lorcana_engine_v2.core.state import MatchState
from lorcana_engine_v2.core.zones import scoped_zone
from lorcana_engine_v2.effects.triggered_abilities import (
    BagItem,
    can_resolve_bag_effect_by_restrictions,
    flush_triggered_events_to_bag,
    get_next_bag_resolver,
    record_bag_effect_resolution,
    remove_bag_effect,
    set_last_bag_resolver,
    update_bag_effect_resolution_input,
)
from lorcana_engine_v2.resolution.action_effect_types import PendingResolutionResult
from lorcana_engine_v2.resolution.action_effects import _evaluate_action_condition, resolve_action_effect
from lorcana_engine_v2.resolution.pending import _state_of, _write_state
from lorcana_engine_v2.targeting.runtime.target_analysis import (
    analyze_effect_targets,
    validate_and_normalize_target_selection,
)
from lorcana_engine_v2.targeting.runtime.target_resolver import resolve_target_player_ids
from lorcana_engine_v2.targeting.slotted_targets import flatten_slotted_targets, is_slotted_target_input
from lorcana_engine_v2.core.turn_owner import resolve_turn_owner_id


def _read_state(target: MatchState | object) -> MatchState:
    try:
        return _state_of(target)
    except TypeError:
        cards = getattr(target, "cards", None)
        getter = getattr(cards, "_state_getter", None)
        if callable(getter):
            state = getter()
            if isinstance(state, MatchState):
                return state
        raise


def _find_bag_item(state: MatchState, bag_id: str) -> BagItem | None:
    return next(
        (item for item in state.G.triggeredAbilities.bag.items if isinstance(item, BagItem) and item.id == bag_id),
        None,
    )


class _StateResolutionTarget:
    def __init__(self, state: MatchState) -> None:
        self.state = state

    def set_state(self, state: MatchState) -> None:
        self.state = state


def _condition_branch(
    target: MatchState | object,
    bag_item: BagItem,
    resolution_input,
) -> object:
    effect = bag_item.effect
    if not isinstance(effect, Mapping) or effect.get("type") != "conditional":
        return effect
    branch = effect.get("then", effect.get("effect", effect.get("ifTrue")))
    if not _evaluate_action_condition(target, bag_item.cardPlayed, effect.get("condition"), resolution_input):
        branch = effect.get("else", effect.get("ifFalse"))
    return branch


def _choice_branch(effect: object, resolution_input) -> object:
    if not isinstance(effect, Mapping) or effect.get("type") not in {"choice", "or"}:
        return effect
    if resolution_input.choiceIndex is None:
        return effect
    options = effect.get("options", effect.get("choices", ()))
    if not isinstance(options, (list, tuple)) or resolution_input.choiceIndex >= len(options):
        return effect
    return options[resolution_input.choiceIndex]


def _has_intermediate_input(params: Mapping[str, object] | None) -> bool:
    if params is None:
        return False
    return any(
        key in params
        for key in ("resolveOptional", "enterPlayExerted", "choiceIndex", "namedCard", "destinations")
    )


def _explicit_target_count(targets: object) -> int:
    if targets is None:
        return 0
    if is_slotted_target_input(targets):
        return len(flatten_slotted_targets(targets))
    if isinstance(targets, str):
        return 1 if targets else 0
    if isinstance(targets, (list, tuple)):
        return len(tuple(item for item in targets if isinstance(item, str) and item))
    return 0


def _effect_requires_explicit_targets(effect: object) -> bool:
    if not isinstance(effect, Mapping):
        return False
    target = effect.get("target")
    if isinstance(target, str) and "CHOSEN" in target.upper():
        return True
    if isinstance(target, Mapping) and target.get("selector") in {"chosen", "chosen-player"}:
        return True
    for key in ("effect", "then", "else", "ifTrue", "ifFalse"):
        if _effect_requires_explicit_targets(effect.get(key)):
            return True
    for key in ("effects", "steps", "options", "choices"):
        value = effect.get(key)
        if isinstance(value, (list, tuple)) and any(_effect_requires_explicit_targets(item) for item in value):
            return True
    return False


def _direct_discard_chooser_id(
    target: MatchState | object,
    bag_item: BagItem,
    effect: object,
) -> PlayerId | None:
    if not isinstance(effect, Mapping) or effect.get("type") != "discard":
        return None
    if str(effect.get("from") or "hand") != "hand":
        return None
    if effect.get("amount") == "all":
        return None
    if effect.get("random") is True and effect.get("chosen") is not True:
        return None
    player_ids = resolve_target_player_ids(target, bag_item.cardPlayed, effect.get("target"))
    return player_ids[0] if len(player_ids) == 1 else None


def _validate_discard_choice_targets(
    state: MatchState,
    *,
    chooser_id: PlayerId,
    targets: object,
) -> RuntimeValidationResult:
    target_ids = flatten_slotted_targets(targets) if is_slotted_target_input(targets) else ()
    if not target_ids:
        if isinstance(targets, str):
            target_ids = (targets,) if targets else ()
        elif isinstance(targets, (list, tuple)):
            target_ids = tuple(str(item) for item in targets if isinstance(item, str) and item)
    if not target_ids:
        return RuntimeValidationResult.fail("resolveBag requires at least 1 explicit target for this effect", "RESOLVE_BAG_TARGETS_REQUIRED")
    for raw_id in target_ids:
        card_id = InstanceId(str(raw_id))
        entry = state.ctx.zones.private.cardIndex.get(card_id)
        if entry is None or entry.ownerID != chooser_id or str(entry.zoneKey) != str(scoped_zone("hand", chooser_id)):
            return RuntimeValidationResult.fail(f"Target {raw_id} is not a legal target", "INVALID_ACTION_TARGET")
    return RuntimeValidationResult.ok()


def validate_resolve_bag(
    state_or_context: MatchState | object,
    *,
    bag_id: str,
    player_id: PlayerId | str,
    params: Mapping[str, object] | None = None,
) -> RuntimeValidationResult:
    state = _read_state(state_or_context)
    if not bag_id:
        return RuntimeValidationResult.fail("resolveBag requires a valid bag id", "RESOLVE_BAG_ID_REQUIRED")
    bag_item = _find_bag_item(state, bag_id)
    if bag_item is None:
        return RuntimeValidationResult.fail("Bag effect was not found", "RESOLVE_BAG_NOT_FOUND")
    resolution_input = bag_item.resolutionInput.merge(params)
    effect_for_validation = _choice_branch(_condition_branch(state_or_context, bag_item, resolution_input), resolution_input)
    direct_chooser = _direct_discard_chooser_id(state_or_context, bag_item, effect_for_validation)
    resolver = get_next_bag_resolver(state)
    actor = PlayerId(str(player_id))
    is_direct_chooser = direct_chooser == actor and bag_item.controllerId != actor
    if not is_direct_chooser and (resolver != actor or bag_item.controllerId != resolver):
        return RuntimeValidationResult.fail("Only the active bag resolver may choose this effect", "RESOLVE_BAG_WRONG_PLAYER")
    targets = params.get("targets") if params is not None else None
    if targets is not None:
        if is_direct_chooser and isinstance(effect_for_validation, Mapping) and effect_for_validation.get("type") == "discard":
            return _validate_discard_choice_targets(state, chooser_id=actor, targets=targets)
        try:
            analysis = analyze_effect_targets(effect_for_validation, state_or_context, bag_item.cardPlayed, resolution_input)
        except Exception:
            if _effect_requires_explicit_targets(effect_for_validation):
                return RuntimeValidationResult.ok()
            return RuntimeValidationResult.fail("Bag effect target selection is invalid", "INVALID_BAG_TARGETS")
        if _explicit_target_count(targets) == 0 and analysis.minSelections > 0:
            return RuntimeValidationResult.fail(
                "resolveBag requires at least 1 explicit target for this effect",
                "RESOLVE_BAG_TARGETS_REQUIRED",
            )
        selection = validate_and_normalize_target_selection(targets, analysis)
        if not getattr(selection, "valid", False):
            return RuntimeValidationResult.fail(
                getattr(selection, "error", None) or "Bag effect target selection is invalid",
                getattr(selection, "errorCode", None) or "INVALID_BAG_TARGETS",
            )
    return RuntimeValidationResult.ok()


def resolve_bag(
    target: MatchState | object,
    *,
    bag_id: str,
    player_id: PlayerId | str | None = None,
    params: Mapping[str, object] | None = None,
    resources: object | None = None,
) -> PendingResolutionResult:
    state = _state_of(target)
    bag_item = _find_bag_item(state, bag_id)
    if bag_item is None:
        return PendingResolutionResult(status="not-found", state=state)

    if player_id is not None:
        validation = validate_resolve_bag(target, bag_id=bag_id, player_id=player_id, params=params)
        if not validation.valid:
            return PendingResolutionResult(status="invalid", state=state, bagItem=bag_item)

    state = set_last_bag_resolver(state, bag_item.controllerId)

    if not can_resolve_bag_effect_by_restrictions(state, bag_item):
        state, _ = remove_bag_effect(state, bag_id)
        state = flush_triggered_events_to_bag(state, resources=resources)
        return PendingResolutionResult(status="cancelled", state=_write_state(target, state), bagItem=bag_item)

    resolution_input = bag_item.resolutionInput.merge(params)
    branch_effect = _choice_branch(_condition_branch(target, bag_item, resolution_input), resolution_input)
    has_targets = params is not None and params.get("targets") is not None
    if not has_targets and _has_intermediate_input(params):
        try:
            requires_more_input = analyze_effect_targets(branch_effect, target, bag_item.cardPlayed, resolution_input).requiresExplicitSelection
        except Exception:
            requires_more_input = _effect_requires_explicit_targets(branch_effect)
        if requires_more_input:
            next_state = update_bag_effect_resolution_input(state, bag_id, params or {})
            return PendingResolutionResult(
                status="pending",
                state=_write_state(target, next_state),
                bagItem=bag_item,
                resolutionInput=resolution_input,
            )

    if isinstance(branch_effect, Mapping) and branch_effect is not bag_item.effect:
        effect_to_resolve = branch_effect
    else:
        effect_to_resolve = bag_item.effect
    working_target = _StateResolutionTarget(state) if isinstance(target, MatchState) else target
    result = resolve_action_effect(
        working_target,
        bag_item.cardPlayed,
        effect_to_resolve,
        resolution_input,
        {"sourceAbilityIndex": bag_item.abilityIndex} if bag_item.abilityIndex is not None else None,
    )
    next_state = result.state if isinstance(result.state, MatchState) else _state_of(working_target)

    if result.status == "suspended":
        next_state, _ = remove_bag_effect(next_state, bag_id)
        return replace(result, state=_write_state(target, next_state), bagItem=bag_item)

    next_state = record_bag_effect_resolution(next_state, bag_item)
    next_state, _ = remove_bag_effect(next_state, bag_id)
    next_state = flush_triggered_events_to_bag(next_state, resources=resources)
    if not next_state.G.triggeredAbilities.bag.items and not next_state.G.pendingEffects and next_state.ctx.priority.pendingChoice is None:
        turn_owner = resolve_turn_owner_id(next_state)
        if turn_owner is not None:
            next_state = MatchState(
                G=next_state.G,
                ctx=next_state.ctx.with_updates(priority=next_state.ctx.priority.with_updates(holder=turn_owner)),
            )
    return PendingResolutionResult(
        status="resolved",
        state=_write_state(target, next_state),
        bagItem=bag_item,
        resolutionInput=resolution_input,
    )


class BagService:
    validate = staticmethod(validate_resolve_bag)
    resolve = staticmethod(resolve_bag)
    next_resolver = staticmethod(get_next_bag_resolver)


__all__ = [
    "BagItem",
    "BagService",
    "resolve_bag",
    "validate_resolve_bag",
]
