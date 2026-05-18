# TECHNICAL IMPLEMENTATION BRIEF 2C - Trigger Filter Projection And Report Alignment

Read `docs/agent_work/microfix_11/MICROFIX_11_SHARED_RULES.md` first.

Goal:
Update projection/report support for string/object trigger filters implemented in Briefs 2A-2B. Runtime code is not allowed here.

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

Update report/projector support only for these already-runtime-tested string filters:

```text
CHARACTERS_HERE
CHARACTER_HERE
YOUR_ITEMS
ANY_ITEM
YOUR_LOCATIONS
YOUR_ACTIONS
YOUR_SONGS
YOUR_CHARACTERS_OR_LOCATIONS
YOUR_CHARACTERS_OR_LOCATIONS_WITH_CARD_UNDER
```

Update object filter support only for these runtime-tested keys:

```text
controller
owner
cardType
cardTypes
classification
classifications
name
hasKeyword
excludeSelf
filters
```

For `filters[]`, mark these types supported:

```text
ink-type
damaged
exerted
ready
has-keyword
has-classification
at-location
```

Do not mark any other filter type supported.

---

## Exact Required Tests

Add tests:

```text
tests/test_trigger_blocker_report.py::test_characters_here_no_longer_reports_unsupported_on
tests/test_trigger_blocker_report.py::test_ink_type_filter_no_longer_reports_complex_filter
tests/test_trigger_projection.py::test_trigger_with_characters_here_projects
tests/test_trigger_projection.py::test_trigger_with_object_filter_ink_type_projects
```

The ink-type report test must use a raw trigger shaped like Pluto style:

```python
{
    "event": "banish-in-challenge",
    "on": {
        "cardType": "character",
        "controller": "you",
        "excludeSelf": True,
        "filters": [{"type": "ink-type", "inkType": "steel"}],
    },
}
```

---

## Forbidden Changes

Do not change runtime matching code.

Do not remove condition, amount, `create-replacement-effect`, or `or` blockers.

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

Report exact support-list changes, report logic changes, tests added, command results, and five yes/no self-audit answers.
