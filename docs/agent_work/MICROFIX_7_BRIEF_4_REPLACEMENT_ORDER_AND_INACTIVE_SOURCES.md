# TECHNICAL IMPLEMENTATION BRIEF 4 — Prove Replacement Ordering And Inactive Source Safety

Goal:
Add focused tests and any small code corrections needed to prove replacement effects are evaluated before final damage/banish mutation, and inactive sources cannot consume or apply replacement effects.

Do not refactor the entire replacement system in this brief.
Do not add new replacement effect types in this brief.

---

### 1. Current Risk Area

* **File Path:** `lorcana_bot/engine.py`
* **Line Range:** Around `_banish_eventful()` and `_deal_damage_eventful()`
* **Snippet:**
```python
banish_event = replacement_banish_card(
    state,
    card_id,
    destination=default_destination,
    controller=target_controller,
)
...
self._move_card_eventful(...)
```

```python
damage_event = replacement_deal_damage(
    state,
    target_id,
    amount,
    source_id,
    source_controller=source_controller,
    target_controller=target_controller,
)
...
state.cards[target_id].damage += damage_event.current_amount
```

* **File Path:** `lorcana_bot/replacement_effects.py`
* **Line Range:** Around `evaluate_prevention()` and `evaluate_banish_replacement()`
* **Snippet:**
```python
for effect in registry.effects:
    if effect.effect_type == ReplacementEffectType.PREVENT_DAMAGE:
        if registry._applies_to(state, damage_event.target_id, effect):
            ...
```

### 2. Expected Code (The Solution)

* **Target State:**
```python
# Replacement is evaluated first.
banish_event = replacement_banish_card(...)

# Final mutation uses replacement result.
self._move_card_eventful(
    state,
    card_id,
    banish_event.destination,
    ...
)
```

```python
# Prevention is evaluated first.
damage_event = replacement_deal_damage(...)

# Final damage mutation uses current_amount only.
if damage_event.current_amount > 0:
    state.cards[target_id].damage += damage_event.current_amount
```

Inactive sources must not apply and must not consume once-per-turn usage:
```python
source.zone != ZONE_PLAY
source.stack_parent_id is not None
```

### 3. Fixes Needed

* **Action:** `EXPAND`
* **Delta Description:** Add regression tests for ordering and inactive-source safety. If tests expose a code gap, make the smallest targeted fix in `replacement_effects.py` or `engine.py`.
* **Delta Description:** Verify once-per-turn replacement usage is not consumed when the source is inactive or under a shifted card.

### 4. Lorcanito Source Reference (The Authority)

* **Reference File:** `packages/lorcana/lorcana-engine/src/runtime-moves/effects/replacement-effects.ts`
* **Logic Context:** Replacement/prevention effects alter an event before the final state mutation is committed.

* **Reference File:** `packages/lorcana/lorcana-engine/src/rules/derived-state.ts`
* **Logic Context:** Derived state should only consider active public cards.

### 5. Acceptance Check(s)

Add tests proving:
- banish replacement to hand leaves the target in hand and never in discard.
- damage prevention reduces the committed damage amount.
- full prevention emits no damage-dealt trigger.
- an under-card replacement source does not replace banish.
- an under-card prevention source does not consume once-per-turn usage.

Run:
```bash
python3 -m pytest tests/test_replacement_effects.py -q
python3 -m pytest tests/test_engine_trigger_pipeline.py -q
```

### 6. Final Response Requirements

Report:
1. Files changed.
2. Whether replacement ordering was already correct or required code changes.
3. What inactive-source tests were added.
4. Exact pytest commands run and results.
