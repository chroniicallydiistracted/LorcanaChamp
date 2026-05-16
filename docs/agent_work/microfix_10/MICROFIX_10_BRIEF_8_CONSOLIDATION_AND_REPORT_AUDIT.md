# TECHNICAL IMPLEMENTATION BRIEF 8 — Microfix 10 Consolidation And Report Audit

Goal:
Run the final Microfix 10 audit after Briefs 1-7. Mark Microfix 10 complete only if action, pending, effect, and automation target paths use the central targeting service and the report recommendation moves or is explained.

This brief may include small fixes only if the audit exposes a concrete missed Microfix 10 route.
Do not start Microfix 11 trigger event expansion here.

---

### 1. Current Risk Area

* **File Paths:**
```text
lorcana_bot/targeting.py
lorcana_bot/engine.py
lorcana_bot/pending_effects.py
lorcana_bot/effects.py
lorcana_bot/automation/candidates.py
lorcana_bot/automation/candidate_enumerator.py
lorcana_bot/automation/move_adapter.py
tests/test_targeting.py
tests/test_pending_effects.py
tests/test_effects.py
tests/test_automation_pending_effects.py
docs/LORCANACHAMP_GAME_ENGINE_REMAINING_WORK.md
```

### 2. Expected Code (The Solution)

* **Target State:**
```text
1. Central targeting service exists in lorcana_bot/targeting.py.
2. Engine action target enumeration uses targeting service.
3. Pending target and multi_target requirements use targeting service.
4. EffectResolver target aliases use targeting service.
5. Ward/cannot-be-targeted and ZONE_UNDER exclusions are centralized.
6. Player targets and card targets are distinguished.
7. Current/context targets are honored.
8. Slotted target input validates, flattens, and round-trips through pending/automation.
9. Existing Microfix 9 pending tests still pass.
```

### 3. Fixes Needed

* **Action:** `VERIFY / REVISE IF NEEDED`
* **Delta Description:** Search for remaining duplicated target enumeration paths in `engine.py`, `pending_effects.py`, and `effects.py`.
* **Delta Description:** Run targeted and full test suites.
* **Delta Description:** Run real-deck/report scripts and record whether `target_choice_prompts` decreases.
* **Delta Description:** If everything passes, update `docs/LORCANACHAMP_GAME_ENGINE_REMAINING_WORK.md` by marking Microfix 10 complete and making Microfix 11 the current highest-priority next action.

### 4. Lorcanito Source Reference (The Authority)

* **Reference File:** `lorcanito-full-src-code/packages/lorcana/lorcana-engine/src/targeting/targeting-service.ts`
* **Reference File:** `lorcanito-full-src-code/packages/lorcana/lorcana-engine/src/targeting/runtime/target-resolver.ts`
* **Reference File:** `lorcanito-full-src-code/packages/lorcana/lorcana-engine/src/targeting/runtime/target-availability.ts`
* **Reference File:** `lorcanito-full-src-code/packages/lorcana/lorcana-engine/src/targeting/slotted-targets.ts`

### 5. Acceptance Check(s)

Run:
```bash
rg -n "_effect_targets_for_card|get_valid_targets_for_requirement|_target_cards|_collection|candidate_ids|slotted_targets|TargetSelectionAvailability" lorcana_bot tests
python3 -m pytest tests/test_targeting.py -q
python3 -m pytest tests/test_pending_effects.py -q
python3 -m pytest tests/test_effects.py -q
python3 -m pytest tests/test_automation_pending_effects.py -q
python3 scripts/report_trigger_blockers.py --print-summary
python3 scripts/report_real_deck_mapping_coverage.py --resolved-deck-dir data/decks/resolved/real_core --out /tmp/real_deck_suite_mapping_coverage.json --print-summary
python3 -m pytest -q
git diff --check
```

Expected:
- All tests pass.
- `target_choice_prompts` decreases if source projection maps newly supported target requirements.
- If the report does not decrease, explain whether mapper/report work belongs to Microfix 15.

### 6. Final Response Requirements

Report:
1. Files changed, if any.
2. Audit commands run.
3. Exact pytest commands run and results.
4. Report movement for `target_choice_prompts`.
5. PASS or FAIL for Microfix 10 completion.
6. If PASS, confirm roadmap marks Microfix 10 complete and Microfix 11 as current next action.
7. Any remaining work that belongs to Microfix 11 or Microfix 15 instead of Microfix 10.
