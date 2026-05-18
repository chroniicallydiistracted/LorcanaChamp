# TECHNICAL IMPLEMENTATION BRIEF 4C - Amount And Scry Report Alignment

Read `docs/agent_work/microfix_11/MICROFIX_11_SHARED_RULES.md` first.

Goal:
Update projection/report support for amount and scry ordering only after Briefs 4A-4B runtime tests pass.

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

In `_project_trigger_effect()`:

```text
Do not silently set dynamic amount to 0.
Preserve raw amount information in EffectDef.raw.
Project amount only when Brief 4A resolver supports the shape.
Return None for unsupported amount shapes.
```

In `trigger_blocker_report.py`:

```text
Do not count amount as a blocker for amount shapes supported by Brief 4A.
Do count amount as a blocker for unsupported amount shapes.
Do not count scry_ordering as a blocker when the scry effect can create pending scry ordering through Brief 4B.
```

---

## Exact Required Tests

Add tests:

```text
tests/test_trigger_projection.py::test_dynamic_amount_shape_supported_by_runtime_projects
tests/test_trigger_projection.py::test_unsupported_amount_shape_does_not_project
tests/test_trigger_blocker_report.py::test_supported_amount_shape_not_reported_as_resolution_blocker
tests/test_trigger_blocker_report.py::test_unsupported_amount_shape_still_reported_as_resolution_blocker
tests/test_trigger_blocker_report.py::test_scry_ordering_not_reported_when_pending_route_supported
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

Report projection/report changes, amount shapes supported, blockers intentionally retained, tests added, command results, and five yes/no self-audit answers.
