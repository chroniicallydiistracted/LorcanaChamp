# V2 Kernel Phase 5 Command Runtime Implementation

Status: complete.

## Lorcanito Source Inspected

Confirmed source-of-truth files:

- `references/lorcana-simulator/packages/lorcana/lorcana-engine/src/core/runtime/types.ts`
- `references/lorcana-simulator/packages/lorcana/lorcana-engine/src/core/runtime/match-runtime.types.ts`
- `references/lorcana-simulator/packages/lorcana/lorcana-engine/src/core/runtime/match-runtime.ts`
- `references/lorcana-simulator/packages/lorcana/lorcana-engine/src/core/runtime/match-runtime.commands.ts`
- `references/lorcana-simulator/packages/lorcana/lorcana-engine/src/core/runtime/match-runtime.validation.ts`
- `references/lorcana-simulator/packages/lorcana/lorcana-engine/src/core/runtime/match-runtime.utils.ts`
- `references/lorcana-simulator/packages/lorcana/lorcana-engine/src/core/runtime/match-runtime.apis.ts`
- `references/lorcana-simulator/packages/lorcana/lorcana-engine/src/core/runtime/match-runtime.flow.ts`
- `references/lorcana-simulator/packages/lorcana/lorcana-engine/src/runtime-moves/moves/core/resources.ts`

Confirmed Lorcanito behavior:

- Commands are `CommandEnvelope { commandID, move, input?: { args }, optimisticHint?, redactInput? }`.
- `executeCommand` rejects missing input with `MISSING_INPUT` before move lookup.
- Validation rejects stale state, game ended, unknown move, server-only player commands, flow-disallowed moves, non-priority actors, and move-specific failures.
- Move reducers receive validation/execution/enumeration contexts with `ctx.args`, `ctx.params`, `ctx.framework`, `ctx.cards`, `ctx.framework.zones`, `ctx.framework.events`, `ctx.framework.log`, and `ctx.framework.undo`.
- Successful execution buffers events/logs, emits `MOVE_EXECUTED`, increments `_stateID`, expires reveals, and returns command success with state ID and undoability.
- `putCardIntoInkwell` reads `ctx.args.cardId`, uses `ctx.framework.zones.moveCard`, patches meta to ready/faceDown, reveals the inked card to all temporarily, logs `lorcana.card.inked`, and records turn inking.

## Previous V2 Mismatch

- `core/commands.py` exposed legacy `Command(kind, actor, card, target, payload)`.
- `core/results.py` exposed legacy `TransitionResult(accepted, reason)` without Lorcanito error codes or published event/log output.
- `core/runtime.py` delegated to `AvailableMoveService.apply` instead of owning state and processing `CommandEnvelope`.
- `core/context.py` only had static `RulesContext`; no Lorcanito move contexts or framework APIs existed.
- `moves/ink.py` read legacy command fields instead of `ctx.args`.

## Implemented Files

- Replaced `lorcana_engine_v2/core/commands.py`.
- Replaced `lorcana_engine_v2/core/results.py`.
- Replaced `lorcana_engine_v2/core/events.py`.
- Replaced `lorcana_engine_v2/core/context.py`.
- Replaced `lorcana_engine_v2/core/runtime.py`.
- Added `lorcana_engine_v2/core/validation.py`.
- Added `lorcana_engine_v2/core/mutator.py`.
- Added `lorcana_engine_v2/core/logs.py`.
- Updated `lorcana_engine_v2/core/replay.py`.
- Updated `lorcana_engine_v2/core/zones.py` with Lorcanito camelCase API aliases.
- Replaced `lorcana_engine_v2/moves/registry.py`.
- Replaced `lorcana_engine_v2/moves/available_moves.py` as an isolated compatibility adapter.
- Replaced `lorcana_engine_v2/moves/ink.py`.
- Updated `lorcana_engine_v2/runtime_game/definition.py`.
- Updated package exports in `lorcana_engine_v2/__init__.py` and `lorcana_engine_v2/core/__init__.py`.

## Parity Mapping

| Lorcanito behavior | V2 implementation |
| --- | --- |
| `CommandEnvelope` and `MoveInput(args)` | `core/commands.py::CommandEnvelope`, `MoveInput` |
| Missing input failure | `execute_command` returns `CommandFailure(errorCode="MISSING_INPUT")` |
| Stale state failure | `core/validation.py::validate_command` returns `STALE_STATE` |
| Unknown move failure | `validate_command` returns `MOVE_NOT_FOUND` |
| Server-only player failure | `validate_command` returns `SERVER_ONLY` |
| Flow move gate | `is_move_allowed_by_flow`, `FLOW_DISALLOWED` |
| Priority gate | `can_player_take_actions`, `NOT_PRIORITY_HOLDER` |
| Runtime validation context | `build_validation_context`, `MoveValidationContext` |
| Runtime execution context | `build_execution_context`, `MoveExecutionContext` |
| Framework state snapshot | `create_framework_state_snapshot` |
| Framework zones/cards/events/log/undo APIs | `FrameworkReadAPI`, `FrameworkWriteAPI`, `CardRuntimeAPI`, `DraftZoneOperations`, `EventAPI`, `UndoAPI` |
| State ID increment and reveal expiry | `advance_state_id_and_expire_reveals` |
| Published command event | `GameEvent(kind="MOVE_EXECUTED")`, `PublishedGameEvent` |
| Inkwell command input | `PutCardIntoInkwellMove.validate/execute` reads `ctx.args.cardId` |

## Tests

Added:

- `tests/v2/test_lorcanito_command_envelope_v2.py`
- `tests/v2/test_lorcanito_runtime_contexts_v2.py`
- `tests/v2/test_lorcanito_command_events_logs_v2.py`

Rewritten:

- `tests/v2/test_put_card_into_inkwell_move_v2.py`

Commands run:

```bash
pytest -q tests/v2/test_lorcanito_command_envelope_v2.py tests/v2/test_lorcanito_runtime_contexts_v2.py tests/v2/test_lorcanito_command_events_logs_v2.py tests/v2/test_put_card_into_inkwell_move_v2.py
pytest -q tests/v2
python -m compileall -q lorcana_engine_v2 tests/v2
```

Observed:

```text
21 passed
83 passed
compileall passed
```

## Remaining Risks

- Flow transition resolution after moves is not complete; Phase 6 owns setup flow moves and lifecycle transitions.
- Clocks, patch capture, registry warm-up, full projected log conversion, and replay-history snapshots are still deferred.
- `putCardIntoInkwell` is command-bound but not final gameplay parity until derived-card inkability, pending effects, static-granted discard inking, triggers, and bag handoff are implemented.
- Packet animations are intentionally not implemented for the headless ML kernel.
