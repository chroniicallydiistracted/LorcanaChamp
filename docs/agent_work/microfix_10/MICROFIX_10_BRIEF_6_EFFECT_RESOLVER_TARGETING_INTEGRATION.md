# TECHNICAL IMPLEMENTATION BRIEF 6 — EffectResolver Targeting Integration

Goal:
Use the targeting service inside `EffectResolver` for target aliases, collections, player targets, and current/context target sets.

Required shared context:
Read `docs/agent_work/microfix_10/MICROFIX_10_SHARED_RULES.md` before making changes.

This brief depends on Briefs 1-5.
Do not add new effect kinds here.
Brief 5 is complete: pending target legal actions now use
`get_valid_target_candidates_for_pending()` and player targets are stored
separately from card targets. Preserve that action/pending routing.

---

### 1. Current Incorrect Code

* **File Path:** `lorcana_bot/effects.py`
* **Line Range:** `Around _target_cards(), _collection(), _target_player()`
* **Snippet:**
```python
def _target_cards(...):
    target = effect.target
    if target in {None, "chosen_character", "chosen_card", ...}:
        ...
    if target == "event_target":
        ...
    if target in {"your_characters", ...}:
        return self._collection(state, target, context)
    raise EffectResolutionError(...)
```

Current issue:

```text
Effect resolution uses a second target interpretation path.
It can diverge from legal_actions()/pending target legality and does not fully support current/context targets.
```

### 2. Expected Code (The Solution)

* **Target State:**
```text
_target_cards() delegates descriptor resolution to targeting service when possible.
_target_player() delegates player aliases to targeting service when possible.
_collection() is either removed or becomes a thin wrapper over targeting service.
context.current_targets and future context_targets are honored.
`EffectResolutionContext` may be expanded to include `context_targets` if it is
not already present.
event_source/event_target/trigger_subject continue to work.
```

Expected integration shape:
```text
Translate effect.target strings/dicts through normalize_target_descriptor().
Build TargetQueryContext from EffectResolutionContext:
  actor=context.actor
  source_id=context.source
  event_payload=context.event_payload
  current_targets=context.current_targets
  context_targets=context.context_targets or ()
Use resolve_candidate_card_ids() for card-targeting effect aliases and collections.
Use resolve_candidate_player_ids() for player aliases.
Preserve existing explicit selected target behavior: pending-selected target remains the first target where existing effects expect one.
```

Required behavior:

```text
selected target from pending apply remains first target.
multi-target pending sets current_targets and effects can consume all selected targets.
for_each collections use targeting service candidates.
player target aliases resolve consistently.
Unsupported descriptors raise EffectResolutionError with a clear message.
No direct state mutation paths should be changed; Microfix 8 eventful-helper routing remains intact.
```

### 3. Fixes Needed

* **Action:** `REVISE`
* **Delta Description:** Replace duplicated target alias logic in `EffectResolver` with targeting service calls.
* **Delta Description:** Add tests for current_targets, trigger_subject, event_target fallback, all/your/opposing character collections, and player targets.
* **Delta Description:** Keep existing effect eventful-helper behavior unchanged.
* **Delta Description:** This is the highest-risk Microfix 10 brief; prefer small helper functions and targeted tests over broad rewrites.

### 4. Lorcanito Source Reference (The Authority)

* **Reference File:** `lorcanito-full-src-code/packages/lorcana/lorcana-engine/src/runtime-moves/resolution/action-effects/selection-state.ts`
* **Line Range:** `Lines 142-177 and 181-220`
* **Logic Context:** Lorcanito chooses current/context/combined selection input depending on target descriptor semantics and can promote current selections into context.

### 5. Acceptance Check(s)

Run:
```bash
python3 -m pytest tests/test_targeting.py -q
python3 -m pytest tests/test_effects.py -q
python3 -m pytest tests/test_pending_effects.py -q
python3 -m pytest -q
```

Expected:
- Effects and legal target enumeration use one targeting interpretation.
- Existing Microfix 8 event-boundary tests still pass.

### 6. Final Response Requirements

Report:
1. Files changed.
2. EffectResolver methods revised.
3. Current/context target behavior covered.
4. Tests added.
5. Exact pytest commands run and results.
