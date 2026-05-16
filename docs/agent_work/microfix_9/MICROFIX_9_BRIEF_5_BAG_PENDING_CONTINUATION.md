# TECHNICAL IMPLEMENTATION BRIEF 5 — Bag Pending Suspension And Completion

Goal:
Fix bag-trigger resolution so a bag item that suspends into a pending effect is not removed or marked resolved until the pending effect completes or is declined.

This brief depends on Briefs 1-4.
Do not implement new trigger events here.
Do not implement Microfix 10 targeting service here.

---

### 1. Current Incorrect Code

* **File Path:** `lorcana_bot/engine.py`
* **Line Range:** `Lines 1905-1915`
* **Snippet:**
```python
# Record resolution
record_bag_effect_resolution(state, entry)

# Remove bag entry
remove_bag_effect(state, bag_id)

# Emit trigger resolved event
self.emit_event(state, EVENT_TRIGGER_RESOLVED, actor=action.actor, source=entry.source_id, payload={"bag_id": bag_id, "ability_id": entry.ability_id}, queue_triggers=False)
```

Current issue:

```text
If resolving entry.effects creates state.pending_effects, the bag item is still removed immediately.
That loses the origin needed to complete or decline the trigger after pending input.
```

### 2. Expected Code (The Solution)

* **Target State:**
```text
When _apply_resolve_bag() creates one or more pending effects:
1. Do not call record_bag_effect_resolution yet.
2. Do not remove the bag entry yet.
3. Set pending.origin = "bag" and pending.origin_id = bag_id.
4. Store raw["bag_id"], raw["event"], raw["event_payload"], raw["trigger_subject"], and raw["resolution_input"].
5. Return after pending creation.

When _apply_resolve_pending_effect() completes a pending effect with origin="bag":
1. Find the matching bag entry by origin_id.
2. Record bag effect resolution.
3. Remove the bag entry.
4. Emit EVENT_TRIGGER_RESOLVED or EVENT_TRIGGER_DECLINED.
```

Decline behavior:

```text
Optional pending decline for a bag-origin pending effect removes the pending effect.
If the originating bag entry is optional, remove and emit EVENT_TRIGGER_DECLINED.
If it is not optional, raise IllegalActionError unless the pending requirement itself permits decline.
```

### 3. Fixes Needed

* **Action:** `REVISE`
* **Delta Description:** Detect pending-effect creation during `_apply_resolve_bag()` by comparing pending count before and after resolving entry effects.
* **Delta Description:** Preserve bag entry when pending effects were created from that bag item.
* **Delta Description:** Mark newly created pending effects with `origin="bag"` and `origin_id=bag_id`.
* **Delta Description:** Complete/remove the bag item only after the corresponding pending effect completes.
* **Delta Description:** Add tests for both completion and decline paths.

### 4. Lorcanito Source Reference (The Authority)

* **Reference File:** `lorcanito-full-src-code/packages/lorcana/lorcana-engine/src/runtime-moves/resolution/action-effects/pending-action-effects.ts`
* **Line Range:** `Lines 42-54 and 171-218`
* **Logic Context:** Lorcanito pending action effects store `continuation`, `resolutionInput`, and optional `selectionContext`, allowing suspended effects to resume instead of being treated as resolved.

* **Reference File:** `lorcanito-full-src-code/packages/lorcana/lorcana-engine/src/types/runtime-state.ts`
* **Line Range:** `Lines 473-488`
* **Logic Context:** Pending action effects retain controller, chooser, source, effect, continuation, resolution input, and selection context until completion.

### 5. Acceptance Check(s)

Run:
```bash
python3 -m pytest tests/test_pending_effects.py -q
python3 -m pytest tests/test_engine_trigger_pipeline.py -q
python3 -m pytest -q
```

New tests required:

```text
bag effect that creates pending target remains in state.bag while pending exists.
resolving pending from bag removes matching bag entry and emits EVENT_TRIGGER_RESOLVED.
declining optional pending from bag removes matching bag entry and emits EVENT_TRIGGER_DECLINED.
unrelated bag entries are not removed when one pending completes.
pending raw preserves event_payload and trigger_subject for effect context.
```

### 6. Final Response Requirements

Report:
1. Files changed.
2. How bag-origin pending effects are detected.
3. How origin/origin_id is stored.
4. How bag completion is finalized after pending resolution.
5. Tests added.
6. Exact pytest commands run and results.
