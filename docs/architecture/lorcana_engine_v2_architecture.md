# LorcanaChamp Rules Kernel v2 — Architecture Plan

## Purpose

Build a Lorcanito-aligned Python rules kernel for LorcanaChamp. The v2 kernel is
a ground-up Python implementation. It may use the current LorcanaChamp engine as
human reference only, but it must not directly import legacy runtime code.

## Placement

Create v2 as a sibling package:

```text
LorcanaChamp/
  lorcana_bot/              # existing v1 engine/bot/reference only
  lorcana_engine_v2/        # new Lorcanito-aligned rules kernel
  tests/v2/                 # v2 tests
```

## Dependency Rule

Allowed in v2 core:

```text
standard library
lorcana_engine_v2.*
normalized Lorcanito card JSON loaded as data
```

Forbidden in v2 core:

```text
lorcana_bot.engine
lorcana_bot.effects
lorcana_bot.static_effects
lorcana_bot.targeting
lorcana_bot.replacement_effects
lorcana_bot.triggers
```

Compatibility with v1, if needed, must live only under `lorcana_engine_v2/adapters/`.

## Lorcanito Architecture Findings

Inspected Lorcanito areas:

```text
packages/lorcana/lorcana-engine/src/core/runtime
packages/lorcana/lorcana-engine/src/runtime-game
packages/lorcana/lorcana-engine/src/runtime-moves
packages/lorcana/lorcana-engine/src/runtime-moves/resolution/action-effects
packages/lorcana/lorcana-engine/src/rules
packages/lorcana/lorcana-engine/src/targeting
packages/lorcana/lorcana-engine/src/operations
packages/lorcana/lorcana-engine/src/automation
packages/lorcana/lorcana-types/src
packages/lorcana/lorcana-cards/src
packages/lorcana/lorcana-simulator/e2e
```

Confirmed model:

```text
MatchRuntimeConfig defines setup, moves, flow, zones, projection, random, and board setup.
Runtime state is separated from static card resources.
Projection builds player/public board views from runtime state plus rules queries.
Static effects are materialized into a registry, then consumed by derived-state queries.
Targeting is a shared runtime service used by action resolution and rule checks.
Condition evaluation is a shared rules service.
Action effects resolve through typed effect handlers.
Automation consumes projected board state and legal move/action candidates.
```

## v2 Design Principle

The v2 kernel should answer shared rules questions through `RulesContext`, not
through a large monolithic `GameEngine`.

```text
Card data -> typed source model -> RulesContext services -> registries/derived state -> moves/effects -> projections/ML
```

## Package Responsibilities

- `core`: ids, immutable state, events, commands, transition results, runtime shell.
- `cards`: v2 card dataclasses and normalized Lorcanito JSON adapter.
- `rules`: query, target, condition, amount, legality, and derived-state services.
- `registries`: static, replacement, restriction, and floating trigger registries.
- `effects`: typed effect specs, dispatcher, and effect handlers.
- `moves`: move enumeration/application handlers.
- `resolution`: pending effects, bag, costs, event pipeline.
- `projections`: public/player/debug/ML views and unsupported report boundaries.
- `ml`: stable ML observation/action/reward adapters.
- `adapters`: temporary migration-only boundary for v1 shape understanding.

## First Vertical Slice

The scaffold includes executable tests for:

```text
real card catalog loading from data/lorcanito_runtime_extracted/cards.normalized.json
RulesContext wiring
static materialization from active public cards
derived lore/strength/keyword reads
shared target alias for YOUR_HERO_CHARACTERS
items-in-play amount provider
```

Real-card parity cards:

```text
Chi-Fu - Imperial Advisor
Mr. Incredible - Super Strong
Tamatoa - So Shiny!
Ling - Imperial Soldier
Aurora - Dreaming Guardian
```

## Migration Gates

1. **Scaffold gate**: package imports, dependency guard passes, real catalog loads.
2. **Read-only rules gate**: targets/conditions/amounts/static/derived state pass real-card tests.
3. **Legal move gate**: v2 enumerates play/ink/quest/challenge/sing/shift/move/use/resolve moves.
4. **Effect resolution gate**: v2 resolves action/trigger effects through typed handlers.
5. **Event pipeline gate**: triggers, bag, replacements, and floating triggers are first-class.
6. **Report integration gate**: unsupported report only marks executable when v2 runtime path exists.
7. **ML boundary gate**: observation/action/reward adapters use stable v2 projection/action space.
8. **Replacement gate**: v1 runtime calls can be swapped to v2 for selected subsystems.

## Report Integration Rules

Unsupported report movement must include runtime-path evidence. Parser recognition alone must not
move a card/effect to executable.

Required evidence examples:

```text
Target shape executable -> TargetResolver test + effect/move user test
Static effect executable -> StaticRegistry materialization + DerivedState test
Action effect executable -> handler resolution test + pending-choice test if applicable
Move executable -> legal move enumeration + apply transition test
ML executable -> action-space encoding + observation projection test
```

## ML Adapter Boundary

ML must consume only:

```text
v2 projected observation
v2 legal action space
v2 transition result
v2 debug/replay trace
```

ML must not inspect raw effect dictionaries, pending internals, or legacy v1 state.
