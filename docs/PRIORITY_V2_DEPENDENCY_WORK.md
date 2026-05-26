# 1. Normalize authoritative runtime identity: current player, turn owner, priority holder

**Current status:** mostly implemented, but must be made universal.

The new `turn_owner.py` correctly introduces `resolve_turn_owner_id`, `resolve_current_player_for_move`, and `require_current_player_for_move`. It resolves `turnOwnerId` before fallback actor and rejects non-current actors. 

**Still needed:**

Every move and resolver must use this shared resolver instead of reading `priority.holder` directly.

**Why this comes first:**

Everything else depends on correct actor identity. Lorcanito separates current turn player from temporary pending-choice priority. A pending chooser must not become eligible to play cards, quest, challenge, or take normal turn actions.

**Pass condition:**

```text
- No gameplay move uses priority.holder as the authoritative current player.
- Current turn player, active resolver, and pending chooser are distinct concepts everywhere.
- playCard, resolveEffect, resolveBag, quest, challenge, inkwell, pass turn, and future moves all use the shared resolver.
```

---

# 2. Remove local compatibility helpers and make shared systems authoritative

**Current status:** not complete.

`play.py` still carries local helper shapes such as `_pending_cost_reductions`, `_static_cost_delta`, `_effective_standard_cost`, local static restriction wrappers, and local target validation wrappers. 

**Still needed:**

Delete or collapse local compatibility helpers once shared systems exist:

```text
- cost math must live in derived_state.py
- static restrictions must live in static_ability_utils.py / StaticRegistry
- target legality must live in targeting runtime
- turn metrics must live in runtime_game/turn_metrics.py
- action-card lifecycle must live in action_card_resolver.py
```

**Why this comes early:**

Leaving duplicate local logic creates two engines: a “play.py engine” and a “real rules engine.” Lorcanito uses shared systems from `play-card.ts`, including targeting, derived state, registry cache, static ability utilities, turn metrics, pending effects, action resolver, triggered abilities, and win-condition recomputation. 

**Pass condition:**

```text
- play.py orchestrates, but does not own rules subsystems.
- No playCard-specific duplicate cost/static/target logic remains.
- Shared modules are the only source of truth.
```

---

# 3. Complete turn metric integration everywhere

**Current status:** helper exists; usage incomplete.

`runtime_game/turn_metrics.py` has correct v2-shaped helpers for card played, Shift played, discard exit, banished character, card put into discard, and cards-under tracking. 

**Still needed:**

Use these helpers consistently across:

```text
- playCard
- Shift lethal banish
- discard effects
- mill effects
- banish effects
- put-under effects
- action finalization
- alternative costs
```

**Why this comes before larger rules logic:**

Triggered abilities and conditions often depend on “this turn” state. If turn metrics are wrong, later static/trigger/effect logic will be wrong even if the individual move works.

**Pass condition:**

```text
- No move manually reconstructs TurnMetadata.
- Every effect that changes a tracked turn metric calls the shared helper.
- Metrics match Lorcanito event boundaries.
```

---

# 4. Complete move registry cache integration

**Current status:** cache exists; registry content incomplete.

`move_registry_cache.py` caches by match ID, `_stateID`, and `staticEffectsVersion`, which is the right direction. 

**Still needed:**

Make every static-dependent subsystem use `get_or_build_move_registry`:

```text
- playCard validation
- play-card-rules Singer threshold
- Shift effective willpower
- static ability utilities
- target filtering when derived values matter
- action effects that create or depend on static modifiers
```

**Why this comes before static logic:**

Lorcanito’s `playCard` imports and uses `getOrBuildMoveRegistry`; static materialization must be cached and shared, not rebuilt inconsistently. 

**Pass condition:**

```text
- StaticRegistry is not rebuilt ad hoc in moves.
- One registry instance is used for a single state/staticEffectsVersion.
- Any static-changing effect bumps staticEffectsVersion at the correct boundary.
```

---

# 5. Complete StaticRegistry materialization

**Current status:** partial.

The registry has many needed effect kinds, but it is not yet a full Lorcanito static-effect registry.

**Still needed:**

Implement full static materialization for:

```text
- cost-reduction
- cost-increase
- restriction
- card restriction
- player restriction
- enters-play-exerted
- cant-sing
- cant-play / cant-play-actions / cant-play-items / cant-play-characters
- self-play-condition
- conditional Shift
- gain-keyword Singer
- property-modification singer-threshold
- stat floors
- stat modifiers
- classification grants
- keyword loss
- ability suppression
- static source zones
- target-specific materialization
```

**Why this comes before playCard parity:**

`playCard` depends on the registry for restrictions, cost changes, Singer threshold, enters-play-exerted, and Shift legality. Lorcanito imports derived state, static ability utilities, and registry cache directly in `play-card.ts`. 

**Pass condition:**

```text
- StaticRegistry materializes the same active static effects Lorcanito would.
- Registry entries preserve source ID, controller, ability index, source zones, raw effect, payload, condition result, and target.
- Static materialization is proven by real-card integration tests.
```

---

# 6. Complete static ability utilities and condition context

**Current status:** partial.

`static_ability_utils.py` exposes the right functions, but condition evaluation is fragile. It attempts to build a query context from `state.cards`, which a `MatchState` does not own. 

**Still needed:**

Implement real Lorcanito-shaped static utilities:

```text
- evaluate_static_condition
- matches_static_ability_target
- has_static_card_restriction
- has_opponent_static_play_restriction
- get_static_property_modifier_total
- get_static_keyword_grant_value
```

These must use real `QueryService`, real target analysis, real actor/source/target context, and real registry entries.

**Why this comes before playCard and songs:**

Without correct static utilities, these cannot be trusted:

```text
- self-play-condition
- cant-play-actions
- cant-sing
- enters-play-exerted
- static Singer grants
- static singer-threshold modifiers
- conditional Shift
```

**Pass condition:**

```text
- Static conditions evaluate against runtime state exactly once, using correct actor/source/target context.
- No condition silently returns false because a query object was missing.
- Static target matching uses the real targeting runtime.
```

---

# 7. Complete derived cost system

**Current status:** mostly implemented, not fully integrated.

`derived_state.py` now includes `get_pending_cost_reductions`, `get_applied_cost_reductions`, `get_static_cost_increase_amount`, and `consume_applied_cost_reductions`. 

**Still needed:**

Finish integration and remove old play-local cost math.

Required behavior:

```text
- pending cost reductions
- static cost reductions
- static cost increases
- playMethod: standard / shift / either
- card type filters
- song subtype filters
- classification filters
- name filters
- expiration windows
- consume-on-use
- correct free-cost calculation from reduced effective cost
```

**Known bug:**

`playCard` still validates `free` using printed cost only. 

**Pass condition:**

```text
- standard cost = printed cost - applied reductions + static increases.
- free cost is legal only when effective reduced cost is zero.
- Shift cost uses Shift-specific reductions.
- consumed reductions are removed only after successful payment.
```

---

# 8. Complete play-card-rules parity

**Current status:** mostly foundational.

The file has ready ink, Shift parsing, Singer threshold, Sing Together, and basic cost handling, but it still depends on incomplete static/registry behavior.

**Still needed:**

Fully mirror Lorcanito helpers:

```text
- getAvailableInk
- spendInk
- validateBasicCost
- payBasicCost
- getShiftRules
- resolveShiftTargetCandidates
- getSingerThresholdForInstance
- getSingTogetherThreshold
- isSongCard
- isReadyAndNotDrying
```

Lorcanito imports all of these directly into `playCard`. 

**Pass condition:**

```text
- Ready inkwell only counts.
- Ink is spent in zone order.
- Shift parses keyword data before text fallback.
- discard-Shift is supported.
- Mimicry satisfies name-based Shift.
- Singer threshold includes printed cost, printed Singer, static Singer, temp Singer, static property modifiers, and continuous modifiers.
```

---

# 9. Complete play-from-under lifecycle

**Current status:** permission state exists; lifecycle is partial.

`playCard` validates limbo/under source permission, but broader lifecycle support still depends on effects and movement.

**Still needed:**

```text
- enable-play-from-under effect must create real permissions.
- put-under / move-cards-under must preserve stack/parent metadata.
- playCard must detach played-under cards exactly once.
- permission windows must expire correctly.
- wrong owner / wrong card type / wrong source item must reject.
```

**Why this matters:**

Lorcanito’s `playCard` treats hand and limbo-under-source-with-permission as the two legal source paths. 

**Pass condition:**

```text
- A real card can put a card under another card.
- A real permission allows playing the correct card type from under the correct source.
- All invalid permission cases reject before cost payment.
```

---

# 10. Complete win-condition recomputation

**Current status:** partial.

`win_condition_effects.py` exists and scans play-zone static abilities for `win-condition-modification`. 

**Still needed:**

```text
- Route through StaticRegistry.
- Evaluate conditions.
- Apply target/controller filters.
- Support all Lorcanito win-condition effect shapes.
- Recompute after entering/leaving play at exact Lorcanito boundaries.
```

Lorcanito calls `recomputeLoreToWin` after a card is moved to play. 

**Pass condition:**

```text
- G.loreToWin matches Lorcanito after any relevant static effect enters/leaves play.
- Default remains 20 when no modifier applies.
```

---

# 11. Complete full targeting runtime

**Current status:** not complete.

The new targeting package exists, but it is shallow. `target_analysis.py` collects explicit chosen targets, computes simple candidate sets, and validates IDs against those sets.  It does not implement the full Lorcanito targeting runtime.

**Still needed:**

```text
- full target DSL normalization
- candidate generation by owner/controller/zone/type/subtype/classification/keyword/cost/name/state
- target availability analysis
- forced target restrictions
- must-be-chosen-for-effects
- slotted targets
- selected-first
- previous target references
- currentTargets
- contextTargets
- trigger subject references
- duplicate target rules
- requireDifferentTargets
- target-selection continuation state
```

Lorcanito `playCard` imports target analysis, target availability, flattening, normalization, candidate resolution, player target resolution, and target validation directly. 

**Pass condition:**

```text
- Every selected target is validated by target analysis before mutation.
- No resolver trusts raw selected IDs.
- playCard, resolveEffect, resolveBag, and action effects all use the same target runtime.
```

---

# 12. Remove selected-target trust from action effects

**Current status:** not done correctly.

`action_effects.py` still immediately returns selected targets if present:

```python
selected = _selected_card_ids(resolution_input)
if selected:
    return selected
```



**Still needed:**

Every effect must validate selected targets through the targeting runtime and selection context.

**Why this matters:**

Even if `playCard.validate` rejects illegal targets, `resolveEffect`, `resolveBag`, and later continuation prompts can still pass illegal selected IDs unless the resolver validates them.

**Pass condition:**

```text
- No action effect applies to a selected target unless that target passed target analysis.
- This is enforced inside the effect resolver, not only at caller boundaries.
```

---

# 13. Complete be-chosen lifecycle

**Current status:** partial.

`be_chosen.py` emits `beChosen` for selected card/player targets and has a real-card test slice. 

**Still needed:**

```text
- exact Lorcanito event payload shape
- deferred resolveEffect be-chosen emission
- be-chosen for slotted targets
- player-target be-chosen parity
- eventSnapshot parity
- trigger candidate snapshot parity
```

Lorcanito `resolveEffect` imports `emitBeChosenEvents`, and `playCard`/action resolution depend on it. 

**Pass condition:**

```text
- Predetermined action targets emit be-chosen before effect mutation.
- Deferred targets emit be-chosen when chosen.
- be-chosen triggers enter bag exactly as Lorcanito would.
```

---

# 14. Complete triggered ability and bag event lifecycle

**Current status:** foundational, not full.

Triggered abilities, pending events, and bag items exist, but exact Lorcanito trigger/bag lifecycle is still incomplete.

**Still needed:**

```text
- exact cardPlayed payloads
- exact sing payloads
- exact exert payloads
- exact cardLeftDiscard payloads
- exact cardBanished payloads
- self-trigger filtering
- delayed/floating triggers
- trigger candidate snapshots
- bag ordering/resolver choice parity
- bag logs
- bag cancellation/fizzle/skipped outcomes
```

Lorcanito `playCard` depends on triggered events, pending bag checks, candidate snapshots, and bag flushing. 

**Pass condition:**

```text
- Every play/effect event that should enter the bag does.
- Every event that should not self-trigger is filtered.
- Bag order, resolver, and flush boundaries match Lorcanito.
```

---

# 15. Complete Shift stack and lethal GSC parity

**Current status:** partial.

`execute_shift_play.py` handles core stack, continuous retarget, inherited damage, effective willpower, lethal banish, banish event, metric, and bag flush. 

**Still needed:**

```text
- keywords-before-banish snapshot
- exact trigger candidate snapshot payload
- exact moveCardOutOfPlayWithStack behavior
- exact stack metadata clearing order
- playCard must pass enters_exerted into execute_shift_play
```

**Known gap:**

`playCard` calls `execute_shift_play` without `enters_exerted`. 

**Pass condition:**

```text
- Shift stack state matches Lorcanito before and after Shift.
- Lethal inherited damage immediately banishes the whole stack.
- Normal cardPlayed is suppressed when Shift GSC banishes immediately.
- Banish snapshot data matches Lorcanito.
```

---

# 16. Complete enter-play state logic

**Current status:** not complete.

`playCard.execute` still sets normal characters to `state="ready"` and non-characters to `state=None`. 

**Still needed:**

```text
- enters-play-exerted static restriction
- self enters-play-exerted restriction
- opponent static enters-play-exerted restriction
- Bodyguard may-enter-exerted option
- may-enter-exerted input validation
- pass enters_exerted into Shift
```

Lorcanito imports `hasBodyguard`, `hasMayEnterPlayExertedOption`, static restriction utilities, and move registry for this purpose. 

**Pass condition:**

```text
- Characters/items/locations enter ready or exerted exactly as Lorcanito would.
- Bodyguard/may-enter-exerted choices are validated and applied.
- Shift entry uses the same enters-exerted result.
```

---

# 17. Complete action-card resolver boundary

**Current status:** partial.

`action_card_resolver.py` emits be-chosen, iterates action abilities, checks conditions, calls `resolve_action_effect`, suspends to limbo, finalizes, and flushes triggers. 

**Still needed:**

```text
- dedicated action-condition evaluator
- exact eventSnapshot lifecycle
- recorded vanish target resolution
- Lorcanito logging/trace/fizzle boundaries
- exact condition context
- no direct fallback shortcuts
```

Lorcanito’s `resolveEffect` and action resolver import vanish resolution and selection context machinery. 

**Pass condition:**

```text
- Action cards resolve ability-by-ability exactly as Lorcanito.
- False conditions skip effects.
- Suspended actions move to limbo.
- Completed actions finalize through replacement-aware finalization.
- Vanish targets resolve at the same boundaries.
```

---

# 18. Complete pending action effect model

**Current status:** partial.

`ActionResolutionInput` and `PendingActionEffect` now contain many required fields: targets, slottedTargets, currentTargets, contextTargets, amount, choiceIndex, resolveOptional, enterPlayExerted, destinations, eventSnapshot, triggerContext, continuation, selectionContext, and allow-zero-target suspension. 

**Still needed:**

```text
- exact selectionContext types
- stagedSequence clone
- collectedTargets clone
- collectedTargetCounts clone
- previousTargetedCardIds clone
- revealedCardIds clone
- revealWindowIds clone
- triggerContext clone
- continuation merge/clear behavior
```

Lorcanito `resolveEffect` has explicit continuation cleanup for optional, target selection, destinations, revealed cards, and reveal windows. 

**Pass condition:**

```text
- Pending effects preserve all state needed to resume exactly.
- No mutation leaks between pending effect objects and resolution inputs.
- Continuation cleanup matches Lorcanito.
```

---

# 19. Complete resolveEffect parity

**Current status:** partial.

`resolve_pending.py` now uses `effectId` and `params`, rejects legacy top-level shape, checks chooser, validates basic pending kinds, and restores turn owner after completion. 

**Still needed:**

```text
- full target analysis validation
- full selectionContext validation
- slotted target validation
- staged sequence continuation
- scry destination validation
- optional decline rules
- choice/or option validation
- matching bag item cleanup in all cases
- vanish target resolution
- pending turn/challenge continuation
- exact priority restoration
```

Lorcanito `resolveEffect` imports selection context, selection state, target validation, scry validation, vanish resolution, bag cleanup, turn/challenge continuation, and turn-owner restoration. 

**Pass condition:**

```text
- resolveEffect can resume every Lorcanito pending kind.
- All params are validated by target/selection context.
- Completion finalizes actions, cleans bag linkage, flushes triggers, and restores priority exactly.
```

---

# 20. Complete resolveBag parity

**Current status:** partial.

`bag.py` validates bag ID, active resolver, direct discard chooser exception, conditional/choice branch, target analysis, partial input, resolution, bag removal, trigger flush, and priority restoration. 

**Still needed:**

```text
- full branch requirement analysis
- full direct chooser exception rules
- full selection context persistence
- full partial input advancement
- optional decline parity
- skipped/fizzled/cancelled outcome parity
- exact logging
- continuation into pending turn/challenge
- target validation through complete targeting runtime
```

**Pass condition:**

```text
- resolveBag behaves exactly like Lorcanito for every bag item kind.
- Conditional unreachable branches do not require targets.
- Partial input updates bag item state only when Lorcanito would pause.
- Priority and resolver flow match Lorcanito.
```

---

# 21. Complete action-effect dispatcher and dedicated handlers

**Current status:** broad but not full parity.

`action_effects.py` has many branches, but still routes several different effect types into generic handlers. For example, many movement effects route through `resolve_move_card_effect`, and reveal variants route through one reveal handler. 

`pay-cost` is still effectively a no-op. 

**Still needed:**

Dedicated Lorcanito-shaped handlers for:

```text
- pay-cost
- play-card
- search-deck
- reveal
- reveal-top-card
- reveal-until-match
- reveal-hand
- reveal-inkwell
- reveal-and-route
- scry
- move-to-location
- put-into-inkwell
- put-under
- put-on-top
- put-on-bottom
- return-from-discard
- return-random-from-inkwell
- move-cards-from-under
- create-triggered-ability
- create-replacement-effect
- property-modification
- support
- count
- for-each
- choice/or
- optional
- sequence
```

**Pass condition:**

```text
- No unrelated effect families share a generic shortcut when Lorcanito has dedicated behavior.
- Malformed or unsupported effects produce explicit unsupported evidence.
- Every supported effect is proven by real-card or normalized-card runtime tests.
```

---

# 22. Complete sequence, optional, choice, and staged selection engine

**Current status:** partial.

There is some `remainingEffects` replay, but not full staged sequence selection state.

**Still needed:**

```text
- shared eventSnapshot across sequence
- staged target collection
- collected target counts
- context target promotion
- current target clearing
- optional decision isolation
- choiceIndex validation
- auto-decline impossible optionals
- auto-resolve legal single-option or branches
- requireDifferentTargets across sequence
- “do as much as you can” skip rules
```

Lorcanito’s `resolveEffect` shows the continuation cleanup and context-target promotion logic that v2 must mirror. 

**Pass condition:**

```text
- Multi-step effects suspend and resume exactly.
- Later sequence steps see the right context targets.
- Optional/choice decisions do not leak into nested or later effects.
```

---

# 23. Complete reveal, scry, and hidden-information runtime

**Current status:** partial.

Current scry/reveal support is simplified. Scry moves cards by destination but does not fully model reveal windows and destination validation.  Reveal variants are collapsed into one handler. 

**Still needed:**

```text
- reveal windows
- revealedCardIds
- revealWindowIds
- private/public visibility
- scry destination validation
- deck-top/deck-bottom ordering
- reveal-and-route
- reveal-until-match
- search-deck
- hidden information logs
```

**Pass condition:**

```text
- Hidden information is revealed only to the correct players.
- Scry/reveal/search mutations exactly match Lorcanito.
- Event snapshots preserve revealed card/window IDs.
```

---

# 24. Complete playCard.validate parity

**Current status:** partial.

`playCard.validate` now has much of the right order: pending guard, current player, card input, definition, source, restrictions, cost, action params, action targets. 

**Still needed:**

```text
- build/fetch static registry before all static-dependent validation
- remove local static/cost shortcuts
- use full target analysis
- validate free from effective cost
- validate entersPlayExerted params
- validate Bodyguard/may-enter-exerted input
- validate action targets through complete targeting runtime
- ensure all play restrictions use static ability utilities
```

**Pass condition:**

```text
playCard.validate follows Lorcanito’s order and rejects every illegal play before mutation.
```

---

# 25. Complete playCard.available parity

**Current status:** not complete.

`available` still checks printed cost and raw Shift cost. 

**Still needed:**

```text
- pending/bag gates
- effective standard cost
- static cost increases
- static/temporary restrictions
- self-play-condition
- Shift reductions
- discard Shift availability
- alternative cost availability
- cant-sing checks
- Singer threshold
- Sing Together threshold
```

**Pass condition:**

```text
playCard.available returns true exactly when Lorcanito would enumerate playCard as available.
```

---

# 26. Complete playCard.execute parity

**Current status:** partial.

`playCard.execute` pays costs, moves card to play, recomputes lore-to-win, logs, records card played, emits cardPlayed/sing/exert events, resolves actions, handles Shift, and flushes triggers. 

**Still needed:**

```text
- effective free cost path
- full alternative cost side effects
- enters-play-exerted
- Bodyguard/may-enter-exerted
- pass enters_exerted into Shift
- exact event payloads
- exact action/non-action trigger boundaries
- exact cardPlayed suppression on lethal Shift GSC
- exact action finalization/limbo behavior
```

**Pass condition:**

```text
Every legal play mutates zones, costs, metadata, logs, triggers, pending effects, and finalization exactly as Lorcanito.
```

---

# 27. Complete full game-state transition and priority continuation engine

**Current status:** not complete.

Some priority restoration exists in `resolveEffect` and `resolveBag`, but full pending turn/challenge continuation is not implemented. Lorcanito imports turn/challenge continuation into `resolveEffect`. 

**Still needed:**

```text
- continuePendingTurnTransition
- continuePendingChallengeResolution
- restore priority after bag/effect drains
- prevent normal moves during pending choices
- resume interrupted moves exactly
```

**Pass condition:**

```text
Pending choices, bag resolution, turn transition, challenge resolution, and normal priority windows resume exactly like Lorcanito.
```

---

# 28. Complete full real-card integration and unsupported-report gating

**Current status:** incomplete.

Some real-card tests exist, but not enough to justify broad support claims.

**Still needed:**

```text
- every supported action effect family has real-card or normalized-card runtime tests
- every static effect family has real-card or normalized-card runtime tests
- every unsupported report movement is backed by execution proof
- parser support alone cannot mark gameplay support
```

**Pass condition:**

```text
A card/effect is reported supported only after it loads, maps, materializes, validates, executes, mutates state, and passes parity tests.
```

---

## Final ordered dependency ladder

```text
1. Runtime identity / current-player / priority model
2. Removal of local compatibility helpers and duplicate rule paths
3. Turn metrics integration
4. Move registry cache integration
5. StaticRegistry materialization
6. Static ability utilities and condition context
7. Derived cost system
8. play-card-rules parity
9. Play-from-under lifecycle
10. Win-condition recomputation
11. Full targeting runtime
12. Remove selected-target trust from action effects
13. Be-chosen lifecycle
14. Triggered ability and bag event lifecycle
15. Shift stack and lethal GSC parity
16. Enter-play state logic
17. Action-card resolver boundary
18. Pending action effect model
19. resolveEffect parity
20. resolveBag parity
21. Dedicated action-effect handlers
22. Sequence / optional / choice / staged selection engine
23. Reveal / scry / hidden-information runtime
24. playCard.validate parity
25. playCard.available parity
26. playCard.execute parity
27. Full game-state transition and priority continuation engine
28. Real-card integration and unsupported-report gating
```

## What counts as a pass

A dependency is complete only when:

```text
- It does not use helper shims, mocked behavior, stubs, or compatibility-only paths.
- It is called by the real runtime path, not just tested in isolation.
- It matches Lorcanito’s source-code behavior and ordering.
- It has real-card or normalized-card integration tests proving state mutation.
- It does not leave a second local implementation in play.py/action_effects.py/resolve_pending.py.
```

The current repo is on the right architectural path, but the next major milestone should be **targeting runtime + selected-target validation**, because almost every higher-level parity item depends on that being exact.
