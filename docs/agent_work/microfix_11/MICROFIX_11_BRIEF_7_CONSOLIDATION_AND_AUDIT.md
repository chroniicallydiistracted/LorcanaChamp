# TECHNICAL IMPLEMENTATION BRIEF 7 - Microfix 11 Consolidation And Audit

Goal:
Run the final Microfix 11 audit, add only small missed-route fixes, and update the roadmap if the Microfix 11 target state is proven.

Read `docs/agent_work/microfix_11/MICROFIX_11_SHARED_RULES.md` before starting.

This is not a new feature brief. Do not start Microfix 12 work here.

---

### 1. Current Risk Area

* **File Paths:**
```text
lorcana_bot/constants.py
lorcana_bot/triggers.py
lorcana_bot/engine.py
lorcana_bot/effects.py
lorcana_bot/pending_effects.py
lorcana_bot/condition_evaluator.py
lorcana_bot/importers/lorcanito_source_mapper.py
lorcana_bot/decks/trigger_blocker_report.py
tests/test_engine_trigger_pipeline.py
tests/test_trigger_projection.py
tests/test_trigger_blocker_report.py
tests/test_bag_resolution.py
tests/test_pending_effects.py
tests/test_condition_evaluator.py
docs/LORCANACHAMP_GAME_ENGINE_REMAINING_WORK.md
```

Known Microfix 11 target surfaces:

```text
draw trigger event
leave-play trigger expansion
banish-in-challenge trigger event
put-card-under trigger event
CHARACTERS_HERE on-filter
object on-filter filters[]
has-card-under condition
turn-metric condition
amount resolution requirements
scry_ordering pending requirements
bag resolution_input continuation
trigger blocker report truthfulness
```

### 2. Expected Code (The Solution)

* **Target State:**
```text
1. Runtime emits and matches Microfix 11 trigger events truthfully.
2. Trigger subject matching does not fail open for unsupported filters.
3. Condition evaluator supports the Microfix 11 condition blockers with real state/metadata.
4. Dynamic amount support does not silently project unsupported values as zero.
5. Triggered scry can suspend to pending scry_ordering and resume through bag completion.
6. Bag resolution_input persists intermediate player choices.
7. Reports accurately distinguish supported blockers from remaining unsupported systems.
8. Roadmap marks Microfix 11 complete only if all acceptance checks pass.
```

### 3. Fixes Needed

* **Action:** `VERIFY / REVISE IF NEEDED`
* **Delta Description:** Use `rg` and focused tests to find missed direct routes or projection/report mismatches.
* **Delta Description:** Add small fixes only when they directly close a Microfix 11 route.
* **Delta Description:** Update `docs/LORCANACHAMP_GAME_ENGINE_REMAINING_WORK.md` only after the full audit passes.

### 4. Lorcanito Source Reference (The Authority)

* **Reference File:** `lorcanito-full-src-code/packages/lorcana/lorcana-engine/src/triggered-abilities/index.ts`
* **Reference File:** `lorcanito-full-src-code/packages/lorcana/lorcana-engine/src/types/domain-events.ts`
* **Reference File:** `lorcanito-full-src-code/packages/lorcana/lorcana-engine/src/runtime-moves/resolution/resolve-bag.ts`
* **Reference File:** `lorcanito-full-src-code/packages/lorcana/lorcana-engine/src/rules/condition-evaluator.ts`
* **Reference File:** `lorcanito-full-src-code/packages/lorcana/lorcana-engine/src/runtime-moves/state/turn-metrics.ts`

### 5. Acceptance Check(s)

Run:
```bash
rg -n "SUPPORTED_TRIGGER_EVENTS|SUPPORTED_CONDITION_KINDS|BLOCKED_CONDITION_KINDS|RESOLUTION_REQUIREMENT_KINDS|expand_trigger_event|turn_metadata|resolution_input|banish-in-challenge|put-card-under|CHARACTERS_HERE|has-card-under|turn-metric" lorcana_bot tests docs/agent_work/microfix_11
python3 -m pytest tests/test_engine_trigger_pipeline.py -q
python3 -m pytest tests/test_trigger_projection.py -q
python3 -m pytest tests/test_trigger_blocker_report.py -q
python3 -m pytest tests/test_bag_resolution.py -q
python3 -m pytest tests/test_pending_effects.py -q
python3 -m pytest tests/test_condition_evaluator.py -q
python3 -m pytest tests/test_targeting.py -q
python3 -m pytest -q
python3 scripts/report_trigger_blockers.py --print-summary
git diff --check
```

Expected:

```text
No Microfix 11 runtime support is claimed only in reports/importers.
No supported trigger on-filter fails open for unsupported variants.
Microfix 11 target blockers decrease in generated report output.
create-replacement-effect and or remain as later work if still unsupported.
Full test suite passes.
Roadmap is updated only after these checks pass.
```

### 6. Final Response Requirements

Report:

1. Files changed, if any.
2. Audit commands run.
3. Exact pytest commands run and results.
4. Trigger blocker report summary after Microfix 11.
5. PASS or FAIL for Microfix 11 completion.
6. Remaining work that belongs to Microfix 12 or later.
