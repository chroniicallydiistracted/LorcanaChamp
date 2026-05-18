# TECHNICAL IMPLEMENTATION BRIEF 3B - Condition Evaluator Runtime

Read `docs/agent_work/microfix_11/MICROFIX_11_SHARED_RULES.md` first.

Goal:
Use turn metadata and shift stack state to implement exact runtime condition kinds. No projector/report updates in this brief.

---

## Allowed Files

You may edit only:

```text
lorcana_bot/condition_evaluator.py
tests/test_condition_evaluator.py
```

---

## Exact Required Runtime Changes

Implement these condition kinds in `evaluate_condition()` and helper methods:

```text
has-card-under
trigger-subject-had-card-under
put-card-under-any-this-turn
put-card-under-self-this-turn
banished-in-challenge-this-turn
turn-metric
```

Required behavior:

```text
has-card-under:
  true when the source/target/context card has non-empty cards_under.

trigger-subject-had-card-under:
  true when event_snapshot cardsUnderCountBeforeBanish > 0 or cardsUnderIdsBeforeBanish is non-empty.

put-card-under-any-this-turn:
  true when state.turn_metadata["cards_put_under_this_turn_by_player"][player] > 0.

put-card-under-self-this-turn:
  true when state.turn_metadata["cards_put_under_self_this_turn_by_card"][source_id] > 0.

banished-in-challenge-this-turn:
  true when state.turn_metadata["banished_characters_in_challenge_by_owner_this_turn"][owner] is non-empty.

turn-metric:
  support at least these metrics:
    cards-drawn-by-player
    challenges-by-player
    banished-characters
    banished-characters-in-challenge
    cards-put-under-by-player
```

Comparison operators must support:

```text
eq
equals
gte
greater-than-or-equal
gt
greater-than
lte
less-than-or-equal
lt
less-than
```

Unknown metrics must raise `UnsupportedConditionError`.

---

## Exact Required Tests

Add tests:

```text
tests/test_condition_evaluator.py::test_has_card_under_true_for_shift_stack
tests/test_condition_evaluator.py::test_trigger_subject_had_card_under_uses_event_snapshot
tests/test_condition_evaluator.py::test_put_card_under_any_this_turn_uses_turn_metadata
tests/test_condition_evaluator.py::test_put_card_under_self_this_turn_uses_turn_metadata
tests/test_condition_evaluator.py::test_banished_in_challenge_this_turn_uses_turn_metadata
tests/test_condition_evaluator.py::test_turn_metric_cards_drawn_by_player
tests/test_condition_evaluator.py::test_turn_metric_challenges_by_player
tests/test_condition_evaluator.py::test_turn_metric_unknown_metric_raises
```

If existing tests assert these conditions raise as unsupported, replace those tests with the new expected behavior.

---

## Acceptance Checks

Run:

```bash
python3 -m pytest tests/test_condition_evaluator.py -q
python3 -m pytest -q
git diff --check
```

---

## Final Response Requirements

Report condition kinds implemented, metrics implemented, tests added/replaced, command results, and five yes/no self-audit answers.
