# LorcanaChamp Engine Completion Audit and Development Roadmap

**Audit target:** LorcanaChamp `main` branch after Microfix 3.1\
**Reference authority:** Lorcanito source tree under `lorcanito-full-src-code/`\
**Purpose:** Track remaining development needed to complete the Game Engine,
Game Logic, Card Logic, and Game State layers before reliable real-deck
execution and ML training.

---

## 0. Current Acceptance Baseline

The following work should be treated as accepted and not reopened unless later
tests prove a regression.

### Accepted fixes

| Area                                                                                | Status   |
| ----------------------------------------------------------------------------------- | -------- |
| Trigger event payload hydration                                                     | Accepted |
| `PendingTriggeredEvent.damage_dealt` / `lore_gained` normalized snapshot properties | Accepted |
| Static `SourceAbilityDef` parsing                                                   | Accepted |
| Replacement `SourceAbilityDef` parsing                                              | Accepted |
| Fake `GameEngine.__new__` removal from replacement damage                           | Accepted |
| `GameEngine._deal_damage_eventful()` introduced                                     | Accepted |
| Challenge damage routed through `_deal_damage_eventful()`                           | Accepted |
| Effect `deal_damage` routed through `_deal_damage_eventful()`                       | Accepted |
| Zero final damage suppresses `EVENT_DAMAGE_DEALT`                                   | Accepted |

### Current major warning

Microfix 4 has not yet been implemented in the audited code.
`pending_effects.py` contains scry/search/reveal helper scaffolding, but
`GameEngine.legal_actions()` and `GameEngine._apply_resolve_pending_effect()`
still do not dispatch by `requirement_kind`.

---

## 1. Current Architecture Snapshot

### 1.1 Engine

`GameEngine` currently handles setup, legal action generation, action
application, draw, inking, play, quest, challenge, bag resolution, pending
effects, activated abilities, static effects, replacement effects, song singing,
and shift. The top-level docstring is stale and still underdescribes newer
systems, so it should not be used as an accurate implementation contract.

**Important files**


lorcana_bot/engine.py
lorcana_bot/actions.py
lorcana_bot/constants.py
lorcana_bot/state.py


### 1.2 Effects

`EffectResolver` now correctly routes `deal_damage` through
`GameEngine._deal_damage_eventful()`, but many other mutating effects still
directly change state:


gain_lore
lose_lore
remove_damage
banish
discard
return_to_hand
ready
exert
put_card_in_hand
put_card_on_top
put_card_on_bottom
put_card_in_discard
reveal routing movement


These need to be moved behind engine-owned eventful mutation helpers.

**Important file**


lorcana_bot/effects.py


### 1.3 Trigger system

Trigger buffering is improved. Trigger matching still has intentionally narrow
`on` support:

SELF
YOU
CONTROLLER
OPPONENT
YOUR_CHARACTERS
YOUR_OTHER_CHARACTERS
OPPOSING_CHARACTERS
ANY_CHARACTER

Runtime matching does not yet fully support:

ANY_PLAYER in SUPPORTED_ON_VALUES
YOUR_ITEMS
ANY_ITEM
YOUR_LOCATIONS
ANY_LOCATION
YOUR_ACTIONS
YOUR_SONGS
CHARACTERS_HERE
CHARACTER_HERE
YOUR_CHARACTERS_OR_LOCATIONS
complex filters such as filters/inkType

**Important file**

lorcana_bot/triggers.py

### 1.4 Pending effects

`pending_effects.py` already contains dataclasses and helper functions for:

ScryRequirement
SearchRequirement
RevealRoutingRequirement
DeckOrderingRequirement
NamedCardRequirement
create_scry_pending_effect()
create_search_pending_effect()
create_reveal_routing_pending_effect()
resolve_scry_ordering()
resolve_search_selection()
resolve_reveal_routing()

But `GameEngine.legal_actions()` still emits generic pending-effect resolution
actions, and `_apply_resolve_pending_effect()` still resolves the current effect
generically instead of routing by `pe.raw["requirement_kind"]`.

**Important files**

lorcana_bot/pending_effects.py
lorcana_bot/engine.py
tests/test_pending_effects.py
tests/test_automation_pending_effects.py

### 1.5 Game state

`CardInstance` includes shift-stack fields:

cards_under
stack_parent_id
played_via_shift
played_cost_type

But there is no `ZONE_UNDER`. Shift targets remain `zone="play"` while being
removed from `player.play`, which creates unsafe mixed state.

**Important file**

lorcana_bot/state.py

### 1.6 Deck blockers

The current blocker reports still show trigger and pending-resolution blockers.
The latest summary reports:

blocked_trigger_copies: 184
blocked_trigger_rows: 50
projected_trigger_rows: 65
broad_unsupported_trigger_copies: 0

The highest-ranked generated recommendation is still:

target_choice_prompts

with:

copies_affected: 124
deck_presence: 11
unique_cards_affected: 20

---

## 2. Source-of-Truth Lorcanito Reference Map

Use these Lorcanito files as the authority when implementing the remaining work.
Do not copy TypeScript code directly; translate the architecture and rule
outcomes into Python.

### 2.1 Trigger and bag lifecycle

packages/lorcana/lorcana-engine/src/triggered-abilities/index.ts
packages/lorcana/lorcana-engine/src/runtime-moves/resolution/resolve-bag.ts
packages/lorcana/lorcana-engine/src/lorcana-engine-base.auto-resolve-bag.test.ts

Use for:

recordEvent
normalizeBufferedEvent
expandTriggerEvent
flushTriggeredEventsToBag
triggerMatchesEvent
subjectMatches
enqueueBagEffect
getNextBagResolver
buildTriggeredResolutionInput
condition recheck at resolution time
bag item removal

### 2.2 Pending effect resolution

packages/lorcana/lorcana-engine/src/runtime-moves/resolution/action-effects/pending-action-effects.ts
packages/lorcana/lorcana-engine/src/runtime-moves/resolution/action-effects/selection-context.ts
packages/lorcana/lorcana-engine/src/runtime-moves/resolution/action-effects/selection-state.ts
packages/lorcana/lorcana-engine/src/targeting/runtime/resolution-requirements.ts
packages/lorcana/lorcana-engine/src/targeting/runtime/target-resolver.ts
packages/lorcana/lorcana-engine/src/targeting/runtime/target-availability.ts
packages/lorcana/lorcana-engine/src/targeting/targeting-service.ts

Use for:

target choice
amount choice
named-card choice
destination choice
scry ordering
search selection
reveal routing
resolution input persistence
target legality
ward/cannot-be-targeted handling

### 2.3 Damage and movement

packages/lorcana/lorcana-engine/src/operations/damage.ts
packages/lorcana/lorcana-engine/src/core/runtime/zone-operations.ts
packages/lorcana/lorcana-engine/src/core/runtime/zone-registry.ts
packages/lorcana/lorcana-engine/src/operations/zones.ts
packages/lorcana/lorcana-engine/src/runtime-moves/state/lethal-damage-sweep.ts

Use for:

damage amount <= 0 suppression
resist
damage replacement/prevention
event emission
zone movement
leave-play handling
lethal damage sweep

### 2.4 Action effect resolution

packages/lorcana/lorcana-engine/src/runtime-moves/resolution/action-effect-resolver.ts
packages/lorcana/lorcana-engine/src/runtime-moves/resolution/action-effects/composed-effect-resolver.ts
packages/lorcana/lorcana-engine/src/runtime-moves/resolution/action-effects/types.ts
packages/lorcana/lorcana-engine/src/runtime-moves/resolution/action-effects/deal-damage-effect.ts
packages/lorcana/lorcana-engine/src/runtime-moves/resolution/action-effects/put-damage-effect.ts
packages/lorcana/lorcana-engine/src/runtime-moves/resolution/action-effects/draw-effect.ts
packages/lorcana/lorcana-engine/src/runtime-moves/resolution/action-effects/gain-lore-effect.ts
packages/lorcana/lorcana-engine/src/runtime-moves/resolution/action-effects/lose-lore-effect.ts
packages/lorcana/lorcana-engine/src/runtime-moves/resolution/action-effects/return-to-hand-effect.ts
packages/lorcana/lorcana-engine/src/runtime-moves/resolution/action-effects/banish-effect.ts
packages/lorcana/lorcana-engine/src/runtime-moves/resolution/action-effects/exert-effect.ts
packages/lorcana/lorcana-engine/src/runtime-moves/resolution/action-effects/ready-effect.ts
packages/lorcana/lorcana-engine/src/runtime-moves/resolution/action-effects/scry-effect.ts
packages/lorcana/lorcana-engine/src/runtime-moves/resolution/action-effects/search-deck-effect.ts
packages/lorcana/lorcana-engine/src/runtime-moves/resolution/action-effects/reveal-and-route-effect.ts
packages/lorcana/lorcana-engine/src/runtime-moves/resolution/action-effects/reveal-top-card-effect.ts
packages/lorcana/lorcana-engine/src/runtime-moves/resolution/action-effects/reveal-hand-effect.ts
packages/lorcana/lorcana-engine/src/runtime-moves/resolution/action-effects/put-under-effect.ts
packages/lorcana/lorcana-engine/src/runtime-moves/resolution/action-effects/move-cards-from-under-effect.ts

Use for:

effect kind dispatch
effect context
eventful mutations
composed sequence/choice/optional/conditional
scry/search/reveal/deck routing
card-under movement

### 2.5 Static, replacement, and condition logic

packages/lorcana/lorcana-engine/src/rules/static-effect-registry.ts
packages/lorcana/lorcana-engine/src/runtime-moves/effects/continuous-effects.ts
packages/lorcana/lorcana-engine/src/runtime-moves/effects/replacement-effects.ts
packages/lorcana/lorcana-engine/src/runtime-moves/rules/static-effects-invalidation.ts
packages/lorcana/lorcana-engine/src/rules/derived-state.ts
packages/lorcana/lorcana-engine/src/runtime-moves/rules/static-ability-utils.ts
packages/lorcana/lorcana-engine/src/rules/condition-evaluator.ts
packages/lorcana/lorcana-engine/src/rules/condition-context.ts

Use for:

continuous static registration
static invalidation
derived strength/willpower/lore/keywords/cost
replacement/prevention lifecycle
condition strictness
event snapshot condition context

### 2.6 Play-card modes

packages/lorcana/lorcana-engine/src/runtime-moves/moves/core/play-card.ts
packages/lorcana/lorcana-engine/src/runtime-moves/rules/play-card-rules.ts
packages/lorcana/lorcana-engine/src/runtime-moves/shared/execute-shift-play.ts
packages/lorcana/lorcana-engine/src/runtime-moves/state/shift-stack.ts

Use for:

normal play
singing songs
Singer threshold
Sing Together
Shift cost modes
Shift target rules
shift stack movement
cards under

---

## 3. Recommended Development Order

The remainder of development should be handled as microfixes in this order.

4. Pending requirement_kind routing
5. Eventful movement and zone operations
6. ShiftRules and ZONE_UNDER stack safety
7. EffectResolver mutation centralization
8. Activated ability effect-kind conversion and cost safety
9. Broader trigger projection and trigger on-values
10. Condition evaluator and turn metric expansion
11. Target/amount choice prompts
12. Static/replacement lifecycle hardening
13. Scry/search/reveal privacy and routing hardening
14. Game state invariants and zone registry checks
15. Report truthfulness and executable/scaffold classification
16. Real-deck gauntlet unlock
17. Full-card execution expansion

---

# Microfix 4 — Pending `requirement_kind` Routing

## Problem

Special pending requirements exist in `pending_effects.py`, but the engine still
treats pending effects generically.

Current issue:

legal_actions() does not enumerate concrete top_cards/bottom_cards, selected_card_id, destination, named_card actions.
_apply_resolve_pending_effect() does not dispatch by pe.raw["requirement_kind"].

## Target

Implement engine-path routing for:

scry_ordering
search_selection
reveal_routing
named_card
destination

## Files

lorcana_bot/pending_effects.py
lorcana_bot/engine.py
tests/test_pending_effects.py
tests/test_automation_pending_effects.py

## Acceptance

```bash
python3 -m pytest tests/test_pending_effects.py -q
python3 -m pytest tests/test_automation_pending_effects.py -q
python3 -m pytest -q
```

## Completion gate

The tests must prove special pending requirements resolve through:

GameEngine.legal_actions()
GameEngine.apply_action()

Helper-only tests are insufficient.

---

# Microfix 5 — Eventful Movement and Zone Operations

## Problem

Many gameplay paths still call `state.move_card()` directly. This bypasses event
emission, trigger buffering, static/replacement deregistration, and shift-stack
handling.

Examples:

EffectResolver.banish
EffectResolver.return_to_hand
EffectResolver.discard
EffectResolver.put_card_in_hand
EffectResolver.put_card_on_top
EffectResolver.put_card_on_bottom
EffectResolver.put_card_in_discard
costs._pay_banish_self
costs._pay_discard_cost
play_modes.execute_sing_song
play_modes.execute_shift_play
pending_effects.resolve_search_selection
pending_effects.resolve_reveal_routing

## Target

Add engine-owned helpers:

```python
GameEngine._move_card_eventful(...)
GameEngine._banish_eventful(...)
GameEngine._discard_eventful(...)
GameEngine._return_to_hand_eventful(...)
GameEngine._ready_eventful(...)
GameEngine._exert_eventful(...)
```

The helpers must:

determine from_zone/to_zone
move the card
emit canonical gameplay events
buffer triggers through emit_event()
deregister static effects when source leaves play
deregister replacement effects when source leaves play
move shift stacks when top card leaves play
preserve public/private visibility

## Lorcanito reference

core/runtime/zone-operations.ts
core/runtime/zone-registry.ts
operations/zones.ts
triggered-abilities/index.ts

## Acceptance

```bash
python3 -m pytest tests/test_engine_trigger_pipeline.py -q
python3 -m pytest tests/test_effects.py -q
python3 -m pytest tests/test_replacement_effects.py -q
python3 -m pytest tests/test_static_effects.py -q
python3 -m pytest -q
```

## Required tests

discard emits CARD_DISCARDED
return-to-hand emits CARD_RETURNED_TO_HAND
banish emits CHARACTER_BANISHED
ink emits INKED
ready emits CARD_READIED
exert emits CARD_EXERTED
leave-play deregisters static and replacement effects
effect-driven movement uses eventful helpers
cost-driven movement uses eventful helpers

---

# Microfix 6 — ShiftRules and `ZONE_UNDER` Stack Safety

## Problem

Shift currently stores target cards under shifted cards but leaves the target
`zone="play"` while removing it from `player.play`. This is unsafe because some
code may identify in-play cards by `inst.zone == ZONE_PLAY`.

Current limitation:

get_shift_info() returns int only.
shift target detection is same-name only.
no ShiftRules dataclass.
no ZONE_UNDER.
get_stacked_card_ids() follows only the first cards_under chain.

## Target

Add:

```python
ZONE_UNDER = "under"
ShiftRules
get_shift_rules()
```

Shift target modes:

name
classification
universal

Shift stack behavior:

target.zone = ZONE_UNDER
target.stack_parent_id = shifted_card_id
shifted.cards_under includes target and previous under-stack
cards under are not questable
cards under are not challengeable
cards under are not normal targets
top leaving play moves full stack

## Files

lorcana_bot/constants.py
lorcana_bot/state.py
lorcana_bot/play_modes.py
lorcana_bot/engine.py
lorcana_bot/effects.py
tests/test_shift.py
tests/test_engine_trigger_pipeline.py

## Lorcanito reference

runtime-moves/shared/execute-shift-play.ts
runtime-moves/state/shift-stack.ts
runtime-moves/rules/play-card-rules.ts

## Acceptance

```bash
python3 -m pytest tests/test_shift.py -q
python3 -m pytest tests/test_engine_trigger_pipeline.py -q
python3 -m pytest -q
```

## Required tests

same-name Shift target works
universal Shift target works
classification Shift target works
unsupported non-ink Shift cost blocks
target moves to ZONE_UNDER
card under cannot quest
card under cannot challenge
card under cannot be normal chosen target
top leaving play moves all cards under

---

# Microfix 7 — EffectResolver Mutation Centralization

## Problem

`EffectResolver` still directly mutates state for many gameplay-relevant
effects.

Current direct mutations include:

state.players[player].lore += amount
state.players[player].lore = max(...)
state.cards[target].damage = max(...)
state.move_card(target, ZONE_DISCARD)
state.move_card(target, ZONE_HAND)
state.cards[target].exerted = False
state.cards[target].exerted = True

## Target

Route every gameplay mutation through engine helpers.

Replace direct logic with:

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

lorcana_bot/effects.py
lorcana_bot/engine.py
tests/test_effects.py
tests/test_engine_trigger_pipeline.py

## Lorcanito reference

runtime-moves/resolution/action-effect-resolver.ts
runtime-moves/resolution/action-effects/*.ts
operations/zones.ts
operations/damage.ts

## Acceptance

```bash
python3 -m pytest tests/test_effects.py -q
python3 -m pytest tests/test_engine_trigger_pipeline.py -q
python3 -m pytest -q
```

## Required tests

gain_lore emits gain-lore or corresponding gameplay event if triggerable
lose_lore emits loss event if triggerable
remove_damage emits remove-damage if triggerable
banish effect emits CHARACTER_BANISHED
return_to_hand effect emits CARD_RETURNED_TO_HAND
discard effect emits CARD_DISCARDED
ready effect emits CARD_READIED
exert effect emits CARD_EXERTED

---

# Microfix 8 — Activated Ability Effect-Kind Conversion and Cost Safety

## Problem

Activated ability conversion still passes source effect kinds directly into
`EffectDef`.

Current issue:

```python
EffectDef(kind=src_effect.kind, ...)
```

This fails for Lorcanito-style hyphenated effect kinds:

gain-lore
deal-damage
return-to-hand
cost-reduction
put-damage
remove-damage
gain-keyword
modify-stat

Cost problems remain:

_pay_discard_cost() can still randomly discard if called.
_pay_banish_self() directly calls state.move_card().

## Target

Use shared normalization:

```python
to_engine_effect_kind()
source_target_alias()
source_effect_amount()
source_effect_condition()
```

Cost safety:

non-random discard cost must raise unless pending cost choice exists
random discard only allowed if raw says random_discard
banish-self cost must route through eventful banish/move helper
cost validation must happen before any cost payment
unsupported effects must block ability legality before costs are paid

## Files

lorcana_bot/abilities.py
lorcana_bot/costs.py
lorcana_bot/card_logic/effect_utils.py
tests/test_activated_abilities_execution.py
tests/test_ability_costs.py

## Lorcanito reference

runtime-moves/resolution/action-effects/types.ts
runtime-moves/resolution/action-effect-resolver.ts
runtime-moves/moves/core/play-card.ts
runtime-moves/rules/play-card-rules.ts

## Acceptance

```bash
python3 -m pytest tests/test_activated_abilities_execution.py -q
python3 -m pytest tests/test_ability_costs.py -q
python3 -m pytest -q
```

## Required tests

gain-lore maps to gain_lore
deal-damage maps to deal_damage
return-to-hand maps to return_to_hand
cost-reduction maps to cost_reduction
put-damage maps intentionally to deal_damage or put_damage
unsupported effect blocks before cost payment
non-random discard payment raises
random discard only works when raw says random_discard
banish-self uses eventful path

---

# Microfix 9 — Broader Trigger Projection and Runtime Trigger Matching

## Problem

Reports show `broad_unsupported_trigger_copies = 0`, but runtime trigger support
remains narrower than projected support. Current blocker report still includes:

unsupported_trigger_event:banish-in-challenge
unsupported_trigger_event:put-card-under
unsupported_trigger_event:draw
unsupported_trigger_event:leave-play
unsupported_trigger_on:CHARACTERS_HERE
unsupported_trigger_on:complex_filter:filters

## Target

Expand trigger events and matching only when the engine can truthfully emit and
match them.

Add runtime support for:

draw
leave-play
banish-in-challenge
put-card-under
CHARACTERS_HERE
filter cardType=song/action/character
filter controller=you/opponent
filter excludeSelf
filters inkType where source data supports it

## Files

lorcana_bot/triggers.py
lorcana_bot/importers/lorcanito_source_mapper.py
lorcana_bot/decks/trigger_blocker_report.py
lorcana_bot/engine.py
lorcana_bot/play_modes.py
tests/test_trigger_projection.py
tests/test_trigger_state.py
tests/test_engine_trigger_pipeline.py
tests/test_trigger_blocker_report.py

## Lorcanito reference

triggered-abilities/index.ts
targeting/runtime/target-resolver.ts
targeting/runtime/target-availability.ts

## Acceptance

```bash
python3 scripts/report_trigger_blockers.py --print-summary
python3 scripts/report_real_deck_mapping_coverage.py --resolved-deck-dir data/decks/resolved/real_core --out data/decks/reports/real_deck_suite_mapping_coverage.json --print-summary
python3 -m pytest tests/test_trigger_state.py tests/test_trigger_projection.py tests/test_trigger_blocker_report.py -q
python3 -m pytest -q
```

## Required tests

draw event buffers and matches draw triggers
leave-play expands to banish/return/ink as appropriate
banish-in-challenge trigger matches only challenge banish
put-card-under emits and matches when Shift or effect puts card under
CHARACTERS_HERE matches location-associated characters
complex filters fail closed unless fully supported
report does not classify runtime-unsupported filters as executable

---

# Microfix 10 — Condition Evaluator and Turn Metrics

## Problem

Condition evaluator has many handlers, but the blocker report still identifies
condition-related gaps:

has-card-under
turn-metric
target-query

Also, some current handlers depend on state that is not yet reliably recorded,
such as cards under, turn metrics, and put-card-under events.

## Target

Implement and prove conditions using reliable state:

has-card-under
trigger-subject-had-card-under
put-card-under-any-this-turn
put-card-under-self-this-turn
banished-in-challenge-this-turn
turn-metric
target-query with real filters
revealed-card checks
discarded-card checks
returned-card checks
used-shift checks

## Files

lorcana_bot/condition_evaluator.py
lorcana_bot/effect_types.py
lorcana_bot/state.py
lorcana_bot/engine.py
tests/test_condition_evaluator.py
tests/test_engine_trigger_pipeline.py

## Lorcanito reference

rules/condition-evaluator.ts
rules/condition-context.ts
runtime-moves/state/turn-metrics.ts

## Acceptance

```bash
python3 -m pytest tests/test_condition_evaluator.py -q
python3 -m pytest tests/test_engine_trigger_pipeline.py -q
python3 -m pytest -q
```

## Required tests

has-card-under true/false
turn metric true/false
banished in challenge this turn true/false
put card under self this turn true/false
target-query with cardType/controller/classification
unsupported nested condition raises UnsupportedConditionError

---

# Microfix 11 — Target and Amount Choice Prompts

## Problem

The report recommends `target_choice_prompts` as the highest-priority next
engine milestone. The current blocker summary shows:

unsupported_trigger_resolution_requirement:amount = 99 copies
by_resolution_requirement.amount = 124 copies

This indicates many real deck triggers require player-selected amounts or
targets at resolution.

## Target

Implement pending requirements for:

amount choice
target choice
multi-target choice
discard choice
optional choice with no valid target
opponent choice

Do not fake choices. The engine must block and require
`ACTION_RESOLVE_PENDING_EFFECT`.

## Files

lorcana_bot/pending_effects.py
lorcana_bot/engine.py
lorcana_bot/effects.py
lorcana_bot/automation/candidate_enumerator.py
lorcana_bot/automation/candidate_validator.py
lorcana_bot/automation/move_adapter.py
tests/test_pending_effects.py
tests/test_automation_pending_effects.py

## Lorcanito reference

targeting/runtime/resolution-requirements.ts
targeting/runtime/target-resolver.ts
targeting/runtime/target-availability.ts
runtime-moves/resolution/action-effects/pending-action-effects.ts

## Acceptance

```bash
python3 -m pytest tests/test_pending_effects.py -q
python3 -m pytest tests/test_automation_pending_effects.py -q
python3 scripts/report_trigger_blockers.py --print-summary
python3 -m pytest -q
```

## Required tests

amount choice creates pending effect
legal_actions enumerates amount choices
apply_action resolves amount choice
target choice creates pending effect
ward/cannot-be-targeted enforced
multi-target selection validates min/max
opponent choice uses correct chooser
automation resolves mandatory pending choices
automation declines harmful optional choices when legal

---

# Microfix 12 — Static and Replacement Lifecycle Hardening

## Problem

Static and replacement parsers now support source dataclasses, but lifecycle
correctness still depends on eventful movement and zone mutation.

Risks:

static effects may remain registered after source leaves play through direct state.move_card()
replacement effects may remain registered after source leaves play
cards under source may not invalidate source effects correctly
source cards in ZONE_UNDER may still count as active

## Target

Register on permanent entry to play. Deregister on every leave-play route.

Must handle:

banish
return to hand
discard
ink
shift stack movement
card under movement
control changes if later implemented

## Files

lorcana_bot/static_effects.py
lorcana_bot/replacement_effects.py
lorcana_bot/engine.py
lorcana_bot/state.py
tests/test_static_effects.py
tests/test_replacement_effects.py
tests/test_engine_trigger_pipeline.py

## Lorcanito reference

rules/static-effect-registry.ts
runtime-moves/effects/replacement-effects.ts
runtime-moves/rules/static-effects-invalidation.ts
rules/derived-state.ts

## Acceptance

```bash
python3 -m pytest tests/test_static_effects.py -q
python3 -m pytest tests/test_replacement_effects.py -q
python3 -m pytest tests/test_engine_trigger_pipeline.py -q
python3 -m pytest -q
```

## Required tests

static source entering play registers effect
static source banished deregisters effect
static source returned to hand deregisters effect
replacement source banished deregisters effect
replacement source returned to hand deregisters effect
card under does not provide active static/replacement effects
stack leaving play deregisters all relevant active effects

---

# Microfix 13 — Scry/Search/Reveal Privacy and Routing Hardening

## Problem

Scry/search/reveal helpers exist, but some helper logic still directly appends
`GameEvent`, directly moves cards, and may expose private card IDs in logs.

Current risks:

resolve_scry_ordering appends SCRY_RESOLVED directly
resolve_search_selection appends SEARCH_RESOLVED directly
resolve_reveal_routing appends CARD_REVEALED directly
private candidate IDs may leak through traces/logs
search filtering is broad and not card-rule accurate
destination routing still uses state.move_card()

## Target

Use engine-owned event/log path or explicitly mark diagnostic events as
non-triggering.

Privacy rules:

private scry cards never appear in fair/public logs
private search candidates never appear in fair/public logs
revealed cards are public only when effect requires reveal
opponent hand/deck contents are redacted in fair traces

Search/routing rules:

filter candidates according to source effect
move selected card to correct destination eventfully
shuffle deterministically when required

## Files

lorcana_bot/pending_effects.py
lorcana_bot/effects.py
lorcana_bot/engine.py
lorcana_bot/automation/decision_trace.py
scripts/export_decision_traces.py
tests/test_scry_search_reveal.py
tests/test_training_export.py

## Lorcanito reference

runtime-moves/resolution/action-effects/scry-effect.ts
runtime-moves/resolution/action-effects/search-deck-effect.ts
runtime-moves/resolution/action-effects/reveal-and-route-effect.ts
runtime-moves/resolution/action-effects/reveal-top-card-effect.ts

## Acceptance

```bash
python3 -m pytest tests/test_scry_search_reveal.py -q
python3 -m pytest tests/test_training_export.py -q
python3 -m pytest -q
```

## Required tests

scry private event contains counts only
fair trace excludes card IDs for private scry
search candidates private
fair trace excludes private search candidate IDs
public reveal includes card identity
search filter selects only matching cards
selected search card moves to correct destination
shuffle is deterministic

---

# Microfix 14 — Game State Invariants and Zone Registry

## Problem

The current state model uses simple zone lists and `CardInstance.zone`. This is
workable but lacks invariant enforcement.

Risks:

card can be in zone="play" but not in player.play
card can appear in multiple zone lists
cards under can still look like in-play cards
discard/hand/deck movement can become inconsistent

## Target

Add invariant utilities:

```python
assert_zone_consistency(state)
is_publicly_in_play(state, instance_id)
is_card_under(state, instance_id)
zone_contains(state, zone, player, instance_id)
remove_from_all_zones(state, instance_id)
```

Longer-term, centralize state movement through `GameState.move_card()` plus
engine eventful wrapper.

## Files

lorcana_bot/state.py
lorcana_bot/engine.py
lorcana_bot/play_modes.py
tests/test_state_invariants.py

## Lorcanito reference

core/runtime/zone-registry.ts
core/runtime/zone-operations.ts

## Acceptance

```bash
python3 -m pytest tests/test_state_invariants.py -q
python3 -m pytest -q
```

## Required tests

card exists in exactly one public zone
ZONE_UNDER excluded from public play
move_card removes from old zone
move stack preserves invariant
failed movement does not duplicate card

---

# Microfix 15 — Report Truthfulness and Executable Classification

## Problem

Reports must not claim runtime support merely because parser projection exists
or helper code exists.

Current risk:

projected trigger rows can be counted separately from executable support
scaffold-only mechanics may appear supported
report and engine capability can drift

## Target

Reports must classify each mechanic as:

executable
projected_but_requires_pending_input
scaffold_only
source_preserved
unsupported

A mechanic is executable only if:

legal_actions path exists when needed
apply_action path exists
EffectResolver handler exists
event emission exists when triggerable
automation candidate path exists if bot must resolve it
tests cover engine path

## Files

lorcana_bot/decks/trigger_blocker_report.py
lorcana_bot/decks/deck_mapping_report.py
scripts/report_trigger_blockers.py
scripts/report_real_deck_mapping_coverage.py
tests/test_trigger_blocker_report.py
tests/test_real_deck_mapping_coverage.py

## Lorcanito reference

No direct runtime equivalent. This is a LorcanaChamp audit/reporting
requirement.

## Acceptance

```bash
python3 scripts/report_trigger_blockers.py --print-summary
python3 scripts/report_real_deck_mapping_coverage.py --resolved-deck-dir data/decks/resolved/real_core --out data/decks/reports/real_deck_suite_mapping_coverage.json --print-summary
python3 -m pytest tests/test_trigger_blocker_report.py tests/test_real_deck_mapping_coverage.py -q
python3 -m pytest -q
```

## Required tests


helper-only mechanics report scaffold_only
projected-but-pending mechanics report projected_but_requires_pending_input
engine-path tested mechanics report executable
real deck coverage and trigger blocker report agree


---

# Microfix 16 — Automation Resolution Completeness

## Problem

Automation can resolve basic pending/bag actions, but every newly added
requirement kind must be reflected in:


candidate enumeration
candidate validation
move adaptation
strategy scoring
decision trace
fair-log redaction


## Target

For every supported pending requirement, automation must produce legal
candidates only from `engine.legal_actions()` and adapt them back into `Action`.

Requirement kinds:


scry_ordering
search_selection
reveal_routing
named_card
destination
amount
target
multi-target
opponent-choice
discard-choice


## Files

lorcana_bot/automation/candidate_enumerator.py
lorcana_bot/automation/candidate_validator.py
lorcana_bot/automation/move_adapter.py
lorcana_bot/automation/strategies/lore_race_strategy.py
lorcana_bot/automation/decision_trace.py
tests/test_automation_pending_effects.py
tests/test_automation_move_adapter.py
tests/test_automation_validator.py
tests/test_training_export.py

## Acceptance

```bash
python3 -m pytest tests/test_automation_pending_effects.py -q
python3 -m pytest tests/test_automation_move_adapter.py -q
python3 -m pytest tests/test_automation_validator.py -q
python3 scripts/export_decision_traces.py --games 5 --out /tmp/decision_traces.jsonl
python3 -m pytest -q
```

## Required tests

candidate set exactly matches engine legal actions
scry/search/reveal pending candidates adapt correctly
amount choice candidates adapt correctly
target choice candidates adapt correctly
private info redacted in traces
no duplicate resolution candidates
resolution candidates ranked before normal play

---

# Microfix 17 — Real-Deck Gauntlet Unlock

## Problem

Real decks are resolved and valid, but previously no deck was fully executable.
After the above microfixes, the gauntlet should progressively unlock.

## Target

Run only decks whose cards are truly executable. Do not mark partially
implemented decks as fully executable.

## Files

scripts/run_real_deck_gauntlet.py
scripts/report_real_deck_mapping_coverage.py
lorcana_bot/decks/*
data/decks/reports/*
tests/test_evaluation.py

## Acceptance

```bash
python3 scripts/report_real_deck_mapping_coverage.py --resolved-deck-dir data/decks/resolved/real_core --out data/decks/reports/real_deck_suite_mapping_coverage.json --print-summary
python3 scripts/run_real_deck_gauntlet.py --resolved-deck-dir data/decks/resolved/real_core --strategy-a deck-aware-lore-race --strategy-b board-control --only-fully-executable --games-per-pair 2 --max-actions 300 --out data/decks/reports/real_deck_suite_gauntlet.json
python3 -m pytest tests/test_evaluation.py -q
python3 -m pytest -q
```

## Required report checks

no illegal moves
no blocked decisions
no private info leak
only fully executable decks run
strength-valid games counted separately
any non-executable deck lists exact blockers

---

# Microfix 18 — Full Card Logic Expansion

## Problem

The Python-native source model preserves many cards, but the executable
projection still covers only a subset of Lorcana mechanics.

## Target

Continue converting preserved Lorcanito source logic into Python-native
executable card logic by impact order from reports.

Mechanic categories:


triggered abilities
static abilities
replacement/prevention
activated abilities
actions/songs
items
locations
shift
singer/sing together
scry/search/reveal
put-card-under / move-from-under
amount choice
multi-target choice


## Files


lorcana_bot/importers/lorcanito_source_mapper.py
lorcana_bot/card_logic/*
lorcana_bot/effects.py
lorcana_bot/condition_evaluator.py
lorcana_bot/triggers.py
lorcana_bot/static_effects.py
lorcana_bot/replacement_effects.py


## Acceptance

```bash
python3 scripts/report_lorcanito_source_mapping.py --source-json data/lorcanito_extracted/cards.normalized.json --out data/lorcanito_extracted/mapping_coverage.json --print-summary
python3 scripts/report_trigger_blockers.py --print-summary
python3 scripts/report_real_deck_mapping_coverage.py --resolved-deck-dir data/decks/resolved/real_core --out data/decks/reports/real_deck_suite_mapping_coverage.json --print-summary
python3 -m pytest -q
```

## Gate

Never mark a card executable unless every card-relevant ability that can affect
gameplay is executable or explicitly no-op by rule.

---

# Microfix 19 — Final Engine Parity Harness

## Problem

Unit tests prove pieces. The engine needs integration-level parity harnesses.

## Target

Create deterministic scenario suites from Lorcanito-style rules tests:


damage/resist/prevention
banish/return/discard
draw triggers
quest triggers
challenge triggers
shift stack
scry/search/reveal
static modifiers
replacement effects
pending target/choice/amount


## Files


tests/parity/*
tests/test_engine_trigger_pipeline.py
tests/test_pending_effects.py
tests/test_scry_search_reveal.py
tests/test_shift.py


## Acceptance

```bash
python3 -m pytest tests/parity -q
python3 -m pytest -q
```

## Required format

Each parity test should include:


scenario name
Lorcanito reference file/path
initial state
action
expected state mutations
expected events
expected pending/bag state
expected visibility/privacy


---

# ML Training Gate

Do not start ML training until all of these are true:


1. At least 12 real decks resolve with 0 unresolved cards.
2. At least 4 real decks are fully executable.
3. Real-deck gauntlet runs complete games without illegal moves.
4. No pending/bag deadlocks.
5. Decision traces contain no private info leaks.
6. Reports distinguish executable from scaffold-only.
7. Engine-path tests cover every supported pending requirement kind.
8. Eventful mutations cover every gameplay zone change.


Initial ML should be imitation/ranking from teacher bots, not self-play-only.

---

# Repository Tracking Checklist

Use this as an issue checklist.


[ ] Microfix 4 — Pending requirement_kind routing
[ ] Microfix 5 — Eventful movement and zone operations
[ ] Microfix 6 — ShiftRules and ZONE_UNDER stack safety
[ ] Microfix 7 — EffectResolver mutation centralization
[ ] Microfix 8 — Activated ability conversion and cost safety
[ ] Microfix 9 — Broader trigger projection and trigger on-values
[ ] Microfix 10 — Condition evaluator and turn metrics
[ ] Microfix 11 — Target and amount choice prompts
[ ] Microfix 12 — Static/replacement lifecycle hardening
[ ] Microfix 13 — Scry/search/reveal privacy and routing hardening
[ ] Microfix 14 — Game state invariants and zone registry
[ ] Microfix 15 — Report truthfulness and executable classification
[ ] Microfix 16 — Automation resolution completeness
[ ] Microfix 17 — Real-deck gauntlet unlock
[ ] Microfix 18 — Full card logic expansion
[ ] Microfix 19 — Final engine parity harness


---

# Current Highest-Priority Next Action

Run and audit Microfix 4 first.

Reason:

Pending scry/search/reveal helpers already exist, but engine legal-action and apply-action routing are missing.
Reports identify target choice / pending resolution as the highest-impact blocker.
This is a prerequisite for target choice, amount choice, scry/search/reveal, and automation correctness.

After Microfix 4 is accepted, proceed to eventful movement before expanding more
card logic.
