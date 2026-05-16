# TECHNICAL IMPLEMENTATION BRIEF 5 — Pending Targeting Integration

Goal:
Use the targeting service for pending `target` and `multi_target` requirements created by Microfix 9.

Required shared context:
Read `docs/agent_work/microfix_10/MICROFIX_10_SHARED_RULES.md` before making changes.

This brief depends on Briefs 1-4.
Do not implement slotted targets yet.

---

### 1. Current Incorrect Code

* **File Path:** `lorcana_bot/pending_effects.py`
* **Line Range:** `Around get_valid_targets_for_requirement()`
* **Snippet:**
```python
def get_valid_targets_for_requirement(
    state: GameState,
    requirement: TargetRequirement,
    chooser_id: int,
    engine: GameEngine | None = None,
) -> list[int]:
    ...
```

* **File Path:** `lorcana_bot/engine.py`
* **Line Range:** `Pending legal_actions target/multi_target branches`
* **Snippet:**
```python
elif requirement_kind == "target":
    candidate_ids = ...
elif requirement_kind == "multi_target":
    raw_candidates = ...
```

Current issue:

```text
Pending target legality still uses simplified TargetRequirement fields and raw candidate IDs.
It does not fully share action targeting logic for Ward, cannot-be-targeted, player targets, filters, or current/context target aliases.
```

### 2. Expected Code (The Solution)

* **Target State:**
```text
pending_effects.get_valid_targets_for_requirement() delegates to targeting service.
engine.legal_actions() target/multi_target branches use targeting service when raw target descriptor is present.
raw["target"] / raw["target_descriptor"] / raw["target_dsl"] are accepted descriptor sources.
raw candidate_ids still act as a narrowing set.
```

Expected integration shape:
```text
Convert TargetRequirement fields into TargetDescriptor only when no richer raw descriptor is present.
Use TargetQueryContext(actor=chooser_id, source_id=source_id when available).
Accept descriptor sources from pe.raw["target"], pe.raw["target_descriptor"], pe.raw["target_dsl"], pe.raw["selector"], and requirement fields.
Treat raw candidate_ids as an intersection/narrowing list after central candidate resolution.
Continue storing chosen target tuples through Microfix 9 resolution_input behavior.
```

Behavior:

```text
target pending emits one action per legal candidate.
multi_target emits combinations respecting min/max after filtering.
chosen_player pending can emit player targets.
Ward/cannot-be-targeted protections are honored.
Cards in ZONE_UNDER are excluded.
chosen_card, chosen_item, chosen_location, chosen_player, and multi_target descriptors follow the same interpretation as action-card targeting.
```

### 3. Fixes Needed

* **Action:** `REVISE`
* **Delta Description:** Add conversion from `TargetRequirement` to targeting descriptors.
* **Delta Description:** Use targeting service from pending legal-action branches.
* **Delta Description:** Preserve Microfix 9 raw candidate behavior as an additional candidate filter.
* **Delta Description:** Add pending tests for target, multi-target, player targets, Ward, and `ZONE_UNDER`.
* **Delta Description:** Do not add slotted_targets support in this brief.

### 4. Lorcanito Source Reference (The Authority)

* **Reference File:** `lorcanito-full-src-code/packages/lorcana/lorcana-engine/src/runtime-moves/resolution/action-effects/selection-context.ts`
* **Line Range:** `Lines 757-844`
* **Logic Context:** Lorcanito builds target-selection contexts with card candidates, player candidates, allowed zones, min/max selections, and current selection.

### 5. Acceptance Check(s)

Run:
```bash
python3 -m pytest tests/test_targeting.py -q
python3 -m pytest tests/test_pending_effects.py -q
python3 -m pytest tests/test_automation_pending_effects.py -q
python3 -m pytest -q
```

Expected:
- Pending target legal actions use the same target service as normal action-card targeting.
- Existing Microfix 9 pending tests still pass.

### 6. Final Response Requirements

Report:
1. Files changed.
2. Pending target branches revised.
3. Descriptor sources supported from `pe.raw`.
4. Tests added.
5. Exact pytest commands run and results.
