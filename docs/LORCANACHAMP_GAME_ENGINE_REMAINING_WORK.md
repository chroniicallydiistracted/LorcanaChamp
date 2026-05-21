# LorcanaChamp Engine Parity Roadmap

**Audit date:** 2026-05-17
**Audit target:** current LorcanaChamp workspace after Microfix 10 targeting service parity
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

Observed baseline test state from the original roadmap audit:

- `516 tests collected`
- Full pytest suite passes.

Observed current test state after Microfix 10:

- Targeting, pending-effect, EffectResolver, and automation pending suites pass.
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

The report still recommends `target_choice_prompts` with 124 affected copies. The dominant blocker is now `unsupported_trigger_resolution_requirement:amount`; central runtime targeting is implemented, so the remaining report movement depends on trigger projection/importer/report classification work rather than another Microfix 10 targeting route.

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
- Microfix 5 eventful engine operation helpers exist for movement, banish, discard, return-to-hand, ink, ready, exert, lore, damage, and damage removal.
- Microfix 6 Shift stack and `ZONE_UNDER` behavior is implemented with stack-aware movement and public-play exclusions.
- Microfix 7 static/replacement lifecycle hardening is implemented for public permanent entry, leave-play deregistration, inactive under-stack sources, and replacement/prevention ordering on hardened routes.
- Microfix 8 `EffectResolver` mutation centralization is implemented with draw privacy hardening, core helper regression tests, zone-routing regression tests, and a direct-mutation audit guard.

### Partial Or Scaffolded

- `pending_effects.py` supports some scry/search/reveal helpers, but privacy, destination structure, continuation, eventfulness, and search filters are not Lorcanito-equivalent.
- `condition_evaluator.py` has many condition handlers, but report-critical conditions still fail or depend on missing turn metrics/cards-under state.
- `triggers.py` can buffer and match common triggers, but runtime trigger support is narrower than Lorcanito's trigger subject/filter model.
- `abilities.py` and `costs.py` can enumerate some activated abilities and costs, but ink/discard/banish costs still block many real cards.
- `play_modes.py` supports singing and Shift stack behavior, including `ZONE_UNDER`, but full play-mode parity still needs later cost/mode work.
- `decks/*` reports useful blockers, but executable/scaffold classification still needs to be stricter.

### Blocked For 1:1 Migration

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

Completed as the prerequisite for Microfix 7.

Remaining direct `EffectResolver` mutation cleanup is tracked separately in Microfix 8.

## Original Problem

Many rule-significant paths called `state.move_card()` or mutated zone lists/state fields directly. This bypassed canonical events, trigger buffering, static/replacement invalidation, shift-stack movement, and zone consistency checks.

Original direct mutation examples:

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

Completed.

Implemented and verified:

- `ZONE_UNDER` exists and is a real player zone.
- Shift target cards move to `ZONE_UNDER` and leave `player.play`.
- Shift stacks preserve `cards_under` / `stack_parent_id`.
- same-name, classification, and universal Shift have coverage.
- unsupported non-ink Shift costs block before payment.
- cards under a shifted card do not generate public play actions.
- top-card movement carries the full stack and preserves zone invariants.
- location departure clears character location association.

## Original Problem

Python shift stored cards under the shifted card but could leave the old card's `zone` as play while removing it from `player.play`. Lorcanito moves the old top out of public play and stores stack relationships in metadata.

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

Completed.

Verified state:

- Microfix 5 eventful operation boundary is available.
- Microfix 6 `ZONE_UNDER` and shift stack safety is complete.
- lifecycle registration exists for public permanents entering play.
- actions do not register lifecycle effects.
- `ZONE_UNDER` / stacked cards are excluded as active static and replacement sources.
- leave-play routes deregister static and replacement sources through engine-owned movement helpers.
- shifted stack movement deregisters all stack sources.
- replacement/prevention effects are evaluated before final mutation on hardened routes.
- technical implementation briefs for this work are in `docs/agent_work/`.

## Original Problem

Static and replacement parsers preserved more source data, but lifecycle correctness depended on eventful zone movement and safe under-stack semantics.

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

## Agent Work Briefs

```text
docs/agent_work/microfix_7/MICROFIX_7_BRIEF_1_REGISTER_LIFECYCLE_ON_ENTRY.md
docs/agent_work/microfix_7/MICROFIX_7_BRIEF_2_REGISTRY_ACTIVE_SOURCE_GUARDS.md
docs/agent_work/microfix_7/MICROFIX_7_BRIEF_3_DEREGISTER_ALL_LEAVE_PLAY_STACK_ROUTES.md
docs/agent_work/microfix_7/MICROFIX_7_BRIEF_4_REPLACEMENT_ORDER_AND_INACTIVE_SOURCES.md
docs/agent_work/microfix_7/MICROFIX_7_BRIEF_5_CONSOLIDATION_AND_AUDIT.md
```

---

# Microfix 8: EffectResolver Mutation Centralization

## Status

**Completed 2026-05-16.**

Verified state after audit:

- `rg` audit confirms no direct gameplay mutation in `lorcana_bot/effects.py` for: `state.move_card(`, `.lore +=`, `.lore -=`, `.damage +=`, `.damage -=`, `.exerted = True`, `.exerted = False`, `state.event_log.append(`, `GameEvent(`.
- Effect draw privacy is hardened: effect-driven draw uses `GameEngine.draw_cards(..., private=True)`.
- Core effect gameplay mutation routes through engine helper methods for: draw, gain_lore, lose_lore, deal_damage, remove_damage, banish, discard, return_to_hand, ready, exert, put_card_in_hand, put_card_on_top, put_card_on_bottom, put_card_in_discard.
- Deck/zone routing effects use `GameEngine._move_card_eventful` for every move.
- EffectResolver does not call `state.move_card` directly.
- EffectResolver does not directly mutate lore, damage, exerted state, or event_log.
- All targeted tests pass: `test_effects.py`, `test_engine_trigger_pipeline.py`, `test_shift.py`, `test_state_invariants.py`.
- Full pytest suite passes.
- Agent work briefs completed: BRIEFS 1-4 established the mutation guards, draw privacy, core helper regression, and zone routing regression coverage. This brief (BRIEF 5) is the consolidation audit.

## Problem

`EffectResolver` must not be allowed to silently reintroduce direct gameplay mutation. Direct resolver mutation creates false positives in unit tests and false negatives in trigger, replacement, lifecycle, and private-information behavior.

## Target

Keep or replace effect gameplay mutations with engine-owned helpers:

```python
self.engine.draw_cards(..., private=True)
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

Allowed resolver-local mutations must stay narrowly scoped to non-zone/non-lifecycle temporary state such as cost reductions, temporary keywords/modifiers, reveal flags, and deterministic shuffle metadata.

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

## Agent Work Briefs

```text
docs/agent_work/microfix_8/MICROFIX_8_BRIEF_1_EFFECT_RESOLVER_MUTATION_AUDIT_GUARD.md
docs/agent_work/microfix_8/MICROFIX_8_BRIEF_2_EFFECT_DRAW_PRIVACY_AND_EVENT_BOUNDARY.md
docs/agent_work/microfix_8/MICROFIX_8_BRIEF_3_CORE_EFFECT_HELPER_REGRESSION.md
docs/agent_work/microfix_8/MICROFIX_8_BRIEF_4_ZONE_ROUTING_EFFECT_REGRESSION.md
docs/agent_work/microfix_8/MICROFIX_8_BRIEF_5_CONSOLIDATION_AND_AUDIT.md
```

---

# Microfix 9: Pending Resolution Generalization

## Status

**Completed 2026-05-16.**

Verified state after audit:

- `PENDING_REQUIREMENT_KINDS` includes all 9 Microfix 9 requirement kinds: `amount`, `target`, `multi_target`, `discard_choice`, `choice`, `optional`, `opponent_choice`, `enter_play_exerted`, plus Microfix 4 special kinds.
- `SPECIAL_PENDING_REQUIREMENT_KINDS` groups all requirement kinds for `is_pending_effect_resolvable()` dispatch.
- `legal_actions()` in `engine.py` has complete coverage for all requirement kinds with proper dispatch: `optional`, `amount`, `target`, `multi_target`, `discard_choice`, `choice`, `opponent_choice`, `enter_play_exerted`, plus special kinds.
- `_apply_resolve_pending_effect()` in `engine.py` handles all requirement kinds and writes to `pe.raw["resolution_input"]` through dedicated resolver functions.
- All Microfix 9 resolver functions in `pending_effects.py` write to `resolution_input`: `resolve_amount_choice`, `resolve_target_selection`, `resolve_multi_target_selection`, `resolve_discard_choice`, `resolve_choice_index`, `resolve_optional_choice`, `resolve_enter_play_exerted_choice`.
- `discard_choice` suspends and resolves through pending effects via `create_discard_choice_pending_effect` and `_apply_resolve_pending_effect` dispatch.
- Bag-origin pending effects keep their bag entry until completion or decline (bag resolution via `ACTION_RESOLVE_BAG` with accept/decline).
- Automation candidates round-trip every pending choice field via `AutomatedActionCandidate` with all fields: `amount`, `choice_index`, `discard_card_ids`, `targets`, `enter_play_exerted`, `named_card`, `destination`.
- All targeted tests pass: `test_pending_effects.py` (65 tests), `test_automation_pending_effects.py` (19 tests), `test_engine_trigger_pipeline.py` (19 tests).
- Full pytest suite passes.
- `git diff --check` passes.
- `unsupported_trigger_resolution_requirement:amount` decreased from 99 to 79 copies (20 copy reduction from scry_ordering and proper amount requirement projection).

## Problem

Reports showed `unsupported_trigger_resolution_requirement:amount` as the highest trigger blocker. Python lacked full pending target, amount, discard, multi-target, optional-with-no-target, and opponent-choice behavior.

## Target (Achieved)

Implemented pending requirement kinds:

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

Achieved behavior:

- `legal_actions()` enumerates legal resolution inputs for each kind.
- `_apply_resolve_pending_effect()` writes to `resolution_input`.
- bag entries that suspend into pending effects are removed or resumed correctly.
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
git diff --check
```

Required report movement achieved:

- `unsupported_trigger_resolution_requirement:amount` decreased: 99 → 79 copies.
- `unsupported_trigger_resolution_requirement:scry_ordering` decreased: 20 copies.

## Agent Work Briefs

```text
docs/agent_work/microfix_9/MICROFIX_9_BRIEF_1_RESOLUTION_INPUT_FOUNDATION.md
docs/agent_work/microfix_9/MICROFIX_9_BRIEF_2_LEGAL_ACTION_ENUMERATION.md
docs/agent_work/microfix_9/MICROFIX_9_BRIEF_3_APPLY_RESOLUTION_AND_CONTEXT.md
docs/agent_work/microfix_9/MICROFIX_9_BRIEF_4_DISCARD_CHOICE_PENDING.md
docs/agent_work/microfix_9/MICROFIX_9_BRIEF_5_BAG_PENDING_CONTINUATION.md
docs/agent_work/microfix_9/MICROFIX_9_BRIEF_6_AUTOMATION_PENDING_ROUND_TRIP.md
docs/agent_work/microfix_9/MICROFIX_9_BRIEF_7_CONSOLIDATION_AND_REPORT_AUDIT.md
```

---

# Microfix 10: Targeting Service Parity

## Status

**Completed 2026-05-17.**

Briefs 1-8 have been completed in code:

```text
lorcana_bot/targeting.py
lorcana_bot/engine.py
lorcana_bot/pending_effects.py
lorcana_bot/effects.py
lorcana_bot/automation/candidates.py
lorcana_bot/automation/candidate_enumerator.py
lorcana_bot/automation/candidate_validator.py
lorcana_bot/automation/move_adapter.py
tests/test_targeting.py
tests/test_pending_effects.py
tests/test_effects.py
tests/test_automation_pending_effects.py
```

Target interpretation is now centralized through `lorcana_bot/targeting.py` for action legal-action enumeration, pending target resolution, EffectResolver target aliases, automation round-trip, current/context targets, and slotted target input preservation. The real-deck reports still recommend `target_choice_prompts`, but the top blocker is `unsupported_trigger_resolution_requirement:amount`; that remaining report movement belongs to trigger projection/importer/report classification work rather than another Microfix 10 runtime targeting route.

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
python3 -m pytest tests/test_effects.py -q
python3 -m pytest tests/test_automation_pending_effects.py -q
python3 scripts/report_trigger_blockers.py --print-summary
python3 scripts/report_real_deck_mapping_coverage.py --resolved-deck-dir data/decks/resolved/real_core --out /tmp/real_deck_suite_mapping_coverage.json --print-summary
python3 -m pytest -q
```

## Agent Work Briefs

```text
docs/agent_work/microfix_10/MICROFIX_10_SHARED_RULES.md
docs/agent_work/microfix_10/MICROFIX_10_BRIEF_1_TARGETING_FOUNDATION.md
docs/agent_work/microfix_10/MICROFIX_10_BRIEF_2_CANDIDATE_RESOLUTION_AND_FILTERS.md
docs/agent_work/microfix_10/MICROFIX_10_BRIEF_3_SELECTION_AVAILABILITY_AND_PROTECTIONS.md
docs/agent_work/microfix_10/MICROFIX_10_BRIEF_4_ENGINE_LEGAL_ACTION_INTEGRATION.md
docs/agent_work/microfix_10/MICROFIX_10_BRIEF_5_PENDING_TARGETING_INTEGRATION.md
docs/agent_work/microfix_10/MICROFIX_10_BRIEF_6_EFFECT_RESOLVER_TARGETING_INTEGRATION.md
docs/agent_work/microfix_10/MICROFIX_10_BRIEF_7_SLOTTED_TARGETS.md
docs/agent_work/microfix_10/MICROFIX_10_BRIEF_8_CONSOLIDATION_AND_REPORT_AUDIT.md
```

---

# Microfix 11: Trigger Event Expansion And Bag/Pending Interaction

## Status

**PASS as of 2026-05-21.**

Runtime, projection, report regeneration, and bag/pending continuation checks passed for the Microfix 11 scope. The regenerated trigger blocker report has:

```text
total_trigger_rows: 115
projected_trigger_rows: 110
blocked_trigger_rows: 5
blocked_trigger_copies: 14
```

Remaining trigger blockers:

```text
unsupported_trigger_effect:create-replacement-effect: 8 copies, 1 unique, 2 decks
unsupported_trigger_resolution_requirement:amount: 4 copies, 2 unique, 2 decks
unsupported_trigger_effect:or: 2 copies, 1 unique, 1 deck
```

Recommended next milestone from `data/decks/reports/next_engine_milestone_recommendation.json`:

```text
target_choice_prompts
confidence: medium
reason: Recommended based on copy/unique/deck impact scoring. Top blocker: unsupported_trigger_resolution_requirement:amount
```

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
- [x] Microfix 5: Eventful movement and zone operations.
- [x] Microfix 6: Shift stack and `ZONE_UNDER`.
- [x] Microfix 7: Static/replacement lifecycle hardening.
- [x] Microfix 8: EffectResolver mutation centralization.
- [x] Microfix 9: Pending resolution generalization.
- [x] Microfix 10: Targeting service parity.
- [x] Microfix 11: Trigger event expansion and bag/pending interaction.
- [ ] Microfix 12: Condition evaluator and turn metrics.
- [ ] Microfix 13: Scry/search/reveal privacy and routing.
- [ ] Microfix 14: Play modes, activated abilities, and cost safety.
- [ ] Microfix 15: Report truthfulness and executable classification.
- [ ] Microfix 16: Real-deck gauntlet unlock.
- [ ] Microfix 17: Card logic expansion by report impact.
- [ ] Microfix 18: Final engine parity harness.

---

## Current Highest-Priority Next Action

Implement the `target_choice_prompts` milestone for the remaining supported-by-impact trigger blockers.

Reason: Microfix 11 is complete for trigger event expansion and bag/pending interaction. The regenerated trigger blocker report now leaves 14 blocked trigger copies: `create-replacement-effect` (8 copies), unsupported `amount` resolution requirements (4 copies), and compound `or` effects (2 copies). The report recommendation is `target_choice_prompts` with medium confidence because the top blocker is `unsupported_trigger_resolution_requirement:amount`.

Tracking note: `_apply_resolve_pending_effect()` currently has a pure-input completion path for general pending requirements (`amount`, `target`, `multi_target`, `discard_choice`, `choice`, `optional`, `opponent_choice`, `enter_play_exerted`) that calls `complete_pending_effect()` and returns when `not pe.effects`. Future bag-origin amount/target/opponent-choice work must either prove bag-origin pending effects cannot reach that path, or route it through `_complete_bag_origin_pending_effect()` before completion.
