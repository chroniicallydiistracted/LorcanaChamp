# TECHNICAL IMPLEMENTATION BRIEF 3 — Core Effect Helper Regression

Goal:
Prove core `EffectResolver` gameplay effects route through engine-owned helpers. This brief should primarily add tests. Only change production code if a helper route is missing.

Do not work on pending requirements, targeting-service parity, or scry/search privacy in this brief.

---

### 1. Current Code To Verify

* **File Path:** `lorcana_bot/effects.py`
* **Line Range:** `Lines 45-114 and 207-235`
* **Snippet:**
```python
elif kind == "gain_lore":
    self.engine._gain_lore_eventful(
        state,
        self._target_player(state, effect, context),
        self._amount(effect),
        source_id=context.source,
    )
elif kind == "lose_lore":
    self.engine._lose_lore_eventful(
        state,
        self._target_player(state, effect, context),
        self._amount(effect),
        source_id=context.source,
    )
elif kind == "deal_damage":
    for target in self._target_cards(state, effect, context):
        self.engine._deal_damage_eventful(
            state,
            target_id=target,
            source_id=context.source,
            amount=self._amount(effect),
            actor=context.actor,
            is_challenge=False,
            apply_resist=True,
        )
elif kind == "remove_damage":
    for target in self._target_cards(state, effect, context):
        self.engine._remove_damage_eventful(
            state,
            target,
            self._amount(effect),
            actor=context.actor,
            source_id=context.source,
        )
elif kind == "banish":
    for target in self._target_cards(state, effect, context):
        self.engine._banish_eventful(
            state,
            target,
            actor=context.actor,
            source_id=context.source,
            reason="effect",
        )
```

```python
if targets:
    for target in targets:
        if state.cards[target].zone != ZONE_HAND:
            raise EffectResolutionError("Discard target must be in hand")
        self.engine._discard_eventful(
            state,
            target,
            actor=state.cards[target].controller,
            source_id=context.source,
            reason="effect",
        )
    return

player = self._target_player(state, effect, context)
for _ in range(min(self._amount(effect), len(state.players[player].hand))):
    self.engine._discard_eventful(
        state,
        state.players[player].hand[0],
        actor=player,
        source_id=context.source,
        reason="effect",
    )
```

### 2. Expected Code (The Solution)

* **Target State:**
```text
Effect kind       Required engine helper
gain_lore         GameEngine._gain_lore_eventful
lose_lore         GameEngine._lose_lore_eventful
deal_damage       GameEngine._deal_damage_eventful
remove_damage     GameEngine._remove_damage_eventful
banish            GameEngine._banish_eventful
discard           GameEngine._discard_eventful
return_to_hand    GameEngine._return_to_hand_eventful
ready             GameEngine._ready_eventful
exert             GameEngine._exert_eventful
```

Add regression tests that spy on these helpers while resolving representative effects. The tests should verify helper invocation, actor/source propagation, and key options such as:

```text
deal_damage: is_challenge=False, apply_resist=True
banish: reason="effect"
discard: reason="effect"
exert: reason="effect"
```

Use `pytest` monkeypatch wrappers that call through to the original helper so state and event assertions still prove behavior.

### 3. Fixes Needed

* **Action:** `EXPAND / REVISE IF NEEDED`
* **Delta Description:** Add helper-spy regression tests for all core gameplay effect kinds listed above.
* **Delta Description:** If any listed effect does not call the required helper, revise `lorcana_bot/effects.py` to route through the helper and update the test accordingly.
* **Delta Description:** Do not assert implementation details unrelated to the helper boundary.

### 4. Lorcanito Source Reference (The Authority)

* **Reference File:** `lorcanito-full-src-code/packages/lorcana/lorcana-engine/src/runtime-moves/resolution/action-effects/discard-effect.ts`
* **Line Range:** `Lines 172-182 and 268-297`
* **Logic Context:**
```typescript
const discardEvent = applyReplacementEffects(ctx, { kind: "discard", ... });
ctx.framework.zones.moveCard(cardId, { zone: "discard", playerId: targetPlayerId });
queueTriggeredEvent(ctx, { event: "discard", playerId: targetPlayerId, subjectCardId: cardId });
```

* **Reference File:** `lorcanito-full-src-code/packages/lorcana/lorcana-engine/src/runtime-moves/resolution/action-effects/ready-effect.ts`
* **Line Range:** `Lines 48-73`
* **Logic Context:**
```typescript
ctx.cards.patchMeta(targetId, { ...currentMeta, state: "ready" });
emitTriggeredLorcanaEvent(ctx, "cardReadied", { cardId: targetId }, { event: "ready", ... });
```

* **Reference File:** `lorcanito-full-src-code/packages/lorcana/lorcana-engine/src/runtime-moves/resolution/action-effects/exert-effect.ts`
* **Line Range:** `Lines 40-60`
* **Logic Context:**
```typescript
ctx.cards.patchMeta(targetId, { state: "exerted" });
emitTriggeredLorcanaEvent(ctx, "cardExerted", { cardId: targetId, source: "effect" }, ...);
```

### 5. Acceptance Check(s)

Run:
```bash
python3 -m pytest tests/test_effects.py -q
python3 -m pytest tests/test_engine_trigger_pipeline.py -q
python3 -m pytest -q
```

Expected:
- Each core effect has a test proving the expected engine helper was called.
- Event and state assertions still pass after spying.
- No direct state mutation is introduced in `lorcana_bot/effects.py`.
- Full suite passes.

### 6. Final Response Requirements

Report:
1. Files changed.
2. Helper route verified for each core effect kind.
3. Any production code revised, with exact snippets.
4. Exact pytest commands run and results.
