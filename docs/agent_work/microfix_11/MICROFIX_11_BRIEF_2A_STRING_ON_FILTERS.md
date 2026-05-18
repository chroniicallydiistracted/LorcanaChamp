# TECHNICAL IMPLEMENTATION BRIEF 2A - String Trigger On Filters

Read `docs/agent_work/microfix_11/MICROFIX_11_SHARED_RULES.md` first.

Goal:
Implement exact Lorcanito string `on` filter matching in runtime trigger matching. No object filters in this brief.

---

## Allowed Files

You may edit only:

```text
lorcana_bot/triggers.py
tests/test_trigger_state.py
tests/test_engine_trigger_pipeline.py
```

Do not edit projector or report files.

---

## Exact Required Runtime Changes

Modify only:

```text
lorcana_bot/triggers.py::_on_filter_matches_string()
lorcana_bot/triggers.py::SUPPORTED_ON_VALUES
```

Implement these string filters exactly:

```text
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
```

Unknown string filters must return `False`.

`CHARACTERS_HERE` and `CHARACTER_HERE` must match only when:

```text
pending.subject_card_id is a character
and the subject card location_instance_id equals candidate.source_instance_id
```

If `pending.event_snapshot["subjectAtLocationId"]` or `pending.event_snapshot["subject_at_location_id"]` is present, prefer that value over live `location_instance_id`.

`YOUR_SONGS` must match an action card whose action subtype is `song`.

`YOUR_CHARACTERS_OR_LOCATIONS_WITH_CARD_UNDER` must match controlled character/location subjects that have at least one card in `cards_under`.

---

## Exact Required Tests

Add these tests:

```text
tests/test_trigger_state.py::test_unknown_string_on_filter_fails_closed
tests/test_trigger_state.py::test_characters_here_matches_subject_at_source_location
tests/test_trigger_state.py::test_characters_here_does_not_match_character_elsewhere
tests/test_trigger_state.py::test_your_items_matches_controlled_item_subject
tests/test_trigger_state.py::test_your_songs_matches_controlled_song_action_subject
tests/test_trigger_state.py::test_your_characters_or_locations_with_card_under_matches_stack_source
```

Do not weaken existing tests by changing expected behavior unrelated to this brief.

---

## Lorcanito Source Reference

```text
lorcanito-full-src-code/packages/lorcana/lorcana-engine/src/triggered-abilities/index.ts
subjectMatches() string switch for SELF, YOUR_CHARACTERS, YOUR_ITEMS, YOUR_LOCATIONS, YOUR_ACTIONS, YOUR_SONGS, CHARACTERS_HERE
```

---

## Acceptance Checks

Run:

```bash
python3 -m pytest tests/test_trigger_state.py tests/test_engine_trigger_pipeline.py -q
python3 -m pytest -q
git diff --check
```

---

## Final Response Requirements

Report filters implemented, support-list entries changed, exact tests added, command results, and five yes/no self-audit answers.
