# TECHNICAL IMPLEMENTATION BRIEF 3 — Apply Pending Resolution And Context Propagation

Goal:
Expand `_apply_resolve_pending_effect()` so general Microfix 9 requirement kinds validate player input, persist it to `resolution_input`, and pass the selected values into effect resolution.

This brief depends on Briefs 1-2.
Do not implement discard-choice effect suspension here; that is Brief 4.
Do not implement automation here; that is Brief 5.

---

### 1. Current Missing Or Incomplete Code

* **File Path:** `lorcana_bot/engine.py`
* **Line Range:** `Lines 1984-2131`
* **Snippet:**
```python
accept = action.choice.get("accept")
choice_index = action.choice.get("choice_index")
...
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

requirement = pe.current_requirement
if pe.requires_target_input and requirement is not None:
    ...

if pe.requires_choice_input:
    ...

current_effect = pe.current_effect
if current_effect is not None:
    selected_target = pe.selected_targets[0] if pe.selected_targets else action.target
    selected_choice = pe.selected_choice if pe.selected_choice is not None else choice_index
    context = EffectResolutionContext(
        actor=pe.controller_id,
        source=pe.source_id,
        target=selected_target,
        event=event,
        event_payload=event_payload,
        choice=selected_choice,
    )
    self.effect_resolver.resolve(state, current_effect, context)
```

Current gaps:

```text
amount is not read from action.choice.
targets tuple is not read from action.choice.
discard_card_ids is not read from action.choice.
enter_play_exerted is not read from action.choice.
general requirement_kind dispatch does not call the new resolver helpers.
EffectResolutionContext has no explicit amount field; dynamic amount must be carried through choice or raw["resolution_input"] until a later context expansion is needed.
current_targets is not populated from multi-target selections.
```

### 2. Expected Code (The Solution)

* **Target State:**
```text
_apply_resolve_pending_effect() dispatches:

amount -> resolve_amount_choice(...)
target -> resolve_target_selection(...)
multi_target -> resolve_target_selection(...)
discard_choice -> resolve_discard_choice(...)
choice -> resolve_choice_index(...)
optional -> resolve_optional_choice(...)
opponent_choice -> target/choice helper based on raw["choice_type"]
enter_play_exerted -> resolve_enter_play_exerted_choice(...)
```

After resolving input:

```text
selected_target = first selected target if present
selected_choice = selected choice index if present
current_targets = all selected targets if present
resolution_input = pe.raw["resolution_input"] persists for later effects/tests
```

Context construction must include:

```python
context = EffectResolutionContext(
    actor=pe.controller_id,
    source=pe.source_id,
    target=selected_target,
    choice=selected_choice,
    event=event,
    event_payload=event_payload,
    pending_trigger_id=pe.origin_id if pe.origin == "bag" else None,
    trigger_source=pe.source_id if pe.origin == "bag" else None,
    trigger_subject=raw.get("trigger_subject"),
    current_targets=tuple(selected_targets),
)
```

Validation:

```text
If action.actor != pe.chooser_id, raise IllegalActionError.
If required input is missing, raise IllegalActionError.
If resolver helper raises ValueError, re-raise as IllegalActionError.
Do not complete a pending effect until its current effect has resolved or the pending is explicitly declined.
```

### 3. Fixes Needed

* **Action:** `EXPAND`
* **Delta Description:** Import the new resolver helpers from `pending_effects.py`.
* **Delta Description:** Add general `requirement_kind` dispatch after existing special requirement dispatch.
* **Delta Description:** Preserve Microfix 4 special dispatch behavior.
* **Delta Description:** Ensure all accepted values are written into `pe.raw["resolution_input"]`.
* **Delta Description:** Populate `EffectResolutionContext.current_targets` from selected target tuples.

### 4. Lorcanito Source Reference (The Authority)

* **Reference File:** `lorcanito-full-src-code/packages/lorcana/lorcana-engine/src/runtime-moves/resolution/action-effects/pending-action-effects.ts`
* **Line Range:** `Lines 171-218`
* **Logic Context:** Lorcanito creates pending action effects with `controllerId`, `chooserId`, `effect`, `continuation`, `resolutionInput`, and `selectionContext`.

* **Reference File:** `lorcanito-full-src-code/packages/lorcana/lorcana-engine/src/runtime-moves/resolution/action-effects/selection-state.ts`
* **Line Range:** `Lines 181-220`
* **Logic Context:** Lorcanito writes current targets into resolution input and can promote them into context targets for subsequent effect steps.

### 5. Acceptance Check(s)

Run:
```bash
python3 -m pytest tests/test_pending_effects.py -q
python3 -m pytest tests/test_engine_trigger_pipeline.py -q
python3 -m pytest -q
```

New tests required:

```text
apply amount pending stores pe.raw["resolution_input"]["amount"] and resolves effect.
apply target pending stores pe.raw["resolution_input"]["targets"] and passes target to EffectResolutionContext.
apply multi_target pending passes all targets in current_targets.
apply choice pending stores choice_index and resolves selected branch.
apply optional decline removes pending without resolving effect.
apply enter_play_exerted stores boolean.
wrong chooser raises IllegalActionError.
missing required input raises IllegalActionError.
```

### 6. Final Response Requirements

Report:
1. Files changed.
2. Requirement kinds dispatched by `_apply_resolve_pending_effect()`.
3. Exact `resolution_input` fields written.
4. Tests added.
5. Exact pytest commands run and results.
