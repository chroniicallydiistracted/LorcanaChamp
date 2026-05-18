# TECHNICAL IMPLEMENTATION BRIEF 3C - Condition Projector And Report Alignment

Read `docs/agent_work/microfix_11/MICROFIX_11_SHARED_RULES.md` first.

Goal:
Update condition projection/report support only for runtime condition kinds implemented in Brief 3B.

---

## Allowed Files

You may edit only:

```text
lorcana_bot/importers/lorcanito_source_mapper.py
lorcana_bot/decks/trigger_blocker_report.py
tests/test_trigger_projection.py
tests/test_trigger_blocker_report.py
```

---

## Exact Required Changes

In `lorcana_bot/importers/lorcanito_source_mapper.py`:

Add to `SUPPORTED_CONDITION_KINDS`:

```text
has-card-under
trigger-subject-had-card-under
put-card-under-any-this-turn
put-card-under-self-this-turn
banished-in-challenge-this-turn
turn-metric
```

Remove those same names from `BLOCKED_CONDITION_KINDS`.

Do not remove:

```text
has-granted-ability
target-aggregate-comparison
used-shift
```

In `trigger_blocker_report.py`, align condition support to the same exact names.

---

## Exact Required Tests

Add tests:

```text
tests/test_trigger_projection.py::test_trigger_with_has_card_under_condition_projects
tests/test_trigger_projection.py::test_trigger_with_turn_metric_condition_projects
tests/test_trigger_blocker_report.py::test_has_card_under_no_longer_reports_unsupported_condition
tests/test_trigger_blocker_report.py::test_turn_metric_no_longer_reports_unsupported_condition
```

---

## Forbidden Changes

Do not edit runtime code.

Do not remove unrelated blockers.

---

## Acceptance Checks

Run:

```bash
python3 -m pytest tests/test_trigger_projection.py tests/test_trigger_blocker_report.py -q
python3 -m pytest -q
git diff --check
```

---

## Final Response Requirements

Report condition support-list changes, blocked-list removals, tests added, command results, and five yes/no self-audit answers.
