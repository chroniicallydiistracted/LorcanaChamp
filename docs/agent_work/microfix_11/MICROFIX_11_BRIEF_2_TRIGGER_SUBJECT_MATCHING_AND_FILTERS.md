# TECHNICAL IMPLEMENTATION BRIEF 2 - Trigger Subject Matching And Filters

Goal:
Implement Lorcanito-aligned trigger `on` subject matching and object filter support needed by current blocker reports.

Read `docs/agent_work/microfix_11/MICROFIX_11_SHARED_RULES.md` before starting.

This brief depends on Brief 1. Do not implement turn-metric conditions here. Do not widen projection support for a filter until runtime matching has a focused test.

---

### 1. Current Missing Or Incorrect Code

* **File Path:** `lorcana_bot/triggers.py`
* **Line Range:** `_on_filter_matches_string()` and `_on_filter_matches_object()`
* **Snippet:**
```python
def _on_filter_matches_string(trigger: TriggerDef, pending: PendingTriggeredEvent, state: GameState) -> bool:
    filt = str(trigger.on_filter)
    subject_id = pending.subject_id
    source_id = pending.source_id
    actor = pending.actor

    if filt == "SELF":
        return subject_id is not None and source_id is not None and subject_id == source_id
    if filt in {"YOU", "CONTROLLER"}:
        return actor == trigger.controller_id
    if filt == "OPPONENT":
        return actor is not None and actor != trigger.controller_id
    if filt == "ANY_PLAYER":
        return actor is not None
    if filt in {"YOUR_CHARACTERS", "YOUR_OTHER_CHARACTERS", "OPPOSING_CHARACTERS", "ANY_CHARACTER"}:
        ...
    return True
```

Current gaps:

```text
Unknown string filters currently match everything.
CHARACTERS_HERE / CHARACTER_HERE is unsupported.
YOUR_ITEMS, ANY_ITEM, YOUR_LOCATIONS, YOUR_ACTIONS, YOUR_SONGS, and location/card-under variants are incomplete.
Object on-filter support is missing filters[], excludeSelf, ink-type, song/action distinction, at-location, and keyword/classification behavior.
classification currently risks checking the wrong card definition fields.
```

### 2. Expected Code (The Solution)

* **Target State:**
```text
1. Unknown trigger on filters fail closed.

2. String on filters support at least:
   SELF
   YOU
   CONTROLLER
   OPPONENT
   ANY_PLAYER
   YOUR_CHARACTERS
   YOUR_OTHER_CHARACTERS
   OPPOSING_CHARACTERS
   OPPONENT_CHARACTERS
   ANY_CHARACTER
   YOUR_ITEMS
   ANY_ITEM
   YOUR_LOCATIONS
   YOUR_ACTIONS
   YOUR_SONGS
   CHARACTERS_HERE
   CHARACTER_HERE
   YOUR_CHARACTERS_OR_LOCATIONS
   YOUR_CHARACTERS_OR_LOCATIONS_WITH_CARD_UNDER

3. Object on filters support:
   controller: "you" | "opponent" | "any"
   owner: "you" | "opponent" | "any"
   cardType / cardTypes
   classification / classifications
   name
   hasKeyword
   excludeSelf
   shiftedOntoSelf when data is available
   filters: [...]

4. filters[] supports at least:
   {type: "ink-type", inkType: "..."}
   {type: "damaged"}
   {type: "exerted"}
   {type: "ready"}
   {type: "has-keyword", keyword: "..."}
   {type: "has-classification", classification: "..."}
   {type: "at-location", location: ...}

5. trigger_blocker_report no longer classifies the implemented filters as complex_filter blockers.
```

### 3. Fixes Needed

* **Action:** `REVISE / EXPAND`
* **Delta Description:** Replace default `return True` fallback for unknown trigger on filters with `False`.
* **Delta Description:** Expand string subject matching according to Lorcanito subject rules.
* **Delta Description:** Expand object filter matching with focused helpers for card type, controller, owner, classification, keyword, and filters list.
* **Delta Description:** Update trigger projection/report support only for filters implemented by runtime tests.

### 4. Lorcanito Source Reference (The Authority)

* **Reference File:** `lorcanito-full-src-code/packages/lorcana/lorcana-engine/src/triggered-abilities/index.ts`
* **Line Range:** `Lines 749-1120`
* **Logic Context:**
```typescript
if (query.excludeSelf && triggerSourceCardId && cardId === triggerSourceCardId) {
  return false;
}

if (query.controller === "you" && card.ownerId !== controller) {
  return false;
}

if (query.cardType && !cardMatchesType(card, query.cardType)) {
  return false;
}

if (query.filters?.length) {
  for (const filter of query.filters) {
    if (!cardMatchesFilter(card, filter)) {
      return false;
    }
  }
}

case "CHARACTERS_HERE":
case "CHARACTER_HERE": {
  return subjectAtLocationId === triggerSourceCardId;
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
Unknown on-filter values no longer match all events.
CHARACTERS_HERE matches only characters at the trigger source location.
Ink-type filters can match Pluto-style trigger subjects.
excludeSelf prevents source card from matching "your other" style object filters.
Report no longer flags implemented filters as unsupported complex_filter blockers.
Full test suite passes.
```

### 6. Final Response Requirements

Report:

1. Files changed.
2. String on filters implemented.
3. Object filter fields implemented.
4. filters[] variants implemented.
5. Tests added or revised.
6. Exact commands run and results.
