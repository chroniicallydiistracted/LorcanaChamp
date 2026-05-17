# TECHNICAL IMPLEMENTATION BRIEF 3 - Turn Metadata And Runtime Conditions

Goal:
Add the missing turn metadata needed by Lorcanito-style trigger conditions, then implement the condition blockers that depend on that metadata.

Read `docs/agent_work/microfix_11/MICROFIX_11_SHARED_RULES.md` before starting.

This brief depends on Briefs 1-2. Do not update projection support for a condition until the runtime evaluator and event metadata are tested.

---

### 1. Current Missing Or Incorrect Code

* **File Path:** `lorcana_bot/condition_evaluator.py`
* **Line Range:** `unsupported condition helper methods`
* **Snippet:**
```python
def _evaluate_banished_in_challenge(self, condition: ConditionDef) -> bool:
    """Evaluate if a character was banished in challenge this turn.

    This would need turn history tracking.
    """
    return False

def _evaluate_has_card_under(self, condition: ConditionDef) -> bool:
    """Evaluate if target has cards under it.

    This needs target context, not just source.
    """
    raise UnsupportedConditionError("has-card-under condition needs target context")
```

Current gaps:

```text
turn-metric is not evaluated.
has-card-under is unsupported despite shift stack/card-under state existing.
trigger-subject-had-card-under is unsupported.
put-card-under-any-this-turn and put-card-under-self-this-turn are unsupported.
banished-in-challenge-this-turn is a stub.
turn metadata is not consistently recorded for draw, challenge, banish-in-challenge, and put-card-under.
```

### 2. Expected Code (The Solution)

* **Target State:**
```text
1. GameState has per-turn metadata storage for:
   cardsDrawnThisTurnByPlayer
   challengesByPlayerThisTurn
   banishedCharactersThisTurn
   banishedCharactersInChallengeByOwnerThisTurn
   cardsPutUnderThisTurnByPlayer
   cardsPutUnderSelfThisTurnByCard

2. Engine records metadata when:
   draw_cards() draws cards
   _apply_challenge() starts a challenge
   _banish_eventful(... happened_in_challenge=True ...) banishes a character
   a card is put under another card

3. Turn metadata resets at the correct turn boundary.

4. Condition evaluator supports:
   has-card-under
   trigger-subject-had-card-under
   put-card-under-any-this-turn
   put-card-under-self-this-turn
   banished-in-challenge-this-turn
   turn-metric

5. trigger projection and blocker report only mark these condition kinds supported after runtime tests pass.
```

### 3. Fixes Needed

* **Action:** `EXPAND`
* **Delta Description:** Add turn metadata storage to `GameState` or the existing state metadata structure.
* **Delta Description:** Add engine recording calls at draw, challenge, challenge-banish, and put-under routes.
* **Delta Description:** Implement condition evaluator branches using real state, event snapshot, and turn metadata.
* **Delta Description:** Update mapper/report condition support after proving each condition.

### 4. Lorcanito Source Reference (The Authority)

* **Reference File:** `lorcanito-full-src-code/packages/lorcana/lorcana-engine/src/runtime-moves/state/turn-metrics.ts`
* **Line Range:** `Lines 25-226`
* **Logic Context:**
```typescript
metadata.cardsDrawnThisTurnByPlayer ??= {};
metadata.challengesByPlayerThisTurn ??= {};
metadata.banishedCharactersInChallengeByOwnerThisTurn ??= {};
metadata.cardsPutUnderThisTurnByPlayer ??= {};
metadata.cardsPutUnderSelfThisTurnByCard ??= {};

export function recordCardDrawnThisTurn(state, player) { ... }
export function recordChallengeThisTurn(state, player) { ... }
export function recordBanishedInChallengeThisTurn(state, ownerId, cardId) { ... }
export function recordCardPutUnderThisTurn(state, playerId, cardId, targetId) { ... }
```

* **Reference File:** `lorcanito-full-src-code/packages/lorcana/lorcana-engine/src/rules/condition-evaluator.ts`
* **Line Range:** `Lines 443-600`
* **Logic Context:**
```typescript
case "turn-metric": {
  return evaluateTurnMetricCondition(condition, ctx);
}

case "cards-drawn-by-player": {
  const count = metadata.cardsDrawnThisTurnByPlayer?.[playerId] ?? 0;
  return compare(count, operator, value);
}
```

### 5. Acceptance Check(s)

Run:
```bash
python3 -m pytest tests/test_condition_evaluator.py -q
python3 -m pytest tests/test_engine_trigger_pipeline.py -q
python3 -m pytest tests/test_trigger_projection.py -q
python3 -m pytest tests/test_trigger_blocker_report.py -q
python3 -m pytest -q
git diff --check
```

Expected:

```text
has-card-under evaluates true for shifted/card-under stacks.
trigger-subject-had-card-under can use event snapshot data from a banish/leave-play event.
turn-metric cards-drawn-by-player and challenges-by-player are tested.
banished-in-challenge-this-turn is driven by real challenge banish metadata.
put-card-under conditions are driven by real put-under metadata.
Full test suite passes.
```

### 6. Final Response Requirements

Report:

1. Files changed.
2. Turn metadata fields added.
3. Engine recording routes added.
4. Condition kinds implemented.
5. Projection/report condition support changed.
6. Exact commands run and results.
