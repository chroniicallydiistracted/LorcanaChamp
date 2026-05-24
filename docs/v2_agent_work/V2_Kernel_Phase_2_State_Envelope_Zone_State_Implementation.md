# v2 Kernel Phase 2 Implementation: Lorcanito State Envelope And Zone State

Status: complete.

This implementation deliberately bundled Phase 2 with the foundational zone-state shape from Phase 3. Lorcanito's `TCGCtx` owns `zones.public`, `zones.reveals`, and `zones.private`; keeping the old flat v2 zones under `ctx` would have preserved a known source mismatch.

## Scope Applied

- Headless Python kernel only. No UI, animations, visual board, or frontend simulator was added.
- Lorcanito remains reference source only. No Lorcanito runtime instance is imported, embedded, or executed.
- The implementation supports the ML Champion bot direction by moving the kernel toward deterministic, serializable, hidden-information-aware state.

## Lorcanito Files Re-Inspected

| File | Confirmed behavior ported |
| --- | --- |
| `references/lorcana-simulator/packages/lorcana/lorcana-engine/src/core/runtime/types.ts` | `MatchState = { G, ctx }`; `TCGCtx` fields; `CtxStatus`; `CtxPriority`; public/reveal/private zone runtime state; `createInitialTCGCtx` defaults. |
| `references/lorcana-simulator/packages/lorcana/lorcana-engine/src/types/runtime-state.ts` | `TurnMetadata`, `LorcanaCardMeta`, `LorcanaG`, triggered ability state, pending effects, replacement effects, continuous effects, and `createInitialLorcanaG` defaults. |
| `references/lorcana-simulator/packages/lorcana/lorcana-engine/src/core/runtime/zone-registry.ts` | Owner-scoped zone registry and initial zone state shape. |
| `references/lorcana-simulator/packages/lorcana/lorcana-engine/src/zones/runtime-zone-config.ts` | Lorcana zone IDs and owner-scoped runtime zones. |

## Current v2 Mismatch Replaced

| Previous v2 shape | Problem | Replacement |
| --- | --- | --- |
| `MatchState(framework, game)` | Not Lorcanito; encouraged old active-player/phase shortcuts. | `MatchState(G, ctx)`. |
| `FrameworkState.state_id`, `active_player`, `turn_number`, `phase`, `winner` | Partial context and wrong field names. | `TCGCtx.protocolVersion`, `matchID`, `gameID`, `rulesetHash`, `_stateID`, `playerIds`, `status`, `priority`, `time`, `random`, `zones`. |
| `GameState.players`, minimal `turn_metadata`, `event_log` | Not Lorcanito `LorcanaG`. | `LorcanaG` with lore, full turn metadata, trigger/bag scaffolding, pending effects, continuous/replacement state, restrictions, challenge state, turns completed, static effects version. |
| Flat `ZoneRuntimeState(zone_cards, card_index, card_meta, zone_summaries)` | Not Lorcanito visibility model. | `ZoneRuntimeState(public, reveals, private)`. |
| `CardMeta.exerted/drying/flags` | Wrong Lorcanito field names. | `LorcanaCardMeta.state/isDrying/publicFaceState/...`. |

## Files Changed

- `lorcana_engine_v2/core/state.py`
- `lorcana_engine_v2/core/zones.py`
- `lorcana_engine_v2/core/bootstrap.py`
- `lorcana_engine_v2/core/__init__.py`
- `lorcana_engine_v2/__init__.py`
- `lorcana_engine_v2/rules/queries.py`
- `lorcana_engine_v2/rules/target_resolver.py`
- `lorcana_engine_v2/moves/ink.py`
- `tests/v2/helpers.py`
- `tests/v2/test_lorcanito_state_envelope_v2.py`
- `tests/v2/test_zone_bootstrap_v2.py`
- `tests/v2/test_card_runtime_query_api_v2.py`
- `tests/v2/test_put_card_into_inkwell_move_v2.py`

## Parity Proof

- `tests/v2/test_lorcanito_state_envelope_v2.py` proves the initial `TCGCtx`, `LorcanaG`, `MatchState(G, ctx)`, zone state, and card meta field names.
- Existing v2 bootstrap/query/inkwell tests were migrated off `state.framework`, `state.game`, flat zone maps, and `CardMeta.exerted/drying`.
- The full v2 test suite passes with the new envelope.

## Commands Run

```bash
pytest -q tests/v2/test_zone_bootstrap_v2.py tests/v2/test_card_runtime_query_api_v2.py tests/v2/test_put_card_into_inkwell_move_v2.py
pytest -q tests/v2
```

Expected and observed result:

```text
45 passed
```

## Phase 3 Follow-Up

The state shape was Lorcanito-aligned in Phase 2. The zone-operation parity items listed below were completed in `docs/v2_agent_work/V2_Kernel_Phase_3_Zone_Operations_View_Filter_Implementation.md`:

- reveal window creation/clearing helpers,
- draw/mill/shuffle helpers,
- filtered zone views,
- Lorcanito-shaped zone operation events.

The interim bootstrap shortcut remains intentionally unresolved because Lorcanito runtime config, seeded random, and `boardSetup` belong to Phase 4.
