# Microfix 18 — Lorcanito Scry Destination Requirement Executability

This guide starts from the current `main` baseline after Microfix 17.

Microfix 18 is intentionally narrow. It does **not** rewrite the pending-effect system. Current LorcanaChamp already has a runtime path for Lorcanito-style scry pending resolution. The gap is that the source resolution-requirement analyzer still classifies scry ordering/destination requirements as `unsupported_choice`, even though the engine can already execute them.

---

# 1. Lorcanito source paths inspected

Inspected from the attached Lorcanito source package:

```text
lorcana/lorcana-engine/src/runtime-moves/resolution/action-effects/scry-effect.ts
lorcana/lorcana-engine/src/runtime-moves/resolution/action-effects/search-deck-effect.ts
lorcana/lorcana-engine/src/runtime-moves/resolution/action-effects/reveal-and-route-effect.ts
lorcana/lorcana-engine/src/runtime-moves/resolution/action-effects/pending-action-effects.ts
lorcana/lorcana-engine/src/runtime-moves/resolution/action-effects/selection-context.ts
lorcana/lorcana-engine/src/runtime-moves/resolution/action-effects/selection-state.ts
```

Current LorcanaChamp paths inspected from `main`:

```text
data/lorcanito_runtime_extracted/reports/unsupported/unsupported_summary.json
lorcana_bot/card_logic/resolution_requirements.py
lorcana_bot/importers/lorcanito_source_mapper.py
lorcana_bot/effects.py
lorcana_bot/pending_effects.py
lorcana_bot/engine.py
tests/test_source_resolution_requirements.py
tests/test_source_projection_policy.py
tests/test_scry_search_reveal.py
```

---

# 2. Exact Lorcanito types/functions/mechanics found

## Lorcanito `scry-effect.ts`

Lorcanito scry handling has three important runtime pieces:

```text
getScryLookedAtCards()
validateScrySelection()
resolveScryEffect()
```

Key mechanics:

```text
1. Read top N cards.
2. Preserve looked-at card ids in pending resolution input.
3. Accept destination selections shaped like:
   { zone: string, cards: CardInstanceId[] }
4. Validate selected cards are from looked-at cards.
5. Reject duplicate assignment.
6. Apply destination rules in order.
7. Respect min/max.
8. Respect filter / filters.
9. If a destination has remainder: true, automatically assign remaining cards.
10. If a destination has reveal: true, reveal those cards publicly.
11. Move non-play destinations first, then play destinations.
```

## Lorcanito scry destination fields observed

```text
zone
cards
min
max
remainder
filter / filters
ordering
reveal
playFilters
entersExerted
exerted
facedown
```

## Lorcanito `selection-context.ts`

Lorcanito builds a `scry-selection` context when:

```text
effect has destinations
revealed/known looked-at card ids exist
the player must submit destinations
```

Submit field:

```text
destinations
```

That matches the current LorcanaChamp pending action shape:

```python
choice={"pending_effect_id": pe.id, "destinations": destinations}
```

---

# 3. Current LorcanaChamp behavior

The current unsupported report shows:

```text
unsupported_choice: 394
effect:scry: 113
```

and the top unsupported patterns list `effect.type:scry:unsupported_choice`.

Current LorcanaChamp already has runtime support for this specific path:

```text
EffectResolver._resolve_scry()
create_scry_pending_effect()
ScryRequirement.destinations
engine.legal_actions() -> ACTION_RESOLVE_PENDING_EFFECT with destinations
engine._scry_destination_choices()
engine._apply_resolve_pending_effect()
resolve_scry_destinations()
_move_scry_card_to_destination()
```

Current tests already verify that structured scry destinations resolve through legal actions and apply_action:

```text
tests/test_scry_search_reveal.py
test_scry_destinations_resolve_through_legal_actions_and_apply_action
test_scry_destinations_reject_duplicate_cards
test_scry_destination_to_inkwell_respects_exerted_destination
```

The current false blocker is in:

```text
lorcana_bot/card_logic/resolution_requirements.py
```

Current logic marks every requirement except `optional`, `choice`, and `target` as unsupported:

```python
unsupported = tuple(
    key.removeprefix("requires_")
    for key, required in values.items()
    if required and key not in {"requires_optional", "requires_choice", "requires_target"}
)
```

That means scry is flagged unsupported because:

```text
requires_ordering: True
requires_destination: True
```

even though those are supported for `effect.kind == "scry"` by the current pending-effect runtime.

---

# 4. Expected Lorcanito-aligned behavior

After Microfix 18:

```text
Lorcanito scry effects with ordering/destination requirements should be executable.
```

Specifically, this kind of raw effect should no longer be `unsupported_choice`:

```json
{
  "type": "scry",
  "amount": 4,
  "destinations": [
    {
      "zone": "hand",
      "min": 0,
      "max": 1,
      "reveal": true,
      "filter": {"type": "song"}
    },
    {
      "zone": "deck-bottom",
      "remainder": true,
      "ordering": "player-choice"
    }
  ]
}
```

Expected mapper behavior:

```text
map_raw_effect(...).execution_status == executable
map_raw_ability(action with that scry).execution_status == executable
project_action_effects(card) includes EffectDef(kind="scry")
```

Expected runtime behavior:

```text
Existing scry pending tests still pass.
No new public information leak.
No raw source data is removed.
```

---

# 5. Files to modify

```text
lorcana_bot/card_logic/resolution_requirements.py

tests/test_source_resolution_requirements.py
tests/test_source_projection_policy.py
```

No engine runtime file should be modified in this phase.

Do **not** modify these files for Microfix 18 unless tests reveal a real issue:

```text
lorcana_bot/effects.py
lorcana_bot/pending_effects.py
lorcana_bot/engine.py
```

---

# 6. Previous code and replacement code

## File 1 — `lorcana_bot/card_logic/resolution_requirements.py`

### Change 1A — add supported requirement constants

Find this block:

```python
@dataclass(frozen=True)
class ResolutionRequirementReport:
    requires_target: bool = False
    requires_optional: bool = False
    requires_choice: bool = False
    requires_named_card: bool = False
    requires_amount: bool = False
    requires_destination: bool = False
    requires_ordering: bool = False
    requires_opponent_choice: bool = False
    unsupported_requirements: tuple[str, ...] = ()
```

Immediately after that block, add:

```python
_ALWAYS_SUPPORTED_REQUIREMENTS = frozenset({
    "optional",
    "choice",
    "target",
})


_SUPPORTED_REQUIREMENTS_BY_EFFECT_KIND = {
    # Lorcanito scry destination routing is already implemented by:
    # EffectResolver._resolve_scry()
    # create_scry_pending_effect()
    # GameEngine.legal_actions() scry_ordering branch
    # GameEngine._apply_resolve_pending_effect()
    # resolve_scry_destinations()
    "scry": frozenset({
        "ordering",
        "destination",
    }),
}


def _requirement_supported_for_effect(effect: SourceEffectDef, requirement: str) -> bool:
    if requirement in _ALWAYS_SUPPORTED_REQUIREMENTS:
        return True
    return requirement in _SUPPORTED_REQUIREMENTS_BY_EFFECT_KIND.get(effect.kind, frozenset())
```

---

### Change 1B — replace `analyze_resolution_requirements()`

#### Previous code

```python
def analyze_resolution_requirements(effect: SourceEffectDef) -> ResolutionRequirementReport:
    values = {
        "requires_target": _requires_target(effect),
        "requires_optional": effect.kind == "optional" or bool(effect.optional),
        "requires_choice": effect.kind in {"choice", "or"},
        "requires_named_card": effect.kind == "name-a-card",
        "requires_amount": _has_amount_choice(effect),
        "requires_destination": _has_destination_choice(effect),
        "requires_ordering": effect.kind == "scry" or _has_ordering(effect),
        "requires_opponent_choice": _has_opponent_choice(effect),
    }
    unsupported = tuple(
        key.removeprefix("requires_")
        for key, required in values.items()
        if required and key not in {"requires_optional", "requires_choice", "requires_target"}
    )
    child_reports = [analyze_resolution_requirements(child) for child in (*effect.effects, *effect.branches)]
    for report in child_reports:
        for key in values:
            values[key] = values[key] or getattr(report, key)
        unsupported += report.unsupported_requirements
    return ResolutionRequirementReport(**values, unsupported_requirements=tuple(sorted(set(unsupported))))
```

#### Replacement code

```python
def analyze_resolution_requirements(effect: SourceEffectDef) -> ResolutionRequirementReport:
    values = {
        "requires_target": _requires_target(effect),
        "requires_optional": effect.kind == "optional" or bool(effect.optional),
        "requires_choice": effect.kind in {"choice", "or"},
        "requires_named_card": effect.kind == "name-a-card",
        "requires_amount": _has_amount_choice(effect),
        "requires_destination": _has_destination_choice(effect),
        "requires_ordering": effect.kind == "scry" or _has_ordering(effect),
        "requires_opponent_choice": _has_opponent_choice(effect),
    }

    unsupported = tuple(
        requirement
        for key, required in values.items()
        for requirement in (key.removeprefix("requires_"),)
        if required and not _requirement_supported_for_effect(effect, requirement)
    )

    child_reports = [analyze_resolution_requirements(child) for child in (*effect.effects, *effect.branches)]
    for report in child_reports:
        for key in values:
            values[key] = values[key] or getattr(report, key)
        unsupported += report.unsupported_requirements

    return ResolutionRequirementReport(**values, unsupported_requirements=tuple(sorted(set(unsupported))))
```

---

# 7. Tests to add/update

## File 2 — `tests/test_source_resolution_requirements.py`

### Change 2A — update imports

#### Previous code

```python
from lorcana_bot.card_logic.resolution_requirements import analyze_resolution_requirements
from lorcana_bot.importers.lorcanito_source_mapper import map_raw_effect
```

#### Replacement code

```python
from lorcana_bot.card_logic import ExecutionStatus
from lorcana_bot.card_logic.resolution_requirements import analyze_resolution_requirements
from lorcana_bot.importers.lorcanito_source_mapper import map_raw_effect
```

---

### Change 2B — add scry executability-policy test

Place this test at the bottom of the file, after `test_resolution_requirement_detection()`.

Add:

```python
def test_lorcanito_scry_destination_requirements_are_runtime_supported():
    effect = map_raw_effect({
        "type": "scry",
        "amount": 4,
        "destinations": [
            {
                "zone": "hand",
                "min": 0,
                "max": 1,
                "reveal": True,
                "filter": {"type": "song"},
            },
            {
                "zone": "deck-bottom",
                "remainder": True,
                "ordering": "player-choice",
            },
        ],
    })

    report = analyze_resolution_requirements(effect)

    assert report.requires_ordering is True
    assert report.requires_destination is True
    assert report.unsupported_requirements == ()
    assert effect.execution_status == ExecutionStatus.EXECUTABLE
```

---

## File 3 — `tests/test_source_projection_policy.py`

### Change 3A — update imports

#### Previous code

```python
from dataclasses import replace

from lorcana_bot.cards import CardDef
from lorcana_bot.importers.lorcanito_source_mapper import (
    map_raw_ability,
    project_action_effects,
    project_keywords,
    project_unsupported_abilities,
)
```

#### Replacement code

```python
from dataclasses import replace

from lorcana_bot.card_logic import ExecutionStatus
from lorcana_bot.cards import CardDef
from lorcana_bot.importers.lorcanito_source_mapper import (
    map_raw_ability,
    project_action_effects,
    project_keywords,
    project_unsupported_abilities,
)
```

Note: `replace` appears unused in the current file, but do not remove it in this microfix.

---

### Change 3B — add scry projection test

Place this test at the bottom of the file, after:

```python
def test_static_and_replacement_do_not_project_as_one_shot_effects():
```

Add:

```python
def test_lorcanito_scry_destination_action_projects_to_engine_effect():
    ability = map_raw_ability({
        "type": "action",
        "effect": {
            "type": "scry",
            "amount": 4,
            "destinations": [
                {
                    "zone": "hand",
                    "min": 0,
                    "max": 1,
                    "reveal": True,
                    "filter": {"type": "song"},
                },
                {
                    "zone": "deck-bottom",
                    "remainder": True,
                    "ordering": "player-choice",
                },
            ],
        },
    })

    assert ability.execution_status == ExecutionStatus.EXECUTABLE

    card = _card(ability)
    effects = project_action_effects(card)

    assert len(effects) == 1
    assert effects[0].kind == "scry"
    assert effects[0].amount == 4
    assert effects[0].raw["raw"]["destinations"][0]["zone"] == "hand"
    assert effects[0].raw["raw"]["destinations"][1]["zone"] == "deck-bottom"
    assert effects[0].raw["raw"]["destinations"][1]["remainder"] is True
```

---

# 8. Validation commands

Run targeted compile:

```bash
python3 -m py_compile \
  lorcana_bot/card_logic/resolution_requirements.py \
  lorcana_bot/importers/lorcanito_source_mapper.py \
  lorcana_bot/effects.py \
  lorcana_bot/pending_effects.py \
  lorcana_bot/engine.py
```

Run targeted tests:

```bash
python3 -m pytest tests/test_source_resolution_requirements.py -q
python3 -m pytest tests/test_source_projection_policy.py -q
python3 -m pytest tests/test_scry_search_reveal.py -q
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

Starting Microfix 18 baseline:

```text
unsupported_choice: 394
detailed unsupported_choice: 394
effect:scry: 113
detailed_record_count: 2118
```

Expected after this phase:

```text
unsupported_choice should drop.
effect:scry should drop sharply or disappear from top unsupported patterns.
```

Likely visible result:

```text
effect:scry: 113 -> 0
```

Exact `unsupported_choice` drop may be larger than 113 because ability-level blockers that were caused by scry child effects may also become executable or move to a deeper blocker.

Expected unchanged categories unless unblocked records reveal deeper blockers:

```text
mapped_not_executable
unsupported_cost
unsupported_engine_mechanic
unsupported_trigger
```

Accept small shifts in:

```text
unsupported_targeting
unsupported_condition
```

only if the detailed report shows previously scry-blocked records now reaching a deeper true blocker.

---

# 10. Acceptance criteria

Accept Microfix 18 only if:

```text
1. py_compile passes.
2. Targeted tests pass.
3. Full pytest passes.
4. v2 import still has errors: [].
5. unsupported_choice decreases.
6. effect:scry no longer appears as a top unsupported_choice bucket, or drops substantially.
7. Existing scry/search/reveal runtime tests still pass.
8. No raw source data is removed or hidden.
9. No engine runtime rewrite is introduced in this phase.
```

---

# Notes for validation interpretation

This phase changes **executability classification**, not the underlying scry resolver. That is intentional because current LorcanaChamp already has Lorcanito-style scry destination pending resolution.

Do not mark all destination, ordering, named-card, amount, or opponent-choice requirements globally supported. Only scry ordering/destination requirements are explicitly supported in this microfix.

Do not modify static/replacement reporting in this phase.
