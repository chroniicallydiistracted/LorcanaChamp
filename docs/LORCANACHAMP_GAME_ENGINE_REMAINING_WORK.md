# LorcanaChamp Engine Parity Roadmap

**Audit date:** 2026-05-16  
**Audit target:** current LorcanaChamp workspace after Microfix 4 follow-up fixes  
**Reference authority:** `lorcanito-full-src-code/packages/lorcana` and `references/lorcana-simulator`  
**Goal:** migrate Lorcanito's rules, card logic, game state, and automation behavior into Python with enough 1:1 fidelity to support teacher-bot creation and LorcanaChamp ML training.

This document is the implementation roadmap. It intentionally distinguishes:

- `complete`: implemented through engine-path code and tests.
- `partial`: some code exists, but behavior is not Lorcanito-equivalent yet.
- `scaffold`: parser/helper code exists but is not safe to count as executable.
- `blocked`: missing runtime behavior needed by real decks or parity tests.

Do not mark a card, mechanic, deck, or training dataset as executable unless the move is legal-action visible, apply-action executable, event/state correct, automation-adaptable, and covered by engine-path tests.

---

## 0. Current Verification Snapshot

Commands run during this audit:

```bash
python3 -m pytest --collect-only
python3 -m pytest -q
python3 scripts/report_trigger_blockers.py --print-summary
python3 scripts/report_real_deck_mapping_coverage.py --resolved-deck-dir data/decks/resolved/real_core --out /tmp/real_deck_suite_mapping_coverage.json --print-summary
python3 scripts/report_lorcanito_source_mapping.py --source-json data/lorcanito_extracted/cards.normalized.json --out /tmp/lorcanito_mapping_coverage.json --print-summary
```

Observed test state:

- `516 tests collected`
- Full pytest suite passes.

Observed real-deck report state:

- `total decks: 12`
- `valid decks: 12`
- `fully executable decks: 0`
- recommended next milestone: `target_choice_prompts`

Top real-deck blockers by copies:

```text
338 unsupported_trigger
111 unsupported_trigger_not_projected
 92 unsupported_static_effect
 79 unsupported_choice
 52 unsupported_effect:scry
 49 unsupported_target:chosen
 48 unsupported_activated_ability
 47 unsupported_cost:ink
 30 keyword:SHIFT
 25 unsupported_effect:restriction
```

Trigger blocker report:

```text
Total trigger rows: 115
Projected trigger rows: 65
Blocked trigger rows: 50
Blocked trigger copies: 184
Broad unsupported_trigger copies: 0

Top blockers:
unsupported_trigger_resolution_requirement:amount: 99 copies, 14 unique, 11 decks
unsupported_trigger_event:banish-in-challenge: 16 copies, 3 unique, 2 decks
unsupported_trigger_event:put-card-under: 16 copies, 1 unique, 4 decks
unsupported_trigger_condition:has-card-under: 12 copies, 3 unique, 3 decks
unsupported_trigger_condition:turn-metric: 8 copies, 2 unique, 2 decks
unsupported_trigger_effect:create-replacement-effect: 8 copies, 1 unique, 2 decks
unsupported_trigger_event:draw: 8 copies, 1 unique, 2 decks
unsupported_trigger_event:leave-play: 7 copies, 1 unique, 2 decks
unsupported_trigger_on:CHARACTERS_HERE: 4 copies, 1 unique, 1 deck
unsupported_trigger_on:complex_filter:filters: 4 copies, 1 unique, 1 deck
```

Source mapping report:

```text
total cards: 2754
total abilities: 3445
fully structured cards: 2416
executable cards: 743
mapped-not-executable cards: 873
unsupported cards: 1138
```

Important interpretation: unit tests are green, but the engine is not yet suitable for real-deck ML training. Reports still show zero fully executable real decks and major trigger/static/choice blockers.

---

## 1. Lorcanito Source Authority Map

Use these files as implementation authority. Translate behavior and invariants; do not copy TypeScript syntax.

### Runtime State And Pending Resolution

```text
packages/lorcana/lorcana-engine/src/types/runtime-state.ts
packages/lorcana/lorcana-engine/src/runtime-moves/resolution/action-effects/pending-action-effects.ts
packages/lorcana/lorcana-engine/src/runtime-moves/resolution/action-effects/selection-context.ts
packages/lorcana/lorcana-engine/src/runtime-moves/resolution/action-effects/selection-state.ts
```

Key Lorcanito concepts to preserve:

- pending action effects have `kind`, `chooserId`, `effect`, `continuation`, `resolutionInput`, and optional `selectionContext`.
- `PendingActionResolutionInput` includes targets, slotted targets, amount, named card, optional resolution, choice index, destinations, event snapshots, and trigger context.
- pending effects resume by merging player input with stored resolution input, not by guessing from current board state.

### Action Resolution

```text
packages/lorcana/lorcana-engine/src/runtime-moves/resolution/action-effects/composed-effect-resolver.ts
packages/lorcana/lorcana-engine/src/runtime-moves/resolution/action-effects/types.ts
packages/lorcana/lorcana-engine/src/runtime-moves/resolution/action-effects/scry-effect.ts
packages/lorcana/lorcana-engine/src/runtime-moves/resolution/action-effects/search-deck-effect.ts
packages/lorcana/lorcana-engine/src/runtime-moves/resolution/action-effects/reveal-and-route-effect.ts
packages/lorcana/lorcana-engine/src/runtime-moves/resolution/action-effects/play-card-effect.ts
```

Key Lorcanito concepts to preserve:

- effect resolution is continuation-aware.
- target, amount, named-card, optional, and destination choices are resolution input.
- scry destinations are structured `destinations`, not just top/bottom helper values.
- private look/search information is projected differently for chooser and opponent.

### Events, Triggers, And Bag

```text
packages/lorcana/lorcana-engine/src/triggered-abilities/index.ts
packages/lorcana/lorcana-engine/src/runtime-moves/resolution/resolve-bag.ts
packages/lorcana/lorcana-engine/src/lorcana-engine-base.auto-resolve-bag.test.ts
```

Key Lorcanito concepts to preserve:

- event emission and trigger buffering are the engine boundary for most rule effects.
- event snapshots preserve source, subject, attacker, defender, zones, and dynamic context.
- trigger conditions are checked with current state plus event snapshot.
- bag effects can update resolution input and can suspend into pending effects.

### Movement, Damage, Stack, And Zones

```text
packages/lorcana/lorcana-engine/src/operations/damage.ts
packages/lorcana/lorcana-engine/src/operations/zones.ts
packages/lorcana/lorcana-engine/src/runtime-moves/state/shift-stack.ts
packages/lorcana/lorcana-engine/src/runtime-moves/state/lethal-damage-sweep.ts
packages/lorcana/lorcana-engine/src/zones/runtime-zone-config.ts
```

Key Lorcanito concepts to preserve:

- damage emits a damage-dealt event and target/source trigger events.
- zero damage suppresses damage event creation.
- cards under shifted cards are not publicly in play.
- top-card zone movement moves the shift stack.
- locations leaving play clear character-at-location metadata.

### Play Modes And Costs

```text
packages/lorcana/lorcana-engine/src/runtime-moves/moves/core/play-card.ts
packages/lorcana/lorcana-engine/src/runtime-moves/shared/execute-shift-play.ts
packages/lorcana/lorcana-engine/src/runtime-moves/rules/play-card-rules.ts
packages/lorcana/lorcana-engine/src/play-card-disabled-reason.ts
```

Key Lorcanito concepts to preserve:

- play-card input validates targets, amount, named card, optional choice, choice index, destinations, and cost mode.
- normal play, shift, sing, sing together, and free play are explicit cost modes.
- cost validation precedes cost payment.
- unsupported targets/effects/costs must block before mutation.

### Static, Replacement, Conditions, And Derived State

```text
packages/lorcana/lorcana-engine/src/rules/static-effect-registry.ts
packages/lorcana/lorcana-engine/src/runtime-moves/effects/replacement-effects.ts
packages/lorcana/lorcana-engine/src/runtime-moves/rules/static-effects-invalidation.ts
packages/lorcana/lorcana-engine/src/rules/condition-evaluator.ts
packages/lorcana/lorcana-engine/src/rules/condition-context.ts
packages/lorcana/lorcana-engine/src/rules/derived-state.ts
```

Key Lorcanito concepts to preserve:

- static/replacement effects are live only while their source is live in the correct zone.
- replacement effects must apply before final movement/damage results.
- conditions evaluate against current state and event-specific context.
- derived stats/keywords/costs are not copied into permanent card state unless the rule says so.

### Automation

```text
packages/lorcana/lorcana-engine/src/automation/actor-resolution.ts
packages/lorcana/lorcana-engine/src/automation/move-adapter.ts
packages/lorcana/lorcana-engine/src/automation/planner.ts
packages/lorcana/lorcana-engine/src/automation/types.ts
```

Key Lorcanito concepts to preserve:

- automation candidates are move requests with the same resolution input fields as user moves.
- resolve-bag and resolve-effect are first-class action families.
- private information must not leak into fair traces.

---

## 2. Current Python Migration State

### Complete Enough To Treat As Accepted

- Trigger event payload hydration for damage/lore snapshots.
- `PendingTriggeredEvent.damage_dealt` and `lore_gained` properties.
- Static and replacement source dataclass parsing.
- Eventful damage helper for effect damage and challenge damage.
- Zero final damage suppresses damage events.
- Microfix 4 pending `requirement_kind` routing:
  - `scry_ordering`
  - `search_selection`
  - `reveal_routing`
  - `named_card`
  - `destination`
- Normal `name_a_card` effects now create `named_card` pending effects.
- Special empty-effect pending requirements are visible to actor resolution.
- Automation candidate conversion now preserves special pending inputs.

### Partial Or Scaffolded

- `pending_effects.py` supports some scry/search/reveal helpers, but privacy, destination structure, continuation, eventfulness, and search filters are not Lorcanito-equivalent.
- `EffectResolver` supports many effect kinds, but many direct mutations bypass eventful helpers.
- `condition_evaluator.py` has many condition handlers, but report-critical conditions still fail or depend on missing turn metrics/cards-under state.
- `triggers.py` can buffer and match common triggers, but runtime trigger support is narrower than Lorcanito's trigger subject/filter model.
- `abilities.py` and `costs.py` can enumerate some activated abilities and costs, but ink/discard/banish costs still block many real cards.
- `play_modes.py` supports singing and shift paths, but Shift stack representation is not safe enough for 1:1 parity.
- `decks/*` reports useful blockers, but executable/scaffold classification still needs to be stricter.

### Blocked For 1:1 Migration

- No canonical eventful zone operation layer for all moves and effects.
- No safe `ZONE_UNDER` / stack zone invariant.
- No complete target selection service equivalent to Lorcanito targeting runtime.
- No amount-choice pending requirement.
- No discard-choice pending requirement.
- No general `resolutionInput` continuation model for sequences that suspend and resume.
- No full event snapshot and turn metric model for trigger conditions.
- No fully executable real deck.
- No parity harness that runs Lorcanito scenario expectations against Python.

---

## 3. Revised Development Order

The highest report recommendation is `target_choice_prompts`, but implementing target/amount prompts before eventful operations and zone invariants would create more scaffold. The revised order is:

1. Microfix 5: Eventful movement and zone operations.
2. Microfix 6: Shift stack and `ZONE_UNDER`.
3. Microfix 7: Static/replacement lifecycle hardening.
4. Microfix 8: EffectResolver mutation centralization.
5. Microfix 9: Pending resolution generalization: target, amount, discard, optional, opponent choice.
6. Microfix 10: Targeting service parity.
7. Microfix 11: Trigger event expansion and bag/pending interaction.
8. Microfix 12: Condition evaluator and turn metrics.
9. Microfix 13: Scry/search/reveal privacy and destination hardening.
10. Microfix 14: Play-card modes and cost safety.
11. Microfix 15: Report truthfulness and executable classification.
12. Microfix 16: Real-deck gauntlet unlock.
13. Microfix 17: Card logic expansion by report impact.
14. Microfix 18: Final parity harness.

---

# Microfix 5: Eventful Movement And Zone Operations

## Status

Blocked and highest priority.

## Problem

Many rule-significant paths still call `state.move_card()` or mutate zone lists/state fields directly. This bypasses canonical events, trigger buffering, static/replacement invalidation, shift-stack movement, and zone consistency checks.

Observed direct mutation examples:

```text
lorcana_bot/effects.py: state.move_card(...), direct lore/damage/exerted mutation
lorcana_bot/pending_effects.py: state.move_card(...), event_log.append(...)
lorcana_bot/costs.py: state.move_card(...), direct exertion
lorcana_bot/play_modes.py: state.move_card(...), direct shift stack list mutation
lorcana_bot/replacement_effects.py: state.move_card(...)
lorcana_bot/engine.py: direct move/exert/lore mutation in core actions
```

## Target

Add engine-owned operation helpers:

```python
GameEngine._move_card_eventful(...)
GameEngine._banish_eventful(...)
GameEngine._discard_eventful(...)
GameEngine._return_to_hand_eventful(...)
GameEngine._put_into_inkwell_eventful(...)
GameEngine._ready_eventful(...)
GameEngine._exert_eventful(...)
GameEngine._gain_lore_eventful(...)
GameEngine._lose_lore_eventful(...)
GameEngine._remove_damage_eventful(...)
```

Each helper must:

- validate source zone and destination zone.
- mutate state exactly once.
- emit the canonical `GameEvent`.
- call `emit_event()` when triggerable.
- include event payload: card id, owner/controller, from zone, to zone, challenge context where relevant.
- deregister static and replacement sources leaving play.
- preserve/clear temporary state according to Lorcanito behavior.
- route stack movement through stack-aware helpers after Microfix 6.

## Files

```text
lorcana_bot/engine.py
lorcana_bot/state.py
lorcana_bot/effects.py
lorcana_bot/pending_effects.py
lorcana_bot/costs.py
lorcana_bot/play_modes.py
lorcana_bot/replacement_effects.py
tests/test_engine_trigger_pipeline.py
tests/test_effects.py
tests/test_replacement_effects.py
tests/test_static_effects.py
tests/test_state_invariants.py
```

## Lorcanito Authority

```text
packages/lorcana/lorcana-engine/src/operations/damage.ts
packages/lorcana/lorcana-engine/src/operations/zones.ts
packages/lorcana/lorcana-engine/src/runtime-moves/state/shift-stack.ts
packages/lorcana/lorcana-engine/src/triggered-abilities/index.ts
```

## Acceptance

```bash
python3 -m pytest tests/test_engine_trigger_pipeline.py -q
python3 -m pytest tests/test_effects.py -q
python3 -m pytest tests/test_replacement_effects.py -q
python3 -m pytest tests/test_static_effects.py -q
python3 -m pytest tests/test_state_invariants.py -q
python3 -m pytest -q
```

## Required Tests

- discard emits `CARD_DISCARDED`.
- return-to-hand emits `CARD_RETURNED_TO_HAND`.
- banish emits `CHARACTER_BANISHED` or correct card-type banish event.
- ink emits `INKED`.
- ready emits `CARD_READIED`.
- exert emits `CARD_EXERTED`.
- draw emits `CARD_DRAWN`.
- movement includes `from_zone` and `to_zone`.
- static source leaving play deregisters.
- replacement source leaving play deregisters.
- effect-driven movement uses eventful helpers.
- cost-driven movement uses eventful helpers.
- pending search/reveal movement uses eventful helpers or explicitly records non-triggering private diagnostics.

---

# Microfix 6: Shift Stack And `ZONE_UNDER`

## Status

Blocked.

## Problem

Python shift currently stores cards under the shifted card but can leave the old card's `zone` as play while removing it from `player.play`. Lorcanito moves the old top out of public play and stores stack relationships in metadata.

## Target

Add:

```python
ZONE_UNDER = "under"
ShiftRules
get_shift_rules()
get_stacked_card_ids()
attach_shift_stack()
move_card_out_of_play_with_stack()
is_card_under()
is_publicly_in_play()
```

Required behavior:

- shifted target moves to `ZONE_UNDER`.
- target is removed from `player.play`.
- target has `stack_parent_id`.
- new top receives all previous cards under.
- cards under cannot quest, challenge, sing, be exerted for costs, or be selected by normal play-zone targeting.
- top leaving play moves all stacked cards to the destination in Lorcanito order.
- location leaving play clears location association on characters there.

## Files

```text
lorcana_bot/constants.py
lorcana_bot/state.py
lorcana_bot/play_modes.py
lorcana_bot/engine.py
lorcana_bot/effects.py
tests/test_shift.py
tests/test_state_invariants.py
```

## Lorcanito Authority

```text
packages/lorcana/lorcana-engine/src/runtime-moves/state/shift-stack.ts
packages/lorcana/lorcana-engine/src/runtime-moves/shared/execute-shift-play.ts
packages/lorcana/lorcana-engine/src/runtime-moves/rules/play-card-rules.ts
```

## Acceptance

```bash
python3 -m pytest tests/test_shift.py -q
python3 -m pytest tests/test_state_invariants.py -q
python3 -m pytest -q
```

## Required Tests

- same-name Shift works.
- classification Shift works.
- universal Shift works when source data allows it.
- unsupported non-ink Shift cost blocks before payment.
- shifted target moves to `ZONE_UNDER`.
- cards under are not legal quest/challenge/target/cost candidates.
- top leaving play moves full stack.
- stack movement preserves zone invariants.

---

# Microfix 7: Static And Replacement Lifecycle Hardening

## Status

Blocked by Microfix 5 and Microfix 6.

## Problem

Static and replacement parsers now preserve more source data, but lifecycle correctness depends on eventful zone movement and safe under-stack semantics.

## Target

- register static effects on valid permanent entry to play.
- register replacement/prevention effects on valid source entry.
- deregister on every leave-play route: banish, discard, return, ink, stack movement.
- prevent cards in `ZONE_UNDER` from providing active static or replacement effects.
- apply replacement effects before final event/mutation where Lorcanito does.

## Files

```text
lorcana_bot/static_effects.py
lorcana_bot/replacement_effects.py
lorcana_bot/engine.py
lorcana_bot/state.py
tests/test_static_effects.py
tests/test_replacement_effects.py
tests/test_engine_trigger_pipeline.py
```

## Lorcanito Authority

```text
packages/lorcana/lorcana-engine/src/rules/static-effect-registry.ts
packages/lorcana/lorcana-engine/src/runtime-moves/effects/replacement-effects.ts
packages/lorcana/lorcana-engine/src/runtime-moves/rules/static-effects-invalidation.ts
packages/lorcana/lorcana-engine/src/rules/derived-state.ts
```

## Acceptance

```bash
python3 -m pytest tests/test_static_effects.py -q
python3 -m pytest tests/test_replacement_effects.py -q
python3 -m pytest tests/test_engine_trigger_pipeline.py -q
python3 -m pytest -q
```

---

# Microfix 8: EffectResolver Mutation Centralization

## Status

Blocked by Microfix 5.

## Problem

`EffectResolver` still performs direct gameplay mutation. This creates false positives in tests and false negatives in trigger/replacement behavior.

## Target

Replace direct effect mutations with eventful helpers:

```python
self.engine._gain_lore_eventful(...)
self.engine._lose_lore_eventful(...)
self.engine._remove_damage_eventful(...)
self.engine._banish_eventful(...)
self.engine._discard_eventful(...)
self.engine._return_to_hand_eventful(...)
self.engine._ready_eventful(...)
self.engine._exert_eventful(...)
self.engine._move_card_eventful(...)
```

## Files

```text
lorcana_bot/effects.py
lorcana_bot/engine.py
tests/test_effects.py
tests/test_engine_trigger_pipeline.py
```

## Lorcanito Authority

```text
packages/lorcana/lorcana-engine/src/runtime-moves/resolution/action-effects/composed-effect-resolver.ts
packages/lorcana/lorcana-engine/src/runtime-moves/resolution/action-effects/*.ts
packages/lorcana/lorcana-engine/src/operations/damage.ts
packages/lorcana/lorcana-engine/src/operations/zones.ts
```

## Acceptance

```bash
python3 -m pytest tests/test_effects.py -q
python3 -m pytest tests/test_engine_trigger_pipeline.py -q
python3 -m pytest -q
```

---

# Microfix 9: Pending Resolution Generalization

## Status

Partial. Microfix 4 is complete for special requirements, but general Lorcanito pending resolution is not complete.

## Problem

Reports show `unsupported_trigger_resolution_requirement:amount` as the highest trigger blocker. Python also lacks full pending target, amount, discard, multi-target, optional-with-no-target, and opponent-choice behavior.

## Target

Implement pending requirement kinds:

```text
amount
target
multi_target
discard_choice
choice
optional
opponent_choice
enter_play_exerted
```

Required behavior:

- `legal_actions()` enumerates only legal resolution inputs.
- `_apply_resolve_pending_effect()` writes to `resolution_input`.
- bag entries that suspend into pending effects are removed or resumed correctly.
- target legality uses the targeting service from Microfix 10.
- automation candidates round-trip exactly to engine legal actions.

## Files

```text
lorcana_bot/pending_effects.py
lorcana_bot/engine.py
lorcana_bot/effects.py
lorcana_bot/automation/candidate_enumerator.py
lorcana_bot/automation/move_adapter.py
tests/test_pending_effects.py
tests/test_automation_pending_effects.py
```

## Lorcanito Authority

```text
packages/lorcana/lorcana-engine/src/types/runtime-state.ts
packages/lorcana/lorcana-engine/src/runtime-moves/resolution/action-effects/pending-action-effects.ts
packages/lorcana/lorcana-engine/src/runtime-moves/resolution/action-effects/selection-context.ts
packages/lorcana/lorcana-engine/src/runtime-moves/resolution/action-effects/selection-state.ts
```

## Acceptance

```bash
python3 -m pytest tests/test_pending_effects.py -q
python3 -m pytest tests/test_automation_pending_effects.py -q
python3 scripts/report_trigger_blockers.py --print-summary
python3 -m pytest -q
```

Required report movement:

- `unsupported_trigger_resolution_requirement:amount` must decrease.
- `unsupported_choice` must decrease only when engine-path tests prove support.

---

# Microfix 10: Targeting Service Parity

## Status

Blocked.

## Problem

Target support is split across simplified helpers. Lorcanito uses target DSL normalization, target availability, slotted target selection, filter evaluation, ward/cannot-be-targeted, and current/effect/context target sets.

## Target

Add a Python targeting service that supports:

- card/player target distinction.
- chosen, all, up-to-N, each-player, self/controller/opponent aliases.
- min/max target counts.
- damaged/exerted/type/classification/keyword/ink filters.
- Ward and cannot-be-targeted rules.
- location-associated targets.
- slotted targets for multi-step effects.
- current targets and context targets for chained effects.

## Files

```text
lorcana_bot/targeting.py
lorcana_bot/pending_effects.py
lorcana_bot/effects.py
lorcana_bot/triggers.py
lorcana_bot/card_logic/targets.py
tests/test_targeting.py
tests/test_pending_effects.py
tests/test_engine_trigger_pipeline.py
```

## Lorcanito Authority

```text
packages/lorcana/lorcana-engine/src/targeting/targeting-service.ts
packages/lorcana/lorcana-engine/src/targeting/runtime/target-resolver.ts
packages/lorcana/lorcana-engine/src/targeting/runtime/target-availability.ts
packages/lorcana/lorcana-engine/src/targeting/slotted-targets.ts
```

## Acceptance

```bash
python3 -m pytest tests/test_targeting.py -q
python3 -m pytest tests/test_pending_effects.py -q
python3 -m pytest -q
```

---

# Microfix 11: Trigger Event Expansion And Bag/Pending Interaction

## Status

Partial.

## Problem

Trigger projection reports are narrower than Lorcanito. Current major blockers include draw, leave-play, banish-in-challenge, put-card-under, `CHARACTERS_HERE`, and complex filters.

## Target

Implement runtime support only when the engine can truthfully emit and match the event:

```text
draw
leave-play
banish-in-challenge
put-card-under
sing
be-chosen
support
CHARACTERS_HERE
filter cardType/action/song/character/item/location
filter controller you/opponent
filter excludeSelf
filter inkType
```

Bag/pending behavior:

- bag entry can suspend into pending effect.
- pending resolution can update bag resolution input.
- completed pending resolution removes matching bag item.
- trigger conditions recheck at resolution time.

## Files

```text
lorcana_bot/triggers.py
lorcana_bot/engine.py
lorcana_bot/pending_effects.py
lorcana_bot/importers/lorcanito_source_mapper.py
lorcana_bot/decks/trigger_blocker_report.py
tests/test_trigger_projection.py
tests/test_trigger_state.py
tests/test_engine_trigger_pipeline.py
tests/test_trigger_blocker_report.py
```

## Lorcanito Authority

```text
packages/lorcana/lorcana-engine/src/triggered-abilities/index.ts
packages/lorcana/lorcana-engine/src/runtime-moves/resolution/resolve-bag.ts
packages/lorcana/lorcana-engine/src/lorcana-engine-base.auto-resolve-bag.test.ts
```

## Acceptance

```bash
python3 scripts/report_trigger_blockers.py --print-summary
python3 -m pytest tests/test_trigger_state.py tests/test_trigger_projection.py tests/test_trigger_blocker_report.py -q
python3 -m pytest -q
```

---

# Microfix 12: Condition Evaluator And Turn Metrics

## Status

Partial.

## Problem

Report-critical condition types are still unsupported or unreliable:

```text
has-card-under
turn-metric
target-query
trigger-subject-had-card-under
put-card-under-self-this-turn
banished-in-challenge-this-turn
used-shift
```

## Target

Add turn metrics and event snapshot condition context:

- damaged this turn.
- banished in challenge this turn.
- put card under this turn.
- played using Shift.
- named/revealed/discarded/returned context.
- target-query against the Microfix 10 targeting service.

## Files

```text
lorcana_bot/condition_evaluator.py
lorcana_bot/state.py
lorcana_bot/engine.py
lorcana_bot/triggers.py
tests/test_condition_evaluator.py
tests/test_engine_trigger_pipeline.py
```

## Lorcanito Authority

```text
packages/lorcana/lorcana-engine/src/rules/condition-evaluator.ts
packages/lorcana/lorcana-engine/src/rules/condition-context.ts
packages/lorcana/lorcana-engine/src/runtime-moves/state/turn-metrics.ts
```

## Acceptance

```bash
python3 -m pytest tests/test_condition_evaluator.py -q
python3 -m pytest tests/test_engine_trigger_pipeline.py -q
python3 -m pytest -q
```

---

# Microfix 13: Scry/Search/Reveal Privacy And Routing

## Status

Partial.

## Problem

Helpers exist, but Lorcanito's scry/search/reveal behavior is richer:

- scry uses structured destination selections.
- private reveal windows must not leak to opponent/fair traces.
- search filters must match source data.
- reveal-and-route depends on named-card and route conditions.
- movement must be eventful where rule-visible.

## Target

- represent scry resolution as structured destinations internally, while keeping Python top/bottom convenience actions if desired.
- filter search candidates by source effect data.
- support reveal-and-route routes/fallback/side effects.
- separate private diagnostics from triggerable public events.
- redact private candidate ids in fair training traces.

## Files

```text
lorcana_bot/pending_effects.py
lorcana_bot/effects.py
lorcana_bot/engine.py
lorcana_bot/automation/decision_trace.py
scripts/export_decision_traces.py
tests/test_scry_search_reveal.py
tests/test_training_export.py
```

## Lorcanito Authority

```text
packages/lorcana/lorcana-engine/src/runtime-moves/resolution/action-effects/scry-effect.ts
packages/lorcana/lorcana-engine/src/runtime-moves/resolution/action-effects/search-deck-effect.ts
packages/lorcana/lorcana-engine/src/runtime-moves/resolution/action-effects/reveal-and-route-effect.ts
packages/lorcana/lorcana-engine/src/runtime-moves/resolution/action-effects/reveal-top-card-effect.ts
```

## Acceptance

```bash
python3 -m pytest tests/test_scry_search_reveal.py -q
python3 -m pytest tests/test_training_export.py -q
python3 -m pytest -q
```

---

# Microfix 14: Play Modes, Activated Abilities, And Cost Safety

## Status

Partial.

## Problem

Real-deck report blockers include `unsupported_cost:ink`, `keyword:SHIFT`, and `unsupported_activated_ability`. Python cost execution still has random-discard fallback paths and incomplete cost-mode support.

## Target

- normalize Lorcanito effect kinds through shared mapping.
- validate all costs before any payment.
- support ink costs for activated abilities.
- support chosen discard/banish/exert costs via pending cost selection.
- support Singer and Sing Together exactly enough for real-deck source data.
- support Shift target rules and cost modes from Microfix 6.
- block unsupported effects before costs are paid.

## Files

```text
lorcana_bot/abilities.py
lorcana_bot/costs.py
lorcana_bot/play_modes.py
lorcana_bot/card_logic/effect_utils.py
tests/test_activated_abilities_execution.py
tests/test_ability_costs.py
tests/test_shift.py
```

## Lorcanito Authority

```text
packages/lorcana/lorcana-engine/src/runtime-moves/moves/core/play-card.ts
packages/lorcana/lorcana-engine/src/runtime-moves/rules/play-card-rules.ts
packages/lorcana/lorcana-engine/src/runtime-moves/shared/execute-shift-play.ts
packages/lorcana/lorcana-engine/src/play-card-disabled-reason.ts
```

## Acceptance

```bash
python3 -m pytest tests/test_activated_abilities_execution.py -q
python3 -m pytest tests/test_ability_costs.py -q
python3 -m pytest tests/test_shift.py -q
python3 -m pytest -q
```

---

# Microfix 15: Report Truthfulness And Executable Classification

## Status

Blocked.

## Problem

Reports must not count a mechanic as executable because parser projection or helper scaffolding exists. Current real-deck reports still show broad blockers and zero fully executable decks.

## Target

Reports classify every card/mechanic as:

```text
executable
projected_but_requires_pending_input
scaffold_only
source_preserved
unsupported
```

Executable requires:

- effect/ability parser projection.
- legal-action path when input is required.
- apply-action path.
- event/state correctness.
- automation candidate adaptation where bots must act.
- engine-path test coverage.

## Files

```text
lorcana_bot/decks/trigger_blocker_report.py
lorcana_bot/decks/deck_mapping_report.py
lorcana_bot/decks/deck_resolver.py
scripts/report_trigger_blockers.py
scripts/report_real_deck_mapping_coverage.py
tests/test_trigger_blocker_report.py
tests/test_real_deck_mapping_coverage.py
```

## Acceptance

```bash
python3 scripts/report_trigger_blockers.py --print-summary
python3 scripts/report_real_deck_mapping_coverage.py --resolved-deck-dir data/decks/resolved/real_core --out data/decks/reports/real_deck_suite_mapping_coverage.json --print-summary
python3 -m pytest tests/test_trigger_blocker_report.py tests/test_real_deck_mapping_coverage.py -q
python3 -m pytest -q
```

---

# Microfix 16: Real-Deck Gauntlet Unlock

## Status

Blocked by Microfix 15 and zero fully executable decks.

## Target

- run only decks truthfully classified as fully executable.
- produce a separate strength-valid-but-not-fully-executable report.
- fail loudly on illegal action, deadlock, private leak, or unsupported decision.

## Files

```text
scripts/run_real_deck_gauntlet.py
scripts/report_real_deck_mapping_coverage.py
lorcana_bot/decks/*
data/decks/reports/*
tests/test_evaluation.py
```

## Acceptance

```bash
python3 scripts/report_real_deck_mapping_coverage.py --resolved-deck-dir data/decks/resolved/real_core --out data/decks/reports/real_deck_suite_mapping_coverage.json --print-summary
python3 scripts/run_real_deck_gauntlet.py --resolved-deck-dir data/decks/resolved/real_core --strategy-a deck-aware-lore-race --strategy-b board-control --only-fully-executable --games-per-pair 2 --max-actions 300 --out data/decks/reports/real_deck_suite_gauntlet.json
python3 -m pytest tests/test_evaluation.py -q
python3 -m pytest -q
```

---

# Microfix 17: Card Logic Expansion By Report Impact

## Status

Ongoing after foundation fixes.

## Target

Convert preserved Lorcanito source logic into executable Python by report impact:

1. amount/target/discard/choice requirements.
2. trigger events and conditions.
3. static/replacement effects.
4. scry/search/reveal and name-a-card routing.
5. activated abilities and costs.
6. Shift, put-under, move-from-under.
7. restrictions and temporary abilities.
8. locations and location-specific targeting.

## Files

```text
lorcana_bot/importers/lorcanito_source_mapper.py
lorcana_bot/card_logic/*
lorcana_bot/effects.py
lorcana_bot/condition_evaluator.py
lorcana_bot/triggers.py
lorcana_bot/static_effects.py
lorcana_bot/replacement_effects.py
```

## Acceptance

```bash
python3 scripts/report_lorcanito_source_mapping.py --source-json data/lorcanito_extracted/cards.normalized.json --out data/lorcanito_extracted/mapping_coverage.json --print-summary
python3 scripts/report_trigger_blockers.py --print-summary
python3 scripts/report_real_deck_mapping_coverage.py --resolved-deck-dir data/decks/resolved/real_core --out data/decks/reports/real_deck_suite_mapping_coverage.json --print-summary
python3 -m pytest -q
```

Gate: never mark a card executable unless every gameplay-relevant ability on the card is executable or explicitly no-op by rule.

---

# Microfix 18: Final Engine Parity Harness

## Status

Blocked until foundation is stable.

## Target

Create deterministic parity scenarios based on Lorcanito test fixtures and card tests:

```text
tests/parity/test_damage_and_banish.py
tests/parity/test_pending_resolution.py
tests/parity/test_shift_stack.py
tests/parity/test_scry_search_reveal.py
tests/parity/test_static_replacement.py
tests/parity/test_trigger_bag.py
tests/parity/test_play_modes_and_costs.py
```

Each test must include:

- scenario name.
- Lorcanito reference path.
- initial state.
- action.
- expected zones/card state.
- expected events.
- expected pending/bag state.
- expected visibility/privacy.

## Acceptance

```bash
python3 -m pytest tests/parity -q
python3 -m pytest -q
```

---

## ML Training Gate

Do not begin teacher-bot training or ML self-play training until all are true:

1. At least 12 real decks resolve with no unresolved deck-list cards.
2. At least 4 real decks are truthfully fully executable.
3. Real-deck gauntlet completes games with no illegal moves.
4. No pending/bag deadlocks.
5. Decision traces contain no private deck/hand/look/search leaks.
6. Reports distinguish executable from scaffold-only.
7. Every supported pending requirement kind has legal-action and apply-action tests.
8. Every gameplay zone change uses eventful operation helpers.
9. Static/replacement sources deregister correctly on every leave-play route.
10. Shift stacks and cards-under are zone-safe.

Initial ML should use imitation/ranking from deterministic teacher bots before self-play.

---

## Repository Tracking Checklist

- [x] Microfix 4: Pending `requirement_kind` routing and immediate follow-up fixes.
- [ ] Microfix 5: Eventful movement and zone operations.
- [ ] Microfix 6: Shift stack and `ZONE_UNDER`.
- [ ] Microfix 7: Static/replacement lifecycle hardening.
- [ ] Microfix 8: EffectResolver mutation centralization.
- [ ] Microfix 9: Pending resolution generalization.
- [ ] Microfix 10: Targeting service parity.
- [ ] Microfix 11: Trigger event expansion and bag/pending interaction.
- [ ] Microfix 12: Condition evaluator and turn metrics.
- [ ] Microfix 13: Scry/search/reveal privacy and routing.
- [ ] Microfix 14: Play modes, activated abilities, and cost safety.
- [ ] Microfix 15: Report truthfulness and executable classification.
- [ ] Microfix 16: Real-deck gauntlet unlock.
- [ ] Microfix 17: Card logic expansion by report impact.
- [ ] Microfix 18: Final engine parity harness.

---

## Current Highest-Priority Next Action

Implement Microfix 5: eventful movement and zone operations.

Reason: the current top report recommendation is target-choice work, but target and pending choices depend on trustworthy event/state mutation. Without canonical movement/exert/ready/lore helpers, later target, trigger, condition, static, replacement, shift, and privacy work will continue to produce scaffold-only support instead of Lorcanito-equivalent execution.
