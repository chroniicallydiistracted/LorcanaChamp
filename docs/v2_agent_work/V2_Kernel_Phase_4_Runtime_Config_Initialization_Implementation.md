# v2 Kernel Phase 4 Implementation: Runtime Config, Initialization, Seeded Random, Board Setup

Status: complete.

This phase replaces the interim v2 bootstrap with Lorcanito-style runtime initialization. It remains headless kernel logic only: no visual simulator, no packet animation implementation, and no Lorcanito runtime embedding.

## Lorcanito Files Re-Inspected

| File | Confirmed behavior ported |
| --- | --- |
| `references/lorcana-simulator/packages/lorcana/lorcana-engine/src/core/runtime/match-runtime.init.ts` | Initialization extracts initial flow state, creates `TCGCtx`, builds zones, runs game setup, then runs `boardSetup`. |
| `references/lorcana-simulator/packages/lorcana/lorcana-engine/src/runtime-game/definition.ts` | Lorcana setup requires exactly two players; `boardSetup` shuffles each owner's instances into `deck:<player>` and writes card index plus public summary. |
| `references/lorcana-simulator/packages/lorcana/lorcana-engine/src/flow/runtime-flow-config.ts` | Initial segment is `startingAGame`; initial phase is `chooseFirstPlayer`; setup and main-game phase valid-move lists are defined by flow. |
| `references/lorcana-simulator/packages/lorcana/lorcana-engine/src/core/runtime/match-runtime.random-apis.ts` | Random API increments `ctx.random.draws` and returns `seedrandom(`${seed}:${draws}`)()`, with Fisher-Yates shuffle. |
| `references/lorcana-simulator/packages/lorcana/lorcana-engine/src/core/runtime/match-runtime.utils.ts` | Runtime match/game IDs and ruleset hash use Lorcanito's current timestamp-based helper shape. |
| `references/lorcana-simulator/packages/lorcana/lorcana-engine/src/core/runtime/match-runtime.types.ts` | Runtime config, setup args, board setup context, and flow definition shape. |

## v2 Files Inspected

| File | Pre-fix behavior |
| --- | --- |
| `lorcana_engine_v2/core/bootstrap.py` | Manually built zones, put cards into decks in deterministic source order, and started directly in `mainGame/main` with priority open. |
| `lorcana_engine_v2/core/state.py` | Had `TCGCtx`, `CtxRandom`, status, priority, and `LorcanaG`, but no runtime config initializer consumed them. |
| `lorcana_engine_v2/core/zones.py` | Had Lorcanito zone state and operations ready for board setup. |
| `tests/v2/test_zone_bootstrap_v2.py` | Protected old owner-outside-match rejection and deterministic deck assumptions. |
| `tests/v2/test_put_card_into_inkwell_move_v2.py` | Relied on bootstrap opening main-phase priority. It is now explicitly marked as an interim main-phase test fixture. |

## Mismatches Closed

| Mismatch | Fix |
| --- | --- |
| Bootstrap skipped runtime config and flow extraction. | Added `core/runtime_config.py` and routed bootstrap through `initialize_match_state`. |
| Bootstrap started in `mainGame/main`. | Initial state now uses `startingAGame/chooseFirstPlayer` from `lorcana_runtime_flow`. |
| Bootstrap used deterministic deck order. | Added `core/random.py` and `runtime_game/definition.py`; board setup shuffles owned instances through Lorcanito's random API pattern. |
| No Lorcanito runtime config object existed. | Added `lorcana_runtime_config`, `lorcana_runtime_zones`, `lorcana_runtime_flow`, `setup_lorcana_g`, and `board_setup`. |
| No exact random proof existed. | Added tests with known `seedrandom@3.0.5` string-seed values and shuffle outputs. |
| Board setup created default card meta via generic put helper. | `board_setup` now writes deck zone cards, card index, and public summaries directly, leaving `cardMeta` empty like Lorcanito board setup. |

## Files Changed

- `lorcana_engine_v2/core/random.py`
- `lorcana_engine_v2/core/runtime_config.py`
- `lorcana_engine_v2/core/bootstrap.py`
- `lorcana_engine_v2/core/__init__.py`
- `lorcana_engine_v2/__init__.py`
- `lorcana_engine_v2/flow/__init__.py`
- `lorcana_engine_v2/flow/runtime_flow_config.py`
- `lorcana_engine_v2/runtime_game/__init__.py`
- `lorcana_engine_v2/runtime_game/definition.py`
- `tests/v2/test_lorcanito_random_api_v2.py`
- `tests/v2/test_lorcanito_match_initialization_v2.py`
- `tests/v2/test_zone_bootstrap_v2.py`
- `tests/v2/test_lorcanito_zone_operations_v2.py`
- `tests/v2/test_put_card_into_inkwell_move_v2.py`
- `docs/v2_agent_work/V2_Kernel_Lorcanito_Simulator_End_To_End_Phased_Implementation_Guide.md`
- `docs/v2_agent_work/V2_Kernel_Phase_3_Zone_Operations_View_Filter_Implementation.md`

## Exact Functions And Classes Added Or Replaced

- `seedrandom`
- `RandomAPI`
- `create_random_api_for_ctx`
- `create_random_api_for_state`
- `Player`
- `RuntimePhaseDefinition`
- `RuntimeTurnDefinition`
- `RuntimeGameSegment`
- `RuntimeFlowDefinition`
- `InitialStatusConfig`
- `SetupArgs`
- `BoardSetupContext`
- `MatchRuntimeConfig`
- `MatchInitContext`
- `MatchInitResult`
- `generate_match_id`
- `generate_game_id`
- `compute_ruleset_hash`
- `extract_initial_flow_state`
- `initialize_match_state`
- `lorcana_runtime_flow`
- `lorcana_runtime_zones`
- `setup_lorcana_g`
- `board_setup`
- `lorcana_player_view`
- `lorcana_runtime_config`
- `initialize_match_state_from_static_resources`

## Tests Added Or Migrated

`tests/v2/test_lorcanito_random_api_v2.py`

- Proves exact `seedrandom@3.0.5` explicit string-seed values used by Lorcanito.
- Proves draw count increments on each random draw.
- Proves Fisher-Yates shuffle uses the Lorcanito random API draw sequence.

`tests/v2/test_lorcanito_match_initialization_v2.py`

- Proves flow extraction starts at `startingAGame/chooseFirstPlayer`.
- Proves runtime config initialization writes match/game IDs, ruleset hash, player IDs, status, priority, `LorcanaG`, zones, shuffled decks, summaries, and random draw count.
- Proves priority opens only when `choosing_first_player` is supplied.
- Proves Lorcana setup rejects non-two-player games.
- Proves runtime zones match Lorcanito visibility/order/owner-scope/face-down flags.

Existing tests migrated:

- `tests/v2/test_zone_bootstrap_v2.py` now matches Lorcanito board setup behavior for owners outside the match.
- `tests/v2/test_lorcanito_zone_operations_v2.py` now accounts for seeded board setup shuffle before zone operation checks.
- `tests/v2/test_put_card_into_inkwell_move_v2.py` explicitly constructs an interim main-phase state instead of relying on bootstrap to do so.

## Commands

Focused Phase 4 command:

```bash
pytest -q tests/v2/test_lorcanito_random_api_v2.py tests/v2/test_lorcanito_match_initialization_v2.py tests/v2/test_zone_bootstrap_v2.py tests/v2/test_lorcanito_zone_operations_v2.py tests/v2/test_lorcanito_view_filter_v2.py tests/v2/test_put_card_into_inkwell_move_v2.py
```

Observed result:

```text
33 passed
```

Full v2 regression command:

```bash
pytest -q tests/v2
```

Observed result:

```text
69 passed
```

## Parity Proof

- v2 no longer starts a match directly in main phase.
- Initial status is derived from `lorcana_runtime_flow`, matching Lorcanito's `extractInitialFlowState`.
- `setup_lorcana_g` requires exactly two players and creates initial `LorcanaG`.
- `board_setup` shuffles each player's static instances into `deck:<player>`, writes `cardIndex`, and sets deck public summary revision/count.
- Random values match `seedrandom@3.0.5` for Lorcanito's explicit string-seed usage.
- `ctx.random.draws` advances by exactly the number of random draws consumed by shuffle.
- No Lorcanito package is imported or executed by v2 runtime code.

## Edge Cases And Risks

- `generate_match_id`, `generate_game_id`, and `compute_ruleset_hash` intentionally mirror Lorcanito's timestamp helper shape. Deterministic replay should pass explicit IDs and static resource refs.
- Phase 4 does not implement command envelopes or setup move execution. A game starts in `startingAGame/chooseFirstPlayer`; Phase 5 and Phase 6 must make command processing and setup progression authoritative.
- Existing inkwell tests remain interim and explicitly construct a main-phase state. They are not Lorcanito card support proof.
