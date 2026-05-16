# TECHNICAL IMPLEMENTATION BRIEF 3 — Deregister Static And Replacement Effects For Every Leave-Play Route

Goal:
Ensure every card leaving public play, including every card in a moved shift stack, deregisters static and replacement effects before movement completes.

Do not change registration behavior in this brief.
Do not change replacement destination selection in this brief.

---

### 1. Current Incorrect Code

* **File Path:** `lorcana_bot/engine.py`
* **Line Range:** Around `_move_card_eventful()`
* **Snippet:**
```python
stacked_card_ids = [card_id]
if include_stack and from_zone == ZONE_PLAY and destination != ZONE_PLAY and inst.cards_under:
    stacked_card_ids.extend(cid for cid in inst.cards_under if cid in state.cards)

if from_zone == ZONE_PLAY and destination != ZONE_PLAY:
    deregister_static_effects_for_card(state, card_id)
    deregister_replacement_effects_from_card(state, card_id)
```

### 2. Expected Code (The Solution)

* **Target State:**
```python
stacked_card_ids = [card_id]
if include_stack and from_zone == ZONE_PLAY and destination != ZONE_PLAY and inst.cards_under:
    stacked_card_ids.extend(cid for cid in inst.cards_under if cid in state.cards)

if from_zone == ZONE_PLAY and destination != ZONE_PLAY:
    for moved_id in stacked_card_ids:
        deregister_static_effects_for_card(state, moved_id)
        deregister_replacement_effects_from_card(state, moved_id)
```

The movement loop must still move cards in Lorcanito stack order:
```python
top_id, *cards_under
```

### 3. Fixes Needed

* **Action:** `REVISE`
* **Delta Description:** Change leave-play deregistration from only `card_id` to every `moved_id` in the resolved stack movement list.
* **Delta Description:** Preserve current `include_stack=False` behavior for internal attach operations, because moving a target into `ZONE_UNDER` must not pull its previous stack through a second movement path.

### 4. Lorcanito Source Reference (The Authority)

* **Reference File:** `packages/lorcana/lorcana-engine/src/runtime-moves/state/shift-stack.ts`
* **Logic Context:** `moveCardOutOfPlayWithStack` moves the top card followed by cards under and then clears metadata for all moved cards.

* **Reference File:** `packages/lorcana/lorcana-engine/src/runtime-moves/rules/static-effects-invalidation.ts`
* **Logic Context:** Live continuous effects must be invalidated when their source leaves play.

### 5. Acceptance Check(s)

Add tests proving:
- `_banish_eventful()` deregisters static effects from the top card and all stacked cards.
- `_return_to_hand_eventful()` deregisters replacement effects from the top card and all stacked cards.
- direct `_move_card_eventful(..., include_stack=True)` preserves zone membership invariants.
- `attach_shift_stack()` with `include_stack=False` still preserves existing `cards_under`.

Run:
```bash
python3 -m pytest tests/test_static_effects.py -q
python3 -m pytest tests/test_replacement_effects.py -q
python3 -m pytest tests/test_state_invariants.py -q
```

### 6. Final Response Requirements

Report:
1. Files changed.
2. Whether deregistration now iterates `stacked_card_ids`.
3. What stack route tests were added.
4. Exact pytest commands run and results.
