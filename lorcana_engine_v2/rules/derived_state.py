from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from lorcana_engine_v2.cards.models import CardDefinition
from lorcana_engine_v2.core.ids import InstanceId, PlayerId, ZoneId
from lorcana_engine_v2.core.static_resources import MatchStaticResources
from lorcana_engine_v2.core.state import MatchState
from lorcana_engine_v2.core.zones import CardMeta, base_zone_from_key
from lorcana_engine_v2.rules.queries import RuntimeCardBase


def _number(value: object, default: int = 0) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str) and value.lstrip("+-").isdigit():
        return int(value)
    return default


def _meta_damage(meta: CardMeta | None) -> int:
    return max(0, _number(getattr(meta, "damage", 0) if meta is not None else 0))


def _base_keyword_entries(definition: CardDefinition) -> tuple[tuple[str, int | None], ...]:
    entries: list[tuple[str, int | None]] = []
    for ability in definition.abilities:
        if ability.kind != "keyword":
            continue
        keyword = ability.raw.get("keyword")
        if not isinstance(keyword, str) or not keyword.strip():
            continue
        raw_value = ability.raw.get("value")
        value = _number(raw_value) if raw_value is not None else None
        entries.append((keyword.strip(), value if value and value > 0 else None))
    return tuple(entries)


def _effects_for_card(registry: object | None, card_id: InstanceId | str, kind: str | None = None) -> tuple[object, ...]:
    if registry is None:
        return ()
    getter = getattr(registry, "get_effects_for_card", None)
    if callable(getter):
        return tuple(getter(InstanceId(str(card_id)), kind=kind))
    by_target = getattr(registry, "byTarget", {})
    effects = tuple(by_target.get(InstanceId(str(card_id)), ()))
    if kind is None:
        return effects
    return tuple(effect for effect in effects if getattr(effect, "kind", None) == kind)


def _effects_for_player(registry: object | None, player_id: PlayerId | str, kind: str | None = None) -> tuple[object, ...]:
    if registry is None:
        return ()
    getter = getattr(registry, "get_effects_for_player", None)
    if callable(getter):
        return tuple(getter(PlayerId(str(player_id)), kind=kind))
    by_player = getattr(registry, "byPlayer", {})
    effects = tuple(by_player.get(PlayerId(str(player_id)), ()))
    if kind is None:
        return effects
    return tuple(effect for effect in effects if getattr(effect, "kind", None) == kind)


def _payload(effect: object) -> Mapping[str, object]:
    value = getattr(effect, "payload", {})
    return value if isinstance(value, Mapping) else {}


def _static_stat_modifier(registry: object | None, card_id: InstanceId, stat: str) -> int:
    total = 0
    for effect in _effects_for_card(registry, card_id, "modify-stat"):
        payload = _payload(effect)
        if payload.get("stat") == stat:
            total += _number(payload.get("modifier", payload.get("amount", 0)))
    return total


def _continuous_stat_modifier(state: MatchState, card_id: InstanceId, stat: str) -> int:
    from lorcana_engine_v2.effects.continuous_effects import get_active_stat_modifier_total

    return get_active_stat_modifier_total(state, card_id, stat)


def _static_stat_floor(registry: object | None, card_id: InstanceId, stat: str) -> int | None:
    floors: list[int] = []
    for effect in _effects_for_card(registry, card_id, "stat-floor"):
        payload = _payload(effect)
        if payload.get("stat") == stat:
            floors.append(_number(payload.get("floor", payload.get("minimum", 0))))
    return max(floors) if floors else None


def _apply_floor(value: int, floor: int | None) -> int:
    return value if floor is None else max(value, floor)


def _derive_strength(state: MatchState, definition: CardDefinition, card_id: InstanceId, registry: object | None) -> int:
    if definition.card_type != "character":
        return 0
    value = definition.strength + _static_stat_modifier(registry, card_id, "strength") + _continuous_stat_modifier(state, card_id, "strength")
    return max(0, _apply_floor(value, _static_stat_floor(registry, card_id, "strength")))


def _derive_willpower(state: MatchState, definition: CardDefinition, card_id: InstanceId, registry: object | None) -> int:
    if definition.card_type in {"action", "item"}:
        return 0
    value = definition.willpower + _static_stat_modifier(registry, card_id, "willpower") + _continuous_stat_modifier(state, card_id, "willpower")
    return max(0, _apply_floor(value, _static_stat_floor(registry, card_id, "willpower")))


def _derive_lore(state: MatchState, definition: CardDefinition, card_id: InstanceId, registry: object | None) -> int:
    value = definition.lore + _static_stat_modifier(registry, card_id, "lore") + _continuous_stat_modifier(state, card_id, "lore")
    return max(0, _apply_floor(value, _static_stat_floor(registry, card_id, "lore")))


def _derive_move_cost(state: MatchState, definition: CardDefinition, card_id: InstanceId, registry: object | None) -> int:
    if definition.card_type != "location":
        return 0
    base = _number(definition.move_cost)
    value = base + _static_stat_modifier(registry, card_id, "moveCost") + _continuous_stat_modifier(state, card_id, "moveCost")
    return max(0, _apply_floor(value, _static_stat_floor(registry, card_id, "moveCost")))


def _derive_play_cost(
    definition: CardDefinition,
    actor_player_id: PlayerId | None,
    registry: object | None,
) -> int:
    value = definition.cost
    if actor_player_id is not None:
        for effect in _effects_for_player(registry, actor_player_id, "cost-reduction"):
            payload = _payload(effect)
            card_type = payload.get("cardType")
            if card_type:
                card_types = set(card_type) if isinstance(card_type, (tuple, list)) else {str(card_type)}
                is_song = definition.card_type == "action" and definition.raw.get("actionSubtype") == "song"
                if definition.card_type not in card_types and not (is_song and "song" in card_types):
                    continue
            value -= max(0, _number(payload.get("amount", payload.get("reduction", 0))))

    global_effects = tuple(getattr(registry, "globalEffects", getattr(registry, "global_", getattr(registry, "globalEffects", ()))) or ())
    global_effects = global_effects or tuple(getattr(registry, "global", ()) if registry is not None else ())
    for effect in global_effects:
        if getattr(effect, "kind", None) != "cost-increase":
            continue
        payload = _payload(effect)
        card_type = payload.get("cardType")
        if card_type:
            card_types = set(card_type) if isinstance(card_type, (tuple, list)) else {str(card_type)}
            if definition.card_type not in card_types:
                continue
        value += max(0, _number(payload.get("amount", 0)))
    return max(0, value)


def _active_static_inkability_grant(
    *,
    state: MatchState,
    static_resources: MatchStaticResources,
    actor_player_id: PlayerId,
    grant_type: str,
) -> bool:
    from lorcana_engine_v2.rules.condition_evaluator import ConditionContext, ConditionEvaluator
    from lorcana_engine_v2.rules.queries import QueryService

    query = QueryService(static_resources, actorPlayerId=actor_player_id, cacheViews=False)
    evaluator = ConditionEvaluator()
    for card_id, entry in state.ctx.zones.private.cardIndex.items():
        if base_zone_from_key(entry.zoneKey) != ZoneId("play"):
            continue
        if entry.controllerID != actor_player_id:
            continue
        definition = static_resources.cards.get(str(static_resources.instances.require(card_id).definition_id))
        for ability in definition.static_abilities():
            effect = ability.raw.get("effect")
            if not isinstance(effect, Mapping) or effect.get("type") != grant_type:
                continue
            source_zones = ability.source_zones or tuple(ability.raw.get("sourceZones") or ("play",))
            if "play" not in source_zones:
                continue
            condition = ability.raw.get("condition")
            if not evaluator.evaluate(
                state,
                type(
                    "StaticInkabilityContext",
                    (),
                    {"query": query},
                )(),
                condition,
                ConditionContext(actor=actor_player_id, source_id=card_id, target_id=card_id),
            ):
                continue
            return True
    return False


def derive_can_be_put_in_inkwell(
    *,
    state: MatchState,
    definition: CardDefinition,
    owner_id: PlayerId,
    zone_id: ZoneId | None,
    actor_player_id: PlayerId | None,
    static_resources: MatchStaticResources,
) -> bool:
    if zone_id is None or actor_player_id is None:
        return False
    if owner_id != actor_player_id:
        return False
    inked_this_turn = state.G.turnMetadata.inkedThisTurn
    ink_limit = 1 + state.G.turnMetadata.additionalInkwellActions
    if len(inked_this_turn) >= ink_limit:
        return False

    base_zone = base_zone_from_key(zone_id)
    if base_zone == ZoneId("hand"):
        if definition.inkable:
            return True
        return _active_static_inkability_grant(
            state=state,
            static_resources=static_resources,
            actor_player_id=actor_player_id,
            grant_type="grant-hand-inkability",
        )

    if base_zone == ZoneId("discard"):
        if not definition.inkable:
            return False
        return _active_static_inkability_grant(
            state=state,
            static_resources=static_resources,
            actor_player_id=actor_player_id,
            grant_type="grant-discard-inkability",
        )

    return False


def derive_runtime_card_fields(
    *,
    state: MatchState,
    card: RuntimeCardBase,
    static_resources: MatchStaticResources,
    actor_player_id: PlayerId | None,
    registry: object | None,
) -> Mapping[str, object]:
    definition = card.definition
    card_id = card.instanceId
    current_turn = state.ctx.status.turn or 1

    removed_keywords = {
        str(_payload(effect).get("keyword"))
        for effect in _effects_for_card(registry, card_id, "lose-keyword")
        if _payload(effect).get("keyword")
    }
    temporary_lost_keywords = card.meta.temporaryLostKeywords or {}
    temporary_lost_starts = card.meta.temporaryLostKeywordStarts or {}
    for keyword, expires_at in temporary_lost_keywords.items():
        starts_at = temporary_lost_starts.get(keyword, 1)
        if starts_at <= current_turn <= expires_at:
            removed_keywords.add(str(keyword))
    keywords: list[str] = []
    keyword_values: dict[str, int] = {}
    for keyword, value in _base_keyword_entries(definition):
        if keyword not in removed_keywords and keyword not in keywords:
            keywords.append(keyword)
        if value is not None:
            keyword_values[keyword] = keyword_values.get(keyword, 0) + value

    for effect in _effects_for_card(registry, card_id, "gain-keyword"):
        payload = _payload(effect)
        keyword = payload.get("keyword")
        if not keyword:
            continue
        keyword_text = str(keyword)
        if keyword_text not in removed_keywords and keyword_text not in keywords:
            keywords.append(keyword_text)
        value = payload.get("value")
        if isinstance(value, int) and value > 0:
            keyword_values[keyword_text] = keyword_values.get(keyword_text, 0) + value

    temporary_keywords = card.meta.temporaryKeywords or {}
    temporary_starts = card.meta.temporaryKeywordStarts or {}
    temporary_values = card.meta.temporaryKeywordValues or {}
    for keyword, expires_at in temporary_keywords.items():
        starts_at = temporary_starts.get(keyword, 1)
        if starts_at <= current_turn <= expires_at and keyword not in keywords:
            keywords.append(str(keyword))
        value = temporary_values.get(keyword)
        if value:
            keyword_values[str(keyword)] = keyword_values.get(str(keyword), 0) + int(value)

    classifications = list(definition.classifications)
    for effect in _effects_for_card(registry, card_id, "grant-classification"):
        classification = _payload(effect).get("classification")
        if classification and str(classification) not in classifications:
            classifications.append(str(classification))
    temporary_classifications = card.meta.temporaryClassifications or {}
    temporary_classification_starts = card.meta.temporaryClassificationStarts or {}
    for classification, expires_at in temporary_classifications.items():
        starts_at = temporary_classification_starts.get(classification, 1)
        if starts_at <= current_turn <= expires_at and str(classification) not in classifications:
            classifications.append(str(classification))

    damage = _meta_damage(card.meta)
    exerted = card.meta.state == "exerted"
    drying = bool(card.meta.isDrying)
    normalized_keywords = {keyword.lower().replace("-", " ").replace("_", " ") for keyword in keywords}
    return {
        "strength": _derive_strength(state, definition, card_id, registry),
        "willpower": _derive_willpower(state, definition, card_id, registry),
        "lore": _derive_lore(state, definition, card_id, registry),
        "playCost": _derive_play_cost(definition, actor_player_id, registry),
        "moveCost": _derive_move_cost(state, definition, card_id, registry),
        "damage": damage,
        "exerted": exerted,
        "drying": drying,
        "canBePutInInkwell": derive_can_be_put_in_inkwell(
            state=state,
            definition=definition,
            owner_id=card.ownerID,
            zone_id=card.zoneID,
            actor_player_id=actor_player_id,
            static_resources=static_resources,
        ),
        "hasSupport": "support" in normalized_keywords,
        "hasRush": "rush" in normalized_keywords,
        "hasReckless": "reckless" in normalized_keywords,
        "hasEvasive": "evasive" in normalized_keywords,
        "hasQuestRestriction": any(
            _payload(effect).get("restriction") in {"cant-quest", "cant-quest-or-challenge"}
            for effect in _effects_for_card(registry, card_id, "restriction")
        )
        or any(
            (card.meta.temporaryRestrictionStarts or {}).get(restriction, 1)
            <= current_turn
            <= expires_at
            for restriction, expires_at in (card.meta.temporaryRestrictions or {}).items()
            if restriction in {"cant-quest", "cant-quest-or-challenge"}
        ),
        "fullName": definition.full_name,
        "keywords": tuple(keywords),
        "keywordValues": keyword_values,
        "classifications": tuple(classifications),
        "temporaryAbilities": card.meta.temporaryAbilities or {},
        "temporaryAbilityStarts": card.meta.temporaryAbilityStarts or {},
        "temporaryRestrictions": card.meta.temporaryRestrictions or {},
        "temporaryRestrictionStarts": card.meta.temporaryRestrictionStarts or {},
        "grantedAbilityTextEntries": (),
    }


@dataclass(frozen=True, slots=True)
class DerivedState:
    """Lorcanito-style read-only derived card projection helpers."""

    def effective_strength(self, state, ctx, instance_id: InstanceId | str) -> int:
        return ctx.query.runtime_card(state, instance_id).strength

    def effective_willpower(self, state, ctx, instance_id: InstanceId | str) -> int:
        return ctx.query.runtime_card(state, instance_id).willpower

    def effective_lore(self, state, ctx, instance_id: InstanceId | str) -> int:
        return ctx.query.runtime_card(state, instance_id).lore

    def play_cost(self, state, ctx, instance_id: InstanceId | str, actor: PlayerId | str | None = None) -> int:
        return ctx.query.runtime_card(state, instance_id, actor_player_id=actor).playCost

    def can_be_put_in_inkwell(self, state, ctx, instance_id: InstanceId | str, actor: PlayerId | str) -> bool:
        return ctx.query.runtime_card(state, instance_id, actor_player_id=actor).canBePutInInkwell

    def keywords(self, state, ctx, instance_id: InstanceId | str) -> frozenset[str]:
        return frozenset(ctx.query.runtime_card(state, instance_id).keywords)

    def classifications(self, state, ctx, instance_id: InstanceId | str) -> frozenset[str]:
        return frozenset(ctx.query.runtime_card(state, instance_id).classifications)


__all__ = [
    "DerivedState",
    "derive_can_be_put_in_inkwell",
    "derive_runtime_card_fields",
]
