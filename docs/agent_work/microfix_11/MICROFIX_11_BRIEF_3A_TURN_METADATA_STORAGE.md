# TECHNICAL IMPLEMENTATION BRIEF 3A - Turn Metadata Storage

Read `docs/agent_work/microfix_11/MICROFIX_11_SHARED_RULES.md` first.

Goal:
Add turn metadata storage and recording routes only. Do not implement condition evaluation in this brief.

---

## Allowed Files

You may edit only:

```text
lorcana_bot/state.py
lorcana_bot/engine.py
lorcana_bot/play_modes.py
tests/test_engine_trigger_pipeline.py
tests/test_shift.py
```

Do not edit `condition_evaluator.py`, projector files, or report files.

---

## Exact Required Runtime Changes

Add `GameState.turn_metadata: dict[str, Any]` with default empty dict.

Use these exact metadata keys:

```text
cards_drawn_this_turn_by_player
challenges_by_player_this_turn
banished_characters_this_turn
banished_characters_in_challenge_by_owner_this_turn
cards_put_under_this_turn_by_player
cards_put_under_self_this_turn_by_card
```

Record:

```text
engine.draw_cards() increments cards_drawn_this_turn_by_player[player]
engine._apply_challenge() increments challenges_by_player_this_turn[player]
engine._banish_eventful() appends card_id to banished_characters_this_turn
engine._banish_eventful(happened_in_challenge=True) appends card_id to banished_characters_in_challenge_by_owner_this_turn[owner]
play_modes.attach_shift_stack() records put-under counts for player and target card
```

Reset `state.turn_metadata` when the active turn changes in `engine._apply_end_turn()`, after the outgoing turn is fully processed and before the next player's turn-start draw.

---

## Exact Required Tests

Add tests:

```text
tests/test_engine_trigger_pipeline.py::test_draw_cards_records_turn_metadata
tests/test_engine_trigger_pipeline.py::test_challenge_records_turn_metadata
tests/test_engine_trigger_pipeline.py::test_challenge_banish_records_turn_metadata
tests/test_shift.py::test_shift_records_put_card_under_turn_metadata
```

---

## Forbidden Changes

Do not implement `turn-metric` condition evaluation here.

Do not update projector/report supported condition lists.

---

## Acceptance Checks

Run:

```bash
python3 -m pytest tests/test_engine_trigger_pipeline.py tests/test_shift.py -q
python3 -m pytest -q
git diff --check
```

---

## Final Response Requirements

Report metadata keys added, recording routes added, tests added, command results, and five yes/no self-audit answers.
