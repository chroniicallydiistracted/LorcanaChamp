# TECHNICAL IMPLEMENTATION BRIEF 6 - Report Truthfulness And Projector Regression

Goal:
Update trigger projection and blocker reporting only after Briefs 1-5 have real runtime support, then prove the reports became more accurate.

Read `docs/agent_work/microfix_11/MICROFIX_11_SHARED_RULES.md` before starting.

Do not change runtime behavior in this brief except for small defects exposed by report tests. Do not remove `create-replacement-effect` or effect-kind `or` blockers unless those systems were actually implemented and tested.

---

### 1. Current Missing Or Incorrect Code

* **File Path:** `lorcana_bot/importers/lorcanito_source_mapper.py`
* **Line Range:** `SUPPORTED_TRIGGER_EVENTS`, `SUPPORTED_CONDITION_KINDS`, `BLOCKED_CONDITION_KINDS`, `_project_trigger_effect()`, `_project_trigger_condition()`
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

* **File Path:** `lorcana_bot/decks/trigger_blocker_report.py`
* **Line Range:** `SUPPORTED_TRIGGER_ON_VALUES`, `SUPPORTED_TRIGGER_ENGINE_EFFECT_KINDS`, `RESOLUTION_REQUIREMENT_KINDS`
* **Snippet:**
```python
RESOLUTION_REQUIREMENT_KINDS = frozenset({
    "amount",
    "target",
    "multi_target",
    "discard_choice",
    "choice",
    "optional",
    "scry_ordering",
})
```

Current gaps:

```text
Report/projector support lists lag behind runtime for some already implemented systems.
Some unsupported requirement kinds are counted as blockers even after runtime can resolve them.
Projection may claim less or more support than runtime actually has.
```

### 2. Expected Code (The Solution)

* **Target State:**
```text
1. Importer SUPPORTED_TRIGGER_EVENTS exactly matches runtime-supported trigger events from Briefs 1-5.

2. Importer SUPPORTED_CONDITION_KINDS includes only condition kinds implemented in condition_evaluator.py.

3. BLOCKED_CONDITION_KINDS no longer contains conditions implemented by Brief 3.

4. trigger_blocker_report treats amount and scry_ordering as blockers only when their specific source-card shapes remain unsupported.

5. trigger_blocker_report supports on-filter values and object filters implemented in Brief 2.

6. Running blocker reports shows reduced blockers for:
   unsupported_trigger_resolution_requirement:amount
   unsupported_trigger_resolution_requirement:scry_ordering
   unsupported_trigger_event:banish-in-challenge
   unsupported_trigger_event:put-card-under
   unsupported_trigger_event:draw
   unsupported_trigger_event:leave-play
   unsupported_trigger_condition:has-card-under
   unsupported_trigger_condition:turn-metric
   unsupported_trigger_on:CHARACTERS_HERE
   unsupported_trigger_on:complex_filter:filters
```

### 3. Fixes Needed

* **Action:** `REVISE`
* **Delta Description:** Align projector support constants to real runtime support.
* **Delta Description:** Align blocker report support constants to real runtime support.
* **Delta Description:** Add regression tests with representative Lorcanito trigger definitions from the report examples.
* **Delta Description:** Regenerate or inspect report output and record remaining blockers honestly.

### 4. Lorcanito Source Reference (The Authority)

* **Reference File:** `lorcanito-full-src-code/packages/lorcana/lorcana-engine/src/triggered-abilities/index.ts`
* **Line Range:** `Lines 1503-1521 and 1876-1890`
* **Logic Context:**
```typescript
const triggerEvents = [
  trigger.event,
  ...(Array.isArray(trigger.events) ? trigger.events : []),
].flatMap(expandTriggerEvent);

if (!triggerEvents.includes(normalized.event)) {
  return false;
}
```

* **Reference File:** `lorcanito-full-src-code/packages/lorcana/lorcana-engine/src/rules/condition-evaluator.ts`
* **Line Range:** `Lines 28-86`
* **Logic Context:**
```typescript
export const CONDITION_VARIANT_TYPES = [
  "has-card-under",
  "turn-metric",
  "put-card-under-any-this-turn",
  "put-card-under-self-this-turn",
  "trigger-subject-had-card-under",
];
```

### 5. Acceptance Check(s)

Run:
```bash
python3 -m pytest tests/test_trigger_projection.py -q
python3 -m pytest tests/test_trigger_blocker_report.py -q
python3 -m pytest tests/test_engine_trigger_pipeline.py -q
python3 -m pytest -q
python3 scripts/report_trigger_blockers.py --print-summary
git diff --check
```

Expected:

```text
Projection tests prove each newly claimed event/condition/filter maps into executable Python trigger definitions.
Blocker report tests prove Microfix 11 blockers decrease for supported shapes.
create-replacement-effect and or remain reported if still unsupported.
Full test suite passes.
```

### 6. Final Response Requirements

Report:

1. Files changed.
2. Projector support constants changed.
3. Blocker report logic changed.
4. Before/after blocker counts for Microfix 11 target blockers.
5. Remaining blockers intentionally left for later Microfixes.
6. Exact commands run and results.
