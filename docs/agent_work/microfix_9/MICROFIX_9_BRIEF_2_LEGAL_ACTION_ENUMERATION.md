# TECHNICAL IMPLEMENTATION BRIEF 2 — General Pending Legal Actions

Goal:
Expand `GameEngine.legal_actions()` so general Microfix 9 pending requirement kinds enumerate concrete legal `RESOLVE_PENDING_EFFECT` actions.

This brief depends on Brief 1 resolver/input foundation.
Do not modify `_apply_resolve_pending_effect()` in this brief except import fallout.
Do not implement the Microfix 10 targeting service here.

---

### 1. Current Missing Or Incomplete Code

* **File Path:** `lorcana_bot/engine.py`
* **Line Range:** `Lines 263-387`
* **Snippet:**
```python
requirement_kind = (pe.raw or {}).get("requirement_kind")
raw_requirement = (pe.raw or {}).get("requirement")

if pe.optional and pe.accepted is None:
    actions.append(Action(
        ACTION_RESOLVE_PENDING_EFFECT,
        actor=player,
        source=pe.source_id,
        choice={"pending_effect_id": pe.id, "accept": True}
    ))
    actions.append(Action(
        ACTION_RESOLVE_PENDING_EFFECT,
        actor=player,
        source=pe.source_id,
        choice={"pending_effect_id": pe.id, "accept": False}
    ))
elif requirement_kind == "scry_ordering":
    ...
elif requirement_kind == "destination":
    ...
elif pe.requires_target_input and requirement is not None:
    ...
elif pe.requires_choice_input:
    ...
else:
    actions.append(Action(
        ACTION_RESOLVE_PENDING_EFFECT,
        actor=player,
        source=pe.source_id,
        choice={"pending_effect_id": pe.id}
    ))
```

Current gaps:

```text
requirement_kind="amount" falls through to generic no-input resolution.
requirement_kind="target" / "multi_target" do not use raw candidate lists or min/max.
requirement_kind="discard_choice" is not enumerated.
requirement_kind="opponent_choice" is not enumerated distinctly.
requirement_kind="enter_play_exerted" is not enumerated.
choice/optional are partly supported through legacy fields, not raw requirement_kind.
```

### 2. Expected Code (The Solution)

* **Target State:**
```text
legal_actions() emits one or more RESOLVE_PENDING_EFFECT actions for:

amount:
  choice={"pending_effect_id": pe.id, "amount": n}

target:
  target=target_id
  choice={"pending_effect_id": pe.id, "targets": (target_id,)}

multi_target:
  choice={"pending_effect_id": pe.id, "targets": tuple_of_target_ids}

discard_choice:
  choice={"pending_effect_id": pe.id, "discard_card_ids": tuple_of_card_ids}

choice:
  choice={"pending_effect_id": pe.id, "choice_index": index}

optional:
  choice={"pending_effect_id": pe.id, "accept": True}
  choice={"pending_effect_id": pe.id, "accept": False}

opponent_choice:
  same shape as choice/target depending on raw["choice_type"], but only for pe.chooser_id

enter_play_exerted:
  choice={"pending_effect_id": pe.id, "enter_play_exerted": True}
  choice={"pending_effect_id": pe.id, "enter_play_exerted": False}
```

Candidate source rules:

```text
amount options: raw["amount_options"], requirement.options, min/max inclusive
target candidates: raw["candidate_ids"], requirement.candidate_ids, existing get_valid_targets_for_requirement fallback
multi_target candidates: combinations of candidate IDs, respecting min_targets/max_targets
discard_choice candidates: raw["card_candidate_ids"], raw["candidate_ids"], requirement.card_candidate_ids
choice options: raw["options"], requirement.options, pe.choice_options
optional: boolean accept/decline
```

Guardrails:

```text
Do not emit actions for a player who is not pe.chooser_id.
Do not emit duplicate actions.
Always include ACTION_CONCEDE after pending resolve actions.
If a requirement has no legal candidates and min required input is > 0, only CONCEDE should remain.
```

### 3. Fixes Needed

* **Action:** `EXPAND`
* **Delta Description:** Add explicit `requirement_kind` branches in `legal_actions()` for `amount`, `target`, `multi_target`, `discard_choice`, `choice`, `optional`, `opponent_choice`, and `enter_play_exerted`.
* **Delta Description:** Keep all Microfix 4 special requirement branches unchanged.
* **Delta Description:** Use existing `get_valid_targets_for_requirement()` only as fallback; do not build the full Microfix 10 targeting service.

### 4. Lorcanito Source Reference (The Authority)

* **Reference File:** `lorcanito-full-src-code/packages/lorcana/lorcana-engine/src/runtime-moves/resolution/action-effects/selection-context.ts`
* **Line Range:** `Lines 136-184`
* **Logic Context:** Lorcanito projects pending input fields into `currentSelection`, including targets, amount, choice index, optional resolution, enter-play exerted, named card, and destinations.

* **Reference File:** `lorcanito-full-src-code/packages/lorcana/lorcana-engine/src/types/runtime-state.ts`
* **Line Range:** `Lines 430-436`
* **Logic Context:**
```typescript
export type PendingActionEffectKind =
  | "discard-choice"
  | "choice-selection"
  | "name-card-selection"
  | "optional-selection"
  | "scry-selection"
  | "target-selection";
```

### 5. Acceptance Check(s)

Run:
```bash
python3 -m pytest tests/test_pending_effects.py -q
python3 -m pytest -q
```

New tests required in `tests/test_pending_effects.py`:

```text
amount pending emits one action per allowed amount.
target pending emits only valid target actions.
multi_target pending emits combinations respecting min/max.
discard_choice pending emits combinations from hand candidates.
choice pending emits one action per choice index.
optional requirement_kind emits accept and decline.
opponent_choice is only visible to the opponent chooser.
enter_play_exerted emits true and false choices.
```

### 6. Final Response Requirements

Report:
1. Files changed.
2. Requirement kinds added to `legal_actions()`.
3. Candidate sources used for amount/target/discard/choice enumeration.
4. Exact pytest commands run and results.
5. Confirmation that `_apply_resolve_pending_effect()` behavior was not expanded in this brief.
