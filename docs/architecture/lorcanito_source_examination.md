# Lorcanito Source Examination Summary

## Scope

Examined the full Lorcanito simulator package structure under:

```text
references/lorcana-simulator/packages/lorcana
```

Primary source areas:

```text
lorcana-engine/src/core/runtime
lorcana-engine/src/runtime-game
lorcana-engine/src/runtime-moves
lorcana-engine/src/runtime-moves/resolution/action-effects
lorcana-engine/src/runtime-moves/rules
lorcana-engine/src/rules
lorcana-engine/src/targeting
lorcana-engine/src/operations
lorcana-engine/src/automation
lorcana-types/src
lorcana-cards/src
lorcana-simulator/e2e
```

## Key Findings

1. Lorcanito is built around a match runtime configuration, not a monolithic card-specific engine.
2. Runtime state and static card resources are separated.
3. Board projection is a first-class layer.
4. Static effects are materialized into registries and consumed by derived-state queries.
5. Targeting is centralized and used by action/effect resolution.
6. Conditions and variable amounts are centralized rules services.
7. Action effects resolve through typed handlers.
8. Automation consumes projected board views and move/action candidates rather than raw internals.
9. The simulator/e2e layer acts as behavior-level parity coverage.

## Architectural Translation to Python

The Python v2 kernel should mirror the architecture, not the TypeScript code:

```text
MatchRuntime -> RulesContext -> services -> registries -> moves/effects -> projections -> ML adapter
```

The scaffold in this archive implements that package shape and a small executable vertical slice.
