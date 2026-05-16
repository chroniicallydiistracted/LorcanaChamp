# TECHNICAL IMPLEMENTATION BRIEF 5 — Microfix 8 Consolidation And Audit

Goal:
Run the final Microfix 8 audit after Briefs 1-4. Mark Microfix 8 complete only if `EffectResolver` mutation centralization is proven by tests and no direct gameplay mutation remains in `lorcana_bot/effects.py`.

This brief may include small fixes only if the audit exposes a concrete missed route. Do not start Microfix 9 pending generalization here.

---

### 1. Current Risk Area

* **File Paths:**
```text
lorcana_bot/effects.py
lorcana_bot/engine.py
tests/test_effects.py
tests/test_engine_trigger_pipeline.py
tests/test_shift.py
tests/test_state_invariants.py
docs/LORCANACHAMP_GAME_ENGINE_REMAINING_WORK.md
```

Known Microfix 8 surfaces to audit:
```text
draw
gain_lore
lose_lore
deal_damage
remove_damage
banish
discard
return_to_hand
ready
exert
put_card_in_hand
put_card_on_top
put_card_on_bottom
put_card_in_discard
reveal_top_card routing
reveal_and_route routing
```

### 2. Expected Code (The Solution)

* **Target State:**
```text
1. Effect-driven draw uses GameEngine.draw_cards(..., private=True).
2. Core effect gameplay mutation routes through engine helper methods.
3. Deck/zone routing effects use GameEngine._move_card_eventful for every move.
4. EffectResolver does not call state.move_card directly.
5. EffectResolver does not directly mutate lore, damage, exerted state, or event_log.
6. Allowed resolver-local mutations are limited to temporary modifiers, temporary keywords, reveal flags, cost reductions, and deterministic shuffle metadata.
7. Existing trigger, shift, lifecycle, and state invariant tests still pass.
```

### 3. Fixes Needed

* **Action:** `VERIFY / REVISE IF NEEDED`
* **Delta Description:** Use `rg` to search for direct gameplay mutation in `lorcana_bot/effects.py`.
* **Delta Description:** Run targeted and full pytest commands.
* **Delta Description:** If everything passes, update `docs/LORCANACHAMP_GAME_ENGINE_REMAINING_WORK.md` by marking Microfix 8 complete and making Microfix 9 the current highest-priority next action.
* **Delta Description:** If anything fails, fix only Microfix 8 resolver-boundary issues.

### 4. Lorcanito Source Reference (The Authority)

* **Reference File:** `lorcanito-full-src-code/packages/lorcana/lorcana-engine/src/runtime-moves/resolution/action-effects/composed-effect-resolver.ts`
* **Reference File:** `lorcanito-full-src-code/packages/lorcana/lorcana-engine/src/runtime-moves/resolution/action-effects/draw-effect.ts`
* **Reference File:** `lorcanito-full-src-code/packages/lorcana/lorcana-engine/src/runtime-moves/resolution/action-effects/discard-effect.ts`
* **Reference File:** `lorcanito-full-src-code/packages/lorcana/lorcana-engine/src/runtime-moves/resolution/action-effects/return-to-hand-effect.ts`
* **Reference File:** `lorcanito-full-src-code/packages/lorcana/lorcana-engine/src/runtime-moves/resolution/action-effects/ready-effect.ts`
* **Reference File:** `lorcanito-full-src-code/packages/lorcana/lorcana-engine/src/runtime-moves/resolution/action-effects/exert-effect.ts`
* **Reference File:** `lorcanito-full-src-code/packages/lorcana/lorcana-engine/src/runtime-moves/state/shift-stack.ts`

Logic context:

```text
Lorcanito resolves action effects through specialized resolver modules that mutate game state via framework zone/card/event operations. Cards leaving public play use stack-aware movement. Draw/discard/ready/exert/damage/lore effects emit triggerable event records through the runtime event pipeline.
```

### 5. Acceptance Check(s)

Run:
```bash
rg -n "state\\.move_card\\(|\\.lore \\+=|\\.lore -=|\\.damage \\+=|\\.damage -=|\\.exerted = True|\\.exerted = False|state\\.event_log\\.append\\(|GameEvent\\(" lorcana_bot/effects.py
python3 -m pytest tests/test_effects.py -q
python3 -m pytest tests/test_engine_trigger_pipeline.py -q
python3 -m pytest tests/test_shift.py -q
python3 -m pytest tests/test_state_invariants.py -q
python3 -m pytest -q
```

Expected:
- The `rg` command reports no prohibited direct gameplay mutation in `lorcana_bot/effects.py`.
- Effect draw privacy test passes.
- Core helper regression tests pass.
- Zone-routing regression tests pass.
- Shift stack and state invariant tests still pass.
- Full suite passes.

### 6. Final Response Requirements

Report:
1. Files changed, if any.
2. Audit commands run.
3. Exact pytest commands run and results.
4. PASS or FAIL for Microfix 8 completion.
5. If PASS, confirm `docs/LORCANACHAMP_GAME_ENGINE_REMAINING_WORK.md` now marks Microfix 8 complete and Microfix 9 as current next action.
6. Any remaining work that belongs to Microfix 9 instead of Microfix 8.
