# LorcanaChamp Rules Kernel v2 — Migration Plan

## Strict Ground-Up Rule

The current `lorcana_bot` engine may be read by humans as an expectation/reference,
but v2 core must not import legacy runtime code. Lorcanito remains the source of
truth for both behavior and architecture.

## Phase 0 — Scaffold

Deliver this scaffold package and tests.

Commands:

```bash
python3 -m pytest tests/v2 -q
```

Expected result: all v2 scaffold tests pass.

## Phase 1 — Read-Only Rules Kernel

Implement complete read-only services:

```text
TargetResolver
ConditionEvaluator
AmountResolver
StaticRegistry
DerivedState
```

Acceptance: real-card parity tests for at least 20 static/target/amount cards.

## Phase 2 — Legal Move Enumeration

Implement legal move services for:

```text
ink
play
quest
challenge
sing
shift
move-to-location
use-ability
resolve-pending
end-turn
```

Acceptance: legal move output matches Lorcanito-style expectations for real board fixtures.

## Phase 3 — Effect Resolution

Implement effect handlers by family:

```text
draw/lore
damage/banish/discard
ready/exert
return/move/put-under
sequence/optional/choice/conditional
scry/reveal/search/name-a-card
play-card/create-triggered-ability/grant-ability
```

Acceptance: every handler has real-card tests and never parses targets/amounts locally.

## Phase 4 — Event Pipeline and Registries

Implement:

```text
event emission
replacement interception
trigger matching
bag ordering
floating/delayed triggers
duration cleanup
```

Acceptance: triggered/replacement/floating cards pass real-card parity tests.

## Phase 5 — Report Integration

Add a v2 report classifier. It must reject shapes without runtime-path evidence.

Acceptance: report movement is tied to tests and path evidence.

## Phase 6 — ML Adapter

Build stable action and observation APIs:

```text
state -> observation
state -> legal action IDs
action ID -> v2 Command
TransitionResult -> reward/debug trace
```

Acceptance: ML tests never import v1 internals.

## Phase 7 — Gradual Engine Replacement

Only after v2 gates pass, replace v1 subsystems one at a time using adapter boundaries.
