# TECHNICAL IMPLEMENTATION BRIEF 1C - Projector Event Alignment

Read `docs/agent_work/microfix_11/MICROFIX_11_SHARED_RULES.md` first.

Goal:
Align source projection and blocker reporting with event runtime support added by Briefs 1A-1B. This brief is projection/report only.

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

### 1. `lorcana_bot/importers/lorcanito_source_mapper.py::SUPPORTED_TRIGGER_EVENTS`

Add exactly these entries if absent:

```python
"banish-in-challenge"
"put-card-under"
"draw"
"leave-play"
```

Also add these only if already runtime-supported in `lorcana_bot/triggers.py::SUPPORTED_TRIGGER_EVENTS`:

```python
"discard"
"return-to-hand"
"gain-lore"
"lose-lore"
"support"
"deal-damage"
```

Do not add:

```python
"be-chosen"
"sing"
```

### 2. `lorcana_bot/decks/trigger_blocker_report.py`

Do not change blocker taxonomy. Only align event support to runtime-supported events if the report imports or mirrors supported event sets.

---

## Exact Required Tests

Add these tests:

```text
tests/test_trigger_projection.py::test_microfix_11_events_are_supported
tests/test_trigger_projection.py::test_banish_in_challenge_trigger_projects
tests/test_trigger_projection.py::test_put_card_under_trigger_projects
tests/test_trigger_projection.py::test_leave_play_trigger_projects
```

Each projection test must build a `CardDef` with one source triggered ability and assert:

```python
len(project_triggers(card)) == 1
result[0].event == expected_event
```

Do not use fake card definition IDs that are absent from the card database when an engine is needed. Projection-only tests may use standalone `CardDef` objects because they do not require `GameEngine.card_def()`.

---

## Forbidden Changes

Do not edit runtime code.

Do not remove amount, condition, filter, `create-replacement-effect`, or `or` blockers.

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

Report files changed, exact supported event entries added, exact tests added, command results, and the five yes/no self-audit answers.
