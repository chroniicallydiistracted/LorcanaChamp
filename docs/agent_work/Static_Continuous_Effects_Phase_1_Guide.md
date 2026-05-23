# LorcanaChamp Development Phase Guide

## Static / Continuous Effects Registry Phase 1 — Lorcanito Parity Alignment

This guide implements the next LorcanaChamp development phase after the `if-you-do` closure. The scope is **static / continuous effects phase 1**.

The implementation intentionally prefers Lorcanito parity over preserving the current MVP static-effect shape. This phase replaces the current entry-only static registry with a Lorcanito-aligned derived/materialized model while preserving backward-compatible helper names where possible.

---

## 1. Lorcanito source findings

### Files inspected

```text
~/LorcanaChamp/references/lorcana-simulator/packages/lorcana/lorcana-engine/src/rules/static-effect-registry.ts
~/LorcanaChamp/references/lorcana-simulator/packages/lorcana/lorcana-engine/src/rules/derived-state.ts
~/LorcanaChamp/references/lorcana-simulator/packages/lorcana/lorcana-engine/src/runtime-moves/rules/static-ability-utils.ts
~/LorcanaChamp/references/lorcana-simulator/packages/lorcana/lorcana-engine/src/runtime-moves/rules/static-effects-invalidation.ts
~/LorcanaChamp/references/lorcana-simulator/packages/lorcana/lorcana-engine/src/operations/static-context.ts
~/LorcanaChamp/references/lorcana-simulator/packages/lorcana/lorcana-engine/src/runtime-moves/moves/core/quest.ts
~/LorcanaChamp/references/lorcana-simulator/packages/lorcana/lorcana-engine/src/runtime-moves/rules/challenge-rules.ts
~/LorcanaChamp/references/lorcana-simulator/packages/lorcana/lorcana-engine/src/runtime-moves/rules/play-card-rules.ts
```

### Confirmed Lorcanito behavior

`static-effect-registry.ts` is the main source of truth. Lorcanito does not treat static effects as one-shot resolved effects and does not permanently mutate printed card definitions. It builds a static-effect registry from active public cards in play.

The Lorcanito registry materializes these buckets:

```ts
export interface StaticEffectRegistry {
  byTarget: Map<CardInstanceId, MaterializedStaticEffect[]>;
  byPlayer: Map<PlayerId, MaterializedStaticEffect[]>;
  global: MaterializedStaticEffect[];
  bySource: Map<CardInstanceId, MaterializedStaticEffect[]>;
}
```

Confirmed materialized effect kinds include:

```ts
"modify-stat"
"stat-floor"
"damage-source-stat-override"
"gain-keyword"
"lose-keyword"
"grant-classification"
"grant-ability"
"grant-abilities-while-here"
"restriction"
"cost-reduction"
"cost-increase"
"property-modification"
```

Important Lorcanito static-effect resolution rules:

1. Active sources are cards in play only. Cards under shifted cards are not active public sources.
2. Static effects are derived from active source card abilities, not applied once and forgotten.
3. Static effects are bucketed by target card, target player, global effects, and source card.
4. Conditions are evaluated at registry-build/read time.
5. Stat modifiers are resolved before keyword/restriction/cost effects so derived stat conditions can be evaluated correctly.
6. Keyword-grant effects are materialized before later keyword-dependent targets.
7. Static targets are resolved through the same target-descriptor system used by runtime targeting, with legacy aliases still supported.
8. Static restrictions are consulted by move validation, quest validation, challenge validation, play-card rules, and derived-state projection.
9. Static cost reductions can originate from play or hand source zones depending on the ability.
10. Static registry invalidation is centralized through `invalidateStaticEffects`; the next read rebuilds the registry.

### Important edge cases from Lorcanito

```text
- SELF target means source instance only.
- YOUR_OTHER_* excludes the source instance.
- sourceZones controls whether static cost reductions apply from hand, play, discard, or inkwell.
- Conditional static wrappers are supported when the branch is a static effect.
- Restrictions may target cards or players.
- cant-quest-or-challenge blocks both quest and challenge.
- cant-be-challenged applies to the defender, not the attacker.
- challengerFilter/costRestriction controls which challengers are blocked.
- Static effects are not copied from cards under a shifted stack.
```

---

## 2. Current LorcanaChamp findings

### Files inspected

```text
lorcana_bot/static_effects.py
lorcana_bot/engine.py
lorcana_bot/state.py
lorcana_bot/condition_evaluator.py
lorcana_bot/importers/lorcanito_source_mapper.py
lorcana_bot/decks/runtime_executability.py
lorcana_bot/card_logic/effect_utils.py
tests/test_static_effects.py
tests/test_real_deck_runtime_executability.py
tests/test_source_effect_mapping.py
data/lorcanito_runtime_extracted/reports/unsupported/unsupported_summary.json
data/lorcanito_runtime_extracted/reports/unsupported/unsupported_report.md
```

### Current behavior

`lorcana_bot/static_effects.py` currently has an MVP registry with a flat list of `StaticEffectEntry` objects and placeholder target matching. It explicitly states it does not support complex layer ordering or condition-dependent modifiers. It supports broad concepts such as stat modifiers, keyword grants, cost reduction, and quest/challenge restriction, but target and condition matching are not Lorcanito-parity.

`GameState` stores `static_effect_registry` directly as state. Current play lifecycle registers static effects when a permanent enters play and deregisters when it leaves play.

`GameEngine` already queries static effects in these places:

```text
can_quest
challenge_targets
keywords_for_instance
effective_strength
effective_willpower
effective_lore
play_cost
_apply_quest
```

Current issues:

```text
1. The registry is lifecycle-entry based instead of Lorcanito-style derived/materialized from active sources.
2. Static source ability support is still reported as mapped_not_executable.
3. Static target matching treats classification/card type as placeholder logic.
4. Static conditions are not evaluated with a consistent runtime condition path.
5. cant-be-challenged is not represented as a defender-side static restriction.
6. additional-inkwell static effects are not wired to legal ink actions.
7. sourceZones hand/play semantics are only partially handled for hand cost reduction and not reflected in static support classification.
8. The runtime report still shows `ability.type:static:mapped_not_executable = 510` as the top unsupported pattern.
```

Current report confirms the next major blocker:

```text
mapped_not_executable: 516
ability:static object count: 580
top unsupported pattern: ability.type:static:mapped_not_executable = 510
```

---

## 3. Required larger refactor callout

The correct Lorcanito-parity answer is a **larger refactor**, not a small patch.

The current static registry stores pre-parsed entries at card-entry time. Lorcanito derives/materializes static effects from active public sources and resolves them through target/condition matching at read time or through a cache invalidation layer.

This phase should therefore replace the static-effect model with a derived/materialized registry while keeping legacy helper names so existing code does not all have to be rewritten in the same phase.

The phase 1 target is not full Lorcanito static parity. It is the first materialized static registry layer covering the largest currently reported static families:

```text
gain-keyword
modify-stat
restriction
cost-reduction
additional-inkwell
```

Out of scope for this phase:

```text
stat-floor
damage-source-stat-override
lose-keyword
grant-classification
grant-ability / grant-abilities-while-here
property-modification except additional-inkwell-like turn allowance
cost-increase
suppression index
full cached invalidation counter
under-card static effects
replacement effects
```

---

## 4. Implementation actions

## File 1 — `lorcana_bot/static_effects.py`

Replace the entire file with the following full contents.

```python
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


def _ability_condition_raw(ability: Any) -> dict[str, Any] | None:
    condition = getattr(ability, "condition", None)
    if condition is not None:
        raw = getattr(condition, "raw", None)
        if isinstance(raw, dict):
            return dict(raw)
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
        amount = raw.get("modifier")
        if amount is None:
            amount = raw.get("amount")
        if amount is None:
            amount = raw.get("value")
        resolved_amount = _resolve_static_amount(state, engine, source_id, amount)
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
        amount = raw.get("amount")
        if amount is None:
            reduction = raw.get("reduction")
            if isinstance(reduction, dict):
                amount = reduction.get("ink")
        resolved_amount = _resolve_static_amount(state, engine, source_id, amount)
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
    return StaticEffectEntry(source_id=source_id, effect_type=StaticEffectType.COST_REDUCTION, target_mode="controller", cost_reduction_amount=int(amount), cost_reduction_card_type=card_type)


def create_quest_restriction_effect(source_id: int, target_mode: str = "self", target_classification: str | None = None) -> StaticEffectEntry:
    return StaticEffectEntry(source_id=source_id, effect_type=StaticEffectType.QUEST_RESTRICTION, target_mode=target_mode, target_classification=target_classification, restriction_type="cant-quest")


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
                amount = raw.get("modifier") if raw.get("modifier") is not None else raw.get("amount", 0)
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
                amount = raw.get("amount") or raw.get("value") or 0
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
```

---

## File 2 — `lorcana_bot/engine.py`

### 2A. Replace the static-effect import block

Find the current `from .static_effects import (` block and replace the whole block with:

```python
from .static_effects import (
    effective_strength as static_effective_strength,
    effective_willpower as static_effective_willpower,
    effective_lore as static_effective_lore,
    keywords_for_instance as static_keywords_for_instance,
    static_cost_reductions,
    static_additional_inkwell_allowance,
    register_static_effects_for_card,
    deregister_static_effects_for_card,
    StaticEffectType,
    create_modify_stat_effect,
    create_keyword_grant_effect,
    create_cost_reduction_effect,
    can_quest as static_can_quest,
    can_challenge as static_can_challenge,
    can_be_challenged as static_can_be_challenged,
)
```

### 2B. Replace the inking availability block in `legal_actions`

Find this block:

```python
        extra_ink_key = f"additional_inkwell:{player}"
        extra_inks = int(state.turn_metadata.get(extra_ink_key, 0) or 0)
        if not state.turn_player_has_inked or extra_inks > 0:
```

Replace with:

```python
        extra_ink_key = f"additional_inkwell:{player}"
        static_extra_ink_key = f"static_additional_inkwell_used:{player}"
        stored_extra_inks = int(state.turn_metadata.get(extra_ink_key, 0) or 0)
        static_allowance = static_additional_inkwell_allowance(state, player, self)
        static_used = int(state.turn_metadata.get(static_extra_ink_key, 0) or 0)
        extra_inks = stored_extra_inks + max(0, static_allowance - static_used)
        if not state.turn_player_has_inked or extra_inks > 0:
```

### 2C. Replace `can_quest`

Replace the entire `def can_quest` method with:

```python
    def can_quest(self, state: GameState, source: int) -> bool:
        inst = state.cards[source]
        if inst.zone != ZONE_PLAY or inst.controller != state.active_player:
            return False
        card = self.card_def(state, source)
        if card.card_type != CARD_CHARACTER:
            return False
        if inst.exerted or inst.drying:
            return False
        if source in set(state.turn_metadata.get("cant_quest_until_turn_end", ()) or ()):
            return False
        if self.has_keyword(state, source, KEYWORD_RECKLESS):
            return False
        if not static_can_quest(state, source, self):
            return False
        return True
```

### 2D. Replace `challenge_targets`

Replace the entire `def challenge_targets` method with:

```python
    def challenge_targets(self, state: GameState, source: int) -> list[int]:
        inst = state.cards[source]
        player = inst.controller
        if inst.zone != ZONE_PLAY or player != state.active_player:
            return []
        source_def = self.card_def(state, source)
        if source_def.card_type != CARD_CHARACTER:
            return []
        if inst.exerted:
            return []
        if inst.drying and not self.has_keyword(state, source, KEYWORD_RUSH):
            return []
        if not static_can_challenge(state, source, self):
            return []

        opponent = state.opponent(player)
        character_candidates: list[int] = []
        bodyguards: list[int] = []
        location_candidates: list[int] = []
        for target in state.players[opponent].play:
            target_inst = state.cards[target]
            target_def = self.card_def(state, target)
            if target_def.card_type == CARD_CHARACTER:
                if not target_inst.exerted:
                    continue
                if self.has_keyword(state, target, KEYWORD_EVASIVE) and not self.has_keyword(state, source, KEYWORD_EVASIVE):
                    continue
                if check_cannot_be_challenged(state, target, source):
                    continue
                if not static_can_be_challenged(state, target, source, self):
                    continue
                if self.has_keyword(state, target, KEYWORD_BODYGUARD):
                    bodyguards.append(target)
                character_candidates.append(target)
            elif target_def.card_type == CARD_LOCATION:
                location_candidates.append(target)

        if bodyguards:
            return bodyguards
        return character_candidates + location_candidates
```

### 2E. Replace `keywords_for_instance`, `effective_strength`, `effective_willpower`, `effective_lore`, and `play_cost`

Replace these five whole methods with:

```python
    def keywords_for_instance(self, state: GameState, instance_id: int) -> tuple[str, ...]:
        """Get printed, temporary, and static-granted keywords."""
        return static_keywords_for_instance(state, instance_id, self)

    def has_keyword(self, state: GameState, instance_id: int, keyword: str) -> bool:
        return keyword in self.keywords_for_instance(state, instance_id)

    def effective_strength(self, state: GameState, instance_id: int) -> int:
        card = self.card_def(state, instance_id)
        return static_effective_strength(state, instance_id, card, self)

    def effective_willpower(self, state: GameState, instance_id: int) -> int:
        card = self.card_def(state, instance_id)
        return static_effective_willpower(state, instance_id, card, self)

    def effective_lore(self, state: GameState, instance_id: int) -> int:
        card = self.card_def(state, instance_id)
        return static_effective_lore(state, instance_id, card, self)

    def play_cost(self, state: GameState, player: int, instance_id: int) -> int:
        """Calculate play cost including Lorcanito-style static cost reductions."""
        card = self.card_def(state, instance_id)
        reductions = self._applicable_cost_reductions(state, player, card.card_type)
        hand_source_reduction = self._hand_source_cost_reduction(state, player, instance_id)
        if hand_source_reduction:
            reductions.append({"amount": hand_source_reduction, "card_type": card.card_type, "source_id": instance_id})
        reductions.extend(static_cost_reductions(state, player, self, card=card, candidate_id=instance_id))
        return max(0, int(card.cost) - sum(int(reduction.get("amount", 0)) for reduction in reductions))
```

### 2F. Replace `_apply_ink`

Replace the entire `_apply_ink` method with:

```python
    def _apply_ink(self, state: GameState, action: Action) -> None:
        """Apply ink action with static additional-inkwell allowance."""
        assert action.card is not None
        if state.cards[action.card].zone == ZONE_DISCARD and not self._can_ink_from_discard(state, action.actor):
            raise IllegalActionError("Cannot ink from discard")

        extra_ink_key = f"additional_inkwell:{action.actor}"
        static_extra_ink_key = f"static_additional_inkwell_used:{action.actor}"
        stored_extra_inks = int(state.turn_metadata.get(extra_ink_key, 0) or 0)
        static_allowance = static_additional_inkwell_allowance(state, action.actor, self)
        static_used = int(state.turn_metadata.get(static_extra_ink_key, 0) or 0)
        static_remaining = max(0, static_allowance - static_used)

        self._put_into_inkwell_eventful(state, action.card, actor=action.actor)

        if state.turn_player_has_inked:
            if stored_extra_inks > 0:
                state.turn_metadata[extra_ink_key] = stored_extra_inks - 1
            elif static_remaining > 0:
                state.turn_metadata[static_extra_ink_key] = static_used + 1
            else:
                raise IllegalActionError("No remaining ink action available")
        else:
            state.turn_player_has_inked = True
            state.players[action.actor].turn_flags.played_ink = True
```

### 2G. Replace `_register_lifecycle_effects_for_public_permanent`

Replace the entire method with:

```python
    def _register_lifecycle_effects_for_public_permanent(
        self,
        state: GameState,
        card_id: int,
    ) -> None:
        """Register non-derived lifecycle effects for a public permanent.

        Lorcanito static effects are derived/materialized from active public
        sources when queried. Do not register static effects here, or they will
        double-apply against the derived static registry.
        """
        inst = state.cards.get(card_id)
        if inst is None or inst.zone != ZONE_PLAY or inst.stack_parent_id is not None:
            return

        card = self.card_def(state, card_id)
        if card.card_type == CARD_ACTION:
            return

        source_abilities = getattr(card, "source_abilities", None) or getattr(card, "abilities", ())
        deregister_static_effects_for_card(state, card_id)
        register_replacement_effects_for_card(state, card_id, source_abilities)
```

### 2H. Replace `_apply_quest`

Replace the entire `_apply_quest` method with:

```python
    def _apply_quest(self, state: GameState, action: Action) -> None:
        """Apply quest action with derived static lore."""
        assert action.source is not None
        source = action.source
        lore = self.effective_lore(state, source)
        self._exert_eventful(state, source, actor=action.actor, source_id=source, emit_event=False)
        state.cards[source].has_quested_this_turn = True
        self._gain_lore_eventful(state, action.actor, lore, source_id=source, emit_event=False)

        self.emit_event(
            state,
            EVENT_QUESTED,
            actor=action.actor,
            source=source,
            payload={
                "player_id": action.actor,
                "subject_card_id": source,
                "lore": lore,
            },
        )
```

---

## File 3 — `lorcana_bot/card_logic/effect_utils.py`

### Add `additional-inkwell` to `STATIC_EFFECT_KIND_MAP`

Find this block inside `STATIC_EFFECT_KIND_MAP`:

```python
    "cost-reduction": "cost_reduction",
    "cost_reduction": "cost_reduction",
```

Replace with:

```python
    "cost-reduction": "cost_reduction",
    "cost_reduction": "cost_reduction",
    "additional-inkwell": "additional_inkwell",
    "additional_inkwell": "additional_inkwell",
```

---

## File 4 — `lorcana_bot/importers/lorcanito_source_mapper.py`

### 4A. Replace the static/replacement branch in `map_raw_ability`

Find this block in `map_raw_ability`:

```python
    elif kind in {AbilityKind.STATIC, AbilityKind.REPLACEMENT}:
        # Static and replacement abilities are structurally preserved, but they
        # are not projected as one-shot action/trigger effects. They remain
        # reported as unsupported/mapped-not-executable at the source ability
        # layer unless handled by a dedicated registry path.
        execution = ExecutionStatus.MAPPED_NOT_EXECUTABLE
```

Replace with:

```python
    elif kind == AbilityKind.STATIC:
        execution = (
            ExecutionStatus.EXECUTABLE
            if _phase1_static_ability_supported(raw, effects, condition)
            else ExecutionStatus.MAPPED_NOT_EXECUTABLE
        )
    elif kind == AbilityKind.REPLACEMENT:
        execution = ExecutionStatus.MAPPED_NOT_EXECUTABLE
```

### 4B. Add these helper functions immediately after `map_raw_effect`

```python
def _phase1_static_ability_supported(
    raw: dict[str, Any],
    effects: tuple[SourceEffectDef, ...],
    condition: SourceConditionDef | None,
) -> bool:
    if condition is not None and condition.execution_status != ExecutionStatus.EXECUTABLE:
        return False
    source_zones = tuple(raw.get("sourceZones", raw.get("source_zones", ("play",))) or ("play",))
    if any(zone not in {"play", "hand"} for zone in source_zones):
        return False
    if not effects:
        return False
    return all(_phase1_static_effect_supported(effect) for effect in effects)


def _phase1_static_condition_supported(raw: Any) -> bool:
    if raw is None:
        return True
    if not isinstance(raw, dict):
        return False
    kind = str(raw.get("type") or raw.get("kind") or "unknown")
    return kind in SUPPORTED_CONDITION_KINDS


def _phase1_static_target_supported(raw: Any) -> bool:
    if raw is None:
        return True
    if isinstance(raw, str):
        return raw in EXECUTABLE_TARGET_ALIASES or raw in SUPPORTED_TARGET_ALIASES
    if isinstance(raw, dict):
        return _source_target_shape_supported(raw)
    return False


def _phase1_static_amount_supported(raw: Any) -> bool:
    if raw is None:
        return True
    if isinstance(raw, bool):
        return False
    if isinstance(raw, int):
        return True
    if isinstance(raw, str):
        return raw.lstrip("+-").isdigit() or raw == "full"
    if isinstance(raw, dict):
        return raw.get("type") in {
            "static",
            "cards-in-hand",
            "classification-character-count",
            "filtered-count",
            "characters-in-play",
        }
    return False


def _phase1_static_effect_supported(effect: SourceEffectDef) -> bool:
    raw = effect.raw or {}
    kind = effect.kind

    if kind == "conditional":
        if not _phase1_static_condition_supported(raw.get("condition")):
            return False
        branch = raw.get("then") or raw.get("effect") or raw.get("ifTrue")
        else_branch = raw.get("else") or raw.get("ifFalse")
        branches = [item for item in (branch, else_branch) if isinstance(item, dict)]
        if not branches:
            return False
        return all(_phase1_static_effect_supported(map_raw_effect(branch_raw)) for branch_raw in branches)

    if kind not in {
        "modify-stat",
        "gain-keyword",
        "gain-keywords",
        "restriction",
        "cost-reduction",
        "additional-inkwell",
    }:
        return False

    if kind in {"modify-stat", "gain-keyword", "gain-keywords", "restriction"}:
        raw_target = raw.get("target")
        if effect.target is not None and effect.target.execution_status != ExecutionStatus.EXECUTABLE:
            return False
        if not _phase1_static_target_supported(raw_target):
            return False

    if kind in {"modify-stat", "cost-reduction", "additional-inkwell"}:
        amount = raw.get("modifier") if raw.get("modifier") is not None else raw.get("amount")
        if amount is None and isinstance(raw.get("reduction"), dict):
            amount = raw["reduction"].get("ink")
        if not _phase1_static_amount_supported(amount):
            return False

    if kind == "restriction" and not raw.get("restriction"):
        return False

    return True
```

---

## File 5 — `lorcana_bot/decks/runtime_executability.py`

### 5A. Replace `SUPPORTED_STATIC_EFFECT_KINDS`

Replace the whole block with:

```python
SUPPORTED_STATIC_EFFECT_KINDS = frozenset({
    "modify_stat",
    "gain_keyword",
    "cost_reduction",
    "additional_inkwell",
    "restriction",
    "grant_abilities_while_here",
    "grant_discard_inkability",
})
```

### 5B. Replace `_classify_static_effect_kind`

Replace the entire function with:

```python
def _classify_static_effect_kind(effect: Any) -> tuple[RuntimeSupportStatus, tuple[str, ...]]:
    raw_kind = str(getattr(effect, "kind", "unknown"))
    raw = getattr(effect, "raw", {}) or {}

    if raw_kind == "conditional":
        condition = getattr(effect, "condition", None)
        raw_condition = raw.get("condition") if isinstance(raw, dict) else None
        if condition is not None and not _source_static_condition_shape_supported(effect, condition):
            return ("scaffold_only", (f"unsupported_static_condition:{_condition_kind(condition)}",))
        if condition is None and raw_condition is not None and not _source_static_condition_shape_supported(effect, raw_condition):
            return ("scaffold_only", (f"unsupported_static_condition:{_condition_kind(raw_condition)}",))
        branch = raw.get("then") or raw.get("effect") or raw.get("ifTrue") if isinstance(raw, dict) else None
        else_branch = raw.get("else") or raw.get("ifFalse") if isinstance(raw, dict) else None
        branch_statuses = []
        branch_blockers = []
        from lorcana_bot.importers.lorcanito_source_mapper import map_raw_effect
        for raw_branch in (branch, else_branch):
            if not isinstance(raw_branch, dict):
                continue
            status, blockers = _classify_static_effect_kind(map_raw_effect(raw_branch))
            branch_statuses.append(status)
            branch_blockers.extend(blockers)
        if not branch_statuses:
            return ("scaffold_only", ("unsupported_static_effect:conditional",))
        if any(status != "executable" for status in branch_statuses):
            return ("scaffold_only", tuple(sorted(set(branch_blockers))))
        return ("executable", ())

    kind = to_engine_static_kind(raw_kind)
    condition = getattr(effect, "condition", None)
    if condition is not None and not _source_static_condition_shape_supported(effect, condition):
        return ("scaffold_only", (f"unsupported_static_condition:{_condition_kind(effect.condition)}",))
    if kind in SUPPORTED_STATIC_EFFECT_KINDS:
        return ("executable", ())
    return ("scaffold_only", (f"unsupported_static_effect:{raw_kind}",))
```

### 5C. Replace `_source_static_condition_shape_supported`

Replace the entire function with:

```python
def _source_static_condition_shape_supported(effect: Any, condition: Any) -> bool:
    """Static conditions are supported when the runtime condition evaluator supports their kind."""
    return _condition_kind(condition) in SUPPORTED_EFFECT_CONDITIONS
```

---

## File 6 — `tests/test_static_continuous_phase1.py`

Create this new file with the following full contents.

```python
from lorcana_bot.actions import Action
from lorcana_bot.card_logic import ExecutionStatus, MappingStatus, SourceAbilityDef, SourceEffectDef
from lorcana_bot.cards import CardDatabase, CardDef
from lorcana_bot.constants import ACTION_CHALLENGE, ACTION_INK_CARD, ACTION_QUEST, KEYWORD_EVASIVE, KEYWORD_WARD, ZONE_HAND, ZONE_PLAY
from lorcana_bot.engine import GameEngine
from lorcana_bot.state import CardInstance, GameState, PlayerState
from lorcana_bot.static_effects import static_additional_inkwell_allowance


def _static_ability(effect: SourceEffectDef, *, condition=None, source_zones=("play",), name="STATIC"):
    return SourceAbilityDef(
        id=name.lower().replace(" ", "-"),
        kind="static",
        name=name,
        effects=(effect,),
        condition=condition,
        source_zones=tuple(source_zones),
        mapping_status=MappingStatus.STRUCTURALLY_MAPPED,
        execution_status=ExecutionStatus.EXECUTABLE,
        raw={
            "type": "static",
            "name": name,
            "sourceZones": list(source_zones),
            "effect": effect.raw,
        },
    )


def _state_with_play(engine, entries):
    state = GameState(players=[PlayerState(), PlayerState()], cards={})
    for instance_id, owner, name in entries:
        card = engine.db.get(name)
        state.cards[instance_id] = CardInstance(
            instance_id=instance_id,
            card_id=card.id,
            owner=owner,
            controller=owner,
            zone=ZONE_PLAY,
        )
        state.players[owner].play.append(instance_id)
    return state


def test_static_gain_keyword_materializes_for_your_other_characters_only():
    ward_source = CardDef(
        "aurora",
        "Aurora",
        "sapphire",
        5,
        True,
        "character",
        3,
        5,
        2,
        source_abilities=(
            _static_ability(
                SourceEffectDef(
                    kind="gain-keyword",
                    raw={
                        "type": "gain-keyword",
                        "keyword": "Ward",
                        "target": {
                            "selector": "all",
                            "owner": "you",
                            "zones": ["play"],
                            "cardTypes": ["character"],
                            "excludeSelf": True,
                        },
                    },
                    mapping_status=MappingStatus.STRUCTURALLY_MAPPED,
                    execution_status=ExecutionStatus.EXECUTABLE,
                ),
                name="PROTECTIVE EMBRACE",
            ),
        ),
    )
    ally = CardDef("ally", "Ally", "amber", 2, True, "character", 1, 2, 1)
    enemy = CardDef("enemy", "Enemy", "ruby", 2, True, "character", 1, 2, 1)
    engine = GameEngine(CardDatabase([ward_source, ally, enemy]))
    state = _state_with_play(engine, [(1, 0, "Aurora"), (2, 0, "Ally"), (3, 1, "Enemy")])

    assert not engine.has_keyword(state, 1, KEYWORD_WARD)
    assert engine.has_keyword(state, 2, KEYWORD_WARD)
    assert not engine.has_keyword(state, 3, KEYWORD_WARD)


def test_static_modify_stat_uses_dynamic_classification_character_count():
    hades = CardDef(
        "hades",
        "Hades",
        "amber",
        8,
        True,
        "character",
        3,
        6,
        1,
        subtypes=("Villain",),
        source_abilities=(
            _static_ability(
                SourceEffectDef(
                    kind="modify-stat",
                    raw={
                        "type": "modify-stat",
                        "stat": "lore",
                        "target": "SELF",
                        "modifier": {
                            "type": "classification-character-count",
                            "classification": "Villain",
                            "controller": "you",
                            "excludeSelf": True,
                        },
                    },
                    mapping_status=MappingStatus.STRUCTURALLY_MAPPED,
                    execution_status=ExecutionStatus.EXECUTABLE,
                ),
                name="SINISTER PLOT",
            ),
        ),
    )
    villain = CardDef("villain", "Villain Ally", "amber", 2, True, "character", 1, 2, 1, subtypes=("Villain",))
    hero = CardDef("hero", "Hero Ally", "amber", 2, True, "character", 1, 2, 1, subtypes=("Hero",))
    engine = GameEngine(CardDatabase([hades, villain, hero]))
    state = _state_with_play(engine, [(1, 0, "Hades"), (2, 0, "Villain Ally"), (3, 0, "Hero Ally")])

    assert engine.effective_lore(state, 1) == 2


def test_static_condition_has_another_character_controls_self_keyword():
    pascal = CardDef(
        "pascal",
        "Pascal",
        "emerald",
        1,
        True,
        "character",
        1,
        1,
        1,
        source_abilities=(
            _static_ability(
                SourceEffectDef(
                    kind="gain-keyword",
                    raw={"type": "gain-keyword", "keyword": "Evasive", "target": "SELF"},
                    mapping_status=MappingStatus.STRUCTURALLY_MAPPED,
                    execution_status=ExecutionStatus.EXECUTABLE,
                ),
                condition={"type": "has-another-character"},
                name="CAMOUFLAGE",
            ),
        ),
    )
    ally = CardDef("ally", "Ally", "amber", 2, True, "character", 1, 2, 1)
    engine = GameEngine(CardDatabase([pascal, ally]))
    state = _state_with_play(engine, [(1, 0, "Pascal")])
    assert not engine.has_keyword(state, 1, KEYWORD_EVASIVE)

    state.cards[2] = CardInstance(2, "ally", owner=0, controller=0, zone=ZONE_PLAY)
    state.players[0].play.append(2)
    assert engine.has_keyword(state, 1, KEYWORD_EVASIVE)


def test_static_cant_be_challenged_with_challenger_cost_filter_blocks_only_matching_attackers():
    defender = CardDef(
        "hook",
        "Captain Hook",
        "steel",
        5,
        True,
        "character",
        3,
        4,
        1,
        source_abilities=(
            _static_ability(
                SourceEffectDef(
                    kind="restriction",
                    raw={
                        "type": "restriction",
                        "restriction": "cant-be-challenged",
                        "target": "SELF",
                        "challengerFilter": {"type": "cost-comparison", "operator": "lte", "value": 3},
                    },
                    mapping_status=MappingStatus.STRUCTURALLY_MAPPED,
                    execution_status=ExecutionStatus.EXECUTABLE,
                ),
                name="STOLEN DUST",
            ),
        ),
    )
    cheap = CardDef("cheap", "Cheap", "ruby", 3, True, "character", 2, 2, 1)
    expensive = CardDef("expensive", "Expensive", "ruby", 4, True, "character", 2, 2, 1)
    engine = GameEngine(CardDatabase([defender, cheap, expensive]))
    state = _state_with_play(engine, [(1, 0, "Captain Hook"), (2, 1, "Cheap"), (3, 1, "Expensive")])
    state.active_player = 1
    state.cards[1].exerted = True

    assert 1 not in engine.challenge_targets(state, 2)
    assert 1 in engine.challenge_targets(state, 3)


def test_static_additional_inkwell_allows_exactly_one_extra_ink_per_turn():
    belle = CardDef(
        "belle",
        "Belle",
        "sapphire",
        4,
        True,
        "character",
        2,
        4,
        1,
        source_abilities=(
            _static_ability(
                SourceEffectDef(
                    kind="additional-inkwell",
                    raw={"type": "additional-inkwell", "amount": 1},
                    mapping_status=MappingStatus.STRUCTURALLY_MAPPED,
                    execution_status=ExecutionStatus.EXECUTABLE,
                ),
                name="READ A BOOK",
            ),
        ),
    )
    inkable = CardDef("inkable", "Inkable", "amber", 1, True, "character", 1, 1, 1)
    engine = GameEngine(CardDatabase([belle, inkable]))
    state = GameState(players=[PlayerState(), PlayerState()], cards={})
    state.active_player = 0
    state.cards[1] = CardInstance(1, "belle", owner=0, controller=0, zone=ZONE_PLAY)
    state.players[0].play.append(1)
    for cid in (2, 3, 4):
        state.cards[cid] = CardInstance(cid, "inkable", owner=0, controller=0, zone=ZONE_HAND)
        state.players[0].hand.append(cid)

    assert static_additional_inkwell_allowance(state, 0, engine) == 1
    state = engine.apply_action(state, Action(ACTION_INK_CARD, actor=0, card=2))
    state = engine.apply_action(state, Action(ACTION_INK_CARD, actor=0, card=3))

    remaining_ink_actions = [action for action in engine.legal_actions(state, 0) if action.kind == ACTION_INK_CARD]
    assert remaining_ink_actions == []
```

---

## File 7 — `tests/test_source_effect_mapping.py`

Add this test at the bottom of the file.

```python
def test_phase1_static_ability_maps_executable_when_static_registry_supports_shape():
    from lorcana_bot.importers.lorcanito_source_mapper import map_raw_ability

    ability = map_raw_ability(
        {
            "id": "protective-embrace",
            "type": "static",
            "effect": {
                "type": "gain-keyword",
                "keyword": "Ward",
                "target": {
                    "selector": "all",
                    "owner": "you",
                    "zones": ["play"],
                    "cardTypes": ["character"],
                    "excludeSelf": True,
                },
            },
        }
    )

    assert ability.kind == "static"
    assert ability.execution_status == ExecutionStatus.EXECUTABLE
```

---

## File 8 — `tests/test_real_deck_runtime_executability.py`

Add this test after the existing `test_if_you_do_condition_is_supported_by_runtime_executability` test.

```python
def test_phase1_static_runtime_executability_accepts_supported_static_shapes():
    static = SourceAbilityDef(
        id="static-ward",
        kind="static",
        effects=(
            SourceEffectDef(
                kind="gain-keyword",
                raw={
                    "type": "gain-keyword",
                    "keyword": "Ward",
                    "target": {
                        "selector": "all",
                        "owner": "you",
                        "zones": ["play"],
                        "cardTypes": ["character"],
                        "excludeSelf": True,
                    },
                },
                mapping_status=MappingStatus.STRUCTURALLY_MAPPED,
                execution_status=ExecutionStatus.EXECUTABLE,
            ),
        ),
        mapping_status=MappingStatus.STRUCTURALLY_MAPPED,
        execution_status=ExecutionStatus.EXECUTABLE,
        raw={
            "id": "static-ward",
            "type": "static",
            "effect": {
                "type": "gain-keyword",
                "keyword": "Ward",
                "target": {
                    "selector": "all",
                    "owner": "you",
                    "zones": ["play"],
                    "cardTypes": ["character"],
                    "excludeSelf": True,
                },
            },
        },
    )

    result = classify_card_runtime_support(
        _card("static-ward", source_abilities=(static,))
    )

    assert result.status == "executable"
    assert not any(blocker.startswith("unsupported_static_effect") for blocker in result.blockers)
```

---

## 5. Why each fix is required

### `static_effects.py`

Required because current static behavior is entry-registration based and target matching is placeholder. Lorcanito materializes active static effects from public in-play sources into target/player/global/source buckets. The phase 1 replacement moves LorcanaChamp toward materialized derived static reads while preserving existing helper names.

### `engine.py`

Required because static effects only matter if core rules read them:

```text
quest legality
challenge legality
defender challenge restriction
effective stats
effective keywords
play cost
additional inkwell allowance
quest lore gain
```

### `effect_utils.py`

Required because `additional-inkwell` is a static effect kind in source data and must normalize to an engine static kind.

### `lorcanito_source_mapper.py`

Required because unsupported report movement must reflect actual support. Static abilities are currently forced to `mapped_not_executable` even when their runtime shape is implemented. This guide changes only phase-1 supported static shapes to executable.

### `runtime_executability.py`

Required because deck/runtime classifier must agree with source mapping and actual runtime support. Otherwise static abilities would continue to show stale blockers.

### Tests

Required because static effects are rule-affecting derived state. Tests prove behavior, not just that source objects are no longer reported unsupported.

---

## 6. Test commands

Run compile first:

```bash
python3 -m py_compile \
  lorcana_bot/static_effects.py \
  lorcana_bot/engine.py \
  lorcana_bot/card_logic/effect_utils.py \
  lorcana_bot/importers/lorcanito_source_mapper.py \
  lorcana_bot/decks/runtime_executability.py
```

Run targeted tests:

```bash
python3 -m pytest \
  tests/test_static_effects.py \
  tests/test_static_continuous_phase1.py \
  tests/test_source_effect_mapping.py::test_phase1_static_ability_maps_executable_when_static_registry_supports_shape \
  tests/test_real_deck_runtime_executability.py::test_phase1_static_runtime_executability_accepts_supported_static_shapes \
  -q
```

Expected targeted result:

```text
all selected tests pass
```

Run full suite:

```bash
python3 -m pytest -q
```

Expected result:

```text
all tests pass
```

Regenerate unsupported report only after full pytest passes:

```bash
python3 scripts/report_lorcanito_v2_unsupported.py
```

Check report movement:

```bash
python3 - <<'PY'
import json
summary = json.load(open('data/lorcanito_runtime_extracted/reports/unsupported/unsupported_summary.json'))
print('mapped_not_executable =', summary['unsupported_by_reason'].get('mapped_not_executable'))
print('ability.type:static:mapped_not_executable =', next((item['count'] for item in summary.get('top_unsupported_patterns', []) if item['pattern'] == 'ability.type:static:mapped_not_executable'), 0))
print('unsupported_static_effect object counts =', {k:v for k,v in summary.get('top_object_kind_counts', {}).items() if 'static' in k or k.startswith('effect:')})
PY
```

Expected movement:

```text
- mapped_not_executable should decrease.
- ability.type:static:mapped_not_executable should decrease from 510.
- unsupported static records should not disappear for out-of-scope effects like grant-abilities-while-here, stat-floor, damage-source-stat-override, suppress-ability, etc.
```

Do not require a specific numeric drop on the first run. The exact movement depends on how many current source static abilities are phase-1 shapes and how many parent ability records were blocked only by static status.

---

## 7. Parity proof

```text
Lorcanito:
static-effect-registry.ts builds active static effects from cards in play.

LorcanaChamp after this phase:
static_effects.materialize_static_effects builds active phase-1 static effects from cards in play.
```

```text
Lorcanito:
Static effects are keyed by target/player/source/global and read by derived state.

LorcanaChamp after this phase:
StaticEffectRegistry keeps compatibility entries, while engine-facing reads materialize active source effects and query them through get_effects_for_instance/static_cost_reductions/static_additional_inkwell_allowance.
```

```text
Lorcanito:
derived-state.ts computes effective strength, willpower, and lore using static registry modifiers.

LorcanaChamp after this phase:
GameEngine.effective_strength/effective_willpower/effective_lore delegate to static_effects effective functions.
```

```text
Lorcanito:
quest.ts and challenge-rules.ts consult static restrictions.

LorcanaChamp after this phase:
GameEngine.can_quest, challenge_targets, and static_can_be_challenged consult phase-1 materialized restrictions.
```

```text
Lorcanito:
play-card-rules.ts applies static cost reductions.

LorcanaChamp after this phase:
GameEngine.play_cost includes static_cost_reductions(state, player, self, card=...).
```

```text
Lorcanito:
source static effects are real executable runtime model pieces when supported by registry.

LorcanaChamp after this phase:
lorcanito_source_mapper and runtime_executability classify phase-1 supported static shapes as executable, while unsupported static shapes remain blocked.
```

---

## 8. Edge cases and risks

### Risks

```text
1. This is a larger refactor. Some old tests may assume static_effect_registry.effects contains lifecycle-registered entries after play. That assumption is intentionally no longer true for source-derived static effects.

2. Keyword-dependent static target matching is only phase-1. Lorcanito has a multi-pass keyword-augmented target matching layer. This phase handles printed/temporary keyword filters, but not every derived keyword dependency.

3. Source mapper movement may reduce mapped_not_executable significantly. That is expected only for phase-1 static shapes. If out-of-scope static kinds disappear from blockers, that is a bug.

4. additional-inkwell changes legal inking behavior. The new turn metadata key `static_additional_inkwell_used:{player}` must reset naturally with turn metadata at turn cleanup. If turn metadata is not fully cleared at turn transition, add explicit cleanup there.

5. Static restrictions that target players are not fully implemented in phase 1. Card-targeted quest/challenge/be-challenged restrictions are covered.
```

### Required follow-up if tests reveal regression

If tests fail around `state.static_effect_registry.effects` counts after play, do **not** restore lifecycle static registration. Update the test expectation to derived behavior or use explicit manual `register_effect()` in the test. Restoring lifecycle registration would double-apply source static effects and diverge from Lorcanito.

---

## 9. Acceptance criteria

This phase is accepted only when:

```text
1. py_compile passes.
2. Existing static tests pass or are updated away from lifecycle-registration assumptions.
3. New phase-1 static tests pass.
4. Full pytest passes.
5. Unsupported report regenerates with no errors.
6. ability.type:static:mapped_not_executable decreases from 510.
7. unsupported report still preserves unsupported blockers for out-of-scope static systems.
8. No copied source-derived static effect double-applies after a card enters play.
```

