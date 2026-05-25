# V2 Kernel Phase 8 Resolution Foundation

Status: Complete.

## Lorcanito Source Inspected

| Lorcanito file | Confirmed behavior |
| --- | --- |
| `runtime-moves/resolution/action-effects/pending-action-effects.ts` | Creates pending action effects, queues them in `G.pendingEffects`, sets `ctx.priority.pendingChoice`, moves suspended action cards to limbo, removes pending effects, and finalizes resolved action cards. |
| `runtime-moves/resolution/action-effects/types.ts` | Defines `ActionResolutionInput`, pending continuation data, and suspended/resolved action-effect result shape. |
| `runtime-moves/resolution/resolve-effect.ts` | Validates pending effect chooser/request input, merges submitted resolution input, resolves the effect, and resumes/clears pending state. |
| `runtime-moves/resolution/resolve-bag.ts` | Validates active bag resolver, resolves bag effects through action-effect resolution, records ledgers, removes resolved/suspended bag rows, and flushes follow-up triggers. |
| `triggered-abilities/index.ts` | Buffers triggered events, scans printed/floating candidates, matches trigger subjects/restrictions, enqueues bag items, tracks occurrence/resolution ledgers, and chooses the next bag resolver. |
| `runtime-moves/effects/replacement-effects.ts` | Registers replacement effects, indexes them by event kind, applies printed and registered replacements, consumes one-shot effects, and prunes expired replacements. |
| `runtime-moves/effects/temporary-effects.ts` | Adds/checks/prunes temporary keywords, lost keywords, classifications, abilities, restrictions, and player restrictions by effect windows. |
| `runtime-moves/effects/continuous-effects.ts` | Adds stat modifier continuous effects, indexes by target, contributes to derived stats, and expires stale effects. |
| `rules/effect-registry.ts` | Defines Lorcanito effect windows and expiry semantics for `this-turn`, `next-turn`, `until-start-of-next-turn`, `permanent`, and related durations. |

## v2 State Before Phase 8

| v2 file | Previous behavior |
| --- | --- |
| `resolution/pending.py` | Scaffold only. |
| `resolution/bag.py` | Scaffold only. |
| `resolution/event_pipeline.py` | Scaffold only. |
| `registries/floating_trigger_registry.py` | Scaffold only. |
| `registries/replacement_registry.py` | Scaffold only. |
| `registries/restriction_registry.py` | Scaffold only. |
| `effects/*` | No triggered ability, replacement, temporary, or continuous-effect runtime systems. |
| `rules/derived_state.py` | Did not include active continuous effects, temporary lost keywords, or temporary classifications. |
| `rules/queries.py` | Runtime card cache invalidated only by `stateID`, not `G.staticEffectsVersion`. |

## Implemented v2 Files

| v2 file | Phase 8 implementation |
| --- | --- |
| `resolution/action_effect_types.py` | Added Lorcanito-shaped `ActionResolutionInput`, `PendingActionEffect`, `BagItem`, and `PendingResolutionResult`. |
| `resolution/pending.py` | Added pending queue, pending-choice validation, pending resolution, limbo movement, pending guards, and action-card finalization helpers. |
| `resolution/action_effects.py` | Added foundational generic action-effect resolver for sequence, optional, choice, target suspension, gain-lore, and lose-lore. |
| `effects/triggered_abilities.py` | Added triggered event buffering, real printed trigger scanning, trigger matching, bag enqueue, next resolver selection, bag ledgers, and bag mutation helpers. |
| `resolution/bag.py` | Added active-resolver validation and bag effect resolution through shared action-effect resolution. |
| `resolution/event_pipeline.py` | Added event pipeline facade for emitting, recording, flushing, and pending guards. |
| `effects/replacement_effects.py` | Added printed and registered replacement application, replacement registration/indexing, preview, consumption, and expiry pruning. |
| `effects/temporary_effects.py` | Added temporary card/player effect add/check/prune helpers and global cleanup. |
| `effects/continuous_effects.py` | Added stat modifier continuous effects, by-target index, active stat totals, and expiry cleanup. |
| `rules/effect_registry.py` | Added shared Lorcanito effect-window and expiry helpers. |
| `rules/derived_state.py` | Runtime derivation now includes active continuous stat modifiers, temporary lost keywords, and temporary classifications. |
| `rules/queries.py` | Runtime card cache now invalidates on `G.staticEffectsVersion` changes. |

## Tests Added

- `tests/v2/test_pending_action_effects_lorcanito_v2.py`
- `tests/v2/test_resolve_effect_lorcanito_v2.py`
- `tests/v2/test_triggered_abilities_lorcanito_v2.py`
- `tests/v2/test_resolve_bag_lorcanito_v2.py`
- `tests/v2/test_replacement_effects_lorcanito_v2.py`
- `tests/v2/test_temporary_effects_lorcanito_v2.py`

## Observed Commands

```bash
pytest -q tests/v2/test_pending_action_effects_lorcanito_v2.py tests/v2/test_resolve_effect_lorcanito_v2.py tests/v2/test_triggered_abilities_lorcanito_v2.py tests/v2/test_resolve_bag_lorcanito_v2.py tests/v2/test_replacement_effects_lorcanito_v2.py tests/v2/test_temporary_effects_lorcanito_v2.py
pytest -q tests/v2
pytest --collect-only tests/v2 | tail -n 5
python -m compileall -q lorcana_engine_v2 tests/v2
```

Observed result:

```text
Phase 8 targeted suite: 11 passed
Full v2 suite: 109 passed
Collection: 109 tests collected
Compileall: passed
```

## Parity Proof

- Pending action effects now use the Lorcanito state locations: `G.pendingEffects` and `ctx.priority.pendingChoice`.
- Real Aladdin - Street Rat (`ZTM`) loads from normalized card data, its `play` trigger is buffered, flushed into a bag item, resolved by `resolve_bag`, and applies the real Lorcanito-derived `lose-lore` effect.
- Real Beast - Selfless Protector (`sLs`) loads from normalized card data and its printed replacement redirects damage from another friendly character to Beast.
- Continuous effects now affect runtime card derivation and invalidate cached runtime cards through `G.staticEffectsVersion`.
- Temporary effects are no longer inert metadata; they are visible in runtime card keywords and pruned by Lorcanito-style effect windows.

## Remaining Risks

- This phase does not claim full action-effect/card support. The resolver intentionally covers only foundational generic variants.
- Trigger subject/filter support is foundational. Later phases must add delayed/floating triggers, source filters, target analysis, auto-resolution heuristics, and all remaining Lorcanito trigger variants from source.
- Replacement support covers the printed and registered variants needed for the foundation. Later damage, challenge, discard, lore, and zone-change operations must call replacements consistently before mutating state.
- Unsupported report movement still requires real-card integration tests that prove actual move execution and gameplay outcomes.
