"""Lorcanito-aligned static / continuous effect materialization.

Static effects are continuous derived state. They are not one-shot effects and
must not mutate printed card definitions. This module keeps the old public helper
names for compatibility, but the engine-facing path now materializes active
static effects from public in-play source cards, matching Lorcanito's
static-effect-registry model.

Phase 1 supports these materialized static families:
- modify-stat
- gain-keyword
- restriction
- cost-reduction
- additional-inkwell

Still intentionally out of scope:
- stat-floor
- damage-source-stat-override
- lose-keyword
- grant-classification
- grant-ability / grant-abilities-while-here
- cost-increase
- suppression index
- full staticEffectsVersion cache invalidation
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import TYPE_CHECKING, Any

from .constants import CARD_CHARACTER, CARD_ITEM, CARD_LOCATION, KEYWORD_RECKLESS, ZONE_PLAY

if TYPE_CHECKING:
    from .engine import GameEngine
    from .state import GameState


class StaticEffectType(Enum):
    """Kinds of materialized static effects supported in phase 1."""

    MODIFY_STRENGTH = auto()
    MODIFY_WILLPOWER = auto()
    MODIFY_LORE = auto()
    GRANT_KEYWORD = auto()
    COST_REDUCTION = auto()
    QUEST_RESTRICTION = auto()
    CHALLENGE_RESTRICTION = auto()
    BE_CHALLENGED_RESTRICTION = auto()
    SING_RESTRICTION = auto()
    ADDITIONAL_INKWELL = auto()


def _normalize_keyword(keyword: str) -> str:
    return keyword.strip().upper().replace(" ", "_").replace("-", "_")


def _is_active_public_source(state: GameState, source_id: int) -> bool:
    source_inst = state.cards.get(source_id)
    return bool(
        source_inst is not None
        and source_inst.zone == ZONE_PLAY
        and source_inst.stack_parent_id is None
    )


def _source_raw(obj: Any) -> dict[str, Any]:
    raw = obj if isinstance(obj, dict) else getattr(obj, "raw", {}) or {}
    if isinstance(raw, dict) and isinstance(raw.get("raw"), dict):
        return dict(raw["raw"])
    return dict(raw) if isinstance(raw, dict) else {}


def _source_kind(obj: Any) -> str:
    raw = _source_raw(obj)
    return str(getattr(obj, "kind", None) or raw.get("type") or raw.get("kind") or "")


def _source_target(obj: Any) -> Any:
    raw = _source_raw(obj)
    target = getattr(obj, "target", None)
    if target is not None:
        alias = getattr(target, "alias", None)
        if alias:
            return alias
        target_raw = getattr(target, "raw", None)
        if target_raw:
            return target_raw
    return raw.get("target")


def _source_amount(obj: Any) -> Any:
    raw = _source_raw(obj)
    amount = getattr(obj, "amount", None)
    if amount is not None:
        return amount
    for key in ("modifier", "amount", "value"):
        if raw.get(key) is not None:
            return raw.get(key)
    reduction = raw.get("reduction")
    if isinstance(reduction, dict):
        return reduction.get("ink")
    return None


def _ability_condition_raw(ability: Any) -> dict[str, Any] | None:
    condition = getattr(ability, "condition", None)
    if isinstance(condition, dict):
        return dict(condition)
    if condition is not None:
        raw = getattr(condition, "raw", None)
        if isinstance(raw, dict):
            return dict(raw)
        kind = getattr(condition, "kind", None)
        if kind:
            result = {"type": str(kind)}
            value = getattr(condition, "value", None)
            if value is not None:
                result["value"] = value
            comparison = getattr(condition, "comparison", None)
            if comparison is not None:
                result["comparison"] = comparison
            subject = getattr(condition, "subject", None)
            if subject is not None:
                result["subject"] = subject
            return result
    raw = _source_raw(ability)
    if isinstance(raw.get("condition"), dict):
        return dict(raw["condition"])
    return None


def _card_type_matches(card_type: str | None, expected: Any) -> bool:
    if expected is None:
        return True
    if isinstance(expected, str):
        expected_values = (expected,)
    else:
        expected_values = tuple(expected or ())
    normalized = {str(value).replace("_", "-").lower() for value in expected_values}
    if "card" in normalized:
        return True
    return (card_type or "").replace("_", "-").lower() in normalized


def _card_has_classification(card_def: Any, classification: str) -> bool:
    expected = classification.casefold()
    return expected in {str(subtype).casefold() for subtype in getattr(card_def, "subtypes", ()) or ()}


def _card_has_name(card_def: Any, name: str) -> bool:
    names = {
        str(getattr(card_def, "full_name", "")),
        str(getattr(card_def, "name", "")),
        str(getattr(card_def, "simple_name", "")),
        str(getattr(card_def, "id", "")),
    }
    return name in names


def _printed_or_temp_keywords(state: GameState, engine: GameEngine, instance_id: int) -> set[str]:
    card = engine.card_def(state, instance_id)
    keywords = {_normalize_keyword(str(keyword)) for keyword in getattr(card, "keywords", ()) or ()}
    keywords.update(_normalize_keyword(str(keyword.keyword)) for keyword in getattr(card, "keyword_defs", ()) or ())
    keywords.update(_normalize_keyword(str(keyword)) for keyword in state.cards[instance_id].temporary_keywords)
    return keywords


def _filter_matches(state: GameState, engine: GameEngine, source_id: int, target_id: int, filter_def: dict[str, Any]) -> bool:
    card = engine.card_def(state, target_id)
    filter_type = str(filter_def.get("type") or "").casefold()

    if filter_type in {"classification", "has-classification"}:
        value = filter_def.get("classification") or filter_def.get("value")
        return bool(value and _card_has_classification(card, str(value)))

    if filter_type in {"has-name", "name"}:
        value = filter_def.get("name") or filter_def.get("value")
        return bool(value and _card_has_name(card, str(value)))

    if filter_type in {"card-type", "cardtype"}:
        value = filter_def.get("cardType") or filter_def.get("card_type") or filter_def.get("value")
        return _card_type_matches(card.card_type, value)

    if filter_type in {"has-keyword", "keyword"}:
        value = filter_def.get("keyword") or filter_def.get("value")
        return bool(value and _normalize_keyword(str(value)) in _printed_or_temp_keywords(state, engine, target_id))

    if filter_type in {"status", "damaged"}:
        status = filter_def.get("status")
        if filter_type == "damaged" or status == "damaged":
            return state.cards[target_id].damage > 0
        if status == "ready":
            return not state.cards[target_id].exerted
        if status == "exerted":
            return state.cards[target_id].exerted
        return True

    if filter_type == "exerted":
        return state.cards[target_id].exerted

    if filter_type == "ready":
        return not state.cards[target_id].exerted

    if filter_type == "cost-comparison":
        value = filter_def.get("value")
        comparison = str(filter_def.get("comparison") or filter_def.get("operator") or "").casefold()
        try:
            expected = int(value)
        except (TypeError, ValueError):
            return False
        actual = int(card.cost or 0)
        if comparison in {"less-or-equal", "lte", "<=", "le"}:
            return actual <= expected
        if comparison in {"greater-or-equal", "gte", ">=", "ge"}:
            return actual >= expected
        if comparison in {"equal", "eq", "=="}:
            return actual == expected
        return False

    if filter_type == "strength-comparison":
        value = filter_def.get("value")
        comparison = str(filter_def.get("comparison") or filter_def.get("operator") or "").casefold()
        try:
            expected = int(value)
        except (TypeError, ValueError):
            return False
        actual = engine.effective_strength(state, target_id)
        if comparison in {"less-or-equal", "lte", "<=", "le"}:
            return actual <= expected
        if comparison in {"greater-or-equal", "gte", ">=", "ge"}:
            return actual >= expected
        if comparison in {"equal", "eq", "=="}:
            return actual == expected
        return False

    if filter_type == "not":
        inner = filter_def.get("filter") or filter_def.get("condition")
        return not (isinstance(inner, dict) and _filter_matches(state, engine, source_id, target_id, inner))

    if filter_type in {"and", "or"}:
        children = filter_def.get("filters") or filter_def.get("conditions") or ()
        if isinstance(children, dict):
            children = (children,)
        results = [
            _filter_matches(state, engine, source_id, target_id, child)
            for child in children
            if isinstance(child, dict)
        ]
        return all(results) if filter_type == "and" else any(results)

    return filter_type in {"", "none"}


def _raw_target_matches(state: GameState, engine: GameEngine, source_id: int, target_id: int, raw_target: Any) -> bool:
    source = state.cards.get(source_id)
    target = state.cards.get(target_id)
    if source is None or target is None or target.zone != ZONE_PLAY:
        return False

    if isinstance(raw_target, str):
        normalized = raw_target.upper()
        card = engine.card_def(state, target_id)
        if normalized in {"SELF", "SOURCE", "THIS_CHARACTER"}:
            return target_id == source_id
        if normalized in {"YOUR_CHARACTERS", "YOUR_CHARACTER"}:
            return target.controller == source.controller and card.card_type == CARD_CHARACTER
        if normalized in {"YOUR_OTHER_CHARACTERS", "YOUR_OTHER_CHARACTER"}:
            return target_id != source_id and target.controller == source.controller and card.card_type == CARD_CHARACTER
        if normalized in {"OPPOSING_CHARACTERS", "ALL_OPPOSING_CHARACTERS"}:
            return target.controller != source.controller and card.card_type == CARD_CHARACTER
        if normalized in {"ALL_CHARACTERS", "ANY_CHARACTER"}:
            return card.card_type == CARD_CHARACTER
        if normalized in {"YOUR_ITEMS", "YOUR_ITEM"}:
            return target.controller == source.controller and card.card_type == CARD_ITEM
        if normalized in {"YOUR_LOCATIONS", "YOUR_LOCATION"}:
            return target.controller == source.controller and card.card_type == CARD_LOCATION
        return False

    if not isinstance(raw_target, dict):
        return target_id == source_id

    selector = str(raw_target.get("selector") or raw_target.get("type") or raw_target.get("kind") or "").casefold()
    if selector in {"self", "source"} or raw_target.get("ref") in {"self", "source"}:
        return target_id == source_id

    owner = raw_target.get("owner") or raw_target.get("controller")
    if owner in {"you", "controller", "self"} and target.controller != source.controller:
        return False
    if owner in {"opponent", "opposing"} and target.controller == source.controller:
        return False

    zones = raw_target.get("zones") or ((raw_target.get("zone"),) if raw_target.get("zone") else (ZONE_PLAY,))
    if isinstance(zones, str):
        zones = (zones,)
    if target.zone not in zones:
        return False

    if raw_target.get("excludeSelf") or raw_target.get("exclude_self"):
        if target_id == source_id:
            return False

    card = engine.card_def(state, target_id)
    card_types = raw_target.get("cardTypes") or raw_target.get("card_types") or raw_target.get("cardType") or raw_target.get("card_type")
    if card_types is not None and not _card_type_matches(card.card_type, card_types):
        return False

    classifications = raw_target.get("classifications") or raw_target.get("classification")
    if classifications:
        if isinstance(classifications, str):
            classifications = (classifications,)
        if not any(_card_has_classification(card, str(classification)) for classification in classifications):
            return False

    filters = raw_target.get("filters") or raw_target.get("filter") or ()
    if isinstance(filters, dict):
        filters = (filters,)
    for filter_def in filters:
        if not isinstance(filter_def, dict) or not _filter_matches(state, engine, source_id, target_id, filter_def):
            return False

    return True


def _static_condition_matches(
    state: GameState,
    engine: GameEngine,
    source_id: int,
    condition: Any,
    *,
    target_id: int | None = None,
) -> bool:
    if condition is None:
        return True
    raw_condition = condition
    if hasattr(condition, "raw"):
        raw_condition = getattr(condition, "raw") or {"type": getattr(condition, "kind", "unknown")}
    if not isinstance(raw_condition, dict):
        return False
    try:
        from .condition_evaluator import evaluate_condition
        return bool(evaluate_condition(raw_condition, state, None, target_id if target_id is not None else source_id, engine))
    except Exception:
        return False


def _resolve_static_amount(state: GameState, engine: GameEngine, source_id: int, raw_amount: Any, *, target_id: int | None = None) -> int:
    if raw_amount is None:
        return 0
    if isinstance(raw_amount, bool):
        return int(raw_amount)
    if isinstance(raw_amount, int):
        return raw_amount
    if isinstance(raw_amount, str):
        if raw_amount.lstrip("+-").isdigit():
            return int(raw_amount)
        return 0
    if not isinstance(raw_amount, dict):
        return 0

    amount_type = raw_amount.get("type")
    if amount_type == "static":
        return int(raw_amount.get("amount") or raw_amount.get("value") or 0)

    controller = state.cards[source_id].controller
    if raw_amount.get("controller") == "opponent":
        controller = state.opponent(controller)

    if amount_type == "cards-in-hand":
        return len(state.players[controller].hand)

    if amount_type == "classification-character-count":
        classification = raw_amount.get("classification")
        exclude_self = bool(raw_amount.get("excludeSelf") or raw_amount.get("exclude_self"))
        total = 0
        for cid in state.players[controller].play:
            if exclude_self and cid == source_id:
                continue
            card = engine.card_def(state, cid)
            if card.card_type == CARD_CHARACTER and classification and _card_has_classification(card, str(classification)):
                total += 1
        return total

    if amount_type == "filtered-count":
        owner = raw_amount.get("owner")
        zones = raw_amount.get("zones") or (ZONE_PLAY,)
        if isinstance(zones, str):
            zones = (zones,)
        card_type = raw_amount.get("cardType") or raw_amount.get("card_type")
        filters = raw_amount.get("filters") or raw_amount.get("filter") or ()
        if isinstance(filters, dict):
            filters = (filters,)
        total = 0
        for cid, inst in state.cards.items():
            if inst.zone not in zones:
                continue
            if owner == "you" and inst.controller != state.cards[source_id].controller:
                continue
            if owner == "opponent" and inst.controller == state.cards[source_id].controller:
                continue
            card = engine.card_def(state, cid)
            if card_type and not _card_type_matches(card.card_type, card_type):
                continue
            if all(isinstance(item, dict) and _filter_matches(state, engine, source_id, cid, item) for item in filters):
                total += 1
        return total * int(raw_amount.get("multiplier") or 1)

    return 0


@dataclass(frozen=True, slots=True)
class StaticEffectEntry:
    """A materialized static effect from an active source card."""

    source_id: int
    effect_type: StaticEffectType
    target_mode: str = "self"
    target_classification: str | None = None
    amount: int = 0
    keyword: str | None = None
    cost_reduction_amount: int = 0
    cost_reduction_card_type: str | None = None
    restriction_type: str | None = None
    raw_target: Any = None
    raw_condition: Any = None
    raw_effect: dict[str, Any] = field(default_factory=dict, compare=False, repr=False)
    ability_index: int | None = None
    ability_name: str | None = None
    exclude_self: bool = False
    challenger_filter: Any = None
    source_zones: tuple[str, ...] = (ZONE_PLAY,)

    def applies_to(self, state: GameState, instance_id: int, engine: GameEngine | None = None) -> bool:
        if not _is_active_public_source(state, self.source_id):
            return False
        if instance_id not in state.cards:
            return False
        if engine is not None and self.raw_target is not None:
            return _raw_target_matches(state, engine, self.source_id, instance_id, self.raw_target)

        inst = state.cards[instance_id]
        source_inst = state.cards[self.source_id]
        if inst.zone != ZONE_PLAY:
            return False

        if self.target_mode == "self":
            return instance_id == self.source_id
        if self.target_mode == "your_characters":
            if self.exclude_self and instance_id == self.source_id:
                return False
            return inst.controller == source_inst.controller
        if self.target_mode == "opposing_characters":
            return inst.controller != source_inst.controller
        if self.target_mode == "all_characters":
            return True
        if self.target_mode == "classification":
            if engine is None:
                return True
            card = engine.card_def(state, instance_id)
            if self.target_classification in {CARD_CHARACTER, CARD_ITEM, CARD_LOCATION}:
                return card.card_type == self.target_classification
            return bool(self.target_classification and _card_has_classification(card, self.target_classification))
        return False


@dataclass
class StaticEffectRegistry:
    """Static effect registry.

    `effects` is retained for explicit/manual tests and legacy callers.
    Engine-facing reads also materialize active source abilities when an engine
    is provided.
    """

    effects: list[StaticEffectEntry] = field(default_factory=list)

    def register_effect(self, entry: StaticEffectEntry) -> None:
        if entry not in self.effects:
            self.effects.append(entry)

    def deregister_effects_from_source(self, source_id: int) -> None:
        self.effects = [entry for entry in self.effects if entry.source_id != source_id]

    def get_effects_for_instance(self, state: GameState, instance_id: int, engine: GameEngine | None = None) -> list[StaticEffectEntry]:
        manual = [entry for entry in self.effects if entry.applies_to(state, instance_id, engine)]
        if engine is None:
            return manual
        materialized = [entry for entry in materialize_static_effects(state, engine) if entry.applies_to(state, instance_id, engine)]
        return manual + materialized

    def get_effects_from_source(self, state: GameState, source_id: int, engine: GameEngine | None = None) -> list[StaticEffectEntry]:
        manual = [entry for entry in self.effects if entry.source_id == source_id and _is_active_public_source(state, source_id)]
        if engine is None:
            return manual
        materialized = [entry for entry in materialize_static_effects(state, engine) if entry.source_id == source_id]
        return manual + materialized

    def clear(self) -> None:
        self.effects.clear()


def get_registry(state: GameState) -> StaticEffectRegistry:
    return state.static_effect_registry


def _entries_from_effect(
    state: GameState,
    engine: GameEngine,
    source_id: int,
    effect_obj: Any,
    *,
    ability_index: int | None = None,
    ability_name: str | None = None,
    ability_condition: Any = None,
    source_zones: tuple[str, ...] = (ZONE_PLAY,),
) -> list[StaticEffectEntry]:
    raw = _source_raw(effect_obj)
    kind = _source_kind(effect_obj)

    if ability_condition is not None and not _static_condition_matches(state, engine, source_id, ability_condition):
        return []

    if kind == "conditional":
        condition = raw.get("condition")
        if _static_condition_matches(state, engine, source_id, condition):
            branch = raw.get("then") or raw.get("effect") or raw.get("ifTrue")
        else:
            branch = raw.get("else") or raw.get("ifFalse")
        if isinstance(branch, dict):
            return _entries_from_effect(
                state,
                engine,
                source_id,
                branch,
                ability_index=ability_index,
                ability_name=ability_name,
                ability_condition=None,
                source_zones=source_zones,
            )
        return []

    raw_target = _source_target(effect_obj)
    if raw_target is None:
        raw_target = raw.get("target") or "SELF"

    target_mode, target_classification, exclude_self = _target_mode_from_raw(raw_target)

    common = dict(
        source_id=source_id,
        target_mode=target_mode,
        target_classification=target_classification,
        raw_target=raw_target,
        raw_condition=ability_condition,
        raw_effect=raw,
        ability_index=ability_index,
        ability_name=ability_name,
        exclude_self=exclude_self,
        source_zones=source_zones,
    )

    if kind == "modify-stat":
        stat = str(raw.get("stat") or raw.get("attribute") or raw.get("property") or "strength").replace("-", "_")
        resolved_amount = _resolve_static_amount(state, engine, source_id, _source_amount(effect_obj))
        if stat == "strength":
            return [StaticEffectEntry(effect_type=StaticEffectType.MODIFY_STRENGTH, amount=resolved_amount, **common)]
        if stat == "willpower":
            return [StaticEffectEntry(effect_type=StaticEffectType.MODIFY_WILLPOWER, amount=resolved_amount, **common)]
        if stat == "lore":
            return [StaticEffectEntry(effect_type=StaticEffectType.MODIFY_LORE, amount=resolved_amount, **common)]
        return []

    if kind in {"gain-keyword", "gain-keywords"}:
        keyword_value = raw.get("keyword") or raw.get("keywords") or raw.get("value")
        if keyword_value is None:
            return []
        values = keyword_value if isinstance(keyword_value, (list, tuple)) else (keyword_value,)
        return [
            StaticEffectEntry(
                effect_type=StaticEffectType.GRANT_KEYWORD,
                keyword=_normalize_keyword(str(keyword)),
                **common,
            )
            for keyword in values
        ]

    if kind == "cost-reduction":
        resolved_amount = _resolve_static_amount(state, engine, source_id, _source_amount(effect_obj))
        card_type = raw.get("cardType") or raw.get("card_type")
        return [
            StaticEffectEntry(
                effect_type=StaticEffectType.COST_REDUCTION,
                target_mode="controller",
                raw_target="CONTROLLER",
                cost_reduction_amount=resolved_amount,
                cost_reduction_card_type=str(card_type) if card_type else None,
                source_id=source_id,
                raw_effect=raw,
                ability_index=ability_index,
                ability_name=ability_name,
                source_zones=source_zones,
            )
        ]

    if kind == "additional-inkwell":
        amount = raw.get("amount") if raw.get("amount") is not None else 1
        return [
            StaticEffectEntry(
                effect_type=StaticEffectType.ADDITIONAL_INKWELL,
                target_mode="controller",
                raw_target="CONTROLLER",
                amount=_resolve_static_amount(state, engine, source_id, amount),
                source_id=source_id,
                raw_effect=raw,
                ability_index=ability_index,
                ability_name=ability_name,
                source_zones=source_zones,
            )
        ]

    if kind == "restriction":
        restriction = str(raw.get("restriction") or raw.get("restriction_type") or raw.get("restrictionType") or "")
        challenger_filter = raw.get("challengerFilter") or raw.get("challenger_filter")
        if restriction in {"cant-quest", "cannot-quest"}:
            return [StaticEffectEntry(effect_type=StaticEffectType.QUEST_RESTRICTION, restriction_type="cant-quest", **common)]
        if restriction in {"cant-challenge", "cannot-challenge"}:
            return [StaticEffectEntry(effect_type=StaticEffectType.CHALLENGE_RESTRICTION, restriction_type="cant-challenge", **common)]
        if restriction == "cant-quest-or-challenge":
            return [
                StaticEffectEntry(effect_type=StaticEffectType.QUEST_RESTRICTION, restriction_type="cant-quest-or-challenge", **common),
                StaticEffectEntry(effect_type=StaticEffectType.CHALLENGE_RESTRICTION, restriction_type="cant-quest-or-challenge", **common),
            ]
        if restriction in {"cant-be-challenged", "cannot-be-challenged"}:
            return [
                StaticEffectEntry(
                    effect_type=StaticEffectType.BE_CHALLENGED_RESTRICTION,
                    restriction_type="cant-be-challenged",
                    challenger_filter=challenger_filter,
                    **common,
                )
            ]
        if restriction in {"cant-sing", "cannot-sing"}:
            return [StaticEffectEntry(effect_type=StaticEffectType.SING_RESTRICTION, restriction_type="cant-sing", **common)]

    return []


def _target_mode_from_raw(raw_target: Any) -> tuple[str, str | None, bool]:
    if isinstance(raw_target, str):
        normalized = raw_target.upper()
        if normalized in {"SELF", "SOURCE", "THIS_CHARACTER"}:
            return "self", None, False
        if normalized == "YOUR_OTHER_CHARACTERS":
            return "your_characters", None, True
        if normalized == "YOUR_CHARACTERS":
            return "your_characters", None, False
        if normalized in {"OPPOSING_CHARACTERS", "ALL_OPPOSING_CHARACTERS"}:
            return "opposing_characters", None, False
        if normalized in {"ALL_CHARACTERS", "ANY_CHARACTER"}:
            return "all_characters", None, False
        if normalized in {"YOUR_ITEMS", "ANY_ITEM"}:
            return "classification", CARD_ITEM, False
        if normalized in {"YOUR_LOCATIONS", "ANY_LOCATION"}:
            return "classification", CARD_LOCATION, False
        return "self", None, False

    if isinstance(raw_target, dict):
        exclude_self = bool(raw_target.get("excludeSelf") or raw_target.get("exclude_self"))
        card_types = raw_target.get("cardTypes") or raw_target.get("card_types") or raw_target.get("cardType") or raw_target.get("card_type")
        if isinstance(card_types, str):
            card_types = (card_types,)
        classification = raw_target.get("classification") or raw_target.get("classifications")
        if isinstance(classification, (list, tuple)):
            classification = classification[0] if classification else None
        if classification:
            return "classification", str(classification), exclude_self
        if card_types:
            return "classification", str(tuple(card_types)[0]), exclude_self
        owner = raw_target.get("owner") or raw_target.get("controller")
        if owner in {"you", "controller", "self"}:
            return "your_characters", None, exclude_self
        if owner in {"opponent", "opposing"}:
            return "opposing_characters", None, exclude_self
    return "self", None, False


def materialize_static_effects(state: GameState, engine: GameEngine) -> list[StaticEffectEntry]:
    """Materialize all active phase-1 static effects from public in-play sources."""
    from .card_logic.effect_utils import source_ability_effects, source_ability_kind

    materialized: list[StaticEffectEntry] = []
    for source_id, inst in state.cards.items():
        if not _is_active_public_source(state, source_id):
            continue
        card = engine.card_def(state, source_id)
        for ability_index, ability in enumerate(getattr(card, "source_abilities", ()) or ()):  # SourceAbilityDef
            if source_ability_kind(ability) != "static":
                continue
            ability_raw = _source_raw(ability)
            source_zones = tuple(getattr(ability, "source_zones", ()) or ability_raw.get("sourceZones") or (ZONE_PLAY,))
            if ZONE_PLAY not in source_zones:
                continue
            ability_condition = _ability_condition_raw(ability)
            ability_name = getattr(ability, "name", None) or ability_raw.get("name")
            for effect in source_ability_effects(ability):
                materialized.extend(
                    _entries_from_effect(
                        state,
                        engine,
                        source_id,
                        effect,
                        ability_index=ability_index,
                        ability_name=ability_name,
                        ability_condition=ability_condition,
                        source_zones=source_zones,
                    )
                )
    return materialized


# Derived-state functions

def get_static_modifier(state: GameState, instance_id: int, stat: str, engine: GameEngine | None = None) -> int:
    registry = get_registry(state)
    total = 0
    for effect in registry.get_effects_for_instance(state, instance_id, engine):
        if stat == "strength" and effect.effect_type == StaticEffectType.MODIFY_STRENGTH:
            total += effect.amount
        elif stat == "willpower" and effect.effect_type == StaticEffectType.MODIFY_WILLPOWER:
            total += effect.amount
        elif stat == "lore" and effect.effect_type == StaticEffectType.MODIFY_LORE:
            total += effect.amount
    return total


def effective_strength(state: GameState, instance_id: int, card_def: Any, engine: GameEngine | None = None) -> int:
    inst = state.cards.get(instance_id)
    if inst is None:
        return 0
    base = int(card_def.strength or 0)
    return max(0, base + get_static_modifier(state, instance_id, "strength", engine) + inst.temporary_modifiers.get("strength", 0))


def effective_willpower(state: GameState, instance_id: int, card_def: Any, engine: GameEngine | None = None) -> int:
    inst = state.cards.get(instance_id)
    if inst is None:
        return 0
    base = int(card_def.willpower or 0)
    return max(0, base + get_static_modifier(state, instance_id, "willpower", engine) + inst.temporary_modifiers.get("willpower", 0))


def effective_lore(state: GameState, instance_id: int, card_def: Any, engine: GameEngine | None = None) -> int:
    inst = state.cards.get(instance_id)
    if inst is None:
        return 0
    base = int(card_def.lore or 0)
    return max(0, base + get_static_modifier(state, instance_id, "lore", engine) + inst.temporary_modifiers.get("lore", 0))


def keywords_for_instance(state: GameState, instance_id: int, engine: GameEngine | None = None) -> tuple[str, ...]:
    inst = state.cards.get(instance_id)
    if inst is None:
        return ()
    keywords = {_normalize_keyword(str(keyword)) for keyword in inst.temporary_keywords}
    if engine is not None:
        card = engine.card_def(state, instance_id)
        keywords.update(_normalize_keyword(str(keyword)) for keyword in getattr(card, "keywords", ()) or ())
        keywords.update(_normalize_keyword(str(keyword.keyword)) for keyword in getattr(card, "keyword_defs", ()) or ())
    for effect in get_registry(state).get_effects_for_instance(state, instance_id, engine):
        if effect.effect_type == StaticEffectType.GRANT_KEYWORD and effect.keyword:
            keywords.add(_normalize_keyword(effect.keyword))
    return tuple(sorted(keywords))


def _card_matches_cost_reduction(state: GameState, engine: GameEngine, effect: StaticEffectEntry, card: Any, candidate_id: int | None) -> bool:
    if effect.cost_reduction_card_type and not _card_type_matches(card.card_type, effect.cost_reduction_card_type):
        return False
    raw = effect.raw_effect or {}
    classification = raw.get("classification")
    if classification and not _card_has_classification(card, str(classification)):
        return False
    card_name = raw.get("cardName") or raw.get("name")
    if card_name and not _card_has_name(card, str(card_name)):
        return False
    return True


def static_cost_reductions(
    state: GameState,
    player: int,
    engine: GameEngine | None = None,
    *,
    card: Any | None = None,
    candidate_id: int | None = None,
) -> list[dict[str, Any]]:
    reductions: list[dict[str, Any]] = []
    for effect in get_registry(state).effects:
        source_inst = state.cards.get(effect.source_id)
        if source_inst is None or source_inst.controller != player or source_inst.zone != ZONE_PLAY:
            continue
        if effect.effect_type == StaticEffectType.COST_REDUCTION:
            reductions.append({"amount": effect.cost_reduction_amount, "card_type": effect.cost_reduction_card_type, "source_id": effect.source_id})

    if engine is None:
        return reductions

    for effect in materialize_static_effects(state, engine):
        source_inst = state.cards.get(effect.source_id)
        if source_inst is None or source_inst.controller != player or source_inst.zone != ZONE_PLAY:
            continue
        if effect.effect_type != StaticEffectType.COST_REDUCTION:
            continue
        if card is not None and not _card_matches_cost_reduction(state, engine, effect, card, candidate_id):
            continue
        reductions.append({"amount": effect.cost_reduction_amount, "card_type": effect.cost_reduction_card_type, "source_id": effect.source_id})
    return reductions


def static_additional_inkwell_allowance(state: GameState, player: int, engine: GameEngine | None = None) -> int:
    if engine is None:
        return 0
    total = 0
    for effect in materialize_static_effects(state, engine):
        source_inst = state.cards.get(effect.source_id)
        if source_inst is None or source_inst.controller != player:
            continue
        if effect.effect_type == StaticEffectType.ADDITIONAL_INKWELL:
            total += max(0, int(effect.amount or 0))
    return total


def _challenger_filter_matches(state: GameState, engine: GameEngine, challenger_id: int | None, filter_def: Any) -> bool:
    if filter_def is None:
        return True
    if challenger_id is None:
        return False
    if isinstance(filter_def, dict):
        return _filter_matches(state, engine, challenger_id, challenger_id, filter_def)
    return False


def can_quest(state: GameState, instance_id: int, engine: GameEngine | None = None) -> bool:
    inst = state.cards.get(instance_id)
    if inst is None:
        return False
    for effect in get_registry(state).get_effects_for_instance(state, instance_id, engine):
        if effect.effect_type == StaticEffectType.QUEST_RESTRICTION:
            return False
    return True


def can_challenge(state: GameState, instance_id: int, engine: GameEngine | None = None) -> bool:
    inst = state.cards.get(instance_id)
    if inst is None:
        return False
    for effect in get_registry(state).get_effects_for_instance(state, instance_id, engine):
        if effect.effect_type == StaticEffectType.CHALLENGE_RESTRICTION:
            return False
    return True


def can_be_challenged(state: GameState, defender_id: int, challenger_id: int | None, engine: GameEngine) -> bool:
    for effect in get_registry(state).get_effects_for_instance(state, defender_id, engine):
        if effect.effect_type != StaticEffectType.BE_CHALLENGED_RESTRICTION:
            continue
        if _challenger_filter_matches(state, engine, challenger_id, effect.challenger_filter):
            return False
    return True


# Creation helpers retained for tests and manual entries

def create_modify_stat_effect(source_id: int, stat: str, amount: int, target_mode: str = "self", target_classification: str | None = None) -> StaticEffectEntry:
    normalized = stat.replace("-", "_").lower()
    if normalized == "strength":
        effect_type = StaticEffectType.MODIFY_STRENGTH
    elif normalized == "willpower":
        effect_type = StaticEffectType.MODIFY_WILLPOWER
    elif normalized == "lore":
        effect_type = StaticEffectType.MODIFY_LORE
    else:
        raise ValueError(f"Unknown stat: {stat}")
    return StaticEffectEntry(source_id=source_id, effect_type=effect_type, target_mode=target_mode, target_classification=target_classification, amount=int(amount))


def create_keyword_grant_effect(source_id: int, keyword: str, target_mode: str = "your_characters", target_classification: str | None = None) -> StaticEffectEntry:
    return StaticEffectEntry(source_id=source_id, effect_type=StaticEffectType.GRANT_KEYWORD, target_mode=target_mode, target_classification=target_classification, keyword=_normalize_keyword(keyword))


def create_cost_reduction_effect(source_id: int, amount: int, card_type: str | None = None) -> StaticEffectEntry:
    return StaticEffectEntry(
        source_id=source_id,
        effect_type=StaticEffectType.COST_REDUCTION,
        target_mode="self",
        cost_reduction_amount=int(amount),
        cost_reduction_card_type=card_type,
    )


def create_quest_restriction_effect(source_id: int, target_mode: str = "self", target_classification: str | None = None) -> StaticEffectEntry:
    return StaticEffectEntry(
        source_id=source_id,
        effect_type=StaticEffectType.QUEST_RESTRICTION,
        target_mode=target_mode,
        target_classification=target_classification,
        restriction_type="cannot_quest",
    )


def create_challenge_restriction_effect(source_id: int, target_mode: str = "self", target_classification: str | None = None) -> StaticEffectEntry:
    return StaticEffectEntry(source_id=source_id, effect_type=StaticEffectType.CHALLENGE_RESTRICTION, target_mode=target_mode, target_classification=target_classification, restriction_type="cant-challenge")


def parse_static_effects_from_card(card_abilities: tuple, source_id: int) -> list[StaticEffectEntry]:
    """Legacy parser used by tests/manual callers.

    Runtime engine reads should prefer materialize_static_effects(state, engine).
    """
    from .card_logic.effect_utils import source_ability_effects, source_ability_kind

    # Use a minimal fake-free path: only direct simple static entries that do not
    # require state/engine condition evaluation are returned here.
    effects: list[StaticEffectEntry] = []
    for ability in card_abilities:
        if source_ability_kind(ability) != "static":
            continue
        for effect_obj in source_ability_effects(ability):
            raw = _source_raw(effect_obj)
            kind = _source_kind(effect_obj)
            target = _source_target(effect_obj) or raw.get("target") or "SELF"
            target_mode, target_class, exclude_self = _target_mode_from_raw(target)
            if kind == "modify-stat":
                stat = str(raw.get("stat") or raw.get("attribute") or "strength")
                amount = _source_amount(effect_obj)
                if isinstance(amount, int) or (isinstance(amount, str) and amount.lstrip("+-").isdigit()):
                    entry = create_modify_stat_effect(source_id, stat, int(amount), target_mode, target_class)
                    object.__setattr__(entry, "exclude_self", exclude_self)
                    effects.append(entry)
            elif kind in {"gain-keyword", "gain-keywords"}:
                keyword = raw.get("keyword") or raw.get("keywords") or raw.get("value")
                if keyword:
                    values = keyword if isinstance(keyword, (list, tuple)) else (keyword,)
                    for value in values:
                        entry = create_keyword_grant_effect(source_id, str(value), target_mode, target_class)
                        object.__setattr__(entry, "exclude_self", exclude_self)
                        effects.append(entry)
            elif kind == "cost-reduction":
                amount = _source_amount(effect_obj)
                if isinstance(amount, int) or (isinstance(amount, str) and amount.isdigit()):
                    effects.append(create_cost_reduction_effect(source_id, int(amount), raw.get("cardType") or raw.get("card_type")))
            elif kind == "restriction":
                restriction = str(raw.get("restriction") or "")
                if "quest" in restriction:
                    effects.append(create_quest_restriction_effect(source_id, target_mode, target_class))
                if "challenge" in restriction and restriction != "cant-be-challenged":
                    effects.append(create_challenge_restriction_effect(source_id, target_mode, target_class))
    return effects


def register_static_effects_for_card(state: GameState, instance_id: int, card_abilities: tuple) -> None:
    registry = get_registry(state)
    for effect in parse_static_effects_from_card(card_abilities, instance_id):
        registry.register_effect(effect)


def deregister_static_effects_for_card(state: GameState, instance_id: int) -> None:
    get_registry(state).deregister_effects_from_source(instance_id)


def has_static_effect(state: GameState, instance_id: int, effect_type: StaticEffectType, engine: GameEngine | None = None) -> bool:
    return any(effect.effect_type == effect_type for effect in get_registry(state).get_effects_for_instance(state, instance_id, engine))