# TECHNICAL IMPLEMENTATION BRIEF 1 — Register Static And Replacement Effects On Permanent Entry

Goal:
Centralize lifecycle registration for permanents entering public play, then call it for both normal play and shifted play. Shifted characters currently enter through `_apply_play_shifted()` and can bypass the registration block used by `_apply_play()`.

Do not change replacement evaluation logic in this brief.
Do not change static/replacement registry internals in this brief except as needed for imports.

---

### 1. Current Incorrect Code

* **File Path:** `lorcana_bot/engine.py`
* **Line Range:** Around `_apply_play()` and `_apply_play_shifted()`
* **Snippet:**
```python
if card.card_type != CARD_ACTION:
    source_abilities = getattr(card, "source_abilities", None) or getattr(card, "abilities", ())
    register_static_effects_for_card(state, action.card, source_abilities)
    # B8: Register replacement effects for non-action cards entering play
    register_replacement_effects_for_card(state, action.card, source_abilities)
```

```python
def _apply_play_shifted(self, state: GameState, action: Action) -> None:
    """Apply PLAY_SHIFTED action - play a shifted character on a target.
    ...
    """
    from .play_modes import execute_shift_play
    ...
    execute_shift_play(state, self, action.card, action.target)
```

### 2. Expected Code (The Solution)

* **Target State:**
```python
def _register_lifecycle_effects_for_public_permanent(
    self,
    state: GameState,
    card_id: int,
) -> None:
    inst = state.cards.get(card_id)
    if inst is None or inst.zone != ZONE_PLAY or inst.stack_parent_id is not None:
        return

    card = self.card_def(state, card_id)
    if card.card_type == CARD_ACTION:
        return

    source_abilities = getattr(card, "source_abilities", None) or getattr(card, "abilities", ())
    register_static_effects_for_card(state, card_id, source_abilities)
    register_replacement_effects_for_card(state, card_id, source_abilities)
```

Then replace the `_apply_play()` inline registration block with:
```python
self._register_lifecycle_effects_for_public_permanent(state, action.card)
```

And after shifted play resolves:
```python
execute_shift_play(state, self, action.card, action.target)
self._register_lifecycle_effects_for_public_permanent(state, action.card)
```

### 3. Fixes Needed

* **Action:** `REVISE`
* **Delta Description:** Move public permanent lifecycle registration into one engine helper and call it from both `_apply_play()` and `_apply_play_shifted()`.
* **Delta Description:** The helper must refuse cards not in `ZONE_PLAY`, cards with `stack_parent_id`, and actions.

### 4. Lorcanito Source Reference (The Authority)

* **Reference File:** `packages/lorcana/lorcana-engine/src/runtime-moves/moves/core/play-card.ts`
* **Logic Context:** Lorcanito registers live continuous/replacement state only after a card becomes an active public permanent.

* **Reference File:** `packages/lorcana/lorcana-engine/src/runtime-moves/shared/execute-shift-play.ts`
* **Logic Context:** Shifted cards become the new active top card; cards under are metadata-associated and not public active sources.

### 5. Acceptance Check(s)

Add tests proving:
- a normal character entering play registers static and replacement effects.
- a shifted character entering play registers static and replacement effects.
- the old shifted-under card does not register as a public permanent.

Run:
```bash
python3 -m pytest tests/test_static_effects.py -q
python3 -m pytest tests/test_replacement_effects.py -q
python3 -m pytest tests/test_shift.py -q
```

### 6. Final Response Requirements

Report:
1. Files changed.
2. Whether the new lifecycle helper exists.
3. Where `_apply_play()` calls the helper.
4. Where `_apply_play_shifted()` calls the helper.
5. Exact pytest commands run and results.
