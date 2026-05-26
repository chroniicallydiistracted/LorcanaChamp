from __future__ import annotations

from collections.abc import Mapping, Sequence
from types import SimpleNamespace

from lorcana_engine_v2.core.ids import InstanceId, PlayerId
from lorcana_engine_v2.core.state import MatchState
from lorcana_engine_v2.core.zones import ZoneId, base_zone_from_key
from lorcana_engine_v2.registries.static_registry import StaticEffectRegistry
from lorcana_engine_v2.rules.condition_evaluator import ConditionContext, ConditionEvaluator
from lorcana_engine_v2.rules.target_resolver import TargetQueryContext, TargetResolver


def _state(value: MatchState | Mapping[str, object] | object) -> MatchState | None:
    if isinstance(value, MatchState):
        return value
    found = getattr(value, "state", None)
    return found if isinstance(found, MatchState) else None


def _payload(effect: object) -> Mapping[str, object]:
    payload = getattr(effect, "payload", {})
    return payload if isinstance(payload, Mapping) else {}


def _registry_effects_for_card(
    registry: StaticEffectRegistry | None,
    card_id: InstanceId | str,
    kind: str | None = None,
) -> tuple[object, ...]:
    if registry is None:
        return ()
    return registry.get_effects_for_card(card_id, kind=kind)


def _registry_effects_for_player(
    registry: StaticEffectRegistry | None,
    player_id: PlayerId | str,
    kind: str | None = None,
) -> tuple[object, ...]:
    if registry is None:
        return ()
    return registry.get_effects_for_player(player_id, kind=kind)


def _query_context(state: MatchState, get_definition_by_instance_id):
    class _Query:
        def runtime_card(self, match_state, instance_id):
            entry = match_state.ctx.zones.private.cardIndex[InstanceId(str(instance_id))]
            definition = get_definition_by_instance_id(InstanceId(str(instance_id)))
            meta = match_state.ctx.zones.private.cardMeta.get(InstanceId(str(instance_id)))
            return SimpleNamespace(
                instanceId=InstanceId(str(instance_id)),
                definition=definition,
                meta=meta,
                ownerID=entry.ownerID,
                controllerID=entry.controllerID,
                zoneID=base_zone_from_key(entry.zoneKey),
            )

        base_runtime_card = runtime_card

    return SimpleNamespace(query=_Query())


def evaluate_static_condition(
    *,
    condition: object,
    state: MatchState | Mapping[str, object] | object,
    controllerId: PlayerId | str | None = None,
    sourceId: InstanceId | str | None = None,
    targetCardId: InstanceId | str | None = None,
    getDefinitionByInstanceId=None,
    resources=None,
) -> bool:
    if condition is None:
        return True
    match_state = _state(state)
    if match_state is None:
        # Static registry build paths pass a Lorcanito-shaped state fragment;
        # unsupported non-null conditions are false rather than guessed.
        return False
    if resources is None and getDefinitionByInstanceId is not None:
        resources = getattr(getDefinitionByInstanceId, "resources", None)
    ctx = SimpleNamespace(query=getattr(getattr(state, "cards", None), "_query", None))
    try:
        return ConditionEvaluator().evaluate(
            match_state,
            ctx,
            condition,
            ConditionContext(
                actor=PlayerId(str(controllerId)) if controllerId is not None else None,
                source_id=InstanceId(str(sourceId)) if sourceId is not None else None,
                target_id=InstanceId(str(targetCardId)) if targetCardId is not None else None,
            ),
        )
    except Exception:
        return False


def matches_static_ability_target(
    *,
    state: MatchState | Mapping[str, object] | object,
    target: object,
    sourceId: InstanceId | str,
    targetCardId: InstanceId | str,
    controllerId: PlayerId | str | None,
    getDefinitionByInstanceId,
) -> bool:
    match_state = _state(state)
    if match_state is None:
        return False
    if target in {"SELF", "SOURCE", None}:
        return InstanceId(str(sourceId)) == InstanceId(str(targetCardId))
    ctx = _query_context(match_state, getDefinitionByInstanceId)
    resolved = TargetResolver().resolve(
        match_state,
        ctx,
        target,
        TargetQueryContext(actor=PlayerId(str(controllerId)), source_id=sourceId, strict_unknown_filters=False),
    )
    return InstanceId(str(targetCardId)) in resolved


def _restriction_payload_matches_card(payload: Mapping[str, object], card_def: object | None) -> bool:
    card_type = payload.get("cardType")
    if card_type is not None and card_def is not None:
        allowed = (
            {str(item) for item in card_type}
            if isinstance(card_type, Sequence) and not isinstance(card_type, (str, bytes, bytearray))
            else {str(card_type)}
        )
        actual = getattr(card_def, "card_type", None) or getattr(card_def, "cardType", None)
        action_subtype = getattr(card_def, "raw", {}).get("actionSubtype") if hasattr(card_def, "raw") else getattr(card_def, "actionSubtype", None)
        if actual not in allowed and not (actual == "action" and action_subtype == "song" and "song" in allowed):
            return False
    min_cost = payload.get("minCost")
    if isinstance(min_cost, int) and card_def is not None:
        if int(getattr(card_def, "cost", 0)) < min_cost:
            return False
    return True


def has_static_card_restriction(
    *,
    state: MatchState | Mapping[str, object] | object,
    cardId: InstanceId | str,
    restriction: str,
    registry: StaticEffectRegistry | None,
) -> bool:
    return any(
        _payload(effect).get("restriction") == restriction
        for effect in _registry_effects_for_card(registry, cardId, "restriction")
    )


def has_opponent_static_play_restriction(
    *,
    state: MatchState | Mapping[str, object] | object,
    playerId: PlayerId | str,
    restriction: str,
    cardDef: object | None = None,
    registry: StaticEffectRegistry | None,
) -> bool:
    player = PlayerId(str(playerId))
    for effect in _registry_effects_for_player(registry, player, "restriction"):
        payload = _payload(effect)
        if payload.get("restriction") == restriction and _restriction_payload_matches_card(payload, cardDef):
            return True
    for effect in registry.globalEffects if registry is not None else ():
        payload = _payload(effect)
        if payload.get("restriction") == restriction and _restriction_payload_matches_card(payload, cardDef):
            return True
    return False


def get_static_property_modifier_total(
    *,
    state: MatchState | Mapping[str, object] | object,
    cardId: InstanceId | str,
    property: str,
    getDefinitionByInstanceId=None,
    registry: StaticEffectRegistry | None,
) -> int:
    total = 0
    for effect in _registry_effects_for_card(registry, cardId, "property-modification"):
        payload = _payload(effect)
        if payload.get("property") != property:
            continue
        value = payload.get("value", payload.get("modifier", payload.get("amount", 0)))
        if isinstance(value, int):
            total += value
    return total


def get_static_keyword_grant_value(
    *,
    state: MatchState | Mapping[str, object] | object,
    cardId: InstanceId | str,
    keyword: str,
    registry: StaticEffectRegistry | None,
) -> int:
    value = 0
    for effect in _registry_effects_for_card(registry, cardId, "gain-keyword"):
        payload = _payload(effect)
        if payload.get("keyword") != keyword:
            continue
        raw_value = payload.get("value")
        if isinstance(raw_value, int):
            value = max(value, raw_value)
    return value


__all__ = [
    "evaluate_static_condition",
    "get_static_keyword_grant_value",
    "get_static_property_modifier_total",
    "has_opponent_static_play_restriction",
    "has_static_card_restriction",
    "matches_static_ability_target",
]
