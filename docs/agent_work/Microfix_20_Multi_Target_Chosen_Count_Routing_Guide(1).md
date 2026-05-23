# Microfix 20 — Multi-Target Chosen Count Routing

This guide starts from the current `main` baseline after Microfix 19.

Microfix 20 implements Lorcanito-style **multi-target chosen count routing** for the runtime paths that already have enough LorcanaChamp infrastructure:

```text
1. action-card target selection
2. activated ability target selection
3. bag-resolution target input
4. pending multi_target input
5. source mapper executability for count > 1 / exact / up-to target shapes
```

This phase does **not** implement opponent-choice ownership transfer, slotted targets, or destination/ordering mechanics. Those are separate runtime orchestration problems. This phase is about selected target arrays/counts.

---

# 1. Lorcanito source paths inspected

Inspected from the attached Lorcanito package:

```text
lorcana/lorcana-types/src/abilities/target-types.ts
lorcana/lorcana-types/src/targeting/enum-expansions.ts
lorcana/lorcana-types/src/targeting/normalize.ts
lorcana/lorcana-engine/src/targeting/runtime/target-availability.ts
lorcana/lorcana-engine/src/targeting/runtime/target-resolver.ts
lorcana/lorcana-engine/src/runtime-moves/resolution/action-effects/selection-context.ts
lorcana/lorcana-engine/src/runtime-moves/resolution/action-effects/selection-state.ts
lorcana/lorcana-engine/src/runtime-moves/resolution/action-effects/pending-action-effects.ts
lorcana/lorcana-engine/src/runtime-moves/resolution/resolve-bag.ts
```

Current LorcanaChamp paths inspected from `main`:

```text
data/lorcanito_runtime_extracted/reports/unsupported/unsupported_summary.json
lorcana_bot/targeting.py
lorcana_bot/importers/lorcanito_source_mapper.py
lorcana_bot/engine.py
lorcana_bot/effects.py
lorcana_bot/pending_effects.py
tests/test_targeting.py
tests/test_source_projection_policy.py
tests/test_activated_abilities_execution.py
```

---

# 2. Exact Lorcanito types/functions/mechanics found

## Lorcanito target count semantics

Lorcanito target descriptors allow count-shaped selections:

```ts
count: 1
count: 2
count: "all"
count: { min: number, max: number }
count: { upTo: number }
```

Lorcanito stores selected targets as arrays, not a single scalar target.

## Lorcanito target availability

Lorcanito target availability computes:

```text
candidateCount
minSelections
maxSelections
allowsExplicitEmptyTargetSelection
canSatisfyRequiredSelection
requiresExplicitTargetSelection
shouldAutoRejectForNoValidTargets
```

Important parity rule:

```text
A multi-target selection can satisfy a required minimum only when enough distinct candidates exist,
unless duplicate targets are explicitly allowed.
```

## Lorcanito selection context

Lorcanito `selection-context.ts` builds target-selection contexts with:

```text
submitField: "targets"
minSelections
maxSelections
candidate ids
```

The input submitted back to resolution is:

```text
targets: CardInstanceId[]
```

## Lorcanito pending input cloning

Lorcanito `pending-action-effects.ts` clones/preserves:

```text
targets
currentTargets
contextTargets
destinations
amount
```

This confirms that multi-target selected arrays must survive suspension/resume and bag resolution.

---

# 3. Current LorcanaChamp behavior

Current LorcanaChamp already has partial support:

```text
TargetDescriptor.min_count / max_count
normalize_target_descriptor(count=...)
analyze_target_selection_availability()
apply_target_protections()
ACTION_PLAY_CARD choice={"targets": (...)}
EffectResolutionContext.current_targets
EffectResolver._resolve_selected_card_targets()
pending_effects requirement_kind="multi_target"
GameEngine.legal_actions() pending multi_target branch
GameEngine._apply_resolve_pending_effect() multi_target branch
```

Current gaps:

```text
1. The source mapper rejects chosen target count > 1.
2. The source mapper rejects count dicts with exactly.
3. Activated ability legal action generation emits one action per single target, not selected target tuples.
4. Activated ability application validates action.target only, not action.choice["targets"].
5. Bag target input actions emit one target at a time even when descriptor min/max requires multiple.
6. Target selection combination enumeration is duplicated or local instead of shared.
```

Current action cards already have a local combination loop in `_targeted_play_actions()`, so this phase should centralize that behavior instead of adding another local pattern.

---

# 4. Expected Lorcanito-aligned behavior

After Microfix 20:

```text
{"selector": "chosen", "count": 2, ...}
```

should be structurally executable when all other target filters are executable.

Action cards should emit legal actions like:

```python
Action(
    ACTION_PLAY_CARD,
    target=first_selected_target,
    choice={"targets": (target_a, target_b)}
)
```

Activated abilities should emit legal actions like:

```python
Action(
    ACTION_USE_ABILITY,
    target=first_selected_target,
    choice={
        "ability_id": "...",
        "ability_index": 0,
        "targets": (target_a, target_b),
    }
)
```

Bag/pending target input should preserve selected target tuples:

```python
choice={"bag_id": ..., "targets": (target_a, target_b)}
choice={"pending_effect_id": ..., "targets": (target_a, target_b)}
```

Effects should continue to resolve through:

```text
EffectResolutionContext.current_targets
EffectResolver._resolve_selected_card_targets()
```

---

# 5. Files to modify

```text
lorcana_bot/targeting.py
lorcana_bot/importers/lorcanito_source_mapper.py
lorcana_bot/engine.py

tests/test_targeting.py
tests/test_source_projection_policy.py
tests/test_activated_abilities_execution.py
```

Do not modify these unless validation proves a direct issue:

```text
lorcana_bot/effects.py
lorcana_bot/pending_effects.py
```

---

# 6. Previous code and replacement code

## File 1 — `lorcana_bot/targeting.py`

### Change 1A — add `itertools` import

#### Previous code

```python
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any
```

#### Replacement code

```python
import itertools
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any
```

---

### Change 1B — update `_normalize_max_count()`

#### Previous code

```python
def _normalize_max_count(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, str) and value.lower() in {"any", "all", "unbounded", "unlimited", "inf", "infinity"}:
        return None
    if isinstance(value, dict):
        if "upTo" in value:
            return int(value["upTo"])
        if "up_to" in value:
            return int(value["up_to"])
        if "max" in value:
            return int(value["max"])
    return int(value)
```

#### Replacement code

```python
def _normalize_max_count(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, str) and value.lower() in {"any", "all", "unbounded", "unlimited", "inf", "infinity"}:
        return None
    if isinstance(value, dict):
        if "exactly" in value:
            return int(value["exactly"])
        if "upTo" in value:
            return int(value["upTo"])
        if "up_to" in value:
            return int(value["up_to"])
        if "max" in value:
            return int(value["max"])
    return int(value)
```

---

### Change 1C — update `_normalize_count_bounds()`

#### Previous code

```python
def _normalize_count_bounds(value: Any, default_min: int, default_max: int | None) -> tuple[int, int | None]:
    if value is None:
        return default_min, default_max
    if isinstance(value, dict):
        if "upTo" in value:
            return 0, int(value["upTo"])
        if "up_to" in value:
            return 0, int(value["up_to"])
        if "min" in value or "max" in value:
            min_count = int(value.get("min", default_min))
            max_count = _normalize_max_count(value.get("max", default_max))
            return min_count, max_count
    if isinstance(value, str) and value.lower() in {"all", "any"}:
        return default_min, None
    count = int(value)
    return count, count
```

#### Replacement code

```python
def _normalize_count_bounds(value: Any, default_min: int, default_max: int | None) -> tuple[int, int | None]:
    if value is None:
        return default_min, default_max
    if isinstance(value, dict):
        if "exactly" in value:
            exact = int(value["exactly"])
            return exact, exact
        if "upTo" in value:
            return 0, int(value["upTo"])
        if "up_to" in value:
            return 0, int(value["up_to"])
        if "min" in value or "max" in value:
            min_count = int(value.get("min", default_min))
            max_count = _normalize_max_count(value.get("max", default_max))
            return min_count, max_count
    if isinstance(value, str) and value.lower() in {"all", "any"}:
        return default_min, None
    count = int(value)
    return count, count
```

---

### Change 1D — add shared target-selection enumerator

Place this immediately after `analyze_target_selection_availability()` and before `apply_target_protections()`.

#### Add code

```python
def enumerate_target_selections(
    candidates: tuple[TargetCandidate, ...],
    descriptor: TargetDescriptor,
    *,
    candidate_kind: str = "card",
) -> tuple[tuple[int, ...], ...]:
    """Enumerate legal target id selections for a descriptor.

    Lorcanito target inputs are submitted as arrays.  This helper centralizes
    Python enumeration for action cards, activated abilities, bag input, and
    pending input so all paths share the same min/max/duplicate semantics.
    """
    ids = tuple(candidate.id for candidate in candidates if candidate.kind == candidate_kind)
    if not ids:
        return ((),) if descriptor.min_count <= 0 else ()

    min_count = max(0, int(descriptor.min_count or 0))
    if descriptor.max_count is None:
        max_count = len(ids) if not descriptor.allow_duplicate_targets else max(min_count, len(ids))
    else:
        max_count = max(0, int(descriptor.max_count))

    if not descriptor.allow_duplicate_targets:
        max_count = min(max_count, len(ids))

    if max_count < min_count:
        return ()

    selections: list[tuple[int, ...]] = []
    if min_count == 0:
        selections.append(())

    for count in range(max(1, min_count), max_count + 1):
        if descriptor.allow_duplicate_targets:
            selections.extend(tuple(choice) for choice in itertools.product(ids, repeat=count))
        else:
            selections.extend(tuple(choice) for choice in itertools.combinations(ids, count))

    return tuple(selections)
```

---

## File 2 — `lorcana_bot/importers/lorcanito_source_mapper.py`

### Change 2A — add source target count support helper

Place this immediately before `_source_target_shape_supported()`.

#### Add code

```python
def _source_target_count_supported(count: Any) -> bool:
    if count is None:
        return True

    if isinstance(count, bool):
        return False

    if isinstance(count, int):
        return count >= 1

    if isinstance(count, str):
        normalized = count.strip().lower()
        return normalized.isdigit() and int(normalized) >= 1

    if isinstance(count, dict):
        if not set(count) <= {"upTo", "up_to", "min", "max", "exactly"}:
            return False
        numeric_values = []
        for key in ("upTo", "up_to", "min", "max", "exactly"):
            if key in count:
                try:
                    numeric_values.append(int(count[key]))
                except (TypeError, ValueError):
                    return False
        return bool(numeric_values) and all(value >= 0 for value in numeric_values)

    return False
```

---

### Change 2B — replace count handling in `_source_target_shape_supported()`

Inside `_source_target_shape_supported()`, find the `selector == "chosen"` count block.

#### Previous code

```python
    count = raw.get("count", 1)
    if isinstance(count, dict):
        if not set(count) <= {"upTo", "up_to", "min", "max"}:
            return False
    elif count not in {1, "1", None}:
        return False
```

#### Replacement code

```python
    count = raw.get("count", 1)
    if not _source_target_count_supported(count):
        return False
```

---

## File 3 — `lorcana_bot/engine.py`

### Change 3A — update activated ability legal-action generation

Inside `legal_actions()`, find this block:

#### Previous code

```python
            target_candidates = self._activated_ability_target_candidates(state, ability, player)
            if target_candidates is None:
                continue
            if target_candidates:
                for target_id in target_candidates:
                    actions.append(Action(
                        ACTION_USE_ABILITY,
                        actor=player,
                        source=ability.source_instance_id,
                        target=target_id,
                        choice={"ability_id": ability.ability_id, "ability_index": ability.ability_index},
                    ))
            else:
                actions.append(Action(
                    ACTION_USE_ABILITY,
                    actor=player,
                    source=ability.source_instance_id,
                    choice={"ability_id": ability.ability_id, "ability_index": ability.ability_index},
                ))
```

#### Replacement code

```python
            target_selections = self._activated_ability_target_selections(state, ability, player)
            if target_selections is None:
                continue
            if target_selections:
                for selected_targets in target_selections:
                    if selected_targets:
                        actions.append(Action(
                            ACTION_USE_ABILITY,
                            actor=player,
                            source=ability.source_instance_id,
                            target=selected_targets[0],
                            choice={
                                "ability_id": ability.ability_id,
                                "ability_index": ability.ability_index,
                                "targets": selected_targets,
                            },
                        ))
                    else:
                        actions.append(Action(
                            ACTION_USE_ABILITY,
                            actor=player,
                            source=ability.source_instance_id,
                            choice={"ability_id": ability.ability_id, "ability_index": ability.ability_index},
                        ))
            else:
                actions.append(Action(
                    ACTION_USE_ABILITY,
                    actor=player,
                    source=ability.source_instance_id,
                    choice={"ability_id": ability.ability_id, "ability_index": ability.ability_index},
                ))
```

---

### Change 3B — replace `_activated_ability_target_candidates()`

#### Previous code

```python
    def _activated_ability_target_candidates(
        self,
        state: GameState,
        ability: ActivatedAbility,
        player: int,
    ) -> tuple[int, ...] | None:
        descriptors = self._activated_ability_explicit_target_descriptors(ability)
        if not descriptors:
            return ()
        if len(descriptors) > 1:
            return None
        descriptor = descriptors[0]
        from .targeting import TargetQueryContext, apply_target_protections, resolve_candidate_targets
        context = TargetQueryContext(actor=player, source_id=ability.source_instance_id)
        candidates = apply_target_protections(
            state,
            self,
            resolve_candidate_targets(state, self, descriptor, context),
            descriptor,
            context,
        )
        return tuple(candidate.id for candidate in candidates if candidate.kind == "card")
```

#### Replacement code

```python
    def _activated_ability_target_selections(
        self,
        state: GameState,
        ability: ActivatedAbility,
        player: int,
    ) -> tuple[tuple[int, ...], ...] | None:
        descriptors = self._activated_ability_explicit_target_descriptors(ability)
        if not descriptors:
            return ((),)
        if len(descriptors) > 1:
            return None

        descriptor = descriptors[0]
        from .targeting import (
            TargetQueryContext,
            analyze_target_selection_availability,
            apply_target_protections,
            enumerate_target_selections,
            resolve_candidate_targets,
        )

        context = TargetQueryContext(actor=player, source_id=ability.source_instance_id)
        candidates = apply_target_protections(
            state,
            self,
            resolve_candidate_targets(state, self, descriptor, context),
            descriptor,
            context,
        )
        availability = analyze_target_selection_availability(descriptor, candidates)
        if not availability.can_satisfy_required_selection:
            return None

        selections = enumerate_target_selections(candidates, descriptor, candidate_kind="card")
        return selections

    def _activated_ability_target_candidates(
        self,
        state: GameState,
        ability: ActivatedAbility,
        player: int,
    ) -> tuple[int, ...] | None:
        """Backward-compatible single-card candidate wrapper."""
        selections = self._activated_ability_target_selections(state, ability, player)
        if selections is None:
            return None
        return tuple(selection[0] for selection in selections if selection)
```

---

### Change 3C — update bag `target_actions()` helper

Inside `_bag_resolution_input_actions()`, find nested function:

```python
        def target_actions(raw_target: Any, base_choice: dict[str, Any]) -> list[Action]:
```

Within that function, replace the import block.

#### Previous import block

```python
            from .targeting import TargetQueryContext, apply_target_protections, normalize_target_descriptor, resolve_candidate_targets
```

#### Replacement import block

```python
            from .targeting import (
                TargetQueryContext,
                apply_target_protections,
                enumerate_target_selections,
                normalize_target_descriptor,
                resolve_candidate_targets,
            )
```

Then in the same nested function, replace the action-building loop.

#### Previous code

```python
            result: list[Action] = []
            for candidate in candidates:
                if candidate.kind != "card":
                    continue
                choice = dict(base_choice)
                choice["targets"] = (candidate.id,)
                result.append(Action(
                    ACTION_RESOLVE_BAG,
                    actor=player,
                    source=entry.source_id,
                    target=candidate.id,
                    choice=choice,
                ))
            return result
```

#### Replacement code

```python
            result: list[Action] = []
            for selected in enumerate_target_selections(candidates, desc, candidate_kind="card"):
                choice = dict(base_choice)
                choice["targets"] = selected
                result.append(Action(
                    ACTION_RESOLVE_BAG,
                    actor=player,
                    source=entry.source_id,
                    target=selected[0] if selected else None,
                    choice=choice,
                ))
            return result
```

---

### Change 3D — update `_bag_target_actions_from_raw()`

Inside `_bag_target_actions_from_raw()`, replace the import block.

#### Previous code

```python
        from .targeting import TargetQueryContext, apply_target_protections, normalize_target_descriptor, resolve_candidate_targets
```

#### Replacement code

```python
        from .targeting import (
            TargetQueryContext,
            apply_target_protections,
            enumerate_target_selections,
            normalize_target_descriptor,
            resolve_candidate_targets,
        )
```

Then replace the action-building loop.

#### Previous code

```python
        result = []
        for candidate in candidates:
            if candidate.kind != "card":
                continue
            choice = dict(base_choice)
            choice["targets"] = (candidate.id,)
            result.append(Action(ACTION_RESOLVE_BAG, actor=player, source=entry.source_id, target=candidate.id, choice=choice))
        return result
```

#### Replacement code

```python
        result = []
        for selected in enumerate_target_selections(candidates, desc, candidate_kind="card"):
            choice = dict(base_choice)
            choice["targets"] = selected
            result.append(Action(
                ACTION_RESOLVE_BAG,
                actor=player,
                source=entry.source_id,
                target=selected[0] if selected else None,
                choice=choice,
            ))
        return result
```

---

### Change 3E — update `_targeted_play_actions()` to use shared helper

Inside `_targeted_play_actions()`, replace the targeting import block.

#### Previous code

```python
        from .targeting import (
            TargetQueryContext,
            analyze_target_selection_availability,
            apply_target_protections,
            resolve_candidate_targets,
        )
```

#### Replacement code

```python
        from .targeting import (
            TargetQueryContext,
            analyze_target_selection_availability,
            apply_target_protections,
            enumerate_target_selections,
            resolve_candidate_targets,
        )
```

Then replace the manual card-id combination loop.

#### Previous code

```python
            card_ids = tuple(c.id for c in candidates if c.kind == "card")
            player_ids = tuple(c.id for c in candidates if c.kind == "player")
            for player_id in player_ids:
                actions.append(Action(
                    ACTION_PLAY_CARD,
                    actor=player,
                    card=source,
                    choice={"target_kind": "player", "player": player_id},
                ))

            max_count = desc.max_count if desc.max_count is not None else len(card_ids)
            max_count = min(max_count, len(card_ids))
            min_count = max(0, desc.min_count)
            for count in range(min_count, max_count + 1):
                for selected in combinations(card_ids, count):
                    if not selected:
                        continue
                    if len(selected) == 1:
                        actions.append(Action(
                            ACTION_PLAY_CARD,
                            actor=player,
                            card=source,
                            target=selected[0],
                            choice={"targets": selected},
                        ))
                    else:
                        actions.append(Action(
                            ACTION_PLAY_CARD,
                            actor=player,
                            card=source,
                            target=selected[0],
                            choice={"targets": selected},
                        ))
```

#### Replacement code

```python
            player_ids = tuple(c.id for c in candidates if c.kind == "player")
            for player_id in player_ids:
                actions.append(Action(
                    ACTION_PLAY_CARD,
                    actor=player,
                    card=source,
                    choice={"target_kind": "player", "player": player_id},
                ))

            for selected in enumerate_target_selections(candidates, desc, candidate_kind="card"):
                if not selected:
                    continue
                actions.append(Action(
                    ACTION_PLAY_CARD,
                    actor=player,
                    card=source,
                    target=selected[0],
                    choice={"targets": selected},
                ))
```

Leave the local `from itertools import combinations` at the top of `_targeted_play_actions()` for now if it remains unused; it can be cleaned later. If linting complains, remove it.

---

### Change 3F — update `_apply_use_ability()` selected-target validation

Inside `_apply_use_ability()`, find:

#### Previous code

```python
        selected_targets = (action.target,) if action.target is not None else ()
        if self._activated_ability_requires_target(ability):
            valid_targets = self._activated_ability_target_candidates(state, ability, action.actor)
            if not valid_targets or action.target not in valid_targets:
                raise IllegalActionError("USE_ABILITY requires a valid selected target")
```

#### Replacement code

```python
        if action.choice and isinstance(action.choice, dict) and action.choice.get("targets") is not None:
            selected_targets = tuple(int(target_id) for target_id in action.choice.get("targets") or ())
        elif action.target is not None:
            selected_targets = (action.target,)
        else:
            selected_targets = ()

        if self._activated_ability_requires_target(ability):
            valid_selections = self._activated_ability_target_selections(state, ability, action.actor)
            if valid_selections is None or selected_targets not in valid_selections:
                raise IllegalActionError("USE_ABILITY requires a valid selected target selection")
```

---

# 7. Tests to add/update

## File 4 — `tests/test_targeting.py`

### Change 4A — import `enumerate_target_selections`

In the `from lorcana_bot.targeting import (` import list, add:

```python
    enumerate_target_selections,
```

near the other helper imports.

---

### Change 4B — add count normalization test

Place this test after:

```python
def test_normalize_target_descriptor_accepts_lorcanito_and_python_field_names():
```

Add:

```python
def test_normalize_target_descriptor_supports_multi_target_counts():
    exact = normalize_target_descriptor({
        "selector": "chosen",
        "count": 2,
        "zones": [ZONE_PLAY],
        "cardTypes": [CARD_CHARACTER],
    })
    exact_dict = normalize_target_descriptor({
        "selector": "chosen",
        "count": {"exactly": 2},
        "zones": [ZONE_PLAY],
        "cardTypes": [CARD_CHARACTER],
    })
    up_to = normalize_target_descriptor({
        "selector": "chosen",
        "count": {"upTo": 2},
        "zones": [ZONE_PLAY],
        "cardTypes": [CARD_CHARACTER],
    })

    assert exact is not None
    assert exact.min_count == 2
    assert exact.max_count == 2

    assert exact_dict is not None
    assert exact_dict.min_count == 2
    assert exact_dict.max_count == 2

    assert up_to is not None
    assert up_to.min_count == 0
    assert up_to.max_count == 2
```

---

### Change 4C — add target selection enumeration test

Place this after:

```python
def test_target_candidate_and_context_dataclasses_are_stable_shapes():
```

Add:

```python
def test_enumerate_target_selections_uses_lorcanito_min_max_count_semantics():
    candidates = (
        TargetCandidate(kind="card", id=1, controller=0, zone=ZONE_PLAY),
        TargetCandidate(kind="card", id=2, controller=0, zone=ZONE_PLAY),
        TargetCandidate(kind="card", id=3, controller=0, zone=ZONE_PLAY),
    )
    exact_two = TargetDescriptor(
        selector="chosen",
        min_count=2,
        max_count=2,
        zones=(ZONE_PLAY,),
        card_types=(CARD_CHARACTER,),
    )
    up_to_two = TargetDescriptor(
        selector="chosen",
        min_count=0,
        max_count=2,
        zones=(ZONE_PLAY,),
        card_types=(CARD_CHARACTER,),
    )

    assert enumerate_target_selections(candidates, exact_two) == (
        (1, 2),
        (1, 3),
        (2, 3),
    )

    assert enumerate_target_selections(candidates, up_to_two) == (
        (),
        (1,),
        (2,),
        (3,),
        (1, 2),
        (1, 3),
        (2, 3),
    )
```

---

## File 5 — `tests/test_source_projection_policy.py`

### Change 5A — add mapper/projection test for count > 1

Place this at the bottom of the file after the Microfix 19 tests.

Add:

```python
def test_microfix20_lorcanito_chosen_count_two_target_projects():
    ability = map_raw_ability({
        "type": "action",
        "effect": {
            "type": "deal-damage",
            "amount": 1,
            "target": {
                "selector": "chosen",
                "count": 2,
                "owner": "opponent",
                "zones": ["play"],
                "cardTypes": ["character"],
            },
        },
    })

    assert ability.execution_status == ExecutionStatus.EXECUTABLE
    assert ability.effects[0].target is not None
    assert ability.effects[0].target.execution_status == ExecutionStatus.EXECUTABLE

    effects = project_action_effects(_card(ability))

    assert len(effects) == 1
    assert effects[0].kind == "deal_damage"
    assert isinstance(effects[0].target, dict)
    assert effects[0].target["selector"] == "chosen"
    assert effects[0].target["count"] == 2
    assert effects[0].target["cardTypes"] == ["character"]


def test_microfix20_lorcanito_exactly_count_target_projects():
    ability = map_raw_ability({
        "type": "action",
        "effect": {
            "type": "exert",
            "target": {
                "selector": "chosen",
                "count": {"exactly": 2},
                "owner": "any",
                "zones": ["play"],
                "cardTypes": ["character"],
            },
        },
    })

    assert ability.execution_status == ExecutionStatus.EXECUTABLE
    assert ability.effects[0].target is not None
    assert ability.effects[0].target.execution_status == ExecutionStatus.EXECUTABLE
```

---

## File 6 — `tests/test_activated_abilities_execution.py`

This file already uses mock card definitions for activated ability flow tests. Keep the style consistent with the existing file.

### Change 6A — add helper for chosen two characters

Place this immediately after:

```python
def _chosen_character_target() -> SourceTargetDef:
```

Add:

```python
def _chosen_two_characters_target() -> SourceTargetDef:
    return SourceTargetDef(
        kind="selector",
        selector="chosen",
        count=2,
        owner="opponent",
        zones=("play",),
        card_types=("character",),
        raw={
            "selector": "chosen",
            "count": 2,
            "owner": "opponent",
            "zones": ["play"],
            "cardTypes": ["character"],
        },
    )
```

---

### Change 6B — add legal-action and application test

Place this inside `class TestUseAbilityAction`, immediately after:

```python
    def test_use_ability_generates_legal_action(self):
```

Add:

```python
    def test_use_ability_generates_multi_target_actions_and_resolves_all_selected_targets(self):
        """USE_ABILITY should carry selected target tuples for count=2 target requirements."""
        db = MagicMock(spec=CardDatabase)

        source_card = _make_card_def("multi_target_card", abilities=[
            _make_source_ability(
                "damage_two",
                costs=[],
                effects=[
                    _make_source_effect(
                        "deal-damage",
                        amount=1,
                        target=_chosen_two_characters_target(),
                    ),
                ],
            )
        ])
        target_card = _make_card_def("target_character")

        def get_card(card_id):
            if card_id == "multi_target_card":
                return source_card
            return target_card

        db.get.side_effect = get_card

        engine = GameEngine(db)
        state = GameState(
            players=[PlayerState(), PlayerState()],
            cards={
                1: CardInstance(instance_id=1, card_id="multi_target_card", owner=0, controller=0),
                2: CardInstance(instance_id=2, card_id="target_character", owner=1, controller=1),
                3: CardInstance(instance_id=3, card_id="target_character", owner=1, controller=1),
                4: CardInstance(instance_id=4, card_id="target_character", owner=1, controller=1),
            },
        )
        state.cards[1].zone = ZONE_PLAY
        state.cards[2].zone = ZONE_PLAY
        state.cards[3].zone = ZONE_PLAY
        state.cards[4].zone = ZONE_PLAY
        state.players[0].play = [1]
        state.players[1].play = [2, 3, 4]
        state.phase = PHASE_MAIN
        state.active_player = 0

        legal = engine.legal_actions(state, 0)
        use_ability_actions = [action for action in legal if action.kind == ACTION_USE_ABILITY]

        selections = {tuple(action.choice["targets"]) for action in use_ability_actions}

        assert selections == {
            (2, 3),
            (2, 4),
            (3, 4),
        }

        action = next(action for action in use_ability_actions if tuple(action.choice["targets"]) == (2, 3))
        next_state = engine.apply_action(state, action)

        assert next_state.cards[2].damage == 1
        assert next_state.cards[3].damage == 1
        assert next_state.cards[4].damage == 0
```

---

# 8. Validation commands

Run targeted compile:

```bash
python3 -m py_compile \
  lorcana_bot/targeting.py \
  lorcana_bot/importers/lorcanito_source_mapper.py \
  lorcana_bot/engine.py \
  lorcana_bot/effects.py \
  lorcana_bot/pending_effects.py
```

Run targeted tests:

```bash
python3 -m pytest tests/test_targeting.py -q
python3 -m pytest tests/test_source_projection_policy.py -q
python3 -m pytest tests/test_activated_abilities_execution.py -q
```

Run nearby safety tests:

```bash
python3 -m pytest tests/test_effects.py -q
python3 -m pytest tests/test_bag_resolution.py -q
python3 -m pytest tests/test_pending_effects.py -q
python3 -m pytest tests/test_real_deck_runtime_executability.py -q
```

Run full suite:

```bash
python3 -m pytest -q
```

Run import check:

```bash
python3 - <<'PY'
from lorcana_bot.importers.lorcanito_source_importer import import_lorcanito_source_cards

db, report = import_lorcanito_source_cards(
    "data/lorcanito_runtime_extracted/cards.normalized.json"
)

print("cards:", len(db))
print("errors:", report.errors)
print("ability records:", report.ability_records_loaded)
print("unsupported:", report.unsupported_by_reason)
print("execution status counts:", report.execution_status_counts)
PY
```

Regenerate unsupported report:

```bash
python3 scripts/report_lorcanito_v2_unsupported.py
```

---

# 9. Expected unsupported-report delta

Starting Microfix 20 baseline after Microfix 19:

```text
unsupported_targeting: 355
detailed unsupported_targeting: 496
```

Expected after this phase:

```text
unsupported_targeting should decrease.
target selector records with count > 1 should decrease.
target selector records with count {"exactly": N} should decrease.
```

Possible acceptable shifts:

```text
unsupported_choice may increase if newly supported multi-targets expose opponent-choice routing.
unsupported_condition may increase if newly supported multi-targets expose if-you-do/result conditions.
unsupported_engine_mechanic may increase if newly supported multi-targets expose unimplemented effect handlers.
```

Not expected to be fixed:

```text
chosenBy: opponent
for-each-opponent
slotted target inputs
move-to-location slot routing
static/replacement mapped_not_executable
selected-object costs
if-you-do conditions
put-under / move-cards-from-under
```

---

# 10. Acceptance criteria

Accept Microfix 20 only if:

```text
1. py_compile passes.
2. Targeted tests pass.
3. Nearby safety tests pass.
4. Full pytest passes.
5. v2 import still has errors: [].
6. unsupported_targeting decreases or detailed report proves count-shaped target blockers moved to deeper true blockers.
7. Action and activated ability selected target tuples resolve through current_targets.
8. Bag target input emits tuple targets, not only singleton targets.
9. No raw source target/effect data is removed or hidden.
10. No global suppression of unsupported_targeting is introduced.
```

---

# Notes for validation interpretation

This phase intentionally supports selected target arrays for count-shaped chosen target descriptors.

This phase does **not** mean all selected-target mechanics are solved. Effects that require different target roles, such as “move damage from one chosen character to another,” need slotted target input and remain out of scope unless they already use `slotted_targets`.

Do not mark `chosenBy: "opponent"` executable unless the action/pending chooser is truly transferred to the opponent. That belongs in a later opponent-choice microfix.
