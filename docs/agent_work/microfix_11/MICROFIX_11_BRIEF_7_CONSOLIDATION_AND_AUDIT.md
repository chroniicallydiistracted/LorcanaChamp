# TECHNICAL IMPLEMENTATION BRIEF 7 - Microfix 11 Consolidation And Audit

Read `docs/agent_work/microfix_11/MICROFIX_11_SHARED_RULES.md` first.

Goal:
Run the final Microfix 11 audit, update the remaining-work roadmap with exact report results, and declare PASS or FAIL.

This brief is audit and documentation only. Do not add feature work in this brief.

---

## Allowed Files

You may edit only:

```text
docs/LORCANACHAMP_GAME_ENGINE_REMAINING_WORK.md
tests/test_trigger_blocker_report.py
```

Do not edit runtime code in this brief. If an audit command proves runtime code is broken, stop implementation, mark Microfix 11 FAIL, and report the exact failed audit command and broken route.

---

## Required Audit Scope

Audit these Microfix 11 routes:

```text
banish-in-challenge event normalization and runtime emission
put-card-under event normalization and runtime emission
leave-play trigger expansion
draw trigger projection support
string on filters for item, action, location, and character selectors
object on filters with fail-closed unknown keys
turn metadata storage for turn-based conditions
condition evaluator support for has-card-under and turn-metric aliases
amount resolver support for event snapshots and projected source raw amount
scry_ordering pending route from triggered bag effects
bag resolution_input persistence
bag-origin pending completion and exact bag entry removal
trigger blocker report truthfulness
```

---

## Required Audit Commands

Run:

```bash
rg -n "SUPPORTED_TRIGGER_EVENTS|SUPPORTED_ON_VALUES|SUPPORTED_CONDITION_KINDS|BLOCKED_CONDITION_KINDS|RESOLUTION_REQUIREMENT_KINDS|expand_trigger_event|turn_metadata|resolution_input|banish-in-challenge|put-card-under|CHARACTERS_HERE|has-card-under|turn-metric|create-replacement-effect|unsupported_trigger_effect:or" lorcana_bot tests docs/agent_work/microfix_11
python3 -m pytest tests/test_trigger_state.py -q
python3 -m pytest tests/test_engine_trigger_pipeline.py -q
python3 -m pytest tests/test_shift.py -q
python3 -m pytest tests/test_condition_evaluator.py -q
python3 -m pytest tests/test_effects.py -q
python3 -m pytest tests/test_bag_resolution.py -q
python3 -m pytest tests/test_pending_effects.py -q
python3 -m pytest tests/test_trigger_projection.py -q
python3 -m pytest tests/test_trigger_blocker_report.py -q
python3 scripts/report_trigger_blockers.py --print-summary
jq '.total_trigger_rows, .projected_trigger_rows, .blocked_trigger_rows, .blocked_trigger_copies, .by_primary_blocker_copies' data/decks/reports/trigger_blocker_summary.json
python3 -m pytest -q
git diff --check
```

---

## Required Roadmap Update

Update `docs/LORCANACHAMP_GAME_ENGINE_REMAINING_WORK.md` with:

```text
Microfix 11 status
exact date of completion
exact total trigger rows
exact projected trigger rows
exact blocked trigger rows
exact blocked trigger copies
exact remaining blocker list and copy counts
exact recommended next milestone from data/decks/reports/next_engine_milestone_recommendation.json
```

Do not claim a blocker is solved unless it is absent from the regenerated report.

Do not claim `create-replacement-effect` or `or` are implemented unless a runtime implementation and tests exist.

---

## PASS Criteria

Mark Microfix 11 PASS only if all are true:

```text
1. Full pytest passes.
2. git diff --check is clean.
3. Runtime tests exist for every support-list entry added in Microfix 11.
4. Trigger blocker report has no completed Microfix 11 blockers:
   unsupported_trigger_event:banish-in-challenge
   unsupported_trigger_event:put-card-under
   unsupported_trigger_event:draw
   unsupported_trigger_event:leave-play
   unsupported_trigger_condition:has-card-under
   unsupported_trigger_condition:turn-metric
   unsupported_trigger_on:CHARACTERS_HERE
   unsupported_trigger_on:complex_filter:filters
   unsupported_trigger_resolution_requirement:scry_ordering
5. create-replacement-effect and or are not falsely marked supported.
6. docs/LORCANACHAMP_GAME_ENGINE_REMAINING_WORK.md is updated with exact regenerated report values.
```

If any criterion fails, mark Microfix 11 FAIL and list the exact failing criterion.

---

## Remaining Work Classification

Remaining blockers must be assigned to future work:

```text
unsupported_trigger_effect:create-replacement-effect -> replacement/prevention effect execution milestone
unsupported_trigger_effect:or -> compound source effect execution milestone
unsupported_trigger_resolution_requirement:amount -> only if it remains in the regenerated report
```

Do not start those future milestones in this brief.

---

## Final Response Requirements

Report:

```text
1. Files changed.
2. Audit command results.
3. Regenerated blocker report summary.
4. PASS or FAIL for Microfix 11.
5. Exact remaining Microfix 12+ work.
6. Confirmation that no runtime code was edited; if runtime code is broken, report FAIL instead of fixing it here.
7. Five yes/no self-audit answers from MICROFIX_11_SHARED_RULES.md.
```
