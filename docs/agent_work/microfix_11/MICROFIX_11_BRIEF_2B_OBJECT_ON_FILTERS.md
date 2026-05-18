# TECHNICAL IMPLEMENTATION BRIEF 2B - Object Trigger On Filters

Read `docs/agent_work/microfix_11/MICROFIX_11_SHARED_RULES.md` first.

Goal:
Implement exact object `on` filter matching and `filters[]` runtime behavior. No projection/report updates in this brief.

---

## Allowed Files

You may edit only:

```text
lorcana_bot/triggers.py
tests/test_trigger_state.py
```

Do not edit projector or report files.

---

## Exact Required Runtime Changes

Modify:

```text
lorcana_bot/triggers.py::_on_filter_matches_object()
```

Implement these object keys:

```text
controller: "you" | "opponent" | "any"
owner: "you" | "opponent" | "any"
cardType
cardTypes
classification
classifications
name
hasKeyword
excludeSelf
filters
```

Card type rules:

```text
"character" matches CardDef.card_type == "character"
"item" matches CardDef.card_type == "item"
"location" matches CardDef.card_type == "location"
"action" matches CardDef.card_type == "action"
"song" matches CardDef.card_type == "action" and action subtype == "song"
```

Classification rules:

```text
Use CardDef.subtypes first.
Also check CardDef.raw_lorcanito_source["classifications"] if present.
Do not check keywords as classifications unless the same value appears in subtypes/classifications.
Comparison is case-insensitive.
```

Implement these `filters[]` entries:

```python
{"type": "ink-type", "inkType": "steel"}
{"type": "damaged"}
{"type": "exerted"}
{"type": "ready"}
{"type": "has-keyword", "keyword": "Evasive"}
{"type": "has-classification", "classification": "Princess"}
{"type": "at-location", "location": "source"}
```

Unknown object keys or unknown filter types must return `False`.

---

## Exact Required Tests

Add these tests:

```text
tests/test_trigger_state.py::test_object_on_filter_exclude_self_blocks_source
tests/test_trigger_state.py::test_object_on_filter_controller_you_matches_controlled_subject
tests/test_trigger_state.py::test_object_on_filter_controller_opponent_matches_opposing_subject
tests/test_trigger_state.py::test_object_on_filter_card_type_song_matches_song_action
tests/test_trigger_state.py::test_object_on_filter_classification_uses_subtypes
tests/test_trigger_state.py::test_object_on_filter_ink_type_matches_subject_ink
tests/test_trigger_state.py::test_object_on_filter_damaged_exerted_ready_keywords
tests/test_trigger_state.py::test_object_on_filter_at_location_source_matches
tests/test_trigger_state.py::test_object_on_filter_unknown_filter_type_fails_closed
```

---

## Lorcanito Source Reference

```text
lorcanito-full-src-code/packages/lorcana/lorcana-engine/src/triggered-abilities/index.ts
queryMatchesSubject()
cardMatchesFilter()
```

---

## Acceptance Checks

Run:

```bash
python3 -m pytest tests/test_trigger_state.py -q
python3 -m pytest -q
git diff --check
```

---

## Final Response Requirements

Report object keys implemented, filters implemented, exact tests added, command results, and five yes/no self-audit answers.
