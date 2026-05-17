# TECHNICAL IMPLEMENTATION BRIEF 5 - Bag Resolution Input And Pending Continuation

Goal:
Bring Python bag resolution closer to Lorcanito by allowing bag entries to persist intermediate resolution input and continue correctly through pending effects.

Read `docs/agent_work/microfix_11/MICROFIX_11_SHARED_RULES.md` before starting.

This brief depends on Briefs 1-4. Do not introduce a separate targeting system. Use the existing pending and targeting services.

---

### 1. Current Missing Or Incorrect Code

* **File Path:** `lorcana_bot/engine.py`
* **Line Range:** `legal_actions() bag section`
* **Snippet:**
```python
if pending_bag:
    first = pending_bag[0]
    actions.append(Action(ACTION_RESOLVE_BAG, actor=player, choice={"bag_id": first.id, "accept": True}))
    optional = bool((first.raw or {}).get("optional", False) or getattr(first.ability, "optional", False))
    if optional:
        actions.append(Action(ACTION_RESOLVE_BAG, actor=player, choice={"bag_id": first.id, "accept": False}))
    return actions
```

Current gaps:

```text
Bag actions do not enumerate or persist amount/target/choice/named-card/destination inputs.
Bag entries have resolution_input, but ACTION_RESOLVE_BAG does not update it for intermediate choices.
Pending effects spawned from bag entries mostly keep origin, but resolution input must be merged back consistently.
Conditions are rechecked in _apply_resolve_bag, but tests must prove they are rechecked after pending input delay.
```

### 2. Expected Code (The Solution)

* **Target State:**
```text
1. ACTION_RESOLVE_BAG accepts and persists:
   amount
   targets
   player_targets
   slotted_targets
   choice_index
   resolve_optional
   named_card
   destinations

2. Bag entry resolution_input is merged with action.choice data before effect execution.

3. If effect execution suspends into pending effects:
   pending.raw["origin"] == "bag"
   pending.raw["origin_id"] == bag_id
   pending.raw["resolution_input"] carries the bag input snapshot
   bag entry remains in state.bag

4. When the pending effect completes:
   pending resolution_input is merged into the matching bag entry resolution_input
   the bag item is recorded/resolved once
   the bag item is removed once

5. Trigger condition and restrictions are checked at final bag resolution, not only at enqueue time.
```

### 3. Fixes Needed

* **Action:** `REVISE / EXPAND`
* **Delta Description:** Add a helper that normalizes `Action.choice` bag params into Lorcanito-style `resolution_input` keys.
* **Delta Description:** Use that helper in `_apply_resolve_bag()` before building `EffectResolutionContext`.
* **Delta Description:** Extend bag legal actions only where current targeting/pending services can enumerate choices truthfully.
* **Delta Description:** Merge pending completion input back into bag entry before removing/resolving the bag item.
* **Delta Description:** Add tests proving no duplicate bag resolution and condition recheck after delayed pending input.

### 4. Lorcanito Source Reference (The Authority)

* **Reference File:** `lorcanito-full-src-code/packages/lorcana/lorcana-engine/src/runtime-moves/resolution/resolve-bag.ts`
* **Line Range:** `Lines 774-895 and 921-1075`
* **Logic Context:**
```typescript
const updatedResolutionInput = {
  ...bagEffect.resolutionInput,
  ...params,
};

bagEffect.resolutionInput = updatedResolutionInput;

const resolutionInput = {
  ...bagEffect.resolutionInput,
  ...ctx.args.params,
};

if (!checkRestrictionsAndConditionsAtResolutionTime(bagEffect, resolutionInput)) {
  removeBagEffect(...);
  return;
}
```

* **Reference File:** `lorcanito-full-src-code/packages/lorcana/lorcana-engine/src/runtime-moves/resolution/action-effects/pending-action-effects.ts`
* **Line Range:** `Lines 56-92 and 171-244`
* **Logic Context:**
```typescript
function cloneActionResolutionInput(input) {
  return {
    targets: cloneTargets(input.targets),
    currentTargets: cloneTargets(input.currentTargets),
    contextTargets: cloneTargets(input.contextTargets),
    targetSelectionResolved: input.targetSelectionResolved,
    destinations: cloneDestinations(input.destinations),
    eventSnapshot: cloneEventSnapshot(input.eventSnapshot),
    triggerContext: cloneTriggerContext(input.triggerContext),
  };
}
```

### 5. Acceptance Check(s)

Run:
```bash
python3 -m pytest tests/test_bag_resolution.py -q
python3 -m pytest tests/test_pending_effects.py -q
python3 -m pytest tests/test_engine_trigger_pipeline.py -q
python3 -m pytest tests/test_targeting.py -q
python3 -m pytest -q
git diff --check
```

Expected:

```text
Bag amount input is persisted in entry.resolution_input.
Bag target input is persisted in entry.resolution_input.
Pending spawned by bag preserves origin and origin_id.
Resolving bag-origin pending removes exactly one matching bag item.
Condition recheck can fail after pending delay and correctly remove/skip the bag item.
Full test suite passes.
```

### 6. Final Response Requirements

Report:

1. Files changed.
2. Bag resolution_input keys supported.
3. Pending continuation behavior changed.
4. Tests added.
5. Exact commands run and results.
6. Any unsupported bag input kinds intentionally deferred.
