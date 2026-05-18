# TECHNICAL IMPLEMENTATION BRIEF 1B - Runtime Event Emission Routes

Read `docs/agent_work/microfix_11/MICROFIX_11_SHARED_RULES.md` first.

Goal:
Wire real runtime event emission for `banish-in-challenge`, `put-card-under`, and `leave-play` matching. This brief may update `lorcana_bot/triggers.py::SUPPORTED_TRIGGER_EVENTS` only after tests prove runtime behavior.

---

## Allowed Files

You may edit only:

```text
lorcana_bot/engine.py
lorcana_bot/play_modes.py
lorcana_bot/triggers.py
tests/test_engine_trigger_pipeline.py
tests/test_shift.py
tests/test_trigger_state.py
```

Do not edit:

```text
lorcana_bot/importers/lorcanito_source_mapper.py
lorcana_bot/decks/trigger_blocker_report.py
```

---

## Exact Runtime Changes

### 1. `lorcana_bot/engine.py::_banish_eventful()`

Keep the existing `EVENT_CHARACTER_BANISHED` emission.

After that emission, add:

```text
if happened_in_challenge:
    emit EVENT_BANISH_IN_CHALLENGE with queue_triggers equal to the helper argument.
```

Payload must include:

```python
{
    "player_id": resolved_actor,
    "card_id": card_id,
    "subject_card_id": card_id,
    "source_card_id": source_id,
    "trigger_source_card_id": source_id if source_id is not None else card_id,
    "owner_id": inst.owner,
    "controller_id": controller,
    "from_zone": from_zone,
    "to_zone": banish_event.actual_destination,
    "happened_in_challenge": True,
    "banished_card_type": card_type,
    "reason": reason,
    "was_replaced": banish_event.was_replaced,
    "replacement_description": banish_event.replacement_description,
}
```

### 2. `lorcana_bot/play_modes.py::attach_shift_stack()`

After stack relationships are set, emit `EVENT_PUT_CARD_UNDER` once for each card in `stack_ids`.

Payload must include:

```python
{
    "player_id": player,
    "card_id": under_id,
    "subject_card_id": under_id,
    "target_id": new_top_id,
    "trigger_source_card_id": new_top_id,
}
```

### 3. `lorcana_bot/triggers.py::expand_trigger_event()`

`expand_trigger_event("leave-play")` must return exactly:

```python
(
    TRIGGER_EVENT_BANISH,
    TRIGGER_EVENT_BANISH_IN_CHALLENGE,
    TRIGGER_EVENT_RETURN_TO_HAND,
    TRIGGER_EVENT_INK,
)
```

### 4. `lorcana_bot/triggers.py::trigger_matches_event()`

Replace direct event comparison with:

```python
if pending.event not in expand_trigger_event(trigger.event):
    return False
```

### 5. `lorcana_bot/triggers.py::SUPPORTED_TRIGGER_EVENTS`

Add only these events after tests exist:

```python
TRIGGER_EVENT_BANISH_IN_CHALLENGE
TRIGGER_EVENT_PUT_CARD_UNDER
TRIGGER_EVENT_LEAVE_PLAY
```

Do not add `TRIGGER_EVENT_BE_CHOSEN`.

---

## Exact Required Tests

Add these tests with exactly these names:

```text
tests/test_engine_trigger_pipeline.py::test_challenge_banish_emits_generic_and_challenge_specific_events
tests/test_shift.py::test_shift_emits_put_card_under_event
tests/test_trigger_state.py::test_leave_play_trigger_matches_expanded_events
tests/test_trigger_state.py::test_leave_play_trigger_flushes_to_bag
```

Test requirements:

```text
The challenge-banish test must assert both event log entries exist and pending events include "banish" and "banish-in-challenge".
The shift test must assert EVENT_PUT_CARD_UNDER is logged and pending events include "put-card-under".
The leave-play match test must check banish, banish-in-challenge, return-to-hand, and ink.
The leave-play flush test must prove a printed trigger with event="leave-play" is collected and enqueued.
```

---

## Forbidden Changes

Do not update `lorcanito_source_mapper.py`.

Do not update `trigger_blocker_report.py`.

Do not add `be-chosen` to runtime support.

---

## Acceptance Checks

Run:

```bash
python3 -m pytest tests/test_trigger_state.py tests/test_engine_trigger_pipeline.py tests/test_shift.py -q
python3 -m pytest -q
git diff --check
```

---

## Final Response Requirements

Report files changed, exact runtime emission routes added, exact support-list entries added, exact tests added, command results, and the five yes/no self-audit answers.
