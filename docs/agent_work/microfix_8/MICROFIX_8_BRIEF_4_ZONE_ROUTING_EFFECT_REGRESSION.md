# TECHNICAL IMPLEMENTATION BRIEF 4 — Zone Routing Effect Regression

Goal:
Prove deck/routing effects in `EffectResolver` use engine movement boundaries for every actual card move. This brief focuses on effects that route selected or revealed cards between deck, hand, discard, and play.

Do not implement full Lorcanito scry/search privacy or target service parity here. Those are later microfixes.

---

### 1. Current Code To Verify

* **File Path:** `lorcana_bot/effects.py`
* **Line Range:** `Lines 417-469 and 564-645 and 681-722`
* **Snippet:**
```python
if effect.value:
    destination = str(effect.value)
    for cid in revealed_cards:
        if destination == "hand":
            self.engine._move_card_eventful(state, cid, ZONE_HAND, actor=player, source_id=context.source)
        elif destination == "discard":
            self.engine._move_card_eventful(state, cid, ZONE_DISCARD, actor=player, source_id=context.source)
        elif destination == "play":
            # Only characters can go to play
            cdef = self.engine.card_def(state, cid)
            if cdef.card_type == "character":
                self.engine._move_card_eventful(state, cid, ZONE_PLAY, actor=player, source_id=context.source)
```

```python
if card_id in state.cards:
    self.engine._move_card_eventful(
        state,
        card_id,
        ZONE_DECK,
        actor=context.actor,
        source_id=context.source,
        controller=state.cards[card_id].owner,
        index=0,
    )
```

```python
if destination == "hand":
    self.engine._move_card_eventful(state, cid, ZONE_HAND, actor=player, source_id=context.source)
elif destination == "discard":
    self.engine._move_card_eventful(state, cid, ZONE_DISCARD, actor=player, source_id=context.source)
elif destination == "play":
    cdef = self.engine.card_def(state, cid)
    if cdef.card_type == "character":
        self.engine._move_card_eventful(state, cid, ZONE_PLAY, actor=player, source_id=context.source)
```

### 2. Expected Code (The Solution)

* **Target State:**
```text
Effect helper                 Required movement route
_resolve_reveal_top_card       GameEngine._move_card_eventful
_resolve_put_card_in_hand      GameEngine._move_card_eventful
_resolve_put_card_on_top       GameEngine._move_card_eventful(index=0)
_resolve_put_card_on_bottom    GameEngine._move_card_eventful
_resolve_put_card_in_discard   GameEngine._move_card_eventful
_resolve_reveal_and_route      GameEngine._move_card_eventful
```

Add tests that monkeypatch `GameEngine._move_card_eventful` with a call-through spy and assert:

```text
destination zone is correct
actor is the resolving player
source_id is preserved
controller is owner when moving to hand/deck
top-of-deck routing uses index=0
revealed cards remain marked revealed before route
```

At least one test must use a shifted stack top card moving from play to another zone and assert stack members move with the top card. If this is already covered in `tests/test_shift.py`, reference that coverage in the final response and add only the missing effect-route test.

### 3. Fixes Needed

* **Action:** `EXPAND / REVISE IF NEEDED`
* **Delta Description:** Add regression tests proving all listed zone-routing effect helpers call `GameEngine._move_card_eventful`.
* **Delta Description:** If any listed helper still mutates zones directly, replace that mutation with `_move_card_eventful`.
* **Delta Description:** Do not rewrite pending search/scry/reveal architecture in this brief.

### 4. Lorcanito Source Reference (The Authority)

* **Reference File:** `lorcanito-full-src-code/packages/lorcana/lorcana-engine/src/runtime-moves/resolution/action-effects/put-on-top-effect.ts`
* **Line Range:** `Lines 20-38`
* **Logic Context:**
```typescript
if (isCardInPlayZone(ctx, cardId)) {
  moveCardOutOfPlayWithStack(ctx, cardId, { zone: "deck", playerId: ownerId });
  return;
}
ctx.framework.zones.moveCard(cardId, { zone: "deck", playerId: ownerId });
```

* **Reference File:** `lorcanito-full-src-code/packages/lorcana/lorcana-engine/src/runtime-moves/resolution/action-effects/return-to-hand-effect.ts`
* **Line Range:** `Lines 38-67`
* **Logic Context:**
```typescript
moveCardOutOfPlayWithStack(ctx, cardId, { zone: "hand", playerId: ownerId });
emitTriggeredLorcanaEvent(ctx, "cardReturnedToHand", { cardId, ownerId, fromZone: zoneKey }, ...);
ctx.framework.zones.moveCard(cardId, { zone: "hand", playerId: ownerId });
```

* **Reference File:** `lorcanito-full-src-code/packages/lorcana/lorcana-engine/src/runtime-moves/resolution/action-effects/put-into-inkwell-effect.ts`
* **Line Range:** `Lines 94-130`
* **Logic Context:**
```typescript
const movedCardIds = moveCardOutOfPlayWithStack(ctx, cardId, { zone: "inkwell", playerId: destinationPlayerId });
emitTriggeredLorcanaEvent(ctx, "cardInked", { playerId: ownerId, cardId, from: sourceZoneKey, to: "inkwell" }, ...);
```

### 5. Acceptance Check(s)

Run:
```bash
rg -n "state\\.move_card\\(" lorcana_bot/effects.py
python3 -m pytest tests/test_effects.py -q
python3 -m pytest tests/test_shift.py -q
python3 -m pytest tests/test_state_invariants.py -q
python3 -m pytest -q
```

Expected:
- `lorcana_bot/effects.py` has no direct `state.move_card(...)`.
- Zone-routing effect tests prove `_move_card_eventful` is called.
- Stack movement remains covered.
- Full suite passes.

### 6. Final Response Requirements

Report:
1. Files changed.
2. Which zone-routing helpers were covered by tests.
3. Any production routes changed.
4. Exact pytest commands run and results.
5. Confirmation that pending search/scry architecture was not expanded here.
