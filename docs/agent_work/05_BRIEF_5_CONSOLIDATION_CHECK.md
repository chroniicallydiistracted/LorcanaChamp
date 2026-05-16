# TECHNICAL IMPLEMENTATION BRIEF 5 — Microfix 4 Consolidation Check

Goal:
Run the post-Microfix 4 verification and ensure no scaffold-only pending requirement remains claimed as engine-routable without tests.

Do not modify code unless a consolidation check fails and the failure is directly in Microfix 4 scope.

---

### 1. Current Incorrect Code

* **File Path:** `lorcana_bot/engine.py`
* **Line Range:** `Lines 1480-1565 before Microfix 4`
* **Snippet:**
```python
        # Resolve the current effect
        current_effect = pe.current_effect
        if current_effect is not None:
            # Get target from stored selected_targets or action target
            selected_target = pe.selected_targets[0] if pe.selected_targets else action.target
            # Get choice from stored selected_choice or action choice_index
            selected_choice = pe.selected_choice if pe.selected_choice is not None else choice_index

            # Extract event context from raw
            raw = pe.raw or {}
            event = raw.get('event')
            event_payload = raw.get('event_payload', {})

            # Build context with target from pending effect
            context = EffectResolutionContext(
                actor=pe.controller_id,
                source=pe.source_id,
                target=selected_target,
                event=event,
                event_payload=event_payload,
                choice=selected_choice,
            )

            # Resolve the effect
            self.effect_resolver.resolve(state, current_effect, context)
```

### 2. Expected Code (The Solution)

* **Target State:**
```python
        raw = pe.raw or {}
        requirement_kind = raw.get("requirement_kind")

        if requirement_kind in {
            "scry_ordering",
            "search_selection",
            "reveal_routing",
            "named_card",
            "destination",
        }:
            ...
            complete_pending_effect(state, pending_id)
            return

        # Generic pending current_effect behavior remains after this block.
        current_effect = pe.current_effect
        if current_effect is not None:
            ...
```

### 3. Fixes Needed

* **Action:** `REVISE`
* **Delta Description:** Confirm the final code contains a special `requirement_kind` dispatch block before generic `current_effect` resolution. Confirm tests prove special requirement routing through `legal_actions()` and `apply_action()`.

### 4. Lorcanito Source Reference (The Authority)

* **Reference File:** `packages/lorcana/lorcana-engine/src/runtime-moves/resolution/action-effects/pending-action-effects.ts`
* **Line Range:** `Pending resolution execution path`
* **Logic Context:**
```typescript
// Pending effects resume through runtime move resolution and dispatch based on
// the stored pending requirement/resolution input.
resolvePendingActionEffect(pendingEffectId, resolutionInput);
```

### 5. Acceptance Check(s)

Run:
```bash
python3 -m pytest tests/test_pending_effects.py -q
python3 -m pytest tests/test_automation_pending_effects.py -q
python3 -m pytest -q
```

Manual checks:
```bash
grep -n "requirement_kind" lorcana_bot/engine.py
grep -n "resolve_scry_ordering" lorcana_bot/engine.py
grep -n "resolve_search_selection" lorcana_bot/engine.py
grep -n "resolve_reveal_routing" lorcana_bot/engine.py
grep -n "resolve_named_card" lorcana_bot/engine.py
grep -n "resolve_destination_choice" lorcana_bot/engine.py
grep -n "class TestSpecialPendingRequirementEngineRouting" tests/test_pending_effects.py
```

Expected:
- All pending tests pass.
- Automation pending tests pass.
- Full pytest passes.
- Special pending requirement dispatch exists.
- Engine-path tests exist for at least scry, search, reveal routing, and named card.
- Generic target/choice pending behavior still passes.

### 6. Final Response Requirements

The implementation agent must report:
1. Files changed across all Microfix 4 briefs.
2. Requirement kinds routed in `legal_actions()`.
3. Requirement kinds dispatched in `_apply_resolve_pending_effect()`.
4. Tests added.
5. Exact pytest commands run and results.
6. Whether generic pending effects still pass existing tests.
7. Confirmation no unrelated systems were changed.
