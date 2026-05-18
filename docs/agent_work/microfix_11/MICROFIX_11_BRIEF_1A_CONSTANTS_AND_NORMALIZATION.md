# TECHNICAL IMPLEMENTATION BRIEF 1A - Constants And Event Normalization Only

Read `docs/agent_work/microfix_11/MICROFIX_11_SHARED_RULES.md` first.

Goal:
Add missing event constants and canonical event normalization only. This brief must not claim runtime support.

---

## Allowed Files

You may edit only:

```text
lorcana_bot/constants.py
tests/test_trigger_state.py
```

Do not edit:

```text
lorcana_bot/triggers.py::SUPPORTED_TRIGGER_EVENTS
lorcana_bot/importers/lorcanito_source_mapper.py
lorcana_bot/decks/trigger_blocker_report.py
lorcana_bot/engine.py
lorcana_bot/play_modes.py
```

---

## Exact Required Changes

In `lorcana_bot/constants.py`, add these constants if absent:

```python
TRIGGER_EVENT_BANISH_IN_CHALLENGE = "banish-in-challenge"
TRIGGER_EVENT_PUT_CARD_UNDER = "put-card-under"

EVENT_BANISH_IN_CHALLENGE = "BANISH_IN_CHALLENGE"
EVENT_PUT_CARD_UNDER = "PUT_CARD_UNDER"
```

Add only emitted event constants to `ALL_GAMEPLAY_EVENTS`:

```python
EVENT_BANISH_IN_CHALLENGE
EVENT_PUT_CARD_UNDER
```

Do not add `EVENT_BE_CHOSEN` to `ALL_GAMEPLAY_EVENTS` in this brief unless a runtime emitter already exists and is tested. It does not belong in Brief 1A.

Add legacy mappings:

```python
"BANISH_IN_CHALLENGE": TRIGGER_EVENT_BANISH_IN_CHALLENGE
"PUT_CARD_UNDER": TRIGGER_EVENT_PUT_CARD_UNDER
```

---

## Exact Required Tests

In `tests/test_trigger_state.py`, add or update exactly these tests:

```text
test_canonical_trigger_event
test_buffer_trigger_event_hydrates_banish_in_challenge_payload_fields
test_buffer_trigger_event_hydrates_put_card_under_payload_fields
```

The put-card-under test must assert:

```python
pending.event == "put-card-under"
pending.player_id == 0
pending.subject_card_id == moved_card_id
pending.event_snapshot["target_id"] == top_card_id
```

---

## Forbidden Changes

Do not add `banish-in-challenge` or `put-card-under` to `SUPPORTED_TRIGGER_EVENTS` in this brief.

Do not update `lorcanito_source_mapper.py`.

Do not update `trigger_blocker_report.py`.

---

## Acceptance Checks

Run:

```bash
python3 -m pytest tests/test_trigger_state.py -q
python3 -m pytest -q
git diff --check
```

Expected:

```text
Canonical event conversion works.
No runtime support list was changed.
Full suite passes.
```

---

## Final Response Requirements

Report the files changed, exact constants added, exact mappings added, test names added, command results, and the five yes/no self-audit answers from shared rules.
