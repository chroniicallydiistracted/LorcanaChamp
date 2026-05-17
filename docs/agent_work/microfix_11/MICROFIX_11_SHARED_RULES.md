# MICROFIX 11 SHARED RULES

Read this file before every Microfix 11 brief. Every implementation brief in this directory assumes these rules.

Goal:
Bring trigger projection and trigger runtime behavior closer to Lorcanito without hiding unsupported logic. Microfix 11 is about event matching, trigger subject filters, turn metadata conditions, dynamic amount/scry requirements, and bag/pending continuation.

Do not implement unrelated card text systems here. In particular, `create-replacement-effect` and effect-kind `or` remain out of scope unless a later brief explicitly expands scope.

---

## Source Of Truth

Use these Lorcanito files as authority:

```text
lorcanito-full-src-code/packages/lorcana/lorcana-engine/src/triggered-abilities/index.ts
lorcanito-full-src-code/packages/lorcana/lorcana-engine/src/types/domain-events.ts
lorcanito-full-src-code/packages/lorcana/lorcana-engine/src/runtime-moves/resolution/resolve-bag.ts
lorcanito-full-src-code/packages/lorcana/lorcana-engine/src/runtime-moves/resolution/action-effects/pending-action-effects.ts
lorcanito-full-src-code/packages/lorcana/lorcana-engine/src/runtime-moves/resolution/action-effects/amount-resolver.ts
lorcanito-full-src-code/packages/lorcana/lorcana-engine/src/rules/condition-evaluator.ts
lorcanito-full-src-code/packages/lorcana/lorcana-engine/src/runtime-moves/state/turn-metrics.ts
```

Use these Python surfaces as the current implementation:

```text
lorcana_bot/constants.py
lorcana_bot/triggers.py
lorcana_bot/engine.py
lorcana_bot/effects.py
lorcana_bot/pending_effects.py
lorcana_bot/condition_evaluator.py
lorcana_bot/importers/lorcanito_source_mapper.py
lorcana_bot/decks/trigger_blocker_report.py
tests/test_engine_trigger_pipeline.py
tests/test_trigger_projection.py
tests/test_pending_effects.py
tests/test_bag_resolution.py
tests/test_condition_evaluator.py
```

---

## Current Blocker Snapshot

Current trigger blocker reports show these high-impact blockers:

```text
unsupported_trigger_resolution_requirement:amount        99 copies
unsupported_trigger_event:banish-in-challenge            16 copies
unsupported_trigger_event:put-card-under                 16 copies
unsupported_trigger_condition:has-card-under             12 copies
unsupported_trigger_condition:turn-metric                 8 copies
unsupported_trigger_effect:create-replacement-effect      8 copies
unsupported_trigger_event:draw                            8 copies
unsupported_trigger_event:leave-play                      7 copies
unsupported_trigger_on:CHARACTERS_HERE                    4 copies
unsupported_trigger_on:complex_filter:filters             4 copies
unsupported_trigger_effect:or                             2 copies
```

Microfix 11 should reduce the trigger/event/condition/amount/scry blockers. Do not claim `create-replacement-effect` or `or` solved unless you actually implement and test those systems.

---

## Non-Negotiable Implementation Rules

1. Runtime comes before projection. Do not add an event, condition, target filter, or requirement to a `SUPPORTED_*` list unless the Python runtime can truthfully execute or evaluate it.
2. Do not make blocker reports pass by deleting blockers from the report taxonomy. A blocker is removed only after runtime and tests prove support.
3. Unknown trigger `on` values and object filters must fail closed. Do not let unsupported trigger filters match everything.
4. Preserve event snapshots. Trigger resolution must carry enough event payload into bag and pending resolution to evaluate dynamic amounts and conditions later.
5. Pending choices created from bag effects must keep bag ownership. Resolving a pending effect that came from a bag item must complete the matching bag item once the effect is actually resolved.
6. Use the targeting service and demo card database. Do not create tests with fake `card_id` values that are absent from the demo database.
7. Do not bypass lifecycle/eventful helpers in `engine.py`.
8. Every brief must run the acceptance checks listed in that brief plus `git diff --check`.

---

## Demo Card Test Rule

When tests need real card definitions, use the shared demo card database and constants from current tests. Do not invent integer card definition IDs such as `1001`.

Preferred pattern:

```python
from tests.helpers.demo_cards import DEMO_FEATURE_CARD_IDS

card_def_id = DEMO_FEATURE_CARD_IDS["character"]
```

If a helper name differs in the current repo, inspect `tests/test_demo_card_database.py` and reuse the repo's existing demo card helpers.

---

## Final Response Requirements For Every Brief

The implementing agent must report:

1. Files changed.
2. Exact runtime behavior added.
3. Exact projection/report behavior added, if any.
4. Exact tests added or revised.
5. Exact pytest commands run and results.
6. Any remaining blockers intentionally left for later Microfixes.
