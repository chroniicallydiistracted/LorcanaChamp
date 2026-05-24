# v2 Kernel Phase 3 Implementation: Lorcanito Zone Operations And View Filtering

Status: complete.

This phase completes the foundational Lorcanito zone layer that Phase 2 started. It is headless engine/runtime logic only: no visual simulator, no animation logic, and no Lorcanito runtime embedding.

## Lorcanito Files Re-Inspected

| File | Confirmed behavior ported |
| --- | --- |
| `references/lorcana-simulator/packages/lorcana/lorcana-engine/src/core/runtime/zone-operations.ts` | Central card movement API; top-card draw/mill orientation; public summary updates; card index ownership/controller preservation; reveal windows; shuffle and shuffle-bottom behavior. |
| `references/lorcana-simulator/packages/lorcana/lorcana-engine/src/core/runtime/match-runtime.zone-apis.ts` | Runtime-facing zone API shape that resolves zone refs and exposes move/draw/mill/shuffle/reveal/query operations. |
| `references/lorcana-simulator/packages/lorcana/lorcana-engine/src/core/runtime/zone-registry.ts` | Owner-scoped registry resolution, public summaries, and initial zone containers. |
| `references/lorcana-simulator/packages/lorcana/lorcana-engine/src/core/runtime/view-filter.ts` | Runtime hidden-information filtering for player, spectator, and judge roles; visible reveal metadata; RNG state filtering; public zone summary helper. |
| `references/lorcana-simulator/packages/lorcana/lorcana-engine/src/core/runtime/types.ts` | `ZoneRuntimeState`, `ZoneRevealWindow`, `ZoneCardIndexEntry`, `ViewRoleContext`, `FilteredMatchView`, and filtered ctx types. |
| `references/lorcana-simulator/packages/lorcana/lorcana-engine/src/zones/runtime-zone-config.ts` | Lorcana runtime zone definitions and visibility/order/owner-scope/face-down flags. |

## v2 Files Inspected

| File | Pre-fix behavior |
| --- | --- |
| `lorcana_engine_v2/core/zones.py` | Had Lorcanito-shaped state from Phase 2 and basic put/move/patch helpers, but lacked the central runtime zone operation API, reveal lifecycle helpers, owner-scoped zone-ref resolution parity, draw/mill/shuffle parity, and filtered observation behavior. |
| `lorcana_engine_v2/core/state.py` | `TCGCtx` owned zones and random state, but no role-filtered view existed. |
| `lorcana_engine_v2/core/__init__.py` and `lorcana_engine_v2/__init__.py` | Did not expose Phase 3 zone operations or view filtering as v2 kernel surface. |
| `tests/v2/*` | Existing tests proved the state envelope and some legacy move behavior but did not prove Lorcanito zone-operation or hidden-information filtering behavior with real card fixtures. |

## Mismatches Closed

| Mismatch | Fix |
| --- | --- |
| Owner-scoped zone refs were not Lorcanito-complete. | Added `ZoneRef`, `_coerce_zone_ref`, and `resolve_zone_id_from_registry` with owner-scoped player validation and unknown-zone failures. |
| Movement helpers reindexed zones but did not provide runtime operation parity. | Added `ZoneOperations` and `create_zone_operations` with move, move-many, draw, draw-specific, mill, shuffle, shuffle-bottom, reveal, reveal-top, clear-reveal, clear-reveals-by-zone, and card/zone query methods. |
| Draw/mill/shuffle behavior was not centrally testable. | Added pure helpers `draw_cards`, `draw_specific_card`, `mill_cards`, `shuffle_zone`, and `shuffle_bottom` with injected RNG for deterministic parity tests. |
| Reveal windows existed in state but lacked lifecycle operations. | Added `reveal_cards`, `reveal_top`, `clear_reveal`, `clear_reveals_by_zone`, and `expire_reveals`. |
| Public summaries could leak top cards from face-down zones. | Updated public summary calculation so `topPublicCardID` is set only for public non-face-down zones. |
| No hidden-information-safe observation boundary existed. | Added `core/view_filter.py` with Lorcanito-equivalent player/spectator/judge filtering, visible reveal metadata, filtered random state, public zone summary, and no-secret-leakage invariant checks. |

## Files Changed

- `lorcana_engine_v2/core/zones.py`
- `lorcana_engine_v2/core/view_filter.py`
- `lorcana_engine_v2/core/__init__.py`
- `lorcana_engine_v2/__init__.py`
- `tests/v2/test_lorcanito_zone_operations_v2.py`
- `tests/v2/test_lorcanito_view_filter_v2.py`
- `docs/v2_agent_work/V2_Kernel_Lorcanito_Simulator_End_To_End_Phased_Implementation_Guide.md`
- `docs/v2_agent_work/V2_Kernel_Phase_2_State_Envelope_Zone_State_Implementation.md`

## Exact Functions And Classes Added Or Replaced

- `ZoneRef`
- `resolve_zone_id_from_registry`
- `get_cards`
- `get_card_count`
- `get_top_card`
- `get_bottom_card`
- `draw_cards`
- `draw_specific_card`
- `mill_cards`
- `shuffle_zone`
- `shuffle_bottom`
- `reveal_cards`
- `reveal_top`
- `clear_reveal`
- `clear_reveals_by_zone`
- `expire_reveals`
- `ZoneOperations`
- `create_zone_operations`
- `ViewRoleContext`
- `FilteredCtxRandom`
- `FilteredZoneRuntimeRevealState`
- `FilteredZoneRuntimeState`
- `FilteredTCGCtx`
- `FilteredMatchView`
- `PublicZoneViewSummary`
- `SecretLeakageCheck`
- `filter_match_view`
- `filter_zones`
- `filter_private_zones_for_player`
- `filter_public_zone_cards`
- `filter_reveals`
- `filter_random`
- `get_public_zone_summary`
- `verify_no_secret_leakage`

## Tests Added

`tests/v2/test_lorcanito_zone_operations_v2.py`

- Uses real normalized card IDs through `resources_for`.
- Proves owner-scoped zone ref resolution.
- Proves top-of-deck draw order and emitted Lorcanito-shaped events.
- Proves mill order.
- Proves draw-specific no-op behavior for a missing card.
- Proves indexed move reindexing.
- Proves deterministic Fisher-Yates shuffle shape with injected RNG values.
- Proves top public summary only for public face-up zones.
- Proves reveal allocation, clearing, zone-based clearing, and expiry.
- Proves top/bottom ordered zone orientation.

`tests/v2/test_lorcanito_view_filter_v2.py`

- Uses real normalized card IDs through `resources_for`.
- Proves player view includes own hand, public play zones, owner secret-zone index/meta without secret card list leakage, and visible reveal metadata.
- Proves spectator view has public summaries and all-visible reveal metadata without private zone card arrays.
- Proves judge view sees all private zones and reveal windows.
- Proves filtered random keeps seed/draw count while removing server-private RNG state.
- Proves public zone summaries expose safe top card IDs only when allowed by zone visibility/face-down rules.
- Proves player-only reveal windows are hidden from unauthorized players.

## Commands

Focused Phase 3 command:

```bash
pytest -q tests/v2/test_lorcanito_zone_operations_v2.py tests/v2/test_lorcanito_view_filter_v2.py
```

Expected result:

```text
16 passed
```

Full v2 regression command:

```bash
pytest -q tests/v2
```

Expected result:

```text
all tests pass
```

## Parity Proof

- Zone state names and structure match Lorcanito's `public/reveals/private` runtime model.
- Zone ref resolution matches Lorcanito's owner-scoped zone behavior.
- Draw and mill use the Lorcanito array orientation: bottom at index `0`, top at the end.
- Shuffle uses the same Fisher-Yates shape Lorcanito uses, with random values injected in tests to make expected order exact.
- Public summaries do not expose face-down top cards.
- Filtered views are generated server-side from authoritative state and role context; this is runtime hidden-information filtering, not UI presentation.
- Parity tests use actual normalized card IDs and Lorcanito-style `CardsMaps`, so they prove real-card resource mapping through runtime zones.

## Edge Cases And Risks

- Zone events are currently Python dicts with Lorcanito event kind names. Full event publication, command causes, logs, and redaction are Phase 5.
- Lorcanito's patch filtering helpers are not ported yet because v2 does not have patch streaming. They should be ported with command processing and network-state/event publication, not as visual logic.
- Phase 4 has replaced the interim bootstrap with runtime config initialization, seeded random, flow extraction, and `board_setup`. Command envelopes and setup moves remain Phase 5 and Phase 6 work.
