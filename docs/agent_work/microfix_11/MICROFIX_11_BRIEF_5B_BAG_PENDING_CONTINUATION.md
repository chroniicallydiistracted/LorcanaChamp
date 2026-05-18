# TECHNICAL IMPLEMENTATION BRIEF 5B - Bag Pending Continuation

Read `docs/agent_work/microfix_11/MICROFIX_11_SHARED_RULES.md` first.

Goal:
When a bag effect creates a pending effect, preserve the bag origin, copy accumulated `resolution_input` into the pending effect, and complete exactly one matching bag item when that pending effect finishes.

This brief depends on Brief 5A.

---

## Allowed Files

You may edit only:

```text
lorcana_bot/engine.py
lorcana_bot/pending_effects.py
tests/test_bag_resolution.py
tests/test_pending_effects.py
```

---

## Current Python Logic To Inspect

Inspect these exact locations before editing:

```text
lorcana_bot/engine.py::GameEngine._apply_resolve_bag
lorcana_bot/engine.py::GameEngine._apply_resolve_pending_effect
lorcana_bot/state.py::BagEffectEntry
lorcana_bot/pending_effects.py::PendingEffect
lorcana_bot/pending_effects.py::complete_pending_effect
lorcana_bot/pending_effects.py::get_pending_effect_by_id
lorcana_bot/triggers.py::record_bag_effect_resolution
lorcana_bot/triggers.py::remove_bag_effect
```

Known current risk:

```text
_apply_resolve_pending_effect() has more than one bag-origin completion branch.
Do not leave duplicated branches with different behavior.
```

---

## Exact Required Runtime Changes

### 1. Pending Effects Created From Bag Must Carry Origin And Input

In `GameEngine._apply_resolve_bag()`, after `_resolve_effects()` creates pending effects and before returning, each pending effect created by that bag entry must have:

```python
pe.origin = "bag"
pe.origin_id = bag_id
pe.raw["origin"] = "bag"
pe.raw["origin_id"] = bag_id
pe.raw.setdefault("bag_id", bag_id)
pe.raw.setdefault("resolution_input", {}).update(entry.resolution_input)
```

Preserve existing raw fields already written by current code:

```python
pe.raw.setdefault("event", entry.event.event if entry.event else None)
pe.raw.setdefault("event_payload", event_payload)
pe.raw.setdefault("trigger_subject", entry.event.subject_card_id if entry.event else None)
pe.raw.setdefault("ability_id", entry.ability_id)
pe.raw.setdefault("source_id", entry.source_id)
pe.raw.setdefault("controller_id", entry.controller_id)
```

Do not overwrite an existing pending raw field unless this brief explicitly says to assign it.

### 2. Add A Single Helper For Completing Bag-Origin Pending Effects

Add this private helper to `GameEngine` near `_apply_resolve_pending_effect()`:

```python
def _complete_bag_origin_pending_effect(
    self,
    state: GameState,
    pe: PendingEffect,
    actor: int,
) -> bool:
    ...
```

Required behavior:

```text
1. If pe.origin != "bag" or pe.origin_id is missing, return False.
2. Find the single BagEffectEntry in state.bag whose id equals pe.origin_id.
3. If no matching bag entry exists, return False.
4. Re-check bag_entry.condition before recording completion.
5. If the condition is now false:
   - remove exactly that bag entry
   - emit EVENT_TRIGGER_SKIPPED with reason "condition_not_met_after_pending"
   - return True
6. If the condition raises UnsupportedConditionError:
   - remove exactly that bag entry
   - emit EVENT_TRIGGER_SKIPPED with reason "unsupported_condition_after_pending"
   - return True
7. If the condition is true or absent:
   - merge pe.raw["resolution_input"] into bag_entry.resolution_input
   - call record_bag_effect_resolution(state, bag_entry) exactly once
   - remove exactly that bag entry
   - emit EVENT_TRIGGER_RESOLVED
   - return True
```

Use the existing condition evaluator that `_apply_resolve_bag()` already uses. Use the same event payload merge rules already present in `_apply_resolve_bag()`:

```python
event_payload = {}
if bag_entry.event:
    event_payload.update(bag_entry.event.event_snapshot)
    event_payload.update(bag_entry.event.payload)
```

The helper must not call `complete_pending_effect()`. The caller already owns pending-effect removal.

### 3. Replace Duplicated Bag-Origin Completion Branches

In `GameEngine._apply_resolve_pending_effect()`:

```text
1. Locate every branch that checks pe.origin == "bag".
2. Replace each branch body with one call to _complete_bag_origin_pending_effect(...).
3. Keep the existing complete_pending_effect(state, pending_id) call after the helper returns.
4. Ensure special requirement kinds and generic pending effects both use the same helper.
```

Do not create any second helper with overlapping responsibility.

---

## Lorcanito Source Reference

* **Reference File:** `lorcanito-full-src-code/packages/lorcana/lorcana-engine/src/runtime-moves/resolution/resolve-bag.ts`
* **Reference File:** `lorcanito-full-src-code/packages/lorcana/lorcana-engine/src/runtime-moves/resolution/action-effects/pending-action-effects.ts`
* **Logic Context:**

```typescript
const updatedResolutionInput = {
  ...bagItem.resolutionInput,
  ...resolutionInput,
};
```

Lorcanito carries resolution input forward through pending resolution and resumes the same bag item with the updated input instead of creating an unrelated effect.

---

## Exact Required Tests

Add these tests:

```text
tests/test_bag_resolution.py::test_pending_created_from_bag_preserves_origin_and_resolution_input
tests/test_bag_resolution.py::test_resolving_bag_origin_pending_merges_resolution_input_before_removal
tests/test_bag_resolution.py::test_resolving_bag_origin_pending_removes_exactly_one_bag_item
tests/test_bag_resolution.py::test_bag_condition_rechecked_after_pending_delay
```

Test construction requirements:

```text
1. Use real demo card definitions from the repository test helpers. Do not invent card_def_id values absent from the demo database.
2. Hold a Python reference to the BagEffectEntry object before pending completion when you need to assert final resolution_input after the entry is removed from state.bag.
3. For "removes exactly one bag item", create two bag entries and assert only the matching origin_id is removed.
4. For "condition rechecked", create a pending-producing bag entry whose condition is true at bag resolution time, mutate state so the condition is false before resolving the pending effect, then assert:
   - the matching bag entry is removed
   - no EVENT_TRIGGER_RESOLVED event is emitted for that bag_id
   - one EVENT_TRIGGER_SKIPPED event is emitted with reason "condition_not_met_after_pending"
```

Use existing `ACTION_RESOLVE_BAG` and `ACTION_RESOLVE_PENDING_EFFECT` actions. Do not call private helpers directly in these tests.

---

## Forbidden Changes

Do not edit projection or report files.

Do not add broad legal action enumeration.

Do not implement replacement-effect or `or` effect execution.

Do not hand-remove all bag entries for a player. Only remove the matching `origin_id`.

---

## Acceptance Checks

Run:

```bash
python3 -m pytest tests/test_bag_resolution.py tests/test_pending_effects.py -q
python3 -m pytest -q
git diff --check
```

---

## Final Response Requirements

Report:

```text
1. Files changed.
2. Exact pending raw origin fields written.
3. Exact resolution_input merge behavior.
4. Exact bag removal behavior.
5. Exact condition recheck behavior.
6. Exact tests added.
7. Exact command results.
8. Five yes/no self-audit answers from MICROFIX_11_SHARED_RULES.md.
```
