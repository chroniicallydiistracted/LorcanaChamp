# LorcanaChamp v2 Kernel Lorcanito Parity End-to-End Implementation Guide

Status: updated after Phase 10 completion. Remaining work starts at Phase 11.

This guide is the active source-mapped roadmap for rebuilding the LorcanaChamp v2 kernel as a headless Python engine that matches Lorcanito's simulator/game-state/rules logic. Lorcanito remains the source of truth for game model, resolution flow, move validation, and card behavior. LorcanaChamp v2 must not preserve an old runtime shape when that shape conflicts with Lorcanito.

## Scope

- The v2 kernel is headless Python engine logic only.
- No front-facing visual simulator, UI board, packet animation system, or animation layer should be built for the ML kernel.
- Lorcanito is a reference implementation, not a runtime dependency. Do not import, embed, shell out to, or run a Lorcanito instance as the v2 engine.
- The product target is a Lorcana TCG Champion bot. Kernel work must prioritize deterministic legal move generation, correct hidden-information state, parity tests, self-play readiness, replay/debug traces, and ML observations.
- UI-facing Lorcanito files such as board projection and packet animations are useful only for identifying runtime boundaries. v2 may implement headless observations and debug snapshots, but not visual behavior.

## Non-Negotiable Development Standard

1. Match Lorcanito's game model first.
2. Match Lorcanito's resolution flow second.
3. Treat Lorcana rules accuracy and Lorcanito parity as higher priority than preserving current Python APIs.
4. Refactor wrong legacy names, helpers, and tests instead of adapting new logic around them.
5. Keep temporary adapters isolated and explicitly marked for deletion.
6. Use unit tests only to prove one helper or one pure function.
7. Use integration/parity tests with actual normalized/Lorcanito-derived card data before claiming real card support.
8. Unsupported card reports move only after real card load, mapping, classification, materialization, and gameplay effects are proven.
9. Do not implement gameplay moves against stale scaffolding. If a move needs command envelopes, derived cards, pending effects, triggers, or flow state, build those foundations first.

## Current Completed Foundation

| Phase | Status | Evidence |
| --- | --- | --- |
| Phase 0: source lock and parity fixture contract | Complete | `docs/v2_agent_work/lorcanito_source_inventory.md`, `tests/v2/parity_fixtures/*`, `tests/v2/test_parity_fixtures_v2.py`. |
| Phase 1: static resources and catalog audit | Complete | `lorcana_engine_v2/core/static_resources.py`, `tests/v2/test_static_resources_lorcanito_contract_v2.py`, real catalog tests. |
| Phase 2: `MatchState = { G, ctx }` state envelope | Complete | `lorcana_engine_v2/core/state.py`, migrated state/bootstrap/query/ink tests, `tests/v2/test_lorcanito_state_envelope_v2.py`. |
| Phase 3: zone runtime operations and hidden-information views | Complete | `lorcana_engine_v2/core/zones.py`, `lorcana_engine_v2/core/view_filter.py`, `tests/v2/test_lorcanito_zone_operations_v2.py`, `tests/v2/test_lorcanito_view_filter_v2.py`. |
| Phase 4: runtime config, initialization, seeded random, board setup | Complete | `lorcana_engine_v2/core/runtime_config.py`, `lorcana_engine_v2/core/random.py`, `lorcana_engine_v2/flow/runtime_flow_config.py`, `lorcana_engine_v2/runtime_game/definition.py`, `tests/v2/test_lorcanito_match_initialization_v2.py`, `tests/v2/test_lorcanito_random_api_v2.py`. |
| Phase 5: command envelope, runtime contexts, results, logs, events | Complete | `lorcana_engine_v2/core/commands.py`, `lorcana_engine_v2/core/results.py`, `lorcana_engine_v2/core/context.py`, `lorcana_engine_v2/core/runtime.py`, `lorcana_engine_v2/core/validation.py`, `tests/v2/test_lorcanito_command_envelope_v2.py`, `tests/v2/test_lorcanito_runtime_contexts_v2.py`, `tests/v2/test_lorcanito_command_events_logs_v2.py`. |
| Phase 6: flow transitions, legal move gates, setup moves | Complete | `lorcana_engine_v2/flow/runtime_flow.py`, `lorcana_engine_v2/flow/runtime_flow_config.py`, `lorcana_engine_v2/moves/setup.py`, registered setup moves, `tests/v2/test_lorcanito_setup_flow_phase6_v2.py`. |
| Phase 7: runtime card derivation, static effect registry, conditions, targeting | Complete | `lorcana_engine_v2/rules/queries.py`, `lorcana_engine_v2/rules/derived_state.py`, `lorcana_engine_v2/registries/static_registry.py`, `lorcana_engine_v2/rules/condition_evaluator.py`, `lorcana_engine_v2/rules/target_resolver.py`, Phase 7 parity tests. |
| Phase 8: resolution foundation, triggers, bag, replacements, temporary effects | Complete | `lorcana_engine_v2/resolution/pending.py`, `lorcana_engine_v2/resolution/bag.py`, `lorcana_engine_v2/resolution/action_effects.py`, `lorcana_engine_v2/effects/triggered_abilities.py`, `lorcana_engine_v2/effects/replacement_effects.py`, `lorcana_engine_v2/effects/temporary_effects.py`, `lorcana_engine_v2/effects/continuous_effects.py`, Phase 8 parity tests. |
| Phase 9: authoritative resource turn action - put card into inkwell | Complete | `lorcana_engine_v2/moves/ink.py`, `lorcana_engine_v2/rules/derived_state.py`, `lorcana_engine_v2/resolution/pending.py`, `lorcana_engine_v2/effects/triggered_abilities.py`, `tests/v2/test_put_card_into_inkwell_lorcanito_v2.py`, `docs/v2_agent_work/V2_Kernel_Phase_9_Authoritative_Inkwell_Implementation.md`. |
| Phase 10: play card, costs, Shift, songs, entering play | Complete | `lorcana_engine_v2/moves/play.py`, `lorcana_engine_v2/rules/play_card_rules.py`, `lorcana_engine_v2/resolution/costs.py`, `lorcana_engine_v2/moves/shared/execute_shift_play.py`, `tests/v2/test_play_card_lorcanito_v2.py`, `tests/v2/test_play_card_costs_lorcanito_v2.py`, `tests/v2/test_shift_lorcanito_v2.py`, `tests/v2/test_songs_lorcanito_v2.py`, `docs/v2_agent_work/V2_Kernel_Phase_10_Play_Card_Costs_Shift_Songs_Implementation.md`. |

Latest observed v2 suite result after Phase 10:

```bash
pytest -q tests/v2
```

Expected and observed:

```text
123 passed
```

## Current v2 State

| v2 file | Current behavior |
| --- | --- |
| `lorcana_engine_v2/core/static_resources.py` | Lorcanito-style `CardsMaps`, `CardInstanceRegistry`, `MatchStaticResources`, refs, validation, and conversion helpers. |
| `lorcana_engine_v2/core/state.py` | Lorcanito-shaped `MatchState(G, ctx)`, `TCGCtx`, `CtxStatus`, `CtxPriority`, `CtxRandom`, `LorcanaG`, and turn metadata scaffolding. |
| `lorcana_engine_v2/core/zones.py` | Lorcanito-shaped public/reveal/private zone state, owner-scoped zone refs, draw/mill/shuffle/reveal helpers, public summaries, and `ZoneOperations`. |
| `lorcana_engine_v2/core/view_filter.py` | Headless Lorcanito-style role filtering for player, spectator, and judge views. |
| `lorcana_engine_v2/core/bootstrap.py` | Delegates to Lorcanito-style runtime config initialization and board setup. No longer starts directly in main phase. |
| `lorcana_engine_v2/core/runtime_config.py` | Defines v2 `MatchRuntimeConfig`, `MatchInitContext`, flow dataclasses, runtime ID/hash helpers, and `initialize_match_state`. |
| `lorcana_engine_v2/core/random.py` | Implements the Lorcanito random API pattern: `seedrandom(f"{seed}:{draws}")`, draw counting, and Fisher-Yates shuffle. |
| `lorcana_engine_v2/flow/runtime_flow.py` | Implements Lorcanito-style flow legality, phase/segment transition resolution, lifecycle hook invocation, and game-end checks. |
| `lorcana_engine_v2/flow/runtime_flow_config.py` | Defines Lorcanito starting-game and main-game flow structure, setup `endIf` hooks, mulligan draw hook, main-game entry hook, beginning auto-advance gate, and lore/game-ended `endIf`. |
| `lorcana_engine_v2/runtime_game/definition.py` | Defines `lorcana_runtime_config`, two-player Lorcana setup, runtime zones, player view, `board_setup` deck materialization, and registered setup plus inkwell moves. |
| `lorcana_engine_v2/core/runtime.py` | Owns loaded state, Lorcanito-style command processing, validation, flow transition resolution, published events, move logs, state ID advancement, reveal expiry, legal move enumeration gates, and game-end tracking. Clocks, patches, registry warm-up, and full history snapshots remain later phases. |
| `lorcana_engine_v2/core/commands.py` | Defines Lorcanito `CommandEnvelope`, `MoveInput(args=...)`, sanitized command redaction, and no longer exports legacy `Command(kind, actor, card, target, payload)`. |
| `lorcana_engine_v2/core/results.py` | Defines Lorcanito command success/failure, runtime validation result, published game event, log, packet animation, and game-end result shapes. |
| `lorcana_engine_v2/core/context.py` | Provides Lorcanito-shaped validation, execution, lifecycle, enumeration, framework, card, zone, random, event, log, undo, status, and priority APIs. Static `RulesContext` remains isolated for non-mutating helper tests. |
| `lorcana_engine_v2/core/validation.py` | Implements Lorcanito validation gates for missing input, stale state, game ended, unknown move, server-only, flow-disallowed, priority, and move-specific validation. |
| `lorcana_engine_v2/moves/available_moves.py` | Isolated compatibility adapter over Lorcanito move definitions, now including setup moves. Authoritative code should use `MatchRuntime.enumerate_moves_for_player` and `MatchRuntime.process_command`. |
| `lorcana_engine_v2/moves/setup.py` | Implements Lorcanito `chooseWhoGoesFirst`, `alterHand`, and runtime player ID resolution. |
| `lorcana_engine_v2/moves/ink.py` | Implements Lorcanito's authoritative `putCardIntoInkwell`: pending-effect guard, turn ink allowance, static additional-inkwell allowance, hand/discard candidates, derived `canBePutInInkwell`, inkwell zone/meta/reveal/log side effects, turn metadata, `cardInked` event, and trigger flush to bag. |
| `lorcana_engine_v2/moves/play.py` | Implements Lorcanito `playCard` foundations: pending-effect/bag guard, standard ink cost, Shift ink cost and stack attachment, song singing and Sing Together exert costs, enter-play meta, action-card resolution through pending/action-effect helpers, turn metadata, play logs, `cardPlayed`/sing/exert trigger events, and bag flush. |
| `lorcana_engine_v2/rules/play_card_rules.py` | Implements Lorcanito play-card cost helpers: available ink, spend ink, basic cost validation/payment, exert cost validation, Shift parsing and target candidates, song detection, Singer threshold, and Sing Together threshold. |
| `lorcana_engine_v2/resolution/costs.py` | Re-exports the Lorcanito-shaped cost helpers through an isolated service wrapper. |
| `lorcana_engine_v2/rules/queries.py` | Provides Lorcanito-shaped runtime card query views: `instanceId`, `definitionId`, `ownerID`, `controllerID`, `zoneID`, `zoneIndex`, meta, definition, derived stats, cost, damage, drying/exerted state, inkability, keywords, classifications, and query helpers. |
| `lorcana_engine_v2/rules/derived_state.py` | Derives effective strength, willpower, lore, play cost, move cost, inkability, keywords, classifications, and metadata-backed status from static resources, zones, meta, and static registry effects, including static additional-inkwell allowance for `canBePutInInkwell`. |
| `lorcana_engine_v2/registries/static_registry.py` | Builds Lorcanito-shaped static effect indexes: `byTarget`, `byPlayer`, `globalEffects`, and `bySource`, with accessor helpers and compatibility materialization. |
| `lorcana_engine_v2/rules/condition_evaluator.py` | Evaluates the foundational Lorcanito condition variants needed by static registry and target gates, including logical conditions, damage/status, turn, resource counts, card counts, named cards, target queries, and stat thresholds. |
| `lorcana_engine_v2/rules/target_resolver.py` | Resolves foundational Lorcanito target descriptors across owner-scoped zones, owner/controller gates, card types, filters, self/source, exclude-self, and real-card classifications/status filters. |
| `lorcana_engine_v2/resolution/*` | Provides Lorcanito-shaped pending action effects, pending-choice validation/resolution, validation/enumeration pending guards, foundational action-effect execution, triggered bag resolution, and event pipeline flushing. Full effect variant coverage remains later card/move phases. |
| `lorcana_engine_v2/effects/triggered_abilities.py` | Buffers Lorcanito triggered events, scans real printed triggered abilities from normalized card data, flushes matches to bag items from runtime contexts, tracks occurrence/resolution ledgers, and resolves next bag controller priority. |
| `lorcana_engine_v2/effects/replacement_effects.py` | Applies printed replacement abilities and registered replacement effects for foundational damage, discard/lore prevention, damage redirection, and zone-destination replacement. |
| `lorcana_engine_v2/effects/temporary_effects.py` | Adds, checks, prunes, and cleans up temporary keywords, lost keywords, classifications, abilities, restrictions, and player restrictions by Lorcanito effect windows. |
| `lorcana_engine_v2/effects/continuous_effects.py` | Adds and expires turn-scoped stat modifiers and feeds derived runtime card stats through continuous effect totals. |
| `lorcana_engine_v2/projections/*` and `lorcana_engine_v2/ml/*` | Useful later as headless observation/ML adapter surfaces, but they must consume the parity kernel, not define game truth. |

## Lorcanito Source Truth Re-Confirmed

### Runtime Model And Initialization

| Lorcanito file | Confirmed behavior |
| --- | --- |
| `references/lorcana-simulator/packages/lorcana/lorcana-engine/src/core/runtime/types.ts` | Authoritative `MatchState = { G, ctx }`, `TCGCtx`, status, priority, zones, random, command envelope, filtered views, logs, and events. |
| `references/lorcana-simulator/packages/lorcana/lorcana-engine/src/core/runtime/match-runtime.types.ts` | `MatchRuntimeConfig`, move definitions, move validation/execution/enumeration contexts, runtime config, board setup context, command result types, and actor roles. |
| `references/lorcana-simulator/packages/lorcana/lorcana-engine/src/core/runtime/match-runtime.init.ts` | Initialization extracts initial flow status, creates `TCGCtx`, builds owner-scoped zones, initializes time, runs game setup, then runs `boardSetup` inside runtime state mutation. |
| `references/lorcana-simulator/packages/lorcana/lorcana-engine/src/runtime-game/definition.ts` | Lorcana config requires two players, creates `LorcanaG`, shuffles owned card instances into each `deck:<player>`, wires moves, flow, zones, player view, board projection, packet animation derivation, and runtime card derivation. |
| `references/lorcana-simulator/packages/lorcana/lorcana-engine/src/core/runtime/match-runtime.random-apis.ts` | Seeded random API used by board setup shuffling and random effects. |
| `references/lorcana-simulator/packages/lorcana/lorcana-engine/src/core/runtime/mutative.ts` | State mutation is draft-based and returns new runtime state plus optional patches. Python does not need Mutative, but must preserve atomic mutation semantics. |

### Runtime Commands, Contexts, Flow, Priority

| Lorcanito file | Confirmed behavior |
| --- | --- |
| `references/lorcana-simulator/packages/lorcana/lorcana-engine/src/core/runtime/match-runtime.commands.ts` | Validates command input, executes move reducers, resolves flow transitions, updates clocks, increments `_stateID`, expires reveals, warms move registry, checks game end, and buffers `MOVE_EXECUTED` plus game events/logs. |
| `references/lorcana-simulator/packages/lorcana/lorcana-engine/src/core/runtime/match-runtime.validation.ts` | Validates stale state, game-ended state, unknown move, server-only moves, flow-allowed moves, priority holder, and move-specific validation. |
| `references/lorcana-simulator/packages/lorcana/lorcana-engine/src/core/runtime/match-runtime.flow.ts` | Applies phase/segment transitions, lifecycle hooks, auto-advance checks, and game-end checks. |
| `references/lorcana-simulator/packages/lorcana/lorcana-engine/src/core/runtime/match-runtime.priority.ts` | Resolves decision-maker from `priority.pendingChoice.playerID` first, then `priority.holder`. |
| `references/lorcana-simulator/packages/lorcana/lorcana-engine/src/core/runtime/match-runtime.utils.ts` | Builds validation, execution, lifecycle, framework, card, zone, time, random, event, log, and undo APIs around the same authoritative state. |
| `references/lorcana-simulator/packages/lorcana/lorcana-engine/src/flow/runtime-flow-config.ts` | Initial segment is `startingAGame`, phase `chooseFirstPlayer`; mulligan draws 7; main game uses beginning/main/end phases; main legal moves are flow-gated. |

### Zones And Hidden Information

| Lorcanito file | Confirmed behavior |
| --- | --- |
| `references/lorcana-simulator/packages/lorcana/lorcana-engine/src/zones/runtime-zone-config.ts` | Runtime zones are deck, hand, play, discard, inkwell, limbo with visibility, ordering, owner scope, and face-down flags. |
| `references/lorcana-simulator/packages/lorcana/lorcana-engine/src/core/runtime/zone-registry.ts` | Builds owner-scoped zone IDs and initial public/private containers. |
| `references/lorcana-simulator/packages/lorcana/lorcana-engine/src/core/runtime/zone-operations.ts` | Central zone operations update zone cards, card index, public summaries, reveal windows, and events. Top of ordered zones is the end of the array. |
| `references/lorcana-simulator/packages/lorcana/lorcana-engine/src/core/runtime/match-runtime.zone-apis.ts` | Runtime-facing zone query/write APIs resolve zone refs and route mutations through zone operations. |
| `references/lorcana-simulator/packages/lorcana/lorcana-engine/src/core/runtime/view-filter.ts` | Role-based view filtering is a runtime guarantee, not UI convention. It filters private zone cards, visible reveals, and server-private RNG state. |

### Card Runtime, Static State, Targeting

| Lorcanito file | Confirmed behavior |
| --- | --- |
| `references/lorcana-simulator/packages/lorcana/lorcana-engine/src/core/runtime/card-runtime.ts` | Runtime card query resolves instance, definition, owner, controller, zone, zone index, meta, and derived card fields. |
| `references/lorcana-simulator/packages/lorcana/lorcana-engine/src/runtime-moves/state/runtime-card-derived.ts` | Lorcana runtime card derivation computes stats, costs, damage, exerted/drying, inkability, keywords, classifications, restrictions, and temporary abilities. |
| `references/lorcana-simulator/packages/lorcana/lorcana-engine/src/rules/derived-state.ts` | Core derived Lorcana state including effective stats, can-be-put-in-inkwell, lore, cost modifiers, and static context. |
| `references/lorcana-simulator/packages/lorcana/lorcana-engine/src/rules/static-effect-registry.ts` | Builds a multi-pass registry for suppression, stat layers, keywords, classifications, restrictions, costs, player modifiers, and granted abilities. |
| `references/lorcana-simulator/packages/lorcana/lorcana-engine/src/targeting/runtime/target-resolver.ts` | Resolves target DSL variants using runtime cards, source context, trigger context, selected cards, and revealed cards. |
| `references/lorcana-simulator/packages/lorcana/lorcana-engine/src/targeting/runtime/target-availability.ts` | Determines target availability and prompt requirements. |
| `references/lorcana-simulator/packages/lorcana/lorcana-engine/src/rules/condition-evaluator.ts` | Evaluates condition variants used by static abilities, action effects, triggers, and restrictions. |

### Setup, Turn Actions, Resolution

| Lorcanito file | Confirmed behavior |
| --- | --- |
| `references/lorcana-simulator/packages/lorcana/lorcana-engine/src/runtime-moves/moves/setup/choose-who-goes-first.ts` | Validates selected player, sets `otp`, `turnOwnerId`, `pendingMulligan`, opens priority, shuffles decks, and logs setup. |
| `references/lorcana-simulator/packages/lorcana/lorcana-engine/src/runtime-moves/moves/setup/alter-hand.ts` | Validates pending mulligan, moves chosen hand cards to bottom of deck, draws equal count, removes pending player, advances priority, and logs. |
| `references/lorcana-simulator/packages/lorcana/lorcana-engine/src/runtime-moves/moves/core/resources.ts` | Inkwell validates pending effects, turn ink allowance, hand/discard candidates, derived inkability, then moves to inkwell, patches meta, reveals, logs, records turn metadata, emits triggers, and flushes to bag. |
| `references/lorcana-simulator/packages/lorcana/lorcana-engine/src/runtime-moves/moves/core/play-card.ts` | Validates play modes, costs, targets, shift, songs, alternative costs, play-from-under, action resolution, enter-play behavior, triggers, and pending effects. |
| `references/lorcana-simulator/packages/lorcana/lorcana-engine/src/runtime-moves/moves/turn/pass-turn.ts` | Blocks pass turn on pending effects/bag/pending choices/stack; enforces active player, Reckless, must-quest; performs end/start turn pipelines. |
| `references/lorcana-simulator/packages/lorcana/lorcana-engine/src/runtime-moves/moves/core/quest.ts` | Validates quest legality, drying/exert costs, Reckless, restrictions, bypass costs, then exerts, gains lore, records questing, emits triggers, and flushes. |
| `references/lorcana-simulator/packages/lorcana/lorcana-engine/src/runtime-moves/moves/core/challenge.ts` | Declares challenge, applies replacement-aware challenge damage, snapshots trigger candidates before banish, handles lethal combatants, and advances post-damage windows. |
| `references/lorcana-simulator/packages/lorcana/lorcana-engine/src/runtime-moves/moves/core/move-character-to-location.ts` | Validates location movement, move cost payment, and movement triggers. |
| `references/lorcana-simulator/packages/lorcana/lorcana-engine/src/runtime-moves/moves/abilities/activate-ability.ts` | Validates activated abilities, costs, once-per-turn usage, target selection, pending effect setup, and resolution. |

### Effects, Triggers, Replacements, Tests

| Lorcanito file | Confirmed behavior |
| --- | --- |
| `references/lorcana-simulator/packages/lorcana/lorcana-engine/src/runtime-moves/resolution/action-effects/pending-action-effects.ts` | Creates, queues, resumes, validates, and removes pending action effects and `pendingChoice`; can suspend action cards in limbo. |
| `references/lorcana-simulator/packages/lorcana/lorcana-engine/src/runtime-moves/resolution/action-effect-resolver.ts` | Routes action effects through composed effect resolution and pending-choice suspension. |
| `references/lorcana-simulator/packages/lorcana/lorcana-engine/src/runtime-moves/resolution/resolve-effect.ts` | Resolves pending action effects from command input. |
| `references/lorcana-simulator/packages/lorcana/lorcana-engine/src/runtime-moves/resolution/resolve-bag.ts` | Resolves triggered ability bag entries and ledgers. |
| `references/lorcana-simulator/packages/lorcana/lorcana-engine/src/runtime-moves/effects/triggered-abilities.ts` | Owns pending triggered events, bag entries, registration, usage ledgers, source-zone scanning, event buffering, flushing, and finalization. |
| `references/lorcana-simulator/packages/lorcana/lorcana-engine/src/runtime-moves/effects/replacement-effects.ts` | Registers replacement effects, indexes by event kind, tracks usage, and applies replacement events. |
| `references/lorcana-simulator/packages/lorcana/lorcana-engine/src/runtime-moves/effects/temporary-effects.ts` | Temporary keywords, restrictions, classifications, ability grants/losses, and cleanup. |
| `references/lorcana-simulator/packages/lorcana/lorcana-engine/src/runtime-moves/resolution/action-effects/__tests__/*.test.ts` | High-value variant parity tests for action effect behavior. |
| `references/lorcana-simulator/packages/lorcana/lorcana-simulator/src/testing/**/*.test.ts` | End-to-end simulator parity corpus for card interactions, regressions, and AI strategy once runtime APIs exist. |

## Required Remaining Build Order

The remaining phases must run in this order unless direct Lorcanito inspection proves a different dependency:

1. Phase 11: broaden action effect resolver and `resolveEffect` coverage.
2. Phase 12: pass turn and beginning/end turn pipeline.
3. Phase 13: quest.
4. Phase 14: challenge and lethal damage cleanup.
5. Phase 15: locations, activated abilities, and remaining move families.
6. Phase 16: headless observations, legal move adapter, replay/debug projection, ML action/observation surfaces.
7. Phase 17: card support gates and unsupported report movement.
8. Phase 18: Lorcanito simulator corpus parity, self-play determinism, performance, and long-run ML readiness.

## Phase 4: Runtime Config, Initialization, Seeded Random, Board Setup

Objective: Replace interim bootstrap with Lorcanito runtime initialization.

Status: complete.

Lorcanito source:

- `core/runtime/match-runtime.init.ts`
- `core/runtime/match-runtime.types.ts`
- `core/runtime/match-runtime.random-apis.ts`
- `core/runtime/match-runtime.utils.ts`
- `runtime-game/definition.ts`
- `flow/runtime-flow-config.ts`

Current v2 gap:

- Closed. `initialize_match_state_from_static_resources` now delegates to `initialize_match_state` with `lorcana_runtime_config`.
- Closed. `MatchRuntimeConfig`, `MatchInitContext`, flow dataclasses, runtime IDs, and ruleset hash helpers exist.
- Closed. `core/random.py` matches Lorcanito's `seedrandom@3.0.5` explicit string-seed path used by `createRandomAPIForDraft`.
- Closed. `lorcana_runtime_config`, `lorcana_runtime_zones`, `lorcana_runtime_flow`, and `board_setup` exist.

Files added or replaced:

- Add `lorcana_engine_v2/core/runtime_config.py`.
- Add `lorcana_engine_v2/core/random.py`.
- Add `lorcana_engine_v2/flow/__init__.py`.
- Add `lorcana_engine_v2/flow/runtime_flow_config.py`.
- Add `lorcana_engine_v2/runtime_game/__init__.py`.
- Add `lorcana_engine_v2/runtime_game/definition.py`.
- Replace `lorcana_engine_v2/core/bootstrap.py` around the new initialization path.
- Update exports in `lorcana_engine_v2/core/__init__.py` and `lorcana_engine_v2/__init__.py`.

Exact functions/classes implemented:

- `Player`
- `MatchRuntimeConfig`
- `RuntimeFlowDefinition`
- `RuntimeGameSegment`
- `RuntimePhaseDefinition`
- `MatchInitContext`
- `initialize_match_state`
- `extract_initial_flow_state`
- `generate_match_id`
- `generate_game_id`
- `compute_ruleset_hash`
- `RandomAPI`
- `create_random_api_for_state`
- `lorcana_runtime_zones`
- `lorcana_runtime_flow`
- `lorcana_runtime_config`
- `setup_lorcana_g`
- `board_setup`

Required behavior:

- Reject player counts other than exactly two.
- Build zone registry from runtime zones and player IDs.
- Initialize `ctx.status.gameSegment == "startingAGame"` and `ctx.status.phase == "chooseFirstPlayer"`.
- Initialize priority closed unless `choosingFirstPlayer` is supplied.
- Run `setup` to create `LorcanaG`.
- Run `board_setup` after zones exist.
- Put each owner's instances into only that owner's deck.
- Shuffle deck order through the seeded random API, not Python global random.
- Keep `ctx.random.seed` and increment draw count through the API.

Tests:

- Added `tests/v2/test_lorcanito_match_initialization_v2.py`.
- Added `tests/v2/test_lorcanito_random_api_v2.py`.
- Updated `tests/v2/test_zone_bootstrap_v2.py` to test Lorcanito board setup behavior instead of the old owner-outside-match rejection.
- Updated Phase 3 zone operation expectations to account for seeded board setup shuffle.
- Marked old inkwell tests as interim main-phase tests by explicitly constructing main-phase state in test helpers.

Commands:

```bash
pytest -q tests/v2/test_lorcanito_match_initialization_v2.py tests/v2/test_lorcanito_random_api_v2.py
pytest -q tests/v2/test_lorcanito_state_envelope_v2.py tests/v2/test_lorcanito_zone_operations_v2.py
pytest -q tests/v2
```

Parity proof:

- Initial match state now comes from a Lorcanito-style runtime config and flow definition.
- Deck population and shuffling happen through `board_setup`.
- No gameplay move is needed to create the initial authoritative state.

Risks:

- `compute_ruleset_hash`, `generate_match_id`, and `generate_game_id` intentionally mirror Lorcanito's current timestamp-based runtime helper shape. Deterministic replay should pass explicit IDs and static resource refs.
- Phase 4 did not implement setup moves. The match starts in `startingAGame/chooseFirstPlayer`, and Phase 6 must make setup progression authoritative through the Phase 5 command envelope path.

## Phase 5: Command Envelope, Runtime Context APIs, Results, Logs, Events, History

Status: Complete.

Implementation proof: `docs/v2_agent_work/V2_Kernel_Phase_5_Command_Runtime_Implementation.md`

Objective: Replace legacy commands/results/runtime shell with Lorcanito command processing.

Lorcanito source:

- `core/runtime/types.ts`
- `core/runtime/match-runtime.ts`
- `core/runtime/match-runtime.commands.ts`
- `core/runtime/match-runtime.validation.ts`
- `core/runtime/match-runtime.utils.ts`
- `core/runtime/match-runtime.apis.ts`
- `core/runtime/match-runtime.logs.ts`
- `core/runtime/network-state.ts`

Completed v2 behavior:

- Commands now enter through `CommandEnvelope(commandID, move, input=MoveInput(args=...))`.
- Legacy `Command(kind, actor, card, target, payload)` was removed from runtime tests and public core exports.
- Results now expose Lorcanito-style `CommandSuccess` / `CommandFailure`, error codes, state IDs, published game events, move logs, processed command, animations placeholder, and undoability.
- Runtime contexts now provide validation, execution, lifecycle, enumeration, framework state, cards, zones, random, events, log, undo, status, and priority APIs.
- Move execution validates first, leaves old state untouched on validation failure, applies reducer output atomically, increments `_stateID`, expires reveals, emits `MOVE_EXECUTED`, publishes buffered events, buffers logs, and tracks game-end state.
- `PutCardIntoInkwellMove` now reads `ctx.args.cardId` and uses Lorcanito-shaped move contexts.

Files added or replaced:

- Replaced `lorcana_engine_v2/core/commands.py`.
- Replaced `lorcana_engine_v2/core/results.py`.
- Replaced `lorcana_engine_v2/core/context.py`.
- Replaced `lorcana_engine_v2/core/runtime.py`.
- Replaced `lorcana_engine_v2/core/events.py`.
- Added `lorcana_engine_v2/core/logs.py`.
- Added `lorcana_engine_v2/core/mutator.py`.
- Added `lorcana_engine_v2/core/validation.py`.
- Updated `lorcana_engine_v2/core/replay.py`.
- Updated `lorcana_engine_v2/core/zones.py` with Lorcanito camelCase API aliases.
- Replaced `lorcana_engine_v2/moves/registry.py`.
- Replaced `lorcana_engine_v2/moves/available_moves.py` as an isolated compatibility adapter.
- Replaced `lorcana_engine_v2/moves/ink.py` to use Lorcanito contexts.
- Updated `lorcana_engine_v2/runtime_game/definition.py` to register `putCardIntoInkwell`.

Exact functions/classes completed:

- `CommandEnvelope`
- `MoveInput`
- `CommandSuccess`
- `CommandFailure`
- `CommandResult`
- `RuntimeActorRole`
- `MoveDefinition`
- `MoveValidationContext`
- `MoveExecutionContext`
- `MoveEnumerationContext`
- `RuntimeLifecycleContext`
- `FrameworkStateSnapshot`
- `FrameworkReadAPI`
- `FrameworkWriteAPI`
- `CardRuntimeReadAPI`
- `CardRuntimeAPI`
- `EventAPI`
- `UndoAPI`
- `validate_command`
- `execute_command`
- `process_command`
- `build_validation_context`
- `build_execution_context`
- `build_lifecycle_context`
- `create_framework_state_snapshot`
- `append_log`
- `publish_game_events`

Observed behavior:

- Missing input returns `MISSING_INPUT`.
- Stale state returns `STALE_STATE`.
- Unknown move returns `MOVE_NOT_FOUND`.
- Server-only player command returns `SERVER_ONLY`.
- Flow-disallowed moves return `FLOW_DISALLOWED`.
- Non-priority actors fail unless the move ignores priority.
- Successful commands increment `_stateID`, expire reveals, emit `MOVE_EXECUTED`, buffer move logs, and leave old state unchanged on validation failure.
- Runtime contexts expose state through Lorcanito-shaped APIs, not legacy command shortcuts.

Tests added or rewritten:

- Add `tests/v2/test_lorcanito_command_envelope_v2.py`.
- Add `tests/v2/test_lorcanito_runtime_contexts_v2.py`.
- Add `tests/v2/test_lorcanito_command_events_logs_v2.py`.
- Rewrote `tests/v2/test_put_card_into_inkwell_move_v2.py` to submit `CommandEnvelope` and assert Lorcanito error codes.

Commands:

```bash
pytest -q tests/v2/test_lorcanito_command_envelope_v2.py tests/v2/test_lorcanito_runtime_contexts_v2.py tests/v2/test_lorcanito_command_events_logs_v2.py
pytest -q tests/v2/test_lorcanito_command_envelope_v2.py tests/v2/test_lorcanito_runtime_contexts_v2.py tests/v2/test_lorcanito_command_events_logs_v2.py tests/v2/test_put_card_into_inkwell_move_v2.py
pytest -q tests/v2
```

Expected and observed:

```text
21 passed
83 passed
```

Parity proof:

- Every mutating move enters through `CommandEnvelope`.
- Move reducers receive Lorcanito-style validation/execution contexts.
- State changes are atomic and state IDs advance only on successful execution.
- Missing input, stale state, unknown move, server-only player command, flow-disallowed command, not-priority command, and move-specific validation return Lorcanito-style error codes.
- Inkwell integration now uses real Lorcanito-normalized card data and the command envelope boundary.

Remaining risks moved to later phases:

- Flow transitions and setup moves were closed in Phase 6. Clocks, patch capture, registry warm-up, full move log projection, and packet animations are still deferred. Packet animations remain non-essential for the headless ML kernel and should not become a UI implementation task.
- `putCardIntoInkwell` gaps from Phase 5 were closed in Phase 9. Later move phases must follow the same command/context/resolution pattern.

## Phase 6: Flow Transitions, Legal Move Gates, Setup Moves

Status: Complete.

Implementation proof: `docs/v2_agent_work/V2_Kernel_Phase_6_Flow_Setup_Implementation.md`

Objective: Implement Lorcanito's start-game segment and legal move filtering before main-game actions are authoritative.

Lorcanito source:

- `flow/runtime-flow-config.ts`
- `core/runtime/match-runtime.flow.ts`
- `core/runtime/match-runtime.validation.ts`
- `runtime-moves/moves/setup/choose-who-goes-first.ts`
- `runtime-moves/moves/setup/alter-hand.ts`
- `runtime-moves/moves/setup/resolve-player-ids.ts`
- `runtime-moves/moves/setup/*.test.ts`

Completed v2 behavior:

- `chooseWhoGoesFirst` and `alterHand` are registered in `lorcana_runtime_config`.
- Command execution runs Lorcanito-style flow transition resolution after the move reducer and before state ID advancement.
- Initial legal move enumeration exposes only `chooseWhoGoesFirst` for the choosing player.
- `chooseWhoGoesFirst` validates runtime player IDs, sets `otp`, `turnOwnerId`, `pendingMulligan`, opens priority for OTP, shuffles pending players' decks, logs setup, and transitions into mulligan.
- Mulligan phase `onEnter` shuffles each player's deck and draws seven cards through zone APIs.
- `alterHand` validates pending mulligan player and selected hand cards, moves selected cards to deck bottom with index `0`, draws equal replacements, advances pending mulligan priority, logs public/private mulligan details, and logs setup completion.
- Once all pending mulligans are complete, flow transitions to `mainGame`, increments turn to 1, opens priority for OTP, auto-advances beginning to main when no bag/effects/choices are pending, and exposes main-phase legal moves.
- Flow game-end check now respects `ctx.status.gameEnded` and lore threshold via `G.loreToWin` fallback to 20.

Files added or replaced:

- Add `lorcana_engine_v2/flow/runtime_flow.py`.
- Add `lorcana_engine_v2/moves/setup.py`.
- Update `lorcana_engine_v2/moves/__init__.py`.
- Add setup move registration in `lorcana_engine_v2/runtime_game/definition.py`.
- Update `lorcana_engine_v2/core/runtime.py`.
- Update `lorcana_engine_v2/core/validation.py`.
- Update `lorcana_engine_v2/flow/runtime_flow_config.py`.
- Update `lorcana_engine_v2/moves/available_moves.py`.

Exact functions/classes completed:

- `is_move_allowed_by_flow`
- `get_flow_disallow_reason`
- `resolve_flow_transitions`
- `check_game_end_condition`
- `apply_game_end`
- `ChooseWhoGoesFirstMove`
- `AlterHandMove`
- `resolve_runtime_player_ids`
- `can_auto_advance_beginning_phase`

Observed behavior:

- Initial legal player move is `chooseWhoGoesFirst`.
- `chooseWhoGoesFirst` validates selected player, sets `otp`, `turnOwnerId`, `pendingMulligan`, opens priority, shuffles decks, and logs.
- Entering mulligan draws 7 cards to each hand through zone APIs.
- `alterHand` validates pending player and selected hand cards.
- Mulliganed cards move to bottom of deck, player draws equal count, pending list advances, priority moves to next pending player.
- When all mulligans finish, flow transitions to `mainGame`, increments turn, and opens priority for OTP.

Tests:

- Added `tests/v2/test_lorcanito_setup_flow_phase6_v2.py`.
- Tests use real normalized Lorcanito-derived card data through `resources_for`, not synthetic card definitions, to prove deck materialization, setup draw, mulligan zone movement, command validation, legal move gates, and flow transition behavior.

Commands:

```bash
pytest -q tests/v2/test_lorcanito_setup_flow_phase6_v2.py
pytest -q tests/v2
```

Expected and observed:

```text
8 passed
91 passed
```

Parity proof:

- A match now progresses from `startingAGame/chooseFirstPlayer` through mulligan into `mainGame/main` using command envelopes only.
- Setup state changes are made through Lorcanito-shaped validation/execution contexts and zone APIs.
- Flow transition resolution follows Lorcanito's phase `endIf`, `nextPhase`, segment transition, lifecycle hook order, and game-end check structure.
- The beginning phase auto-advances to main only when there are no pending turn transitions, bag items, pending choices, or pending effects.

Risks:

- Beginning phase ready/drying logic from Lorcanito `runtime-flow-config.ts` remains Phase 12 because turn pipeline and static restriction support are not present yet. Phase 6 only proves setup-time transition where no board cards need beginning-phase ready/drying.
- Board setup currently shuffles decks before setup moves also shuffle, matching the current v2 Phase 4 board materialization plus Lorcanito setup move behavior. Determinism is preserved through the seeded random API.

## Phase 7: Runtime Card Derivation, Static Effect Registry, Conditions, Targeting

Status: Complete.

Implementation proof: `docs/v2_agent_work/V2_Kernel_Phase_7_Runtime_Card_Derivation_Static_Targeting_Implementation.md`

Objective: Make all move validation read Lorcanito-derived runtime cards and target legality.

Lorcanito source:

- `core/runtime/card-runtime.ts`
- `runtime-moves/state/runtime-card-derived.ts`
- `runtime-moves/state/derived-card-cache.ts`
- `rules/derived-state.ts`
- `rules/static-effect-registry.ts`
- `runtime-moves/rules/static-ability-utils.ts`
- `rules/condition-evaluator.ts`
- `targeting/runtime/target-resolver.ts`
- `targeting/runtime/target-availability.ts`
- `targeting/targeting-service.ts`
- `targeting/variants/__tests__/*.test.ts`

Completed v2 behavior:

- Runtime cards now expose Lorcanito field names and derived values from static resources plus zone/meta state.
- Static effects are indexed by target, player, global bucket, and source, matching Lorcanito's registry shape.
- Derived state consumes static registry output instead of rescanning legacy flat materialization.
- Conditions and targets use shared Lorcanito-shaped contexts so static registry, derived card projection, and future move validation read the same logic.
- Real normalized card data proves stat modifiers, filtered-count amounts, item-count amounts, classification targets, keyword grants, damage-on-self amounts, meta damage/exertion, and inkwell eligibility.

Files added or replaced:

- Replace `lorcana_engine_v2/rules/queries.py`.
- Replace `lorcana_engine_v2/rules/derived_state.py`.
- Replace `lorcana_engine_v2/registries/static_registry.py`.
- Replace `lorcana_engine_v2/rules/condition_evaluator.py`.
- Replace `lorcana_engine_v2/rules/target_resolver.py`.
- Update `lorcana_engine_v2/core/context.py` card runtime APIs to return derived Lorcanito-shaped runtime cards.
- Update `lorcana_engine_v2/runtime_game/definition.py` to expose a Lorcanito runtime-card deriver.

Exact functions/classes completed:

- `RuntimeCard`
- `RuntimeCardBase`
- `RuntimeCardDeriver`
- `create_lorcana_runtime_card_deriver`
- `derive_runtime_card_fields`
- `derive_can_be_put_in_inkwell`
- `StaticEffectRegistry`
- `StaticRegistry.build`
- `buildStaticEffectRegistry`
- `getEffectsForCard`
- `getEffectsForPlayer`
- `getEffectsFromCard`
- `ConditionEvaluator.evaluate`
- `TargetResolver.resolve`
- `normalize_target_descriptor`

Observed behavior:

- Runtime card base fields always come from static resources and zone index.
- Derived fields include strength, willpower, lore, costs, damage, exerted, drying, inkability, keywords, classifications, restrictions, temporary effects, and granted abilities.
- Static effect registry indexes materialized effects by target, player, global bucket, and source.
- Target DSL resolution uses actor player, source card, owner-scoped zones, card types, filters, and exclude-self.

Tests:

- Added `tests/v2/test_runtime_card_derived_lorcanito_phase7_v2.py`.
- Added `tests/v2/test_static_effect_registry_lorcanito_phase7_v2.py`.
- Added `tests/v2/test_conditions_and_targeting_lorcanito_phase7_v2.py`.
- Updated `tests/v2/test_card_runtime_query_api_v2.py`, `tests/v2/test_first_real_card_parity_v2.py`, `tests/v2/test_lorcanito_runtime_contexts_v2.py`, and `tests/v2/test_static_registry_v2.py` to assert Lorcanito field names and registry shape.

Commands:

```bash
pytest -q tests/v2/test_card_runtime_query_api_v2.py tests/v2/test_first_real_card_parity_v2.py tests/v2/test_lorcanito_runtime_contexts_v2.py tests/v2/test_runtime_card_derived_lorcanito_phase7_v2.py tests/v2/test_static_effect_registry_lorcanito_phase7_v2.py tests/v2/test_conditions_and_targeting_lorcanito_phase7_v2.py
pytest -q tests/v2
```

Expected and observed:

```text
19 passed
98 passed
```

Parity proof:

- Move validation and future gameplay moves can consume derived runtime cards rather than static card data plus ad hoc meta checks.
- Static abilities from real Lorcanito-normalized cards now materialize through a registry with Lorcanito indexing semantics.
- Conditions and targets are shared by the registry and derived-card projection.

Risks:

- Do not classify real cards as supported after this phase. Derived state proves classification/query foundations, not full gameplay effects.
- Condition and target variant coverage is foundational, not exhaustive. Phase 10 and later effect/move phases must extend variants only from Lorcanito source and real-card parity tests.

## Phase 8: Resolution Foundation, Triggers, Bag, Replacements, Temporary Effects

Status: Complete.

Objective: Port the resolution systems that gameplay moves call into. Inkwell, play, quest, challenge, and pass-turn all depend on these systems.

Lorcanito source:

- `runtime-moves/resolution/action-effects/pending-action-effects.ts`
- `runtime-moves/resolution/action-effect-resolver.ts`
- `runtime-moves/resolution/resolve-effect.ts`
- `runtime-moves/resolution/resolve-bag.ts`
- `runtime-moves/effects/triggered-abilities.ts`
- `runtime-moves/effects/replacement-effects.ts`
- `runtime-moves/effects/temporary-effects.ts`
- `runtime-moves/effects/continuous-effects.ts`
- `runtime-moves/effects/play-from-under-permissions.ts`
- `runtime-moves/resolution/action-effects/types.ts`

Implemented files:

- `lorcana_engine_v2/resolution/action_effect_types.py`
- `lorcana_engine_v2/resolution/action_effects.py`
- `lorcana_engine_v2/resolution/pending.py`
- `lorcana_engine_v2/resolution/bag.py`
- `lorcana_engine_v2/resolution/event_pipeline.py`
- `lorcana_engine_v2/effects/triggered_abilities.py`
- `lorcana_engine_v2/effects/replacement_effects.py`
- `lorcana_engine_v2/effects/temporary_effects.py`
- `lorcana_engine_v2/effects/continuous_effects.py`
- `lorcana_engine_v2/rules/effect_registry.py`
- `lorcana_engine_v2/registries/floating_trigger_registry.py`
- `lorcana_engine_v2/registries/replacement_registry.py`
- `lorcana_engine_v2/registries/restriction_registry.py`
- `lorcana_engine_v2/rules/queries.py` cache invalidation now includes `G.staticEffectsVersion`.
- `lorcana_engine_v2/rules/derived_state.py` now includes active continuous modifiers, temporary lost keywords, and temporary classifications in runtime card derivation.

Implemented functions/classes:

- `PendingActionEffect`
- `enqueue_pending_action_effect`
- `resolve_pending_action_effect`
- `validate_pending_choice_input`
- `move_suspended_action_card_to_limbo`
- `TriggeredAbilitiesState`
- `BagItem`
- `emit_triggered_lorcana_event`
- `flush_triggered_events_to_bag`
- `resolve_bag`
- `finalize_resolution_boundary`
- `ReplacementEffectsState`
- `register_replacement_effect`
- `apply_replacement_effects`
- `has_any_pending_effects`
- `validate_no_pending_effects`
- `prune_expired_temporary_effects`
- `cleanup_expired_effects`

Completed behavior:

- Pending effects set `G.pendingEffects` and `ctx.priority.pendingChoice`.
- Pending resolution validates chooser/request ID, consumes the pending entry, clears `pendingChoice`, and can resume through the shared action-effect resolver.
- Action cards suspended by pending effects move from play to Lorcanito limbo and are exposed face-up.
- Triggered events buffer and flush to bag at Lorcanito resolution boundaries.
- Real printed triggered abilities from normalized card data can materialize into `BagItem` entries with source/controller/ability metadata and occurrence ledgers.
- Bag resolution validates the active resolver, executes foundational action effects, removes resolved/suspended bag rows, and flushes follow-up trigger events.
- Printed replacement abilities and registered replacements can redirect/prevent damage, prevent discard/lore loss, and rewrite zone destinations.
- Temporary card/player effects and continuous stat modifiers expire by Lorcanito-style effect windows.
- Continuous stat modifiers affect runtime card derivation through `G.staticEffectsVersion` cache invalidation.

Tests added:

- `tests/v2/test_pending_action_effects_lorcanito_v2.py`
- `tests/v2/test_resolve_effect_lorcanito_v2.py`
- `tests/v2/test_triggered_abilities_lorcanito_v2.py`
- `tests/v2/test_resolve_bag_lorcanito_v2.py`
- `tests/v2/test_replacement_effects_lorcanito_v2.py`
- `tests/v2/test_temporary_effects_lorcanito_v2.py`

Observed commands:

```bash
pytest -q tests/v2/test_pending_action_effects_lorcanito_v2.py tests/v2/test_resolve_effect_lorcanito_v2.py tests/v2/test_triggered_abilities_lorcanito_v2.py tests/v2/test_resolve_bag_lorcanito_v2.py tests/v2/test_replacement_effects_lorcanito_v2.py tests/v2/test_temporary_effects_lorcanito_v2.py
pytest -q tests/v2
pytest --collect-only tests/v2 | tail -n 5
python -m compileall -q lorcana_engine_v2 tests/v2
```

Expected and observed:

```text
Phase 8 targeted suite: 11 passed
Full v2 suite: 109 passed
Collection: 109 tests collected
Compileall: passed
```

Parity proof:

- Lorcanito pending effect source queues `G.pendingEffects` and sets `ctx.priority.pendingChoice`; v2 now does the same through `PendingActionEffect` and `enqueue_pending_action_effect`.
- Lorcanito triggered abilities buffer domain events, scan printed/floating candidates, enqueue `BagEffectEntry`, and choose a next bag resolver; v2 now buffers events, scans real normalized printed triggers, creates `BagItem`, tracks occurrence/resolution ledgers, and sets bag resolver priority.
- Real Aladdin - Street Rat (`ZTM`) proves a normalized Lorcanito `play` trigger loads, flushes to a bag item, resolves through the shared bag path, and changes opponent lore.
- Real Beast - Selfless Protector (`sLs`) proves a printed Lorcanito replacement ability loads and redirects damage from another friendly character to Beast.
- Continuous and temporary effects now influence derived runtime cards instead of being inert metadata.

Risks:

- This phase is a resolution foundation, not full action effect coverage. Do not mark broad card gameplay support complete from these tests.
- The action-effect resolver intentionally supports only foundational `sequence`, `optional`, `choice`, target suspension, and lore effects needed to prove the pipeline. Phase 10 and Phase 11 must expand effect variants from Lorcanito source and real-card parity tests.
- Trigger matching is foundational. Later phases must add the remaining Lorcanito subject filters, delayed/floating trigger windows, auto-resolution heuristics, and target-analysis variants before moving unsupported card reports.
- Per-card hacks are not acceptable substitutes. Effects must remain generic before support reports move.

## Phase 9: Authoritative Resource Turn Action - Put Card Into Inkwell

Status: Complete.

Implementation proof: `docs/v2_agent_work/V2_Kernel_Phase_9_Authoritative_Inkwell_Implementation.md`

Objective: Replace the interim inkwell move with Lorcanito's authoritative `putCardIntoInkwell` behavior.

Lorcanito source:

- `runtime-moves/moves/core/resources.ts`
- `runtime-moves/state/turn-action-ink.ts`
- `runtime-moves/state/turn-metrics.ts`
- `rules/derived-state.ts`
- `runtime-moves/state/runtime-card-derived.ts`
- `runtime-moves/effects/triggered-abilities.ts`
- `runtime-moves/resolution/action-effects/pending-action-effects.ts`

Closed v2 gaps:

- Interim hand-only inking was replaced with the Lorcanito command-context move.
- Pending effects now block validation and enumeration before card-specific validation.
- Candidate cards now come from hand and discard, with actual discard inking requiring derived Lorcanito permission.
- Runtime validation uses derived `runtimeCard.canBePutInInkwell`, not raw `definition.inkable`.
- The turn-action ink limit now includes base one-per-turn, temporary additional allowance, and static `additional-inkwell` allowance.
- Execution now writes Lorcanito zone/meta/reveal/log/turn-metadata/event/trigger side effects.
- Trigger flushing now works from runtime execution contexts, so real printed ink triggers can enter the bag.

Files replaced or updated:

- Replace `lorcana_engine_v2/moves/ink.py`.
- Update `lorcana_engine_v2/resolution/pending.py`.
- Update `lorcana_engine_v2/rules/derived_state.py`.
- Update `lorcana_engine_v2/effects/triggered_abilities.py`.
- Update `tests/v2/test_put_card_into_inkwell_move_v2.py`.
- Add `tests/v2/test_put_card_into_inkwell_lorcanito_v2.py`.

Exact functions/classes completed:

- `PutCardIntoInkwellMove`
- `PUT_CARD_INTO_INKWELL`
- `INKWELL_CANDIDATE_QUERY_DSL`
- `can_ink_this_turn`
- `get_turn_action_ink_limit`
- `get_additional_turn_action_ink_allowance`
- `get_static_additional_turn_action_ink_allowance`
- `get_temporary_additional_turn_action_ink_allowance`
- `build_turn_action_ink_state`
- `record_card_put_into_inkwell_this_turn`
- `validate_no_pending_effects` now supports validation/enumeration contexts.
- `derive_can_be_put_in_inkwell` now accounts for static additional-inkwell allowance.
- `finalize_resolution_boundary` now preserves runtime context for printed trigger scanning.

Observed behavior:

- Reject if pending effects exist.
- Reject if actor is not the priority holder through the existing command validation gate.
- Allow hand cards by default when derived `canBePutInInkwell` is true.
- Allow discard cards only when Lorcanito-derived state grants discard inkwell permission and the card is otherwise inkable.
- Reject non-inkable cards unless a Lorcanito static grant makes `canBePutInInkwell` true.
- Enforce one ink action plus temporary and static Lorcanito additional allowances.
- Move card to `inkwell:<player>`.
- Patch card meta `{ state: "ready", publicFaceState: "faceDown" }`.
- Reveal card to all until `stateID + 3`.
- Log public inking event.
- Record `inkedThisTurn` and `cardsPutIntoInkwellThisTurn`.
- Emit `cardInked` and flush triggered events to bag.

Tests:

- Add `tests/v2/test_put_card_into_inkwell_lorcanito_v2.py`.
- Updated `tests/v2/test_put_card_into_inkwell_move_v2.py`.
- Real Belle - Strange but Special (`6qy`) proves static `additional-inkwell` allows a second ink action this turn.
- Real Hidden Inkcaster (`RqX`) proves hand inkability can be granted to a real non-inkable card.
- Real Moana - Curious Explorer (`wRv`) proves discard inking for a normally inkable real card.
- Real Gramma Tala - Spirit of the Ocean (`0Rd`) proves an ink trigger flushes to the Lorcanito bag.
- Real non-inkable card (`5XS`) remains rejected without a static grant.

Commands:

```bash
pytest -q tests/v2/test_put_card_into_inkwell_move_v2.py tests/v2/test_put_card_into_inkwell_lorcanito_v2.py
pytest -q tests/v2/test_triggered_abilities_lorcanito_v2.py tests/v2/test_resolve_bag_lorcanito_v2.py tests/v2/test_put_card_into_inkwell_move_v2.py tests/v2/test_put_card_into_inkwell_lorcanito_v2.py
pytest -q tests/v2
pytest --collect-only tests/v2 | tail -n 5
python -m compileall -q lorcana_engine_v2 tests/v2
```

Expected and observed:

```text
Phase 9 inkwell suite: 12 passed
Trigger/bag/inkwell regression suite: 15 passed
Full v2 suite: 114 passed
Collection: 114 tests collected
Compileall: passed
```

Parity proof:

- Inkwell is executed as a Lorcanito command in `mainGame/main`, mutates state through runtime contexts, and produces the same state/log/event side effects Lorcanito requires.
- Move validation calls the same pending-effect guard shape Lorcanito uses before ink-specific checks.
- Candidate cards match Lorcanito's hand/discard `INKWELL_CANDIDATE_QUERY_DSL`.
- Turn metadata records both `inkedThisTurn` and `cardsPutIntoInkwellThisTurn`.
- Trigger proof uses real normalized Lorcanito card data, not a synthetic trigger.

Risks:

- Do not use this phase to claim broad card ability support. It proves one turn action.
- The inkwell action is authoritative, but later play/quest/challenge/pass-turn phases still need broader action-effect, trigger-filter, replacement, and turn-pipeline coverage before unsupported card reports move.

## Phase 10: Play Card, Costs, Shift, Songs, Entering Play

Status: Complete.

Implementation proof: `docs/v2_agent_work/V2_Kernel_Phase_10_Play_Card_Costs_Shift_Songs_Implementation.md`

Objective: Implement Lorcanito play-card validation and execution around cost/payment and entry semantics.

Lorcanito source:

- `runtime-moves/moves/core/play-card.ts`
- `runtime-moves/rules/play-card-rules.ts`
- `runtime-moves/shared/execute-shift-play.ts`
- `runtime-moves/state/shift-stack.ts`
- `runtime-moves/resolution/action-effects/play-card-effect.ts`
- `runtime-moves/moves/core/play-card.test.ts`
- `runtime-moves/rules/play-card-rules.test.ts`

Closed v2 gaps:

- `moves/play.py`, `moves/shift.py`, `moves/sing.py`, and `resolution/costs.py` are no longer inert scaffolds.
- Standard ink cost, ready-ink payment, exert costs, Shift ink costs, Shift target selection, Shift stack attachment, song singing, and Sing Together threshold/exertion foundations exist.
- Character/item/location enter-play metadata is set through runtime card meta, and action cards route through the pending/action-effect helpers.
- `playCard` is registered in the Lorcana runtime config and exposed by main-phase flow legal move enumeration.
- Real-card play triggers and foundational action effects use the Phase 8 event/bag/effect foundation.

Files replaced or added:

- Replace `lorcana_engine_v2/moves/play.py`.
- Replace `lorcana_engine_v2/moves/shift.py`.
- Replace `lorcana_engine_v2/moves/sing.py`.
- Replace `lorcana_engine_v2/resolution/costs.py`.
- Add `lorcana_engine_v2/rules/play_card_rules.py`.
- Add `lorcana_engine_v2/moves/shared/execute_shift_play.py`.
- Add `lorcana_engine_v2/moves/shared/__init__.py`.
- Update `lorcana_engine_v2/runtime_game/definition.py`.
- Update `lorcana_engine_v2/moves/__init__.py`.
- Update `lorcana_engine_v2/resolution/action_effects.py` with foundational draw support for action/song play.

Exact functions/classes completed:

- `PLAY_CARD`
- `PlayCardMove`
- `validate_basic_cost`
- `pay_basic_cost`
- `get_available_ink`
- `spend_ink`
- `validate_exert_cost`
- `get_shift_rules`
- `resolve_shift_target_candidates`
- `execute_shift_play`
- `attach_shift_stack`
- `get_singer_threshold`
- `get_singer_threshold_for_instance`
- `get_sing_together_threshold`
- `move_suspended_action_card_to_limbo`
- `finalize_resolved_action_card`

Observed behavior:

- Validate source zones and play permissions.
- Validate main-phase flow and pending-effect gates.
- Support character, item, location, and action play destinations for hand plays.
- Support normal cost, ink-only Shift cost, Singer cost, and Sing Together exert costs.
- Exert and mark ink payment correctly.
- Set entering-play meta including drying and ready/exerted state.
- Handle action cards through pending/resolution path instead of immediately discarding when unresolved.
- Emit card-played events, update turn metadata, invalidate static effects, and flush triggers.
- Explicitly reject unsupported/non-implemented cost modes instead of silently no-oping.

Tests:

- Added `tests/v2/test_play_card_lorcanito_v2.py`.
- Added `tests/v2/test_play_card_costs_lorcanito_v2.py`.
- Added `tests/v2/test_shift_lorcanito_v2.py`.
- Added `tests/v2/test_songs_lorcanito_v2.py`.
- Real Chi-Fu (`XGm`) proves standard character play, ink payment, enter-play meta, logs, and `cardPlayed`.
- Real Tangle (`X1Y`) proves an action resolves through the shared action-effect path and moves to discard.
- Real Aladdin (`ZTM`) proves a printed play trigger flushes to the bag after play.
- Real Gramma Tala (`0Rd`) and Gramma Tala (`ROE`) prove Shift rules and stack attachment.
- Real Friends on the Other Side (`3E2`) and Mr. Incredible (`Y1z`) prove song singing and singer exertion.

Commands:

```bash
pytest -q tests/v2/test_play_card_lorcanito_v2.py tests/v2/test_play_card_costs_lorcanito_v2.py tests/v2/test_shift_lorcanito_v2.py tests/v2/test_songs_lorcanito_v2.py
pytest -q tests/v2
pytest --collect-only tests/v2 | tail -n 5
python -m compileall -q lorcana_engine_v2 tests/v2
```

Expected and observed:

```text
Phase 10 play-card suite: 9 passed
Full v2 suite: 123 passed
Collection: 123 tests collected
Compileall: passed
```

Parity proof:

- Real cards can be played only when Lorcanito would allow them, with cost payment and zone/meta side effects matching runtime state.
- Costs are paid before the played card changes zones.
- Action cards enter play, emit `cardPlayed`, resolve through the action-effect foundation, then move to discard or limbo if suspended.
- Non-action cards emit `cardPlayed` after enter-play meta is established and then flush triggers to the bag.

Risks:

- Do not shortcut action cards into bespoke effects. Action cards must use the pending/effect resolver path.
- Phase 10 does not claim full action-effect variant support. Broader effect resolution remains Phase 11.
- Alternative play costs and play-from-under permissions are not broad support claims until real-card parity tests prove them.

## Phase 11: Action Effect Resolver And `resolveEffect`

Objective: Port Lorcanito action effect resolution generically, with variant coverage gates.

Lorcanito source:

- `runtime-moves/resolution/action-effect-resolver.ts`
- `runtime-moves/resolution/resolve-effect.ts`
- `runtime-moves/resolution/action-effects/*.ts`
- `runtime-moves/resolution/action-effects/__tests__/*.test.ts`
- `runtime-moves/shared/amount/*`

Current v2 gap:

- Existing `effects/handlers/*` and `effects/resolver.py` are legacy-shaped and not Lorcanito-complete.
- Many effect variants exist in normalized card data but are not generically supported.

Files to replace:

- Replace `lorcana_engine_v2/effects/resolver.py`.
- Replace `lorcana_engine_v2/effects/specs.py`.
- Replace or delete incompatible `lorcana_engine_v2/effects/handlers/*`.
- Add `lorcana_engine_v2/resolution/action_effects/` modules grouped by Lorcanito variant.
- Replace `lorcana_engine_v2/moves/resolve_pending.py` with Lorcanito `resolveEffect`.

Exact functions/classes required:

- `resolve_action_effect`
- `resolve_composed_effect`
- `resolve_effect`
- `resolve_variable_amount`
- `resolve_draw_effect`
- `resolve_discard_effect`
- `resolve_banish_effect`
- `resolve_damage_effect`
- `resolve_lore_effect`
- `resolve_reveal_effect`
- `resolve_scry_effect`
- `resolve_search_deck_effect`
- `resolve_put_under_effect`
- `resolve_move_card_effect`
- `resolve_restriction_effect`
- `resolve_create_replacement_effect`
- `resolve_create_triggered_ability_effect`
- `unsupported_action_effect`

Required behavior:

- Effect variants either execute with Lorcanito semantics or return explicit unsupported evidence.
- Optional, choice, sequence, conditional, for-each, target selection, and prompt suspension behave through pending effects.
- Hidden information operations create reveal windows and undo barriers.
- Effects integrate with triggers, replacements, turn metrics, temporary effects, and static effect invalidation.

Tests:

- Add `tests/v2/resolution/action_effects/`.
- Port Lorcanito variant tests in priority order: draw, discard, damage, banish, gain/lose lore, selection, optional, sequence, conditional, reveal, scry, search, put under, restrictions, keyword grants/losses, additional inkwell, replacement creation.

Commands:

```bash
pytest -q tests/v2/resolution/action_effects
pytest -q tests/v2/test_resolve_effect_lorcanito_v2.py
pytest -q tests/v2
```

Parity proof:

- Support movement for action cards is tied to effect variant coverage and real-card integration tests, not static load success.

Risks:

- The action-effect corpus is large. Add unsupported reports for missing variants instead of silently no-oping.

## Phase 12: Pass Turn And Beginning/End Turn Pipeline

Objective: Implement Lorcanito turn transition and cleanup before quest/challenge support broadens.

Lorcanito source:

- `runtime-moves/moves/turn/pass-turn.ts`
- `runtime-moves/moves/turn/concede.ts`
- `runtime-moves/state/turn-metrics.ts`
- `runtime-moves/state/game-state-check.ts`
- `runtime-moves/state/lethal-damage-sweep.ts`
- `runtime-moves/effects/temporary-effects.ts`
- `runtime-moves/effects/continuous-effects.ts`
- `runtime-moves/effects/replacement-effects.ts`
- `runtime-moves/effects/play-from-under-permissions.ts`

Current v2 gap:

- Existing end-turn/pass-turn logic is not Lorcanito's pending transition pipeline.
- No ready/set/draw cleanup, start/end trigger windows, location lore gain, deck-empty loss, static-effect invalidation, or reveal cleanup parity.

Files to replace:

- Replace `lorcana_engine_v2/moves/end_turn.py` or add `lorcana_engine_v2/moves/pass_turn.py`.
- Add `lorcana_engine_v2/runtime_moves/state/turn_metrics.py`.
- Add `lorcana_engine_v2/runtime_moves/state/game_state_check.py`.
- Add `lorcana_engine_v2/runtime_moves/state/lethal_damage_sweep.py`.

Exact functions/classes required:

- `pass_turn`
- `advance_turn_to_next_player`
- `continue_pending_turn_transition`
- `ready_cards_for_player`
- `draw_for_turn`
- `should_skip_draw_step_for_player`
- `gain_lore_from_locations`
- `clear_hand_reveals_for_player`
- `clear_inkwell_reveals_for_all_players`
- `clear_activated_ability_usage_meta`
- `record_card_drawn_this_turn`
- `check_deck_empty_for_player`
- `check_lore_win_condition`

Required behavior:

- Reject pass turn if not active turn player.
- Reject while pending effects, pending choices, bag items, or stack depth exist.
- Enforce Reckless and must-quest if able.
- Queue end-of-turn, advance-turn, and start-of-turn stages.
- Ready current player's play and inkwell cards with Lorcanito restrictions.
- Clear drying only where Lorcanito clears it.
- Prune expired temporary/continuous/replacement/play-from-under effects.
- Draw for turn except opening player first turn or skip-draw effects.
- Emit start/end/draw/ready/turn-passed events and flush triggers.

Tests:

- Add `tests/v2/test_pass_turn_lorcanito_v2.py`.
- Add `tests/v2/test_beginning_phase_lorcanito_v2.py`.
- Add `tests/v2/test_turn_cleanup_lorcanito_v2.py`.
- Add `tests/v2/test_game_end_lorcanito_v2.py`.

Commands:

```bash
pytest -q tests/v2/test_pass_turn_lorcanito_v2.py tests/v2/test_beginning_phase_lorcanito_v2.py tests/v2/test_turn_cleanup_lorcanito_v2.py tests/v2/test_game_end_lorcanito_v2.py
pytest -q tests/v2
```

Parity proof:

- A setup-complete game can pass turns through Lorcanito's turn transition stages without direct state shortcuts.

Risks:

- Pass-turn touches many systems. Do not implement it as "swap active player and draw."

## Phase 13: Quest

Objective: Implement Lorcanito quest validation and execution.

Lorcanito source:

- `runtime-moves/moves/core/quest.ts`
- `runtime-moves/rules/play-card-rules.ts` for exert cost validation.
- `rules/derived-state.ts`
- `rules/static-effect-registry.ts`
- `runtime-moves/effects/triggered-abilities.ts`

Current v2 gap:

- Quest is stubbed or simplified.
- Exert/drying restrictions, Reckless, static restrictions, quest bypass costs, and lore-gain blockers are missing or incomplete.

Files to replace:

- Replace `lorcana_engine_v2/moves/quest.py`.
- Update shared operations helpers if missing: exert, gain lore, restriction bypass.

Exact functions/classes required:

- `quest`
- `validate_quest_card`
- `execute_quest_card`
- `get_eligible_quest_characters`
- `is_player_blocked_from_gaining_lore`
- `apply_static_restriction_bypass`
- `gain_lore`
- `exert_card`

Required behavior:

- Reject if pending effects exist.
- Require current player's character in play.
- Enforce drying/exert costs unless Lorcanito grants bypass.
- Block Reckless characters from questing.
- Enforce temporary and static quest restrictions.
- Pay bypass costs when present.
- Exert character, gain effective lore unless blocked, record questing, emit quest/exert/gain-lore triggers, flush to bag.

Tests:

- Add `tests/v2/test_quest_lorcanito_v2.py`.
- Include real-card parity for normal quest, drying block, Reckless block, lore gain, and trigger emission.

Commands:

```bash
pytest -q tests/v2/test_quest_lorcanito_v2.py
pytest -q tests/v2
```

Parity proof:

- Quest legality and state mutation use derived runtime cards, static restrictions, pending guards, and trigger flushing.

Risks:

- Quest depends on derived state and effects. Do not use static printed lore as the only lore source.

## Phase 14: Challenge And Lethal Damage Cleanup

Objective: Implement Lorcanito challenge declaration, damage, replacement windows, banish snapshots, and lethal cleanup.

Lorcanito source:

- `runtime-moves/moves/core/challenge.ts`
- `runtime-moves/rules/challenge-rules.ts`
- `runtime-moves/state/lethal-damage-sweep.ts`
- `runtime-moves/shared/banish-snapshot.ts`
- `runtime-moves/effects/replacement-effects.ts`
- `runtime-moves/effects/triggered-abilities.ts`

Current v2 gap:

- Challenge is simplified or stubbed.
- Bodyguard, Evasive, Rush, drying, exerted defender, replacement damage, resist, ward/targeting interactions, and banish trigger snapshots are missing or incomplete.

Files to replace:

- Replace `lorcana_engine_v2/moves/challenge.py`.
- Add `lorcana_engine_v2/rules/challenge_rules.py`.
- Add `lorcana_engine_v2/runtime_moves/shared/banish_snapshot.py`.
- Add or replace lethal damage sweep helpers.

Exact functions/classes required:

- `challenge`
- `validate_challenge_action`
- `get_eligible_challenge_attackers`
- `get_legal_challenge_defenders_for_attacker`
- `compute_challenge_damage_result`
- `finalize_challenge_damage_amount`
- `apply_challenge_damage`
- `snapshot_and_banish_lethal_combatant`
- `sweep_lethal_damage_in_play`
- `set_challenge_state`

Required behavior:

- Validate attacker and defender legality using Lorcanito challenge rules.
- Exert attacker and record challenge metrics.
- Apply replacement effects to challenge damage before final damage.
- Apply Resist/static damage modifiers.
- Set and invalidate `G.challengeState` across challenge stages.
- Snapshot keywords/classifications/cards-under/location state before lethal banish.
- Emit challenged, damage, banish, banish-in-challenge, and challenged-and-banished triggers with Lorcanito snapshots.

Tests:

- Add `tests/v2/test_challenge_lorcanito_v2.py`.
- Add `tests/v2/test_challenge_keyword_rules_lorcanito_v2.py`.
- Add `tests/v2/test_lethal_damage_sweep_lorcanito_v2.py`.
- Add real-card parity for Bodyguard, Evasive, Rush, Resist, and mutual banish.

Commands:

```bash
pytest -q tests/v2/test_challenge_lorcanito_v2.py tests/v2/test_challenge_keyword_rules_lorcanito_v2.py tests/v2/test_lethal_damage_sweep_lorcanito_v2.py
pytest -q tests/v2
```

Parity proof:

- Challenge behavior is implemented as a staged Lorcanito resolution with replacement and trigger windows, not direct damage shortcuts.

Risks:

- Banish snapshots are essential for many card triggers. Missing snapshots cause subtle ML-invalid state histories.

## Phase 15: Locations, Activated Abilities, Remaining Move Families

Objective: Complete remaining main-game move families after core state, effects, triggers, and costs exist.

Lorcanito source:

- `runtime-moves/moves/core/move-character-to-location.ts`
- `runtime-moves/moves/abilities/activate-ability.ts`
- `runtime-moves/moves/abilities/banish-character-cost-candidates.ts`
- `runtime-moves/moves/turn/concede.ts`
- `runtime-moves/debug/manual-moves.ts`

Current v2 gap:

- Location movement and activated abilities are stubs.
- Activated ability usage, costs, target prompts, and once-per-turn ledgers are missing.
- Debug/manual moves should not become ML training legal moves.

Files to replace:

- Replace `lorcana_engine_v2/moves/move_to_location.py`.
- Replace `lorcana_engine_v2/moves/use_ability.py`.
- Add `lorcana_engine_v2/moves/concede.py` if absent.
- Keep debug/manual moves separate from normal move enumeration.

Exact functions/classes required:

- `move_character_to_location`
- `validate_location_move_cost`
- `activate_ability`
- `validate_activated_ability_costs`
- `record_activated_ability_use`
- `banish_character_cost_candidates`
- `concede`

Required behavior:

- Validate location move source/destination and move cost.
- Pay location move costs and update `atLocationId`.
- Emit movement triggers.
- Validate activated ability ownership/controller/source zone.
- Enforce exert/ink/banish/discard costs and once-per-turn usage.
- Create pending effect prompts when abilities require choices.
- Separate judge/debug moves from player legal moves and ML action space.

Tests:

- Add `tests/v2/test_move_character_to_location_lorcanito_v2.py`.
- Add `tests/v2/test_activate_ability_lorcanito_v2.py`.
- Add `tests/v2/test_concede_lorcanito_v2.py`.
- Add real-card parity for at least one location movement and one activated ability.

Commands:

```bash
pytest -q tests/v2/test_move_character_to_location_lorcanito_v2.py tests/v2/test_activate_ability_lorcanito_v2.py tests/v2/test_concede_lorcanito_v2.py
pytest -q tests/v2
```

Parity proof:

- Remaining core move families use the same command/context/effects systems as play, quest, challenge, and inkwell.

Risks:

- Do not expose manual/debug moves as normal ML actions unless a training/debug mode explicitly requests them.

## Phase 16: Headless Observations, Legal Move Adapter, Replay, ML Surfaces

Objective: Attach ML-ready observation/action surfaces to the parity kernel without changing game truth.

Lorcanito source:

- `core/runtime/match-runtime.queries.ts`
- `core/runtime/view-filter.ts`
- `core/runtime/network-state.ts`
- `core/runtime/match-runtime.ts`
- `runtime-game/project-board.ts`
- `runtime-game/lorcanaPacketAnimations.ts`
- `lorcana-simulator/src/testing/ai-strategy/*.test.ts`

Current v2 gap:

- Existing projection and ML modules are not guaranteed to consume Lorcanito legal moves and filtered state.
- There is no parity-proof legal action adapter for self-play.
- Replay/debug traces do not yet align with command envelope state IDs, logs, events, and random seeds.

Files to add or replace:

- Replace `lorcana_engine_v2/projections/player_view.py` around `core.view_filter`.
- Replace `lorcana_engine_v2/projections/public_view.py`.
- Replace `lorcana_engine_v2/projections/ml_observation.py`.
- Replace `lorcana_engine_v2/ml/action_space.py`.
- Replace `lorcana_engine_v2/ml/observation_space.py`.
- Replace `lorcana_engine_v2/ml/policy_adapter.py`.
- Replace `lorcana_engine_v2/core/replay.py`.
- Add `lorcana_engine_v2/projections/legal_actions.py`.

Exact functions/classes required:

- `get_filtered_view`
- `project_headless_observation`
- `encode_legal_actions`
- `decode_policy_action`
- `mask_illegal_actions`
- `serialize_command_replay`
- `replay_commands`
- `validate_replay_determinism`
- `build_debug_snapshot`

Required behavior:

- ML observations must be derived from hidden-information-safe views for the actor role.
- Legal action masks must come from runtime legal move enumeration, not hardcoded move lists.
- Replay must include seed, static resource refs, command envelopes, state IDs, and relevant logs/events.
- No animation data is required. Packet animation parity is explicitly out of scope for the ML kernel.

Tests:

- Add `tests/v2/test_player_view_lorcanito_v2.py`.
- Add `tests/v2/test_ml_observation_projection_v2.py`.
- Add `tests/v2/test_automation_legal_move_adapter_v2.py`.
- Add `tests/v2/test_command_replay_determinism_v2.py`.

Commands:

```bash
pytest -q tests/v2/test_player_view_lorcanito_v2.py tests/v2/test_ml_observation_projection_v2.py tests/v2/test_automation_legal_move_adapter_v2.py tests/v2/test_command_replay_determinism_v2.py
pytest -q tests/v2
```

Parity proof:

- The ML bot sees only legal hidden-information-safe observations and can act only through legal command envelopes.

Risks:

- Do not let ML convenience fields become authoritative game state.

## Phase 17: Card Support Gates And Unsupported Report Movement

Objective: Move cards out of unsupported status only when Lorcanito behavior is proven by real gameplay evidence.

Lorcanito source:

- `lorcana-cards/src/data/canonical-cards.json`
- `lorcana-cards/src/cards/types.ts`
- `runtime-moves/resolution/action-effects/__tests__/*.test.ts`
- `rules/conditions/__tests__/*.test.ts`
- `targeting/variants/__tests__/*.test.ts`
- `lorcana-simulator/src/testing/**/*.test.ts`

Current v2 gap:

- Card loading and support reporting can drift into optimistic support claims.
- Some card behavior can appear supported because static data loads even when effect variants are not implemented.

Files to add or replace:

- Replace `lorcana_engine_v2/projections/unsupported_report.py`.
- Replace `lorcana_engine_v2/adapters/report_adapter.py`.
- Add `lorcana_engine_v2/support/coverage.py`.
- Add `lorcana_engine_v2/support/evidence.py`.
- Add `tests/v2/test_support_report_requires_parity_evidence.py`.

Exact functions/classes required:

- `collect_card_required_variants`
- `collect_supported_effect_variants`
- `collect_supported_condition_variants`
- `collect_supported_target_variants`
- `collect_real_card_parity_evidence`
- `evaluate_card_support_status`
- `write_support_report`

Required behavior:

- A card that only loads remains unsupported.
- A card with unsupported effect/condition/target variants remains unsupported.
- A card with implemented variants still requires at least one real integration/parity gameplay test.
- Reports name the first missing runtime feature or missing evidence item.

Tests:

- Add `tests/v2/test_support_report_requires_parity_evidence.py`.
- Add fixture cards that load but remain unsupported due to missing gameplay evidence.
- Add fixture cards that move only after a real parity test marker exists.

Commands:

```bash
pytest -q tests/v2/test_support_report_requires_parity_evidence.py
pytest -q tests/v2
```

Parity proof:

- Support status follows demonstrated Lorcanito behavior, not card catalog availability.

Risks:

- Optimistic support movement will poison ML self-play with incorrect rules.

## Phase 18: Lorcanito Simulator Corpus Parity, Self-Play Determinism, Performance

Objective: Use the mature kernel against broad Lorcanito behavior corpora and make it stable enough for training.

Lorcanito source:

- `lorcana-simulator/src/testing/**/*.test.ts`
- `lorcana-simulator/src/testing/ai-strategy/*.test.ts`
- `runtime-moves/**/__tests__/*.test.ts`
- `rules/**/__tests__/*.test.ts`
- `targeting/**/__tests__/*.test.ts`

Current v2 gap:

- No broad corpus runner maps Lorcanito behavior cases into Python parity fixtures.
- No long self-play determinism checks exist.
- No performance envelope exists for legal move enumeration, derived state, and replay.

Files to add:

- Add `tests/v2/parity_corpus/`.
- Add `tools/v2/import_lorcanito_parity_case.py`.
- Add `tools/v2/run_v2_self_play_smoke.py`.
- Add `tools/v2/profile_v2_kernel.py`.
- Add `lorcana_engine_v2/training/self_play.py` only after the kernel is authoritative.

Exact functions/classes required:

- `load_lorcanito_parity_case`
- `materialize_parity_match`
- `run_parity_command_sequence`
- `compare_expected_state_projection`
- `run_seeded_self_play`
- `profile_legal_move_enumeration`
- `profile_runtime_card_derivation`

Required behavior:

- Imported parity cases must state which Lorcanito source test they came from.
- Self-play must be reproducible from static resources, seed, and command log.
- Legal move enumeration must not expose illegal or hidden-information actions.
- Performance work may cache derived projections but must invalidate on `stateID` and `staticEffectsVersion`.

Tests:

- Add `tests/v2/test_lorcanito_parity_case_loader_v2.py`.
- Add `tests/v2/test_self_play_determinism_v2.py`.
- Add `tests/v2/test_v2_kernel_performance_smoke.py`.

Commands:

```bash
pytest -q tests/v2/test_lorcanito_parity_case_loader_v2.py tests/v2/test_self_play_determinism_v2.py tests/v2/test_v2_kernel_performance_smoke.py
pytest -q tests/v2
```

Parity proof:

- The engine can replay real Lorcanito-derived behavior cases and run deterministic self-play through the same command path used by gameplay tests.

Risks:

- Do not tune performance by weakening correctness, hidden information, or invalidation rules.

## Regression Command Ladder

Run the phase-specific command after each implementation, then run the full v2 suite.

```bash
pytest -q tests/v2/test_card_catalog_loads_real_lorcanito_data.py tests/v2/test_static_resources_v2.py tests/v2/test_static_resources_lorcanito_contract_v2.py
pytest -q tests/v2/test_lorcanito_state_envelope_v2.py
pytest -q tests/v2/test_lorcanito_zone_operations_v2.py tests/v2/test_lorcanito_view_filter_v2.py
pytest -q tests/v2/test_lorcanito_match_initialization_v2.py tests/v2/test_lorcanito_random_api_v2.py
pytest -q tests/v2/test_lorcanito_command_envelope_v2.py tests/v2/test_lorcanito_runtime_contexts_v2.py tests/v2/test_lorcanito_command_events_logs_v2.py
pytest -q tests/v2/test_lorcanito_setup_flow_phase6_v2.py
pytest -q tests/v2/test_card_runtime_query_api_v2.py tests/v2/test_first_real_card_parity_v2.py tests/v2/test_runtime_card_derived_lorcanito_phase7_v2.py tests/v2/test_static_effect_registry_lorcanito_phase7_v2.py tests/v2/test_conditions_and_targeting_lorcanito_phase7_v2.py
pytest -q tests/v2/test_pending_action_effects_lorcanito_v2.py tests/v2/test_resolve_effect_lorcanito_v2.py tests/v2/test_triggered_abilities_lorcanito_v2.py tests/v2/test_resolve_bag_lorcanito_v2.py tests/v2/test_replacement_effects_lorcanito_v2.py tests/v2/test_temporary_effects_lorcanito_v2.py
pytest -q tests/v2/test_put_card_into_inkwell_move_v2.py tests/v2/test_put_card_into_inkwell_lorcanito_v2.py
pytest -q tests/v2/test_play_card_lorcanito_v2.py tests/v2/test_play_card_costs_lorcanito_v2.py tests/v2/test_shift_lorcanito_v2.py tests/v2/test_songs_lorcanito_v2.py
pytest -q tests/v2/resolution/action_effects
pytest -q tests/v2/test_pass_turn_lorcanito_v2.py tests/v2/test_beginning_phase_lorcanito_v2.py tests/v2/test_turn_cleanup_lorcanito_v2.py tests/v2/test_game_end_lorcanito_v2.py
pytest -q tests/v2/test_quest_lorcanito_v2.py
pytest -q tests/v2/test_challenge_lorcanito_v2.py tests/v2/test_challenge_keyword_rules_lorcanito_v2.py tests/v2/test_lethal_damage_sweep_lorcanito_v2.py
pytest -q tests/v2/test_move_character_to_location_lorcanito_v2.py tests/v2/test_activate_ability_lorcanito_v2.py tests/v2/test_concede_lorcanito_v2.py
pytest -q tests/v2/test_player_view_lorcanito_v2.py tests/v2/test_ml_observation_projection_v2.py tests/v2/test_automation_legal_move_adapter_v2.py tests/v2/test_command_replay_determinism_v2.py
pytest -q tests/v2/test_support_report_requires_parity_evidence.py
pytest -q tests/v2/test_lorcanito_parity_case_loader_v2.py tests/v2/test_self_play_determinism_v2.py tests/v2/test_v2_kernel_performance_smoke.py
pytest -q tests/v2
```

## Parity Proof Checklist

A phase is complete only when all of these are true:

1. The phase cites exact Lorcanito source files inspected.
2. v2 names and data flow match Lorcanito unless an adapter is explicitly isolated and temporary.
3. Legacy tests that protect wrong state/API names are rewritten.
4. Unit tests prove helpers only and do not claim real card support.
5. Integration/parity tests use actual normalized/Lorcanito-derived card data.
6. Mutating behavior goes through runtime initialization, command envelopes, flow, and context APIs.
7. Hidden-information state is filtered by runtime logic before ML observation.
8. Support reports move only after effect/condition/target/runtime behavior is proven by tests.

## Immediate Next Implementation

The next development task is Phase 11: broaden the action effect resolver and `resolveEffect` coverage.

Do not claim broad action-card or card-support parity from Phase 10. Play cards now enter the Lorcanito play pipeline, but many real action effects still need generic Lorcanito variant support before card reports can move.
