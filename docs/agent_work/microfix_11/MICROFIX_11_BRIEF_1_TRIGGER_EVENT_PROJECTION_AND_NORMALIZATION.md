# TECHNICAL IMPLEMENTATION BRIEF 1 - Trigger Event Projection And Normalization

Goal:
Make trigger event names line up between Lorcanito, Python runtime events, trigger matching, and trigger projection for the Microfix 11 event blockers.

Read `docs/agent_work/microfix_11/MICROFIX_11_SHARED_RULES.md` before starting.

Do not implement subject filters here. Do not implement turn-metric conditions here. Do not remove report blockers unless the runtime event is emitted and matched by tests.

---

### 1. Current Missing Or Incorrect Code

* **File Path:** `lorcana_bot/triggers.py`
* **Line Range:** `trigger_matches_event() and SUPPORTED_TRIGGER_EVENTS`
* **Snippet:**
```python
SUPPORTED_TRIGGER_EVENTS = {
    "play",
    "quest",
    "challenge",
    "banish",
    "start-turn",
    "end-turn",
    "ink",
    "move",
    "discard",
    "return-to-hand",
    "draw",
    "exert",
    "ready",
    "gain-lore",
    "lose-lore",
    "support",
    "deal-damage",
    "banish-in-challenge",
}
```

Current gaps:

```text
put-card-under is not supported.
leave-play expansion exists but trigger_matches_event() compares trigger.event directly.
banish-in-challenge is listed but engine only emits the generic banish event in some paths.
draw, leave-play, support, sing, be-chosen, and put-card-under must only be projected after runtime can emit or normalize them truthfully.
```

* **File Path:** `lorcana_bot/importers/lorcanito_source_mapper.py`
* **Line Range:** `SUPPORTED_TRIGGER_EVENTS`
* **Snippet:**
```python
SUPPORTED_TRIGGER_EVENTS = frozenset({
    "play",
    "quest",
    "challenge",
    "banish",
    "start-turn",
    "end-turn",
    "ink",
    "move",
    "challenged",
    "damage",
    "exert",
    "ready",
})
```

### 2. Expected Code (The Solution)

* **Target State:**
```text
1. constants.py exposes trigger constants and event constants for:
   - banish-in-challenge
   - put-card-under
   - leave-play
   - draw
   - support
   - be-chosen

2. LEGACY_EVENT_MAP maps emitted Python GameEvent names to canonical trigger event names:
   - CARD_DRAWN -> draw
   - CHARACTER_BANISHED -> banish
   - BANISH_IN_CHALLENGE -> banish-in-challenge
   - PUT_CARD_UNDER -> put-card-under
   - CARD_RETURNED_TO_HAND -> return-to-hand
   - SUPPORT -> support
   - BE_CHOSEN -> be-chosen

3. triggers.expand_trigger_event("leave-play") returns:
   ("banish", "banish-in-challenge", "return-to-hand", "ink")

4. trigger_matches_event() checks pending.event against expanded trigger events:
   pending.event in expand_trigger_event(trigger.event)

5. _banish_eventful(... happened_in_challenge=True ...) buffers both:
   - banish
   - banish-in-challenge

6. put-card-under movement emits/buffers a PUT_CARD_UNDER event with:
   - player_id
   - card_id
   - target_id

7. importer/report supported event sets are expanded only for events proven by runtime tests.
```

### 3. Fixes Needed

* **Action:** `EXPAND`
* **Delta Description:** Add missing canonical event constants and legacy event mappings.
* **Delta Description:** Update trigger matching to use Lorcanito-style event expansion for `leave-play`.
* **Delta Description:** Ensure challenge banish produces a `banish-in-challenge` trigger event without removing the existing `banish` event.
* **Delta Description:** Add a `put-card-under` event emission route for shift/under-card movement or the central helper that performs put-under behavior.
* **Delta Description:** Update `lorcanito_source_mapper.py` and `trigger_blocker_report.py` event support only after tests prove runtime support.

### 4. Lorcanito Source Reference (The Authority)

* **Reference File:** `lorcanito-full-src-code/packages/lorcana/lorcana-engine/src/triggered-abilities/index.ts`
* **Line Range:** `Lines 258-341`
* **Logic Context:**
```typescript
const LEAVE_PLAY_EVENTS = [
  "banish",
  "banish-in-challenge",
  "return-to-hand",
  "ink",
];

function expandTriggerEvent(event: string): string[] {
  if (event === "leave-play") {
    return LEAVE_PLAY_EVENTS;
  }

  return [event];
}
```

* **Reference File:** `lorcanito-full-src-code/packages/lorcana/lorcana-engine/src/types/domain-events.ts`
* **Line Range:** `Lines 260-310`
* **Logic Context:**
```typescript
export interface PutCardUnderPayload {
  playerId: PlayerId;
  cardId: CardInstanceId;
  targetId: CardInstanceId;
}

export interface LorcanaDomainEventMap {
  cardsDrawn: CardsDrawnPayload;
  cardPlayed: CardPlayedPayload;
  putCardUnder: PutCardUnderPayload;
}
```

### 5. Acceptance Check(s)

Run:
```bash
python3 -m pytest tests/test_engine_trigger_pipeline.py -q
python3 -m pytest tests/test_trigger_projection.py -q
python3 -m pytest tests/test_trigger_blocker_report.py -q
python3 -m pytest -q
git diff --check
```

Expected:

```text
banish-in-challenge triggers fire during challenge banish.
leave-play triggers match banish, banish-in-challenge, return-to-hand, and ink events.
put-card-under triggers can be buffered from the real stack/under-card route.
Importer/report event support does not claim unsupported runtime events.
Full test suite passes.
```

### 6. Final Response Requirements

Report:

1. Files changed.
2. Trigger events added.
3. Runtime event emission routes added.
4. Projection/report event support changed.
5. Exact tests added.
6. Exact commands run and results.
