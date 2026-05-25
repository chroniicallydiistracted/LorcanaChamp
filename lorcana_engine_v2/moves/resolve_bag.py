from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from lorcana_engine_v2.core.results import RuntimeValidationResult
from lorcana_engine_v2.core.state import MatchState
from lorcana_engine_v2.effects.triggered_abilities import get_next_bag_resolver
from lorcana_engine_v2.resolution.bag import resolve_bag, validate_resolve_bag

from .registry import MoveEnumerationContext, MoveExecutionContext, MoveValidationContext


RESOLVE_BAG = "resolveBag"


def _bag_id(context: MoveValidationContext | MoveExecutionContext) -> str | None:
    raw = context.args.get("bagId")
    return str(raw) if isinstance(raw, str) and raw else None


def _params(context: MoveValidationContext | MoveExecutionContext) -> Mapping[str, object] | None:
    value = context.args.get("params")
    return value if isinstance(value, Mapping) else None


def _validate_params(value: object) -> RuntimeValidationResult:
    if value is None:
        return RuntimeValidationResult.ok()
    if not isinstance(value, Mapping):
        return RuntimeValidationResult.fail("resolveBag params must be an object", "RESOLVE_BAG_INVALID_PARAMS")
    choice_index = value.get("choiceIndex")
    if choice_index is not None and (not isinstance(choice_index, int) or choice_index < 0):
        return RuntimeValidationResult.fail("resolveBag choiceIndex must be a non-negative integer", "RESOLVE_BAG_INVALID_CHOICE")
    resolve_optional = value.get("resolveOptional")
    if resolve_optional is not None and not isinstance(resolve_optional, bool):
        return RuntimeValidationResult.fail("resolveBag resolveOptional must be a boolean", "RESOLVE_BAG_INVALID_OPTIONAL")
    targets = value.get("targets")
    if targets is not None:
        if isinstance(targets, str):
            if not targets:
                return RuntimeValidationResult.fail("resolveBag targets must be non-empty", "RESOLVE_BAG_INVALID_TARGETS")
        elif not isinstance(targets, (list, tuple)):
            return RuntimeValidationResult.fail("resolveBag targets must be card ids", "RESOLVE_BAG_INVALID_TARGETS")
        elif not all(isinstance(target, str) and target for target in targets):
            return RuntimeValidationResult.fail("resolveBag targets must be card ids", "RESOLVE_BAG_INVALID_TARGETS")
    return RuntimeValidationResult.ok()


def _state_for_enumeration(context: MoveEnumerationContext) -> MatchState | None:
    getter = getattr(context.cards, "_state_getter", None)
    if callable(getter):
        state = getter()
        return state if isinstance(state, MatchState) else None
    return None


@dataclass(frozen=True, slots=True)
class ResolveBagMove:
    serverOnly: bool = False
    ignorePriority: bool = True
    ignoreStaleStateID: bool = False

    def available(self, context: MoveEnumerationContext) -> bool:
        state = _state_for_enumeration(context)
        if state is None:
            return False
        resolver = get_next_bag_resolver(state)
        return any(getattr(item, "controllerId", None) == resolver for item in state.G.triggeredAbilities.bag.items)

    def validate(self, context: MoveValidationContext) -> RuntimeValidationResult:
        bag_id = _bag_id(context)
        if bag_id is None:
            return RuntimeValidationResult.fail("resolveBag requires a valid bag id", "RESOLVE_BAG_ID_REQUIRED")
        validation = validate_resolve_bag(context, bag_id=bag_id, player_id=context.playerId)
        if not validation.valid:
            return validation
        return _validate_params(context.args.get("params"))

    def execute(self, context: MoveExecutionContext) -> MatchState:
        bag_id = _bag_id(context)
        if bag_id is None:
            raise RuntimeError("resolveBag execute called without a valid bagId")
        result = resolve_bag(
            context,
            bag_id=bag_id,
            player_id=context.playerId,
            params=_params(context),
        )
        if result.status not in {"resolved", "suspended", "cancelled"}:
            raise RuntimeError(f"Failed to resolve bag effect: {result.status}")
        return context.state


Move = ResolveBagMove


__all__ = ["RESOLVE_BAG", "ResolveBagMove", "Move"]
