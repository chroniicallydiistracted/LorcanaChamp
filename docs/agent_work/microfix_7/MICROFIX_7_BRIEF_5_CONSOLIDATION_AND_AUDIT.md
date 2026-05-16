# TECHNICAL IMPLEMENTATION BRIEF 5 — Microfix 7 Consolidation And Audit

Goal:
Run a final targeted audit after Briefs 1-4 to prove static/replacement lifecycle hardening is complete and no obvious lifecycle gaps remain.

This brief may include small fixes only if the audit exposes a concrete missed route. Do not start Microfix 8 work here.

---

### 1. Current Risk Area

* **File Paths:**
```text
lorcana_bot/static_effects.py
lorcana_bot/replacement_effects.py
lorcana_bot/engine.py
lorcana_bot/play_modes.py
tests/test_static_effects.py
tests/test_replacement_effects.py
tests/test_engine_trigger_pipeline.py
tests/test_state_invariants.py
```

Known lifecycle surfaces to audit:
```text
normal play
shifted play
banish
discard
return to hand
put into inkwell
generic _move_card_eventful
shift stack movement
ZONE_UNDER cards
```

### 2. Expected Code (The Solution)

* **Target State:**
```text
1. Public permanent entering play registers static and replacement effects.
2. Actions do not register lifecycle effects.
3. Cards in ZONE_UNDER do not provide static or replacement effects.
4. Any source leaving public play deregisters static and replacement effects.
5. Any shifted stack leaving play deregisters all stack sources.
6. Replacement/prevention effects evaluate before final mutation.
7. Existing trigger pipeline tests still pass.
```

### 3. Fixes Needed

* **Action:** `VERIFY / REVISE IF NEEDED`
* **Delta Description:** Use `rg` to search for lifecycle registration/deregistration routes and direct registry mutations. Add or adjust tests only for concrete missing coverage.
* **Delta Description:** Do not mark this complete if the full acceptance commands fail.

### 4. Lorcanito Source Reference (The Authority)

* **Reference File:** `packages/lorcana/lorcana-engine/src/rules/static-effect-registry.ts`
* **Reference File:** `packages/lorcana/lorcana-engine/src/runtime-moves/effects/replacement-effects.ts`
* **Reference File:** `packages/lorcana/lorcana-engine/src/runtime-moves/rules/static-effects-invalidation.ts`
* **Reference File:** `packages/lorcana/lorcana-engine/src/runtime-moves/state/shift-stack.ts`

### 5. Acceptance Check(s)

Run:
```bash
rg -n "register_static_effects_for_card|register_replacement_effects_for_card|deregister_static_effects_for_card|deregister_replacement_effects_from_card|stack_parent_id|ZONE_UNDER" lorcana_bot tests
python3 -m pytest tests/test_static_effects.py -q
python3 -m pytest tests/test_replacement_effects.py -q
python3 -m pytest tests/test_engine_trigger_pipeline.py -q
python3 -m pytest tests/test_state_invariants.py -q
python3 -m pytest -q
```

Expected:
- No duplicate registration route for shifted play.
- No active static/replacement source in `ZONE_UNDER`.
- All targeted tests pass.
- Full test suite passes.

### 6. Final Response Requirements

Report:
1. Files changed, if any.
2. Audit commands run.
3. Exact pytest commands run and results.
4. PASS or FAIL for Microfix 7 completion.
5. Any remaining work that belongs to Microfix 8 instead of Microfix 7.
