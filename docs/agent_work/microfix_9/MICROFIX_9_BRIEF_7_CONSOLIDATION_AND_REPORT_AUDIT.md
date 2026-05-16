# TECHNICAL IMPLEMENTATION BRIEF 7 — Microfix 9 Consolidation And Report Audit

Goal:
Run the final Microfix 9 audit after Briefs 1-6. Mark Microfix 9 complete only if general pending resolution works end to end for engine legal actions, apply-action execution, bag-origin pending completion, and automation round trip.

This brief may include small fixes only if the audit exposes a concrete missed Microfix 9 route.
Do not start Microfix 10 targeting-service parity here.

---

### 1. Current Risk Area

* **File Paths:**
```text
lorcana_bot/pending_effects.py
lorcana_bot/engine.py
lorcana_bot/effects.py
lorcana_bot/automation/candidates.py
lorcana_bot/automation/candidate_enumerator.py
lorcana_bot/automation/move_adapter.py
tests/test_pending_effects.py
tests/test_automation_pending_effects.py
tests/test_engine_trigger_pipeline.py
docs/LORCANACHAMP_GAME_ENGINE_REMAINING_WORK.md
```

Microfix 9 requirement kinds to audit:

```text
amount
target
multi_target
discard_choice
choice
optional
opponent_choice
enter_play_exerted
```

### 2. Expected Code (The Solution)

* **Target State:**
```text
1. All Microfix 9 requirement kinds are listed in PENDING_REQUIREMENT_KINDS.
2. Each kind has legal_actions() coverage.
3. Each kind has _apply_resolve_pending_effect() coverage.
4. Each kind writes into pe.raw["resolution_input"].
5. discard_choice suspends and resolves through pending effects.
6. bag-origin pending effects keep their bag entry until completion or decline.
7. automation candidates round-trip every pending choice field.
8. Existing Microfix 4 special pending kinds still pass.
```

### 3. Fixes Needed

* **Action:** `VERIFY / REVISE IF NEEDED`
* **Delta Description:** Search for all requirement kinds and resolver functions.
* **Delta Description:** Run pending, automation, trigger, and full test suites.
* **Delta Description:** Run trigger blocker report and record whether `unsupported_trigger_resolution_requirement:amount` decreased.
* **Delta Description:** If everything passes, update `docs/LORCANACHAMP_GAME_ENGINE_REMAINING_WORK.md` by marking Microfix 9 complete and making Microfix 10 the current highest-priority next action.

### 4. Lorcanito Source Reference (The Authority)

* **Reference File:** `lorcanito-full-src-code/packages/lorcana/lorcana-engine/src/types/runtime-state.ts`
* **Reference File:** `lorcanito-full-src-code/packages/lorcana/lorcana-engine/src/runtime-moves/resolution/action-effects/pending-action-effects.ts`
* **Reference File:** `lorcanito-full-src-code/packages/lorcana/lorcana-engine/src/runtime-moves/resolution/action-effects/selection-context.ts`
* **Reference File:** `lorcanito-full-src-code/packages/lorcana/lorcana-engine/src/runtime-moves/resolution/action-effects/selection-state.ts`
* **Reference File:** `lorcanito-full-src-code/packages/lorcana/lorcana-engine/src/runtime-moves/resolution/action-effects/discard-effect.ts`

Logic context:

```text
Lorcanito stores all player-provided pending inputs in PendingActionResolutionInput and resumes effect resolution with those inputs. Pending action effects retain controller, chooser, effect, continuation, resolution input, and selection context until completed.
```

### 5. Acceptance Check(s)

Run:
```bash
rg -n "\"amount\"|\"target\"|\"multi_target\"|\"discard_choice\"|\"choice\"|\"optional\"|\"opponent_choice\"|\"enter_play_exerted\"|resolution_input" lorcana_bot/pending_effects.py lorcana_bot/engine.py lorcana_bot/automation tests
python3 -m pytest tests/test_pending_effects.py -q
python3 -m pytest tests/test_automation_pending_effects.py -q
python3 -m pytest tests/test_engine_trigger_pipeline.py -q
python3 scripts/report_trigger_blockers.py --print-summary
python3 -m pytest -q
git diff --check
```

Expected:
- All targeted tests pass.
- Full suite passes.
- `git diff --check` passes.
- `unsupported_trigger_resolution_requirement:amount` decreases if source mapping includes newly supported amount requirements.
- If the report does not decrease, explain exactly why the runtime support did not move source projection yet.

### 6. Final Response Requirements

Report:
1. Files changed, if any.
2. Audit commands run.
3. Exact pytest commands run and results.
4. Trigger blocker report before/after summary for amount requirements.
5. PASS or FAIL for Microfix 9 completion.
6. If PASS, confirm roadmap now marks Microfix 9 complete and Microfix 10 as current next action.
7. Any remaining work that belongs to Microfix 10 instead of Microfix 9.
