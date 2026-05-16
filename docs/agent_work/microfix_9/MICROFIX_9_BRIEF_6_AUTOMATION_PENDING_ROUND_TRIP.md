# TECHNICAL IMPLEMENTATION BRIEF 6 — Automation Pending Round Trip

Goal:
Update automation candidates and move adapter logic so every Microfix 9 pending legal action round-trips through `AutomatedActionCandidate` back into an equivalent `ACTION_RESOLVE_PENDING_EFFECT`.

This brief depends on Briefs 1-5.
Do not change strategy scoring except labels/metadata needed for new pending fields.

---

### 1. Current Missing Or Incomplete Code

* **File Path:** `lorcana_bot/automation/move_adapter.py`
* **Line Range:** `Lines 82-103`
* **Snippet:**
```python
choice: dict[str, Any] = {"pending_effect_id": pending_effect_id}

if candidate.resolve_optional is not None:
    choice["accept"] = candidate.resolve_optional

if candidate.target_instance_id is not None:
    choice["target"] = candidate.target_instance_id

if candidate.choice_index is not None:
    choice["choice_index"] = candidate.choice_index

if candidate.named_card is not None:
    choice["named_card"] = candidate.named_card

for key in ("selected_card_id", "top_cards", "bottom_cards", "destination"):
    if candidate.metadata and key in candidate.metadata:
        choice[key] = candidate.metadata[key]
```

Current gaps:

```text
amount is not adapted.
targets tuple is not adapted.
discard_card_ids is not adapted.
enter_play_exerted is not adapted.
candidate stable keys may not include these fields.
candidate summaries may not label these pending choices clearly.
```

### 2. Expected Code (The Solution)

* **Target State:**
```text
action_to_candidate() captures these pending choice fields:
amount
targets
discard_card_ids
choice_index
accept
enter_play_exerted
named_card
destination
selected_card_id
top_cards
bottom_cards

candidate_to_action() writes the same fields back into Action.choice.
```

If needed, add fields to `AutomatedActionCandidate`:

```python
amount: int | None = None
enter_play_exerted: bool | None = None
discard_card_ids: tuple[int, ...] = ()
```

Round-trip invariant:

```python
candidate_to_action(action_to_candidate(action, state, engine)) == action
```

Apply the invariant for every new Microfix 9 pending requirement kind.

### 3. Fixes Needed

* **Action:** `EXPAND`
* **Delta Description:** Update `automation/candidates.py` if new structured fields are required.
* **Delta Description:** Update `automation/candidate_enumerator.py` pending-action conversion to capture amount, targets, discard_card_ids, enter_play_exerted, and new metadata.
* **Delta Description:** Update `automation/move_adapter.py` to emit those fields back into `Action.choice`.
* **Delta Description:** Add round-trip tests in `tests/test_automation_pending_effects.py`.

### 4. Lorcanito Source Reference (The Authority)

* **Reference File:** `lorcanito-full-src-code/packages/lorcana/lorcana-engine/src/automation/move-adapter.ts`
* **Reference File:** `lorcanito-full-src-code/packages/lorcana/lorcana-engine/src/automation/types.ts`
* **Reference File:** `lorcanito-full-src-code/packages/lorcana/lorcana-engine/src/types/runtime-state.ts`
* **Line Range:** `runtime-state.ts Lines 448-471`
* **Logic Context:** Automation candidates must carry the same pending resolution input fields that legal user moves carry: targets, amount, optional resolution, enter-play exertion, choice index, named card, and destinations.

### 5. Acceptance Check(s)

Run:
```bash
python3 -m pytest tests/test_automation_pending_effects.py -q
python3 -m pytest tests/test_pending_effects.py -q
python3 -m pytest -q
```

New tests required:

```text
amount pending action round-trips through automation candidate.
target pending action round-trips.
multi_target pending action round-trips.
discard_choice pending action round-trips.
choice pending action round-trips.
optional pending action round-trips.
enter_play_exerted pending action round-trips.
special Microfix 4 pending actions still round-trip.
```

### 6. Final Response Requirements

Report:
1. Files changed.
2. New candidate fields added, if any.
3. Pending choice fields preserved in metadata.
4. Round-trip tests added.
5. Exact pytest commands run and results.
