# TECHNICAL IMPLEMENTATION BRIEF 2 — Effect Draw Privacy And Event Boundary

Goal:
Harden effect-driven card draw so resolver calls use the engine draw boundary in private mode. Opponents must not receive drawn card IDs from ordinary draw effects.

Do not modify target selection, pending effects, or trigger matching in this brief.

---

### 1. Current Incorrect Code

* **File Path:** `lorcana_bot/effects.py`
* **Line Range:** `Lines 41-45`
* **Snippet:**
```python
elif kind == "for_each":
    self._resolve_for_each(state, effect, context)
elif kind == "draw":
    self.engine.draw_cards(state, self._target_player(state, effect, context), self._amount(effect))
elif kind == "gain_lore":
    self.engine._gain_lore_eventful(
```

Current issue:

```text
GameEngine.draw_cards(..., private=False) includes card_ids in EVENT_CARD_DRAWN payload.
Effect-driven draws are ordinary hidden draws and should not leak drawn card identities in public traces.
```

### 2. Expected Code (The Solution)

* **Target State:**
```python
elif kind == "for_each":
    self._resolve_for_each(state, effect, context)
elif kind == "draw":
    self.engine.draw_cards(
        state,
        self._target_player(state, effect, context),
        self._amount(effect),
        private=True,
    )
elif kind == "gain_lore":
    self.engine._gain_lore_eventful(
```

Add or expand tests to prove the emitted `CARD_DRAWN` event is privacy-safe:

```python
draw_event = next(event for event in reversed(state.event_log) if event.event_type == EVENT_CARD_DRAWN)
assert draw_event.payload["private"] is True
assert draw_event.payload["count"] == 2
assert "card_ids" not in draw_event.payload
```

Also keep a direct engine draw test or existing behavior proving explicit non-private draws still include card IDs when `private=False`.

### 3. Fixes Needed

* **Action:** `REPLACE`
* **Delta Description:** Change only the `draw` branch in `EffectResolver.resolve()` so effect-driven draws call `GameEngine.draw_cards(..., private=True)`.
* **Delta Description:** Add a regression test that plays an action with a draw effect and asserts the `EVENT_CARD_DRAWN` payload contains count/private metadata but no `card_ids`.
* **Delta Description:** Preserve current card movement from deck to hand and draw trigger buffering.

### 4. Lorcanito Source Reference (The Authority)

* **Reference File:** `lorcanito-full-src-code/packages/lorcana/lorcana-engine/src/runtime-moves/resolution/action-effects/draw-effect.ts`
* **Line Range:** `Lines 97-127`
* **Logic Context:**
```typescript
const drawnCards = ctx.framework.zones.drawCards({
  from: { zone: "deck", playerId },
  to: { zone: "hand", playerId },
  count: drawAmount,
});
emitTriggeredLorcanaEvent(ctx, "cardsDrawn", { playerId, amount: 1, cardIds: [cardId] }, ...);
```

Lorcanito performs draw through the framework zone operation and then emits draw trigger metadata. Python must keep the same engine boundary while avoiding public trace leakage of hidden card IDs.

### 5. Acceptance Check(s)

Run:
```bash
python3 -m pytest tests/test_effects.py -q
python3 -m pytest tests/test_engine_trigger_pipeline.py -q
python3 -m pytest -q
```

Manual check:
```bash
grep -n "private=True" lorcana_bot/effects.py
```

Expected:
- Effect-driven draw calls `draw_cards(..., private=True)`.
- The action draw test sees no `card_ids` in the draw event payload.
- Existing trigger pipeline tests pass.
- Full suite passes.

### 6. Final Response Requirements

Report:
1. Files changed.
2. Exact previous draw branch.
3. Exact updated draw branch.
4. Test proving no card-id leak.
5. Exact pytest commands run and results.
