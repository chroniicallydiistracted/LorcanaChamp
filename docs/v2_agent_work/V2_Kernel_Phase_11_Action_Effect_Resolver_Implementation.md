# Phase 11: Action Effect Resolver And resolveEffect

Status: Complete.

## Lorcanito Source Inspected

- `references/lorcana-simulator/packages/lorcana/lorcana-engine/src/runtime-moves/resolution/action-effect-resolver.ts`
- `references/lorcana-simulator/packages/lorcana/lorcana-engine/src/runtime-moves/resolution/resolve-effect.ts`
- `references/lorcana-simulator/packages/lorcana/lorcana-engine/src/runtime-moves/resolution/action-effects/draw-effect.ts`
- `references/lorcana-simulator/packages/lorcana/lorcana-engine/src/runtime-moves/resolution/action-effects/discard-effect.ts`
- `references/lorcana-simulator/packages/lorcana/lorcana-engine/src/runtime-moves/resolution/action-effects/deal-damage-effect.ts`
- `references/lorcana-simulator/packages/lorcana/lorcana-engine/src/runtime-moves/resolution/action-effects/banish-effect.ts`
- `references/lorcana-simulator/packages/lorcana/lorcana-engine/src/runtime-moves/resolution/action-effects/ready-effect.ts`
- `references/lorcana-simulator/packages/lorcana/lorcana-engine/src/runtime-moves/resolution/action-effects/exert-effect.ts`
- `references/lorcana-simulator/packages/lorcana/lorcana-engine/src/runtime-moves/resolution/action-effects/scry-effect.ts`

Confirmed Lorcanito behavior:

- Action card abilities resolve through one generic `resolveActionEffect` path.
- Target, optional, choice, discard, and scry prompts suspend into pending action effects.
- `resolveEffect` validates the pending choice, merges resolution input, removes pending state, resumes the stored effect, and finalizes the action card when pending effects are clear.
- Draw/discard/damage/banish/ready/exert/restriction variants mutate zones/meta/turn state through the runtime context and integrate with triggers/replacements.

## v2 Files Changed

- `lorcana_engine_v2/resolution/action_effects.py`
- `lorcana_engine_v2/moves/resolve_pending.py`
- `lorcana_engine_v2/effects/resolver.py`
- `lorcana_engine_v2/resolution/pending.py`
- `lorcana_engine_v2/moves/__init__.py`
- `lorcana_engine_v2/runtime_game/definition.py`
- `tests/v2/resolution/test_action_effects_lorcanito_v2.py`
- `tests/v2/resolution/__init__.py`
- `docs/v2_agent_work/V2_Kernel_Lorcanito_Simulator_End_To_End_Phased_Implementation_Guide.md`

## Implemented Behavior

- Added generic action effect dispatch for composed effects, lore, draw, discard, banish, deal/put damage, ready, exert, restriction, keyword grant/loss, move-card, reveal, scry, and replacement creation foundations.
- Added explicit `unsupportedActionEffect` evidence for variants that are not implemented yet.
- Added registered `resolveEffect` move.
- Fixed runtime pending removal so continuation resolution mutates the execution context before resuming the saved effect.
- Preserved the removed pending effect in `resolve_pending_action_effect` results so action-card finalization can move suspended actions from limbo to discard.
- Assigned discard pending choices to the target player by default, matching Lorcanito discard-choice behavior.

## Parity Tests

Real normalized/Lorcanito-derived card data:

- Fire the Cannons! (`BFV`) proves chosen-target `deal-damage`.
- Dragon Fire (`NCd`) proves chosen-target `banish`.
- Freeze (`D1e`) proves chosen opposing character `exert`.
- Fan the Flames (`iMK`) proves `sequence` of `ready` plus temporary `restriction`.
- Sudden Chill (`DDi`) proves opponent discard pending choice, `resolveEffect`, pending cleanup, and action-card finalization.

## Verification

Commands run:

```bash
pytest -q tests/v2/resolution/test_action_effects_lorcanito_v2.py --tb=short
pytest -q tests/v2/resolution/test_action_effects_lorcanito_v2.py tests/v2/test_play_card_lorcanito_v2.py tests/v2/test_play_card_costs_lorcanito_v2.py tests/v2/test_shift_lorcanito_v2.py tests/v2/test_songs_lorcanito_v2.py tests/v2/test_resolve_effect_lorcanito_v2.py tests/v2/test_pending_action_effects_lorcanito_v2.py tests/v2/test_replacement_effects_lorcanito_v2.py --tb=short
pytest tests/v2 --tb=short
python -m compileall -q lorcana_engine_v2 tests/v2
```

Observed:

```text
Phase 11 action-effect suite: 5 passed
Focused play/resolution regression suite: 20 passed
Full v2 suite: 128 passed
Compileall: passed
```

## Remaining Risks

- This phase does not claim full action-effect corpus parity.
- Search deck, put-under, create-triggered-ability, for-each, slotted targets, full scry validation, dynamic amount references, resist/static damage prevention, and lethal cascade checks remain later work.
- Hidden-information operations need stricter Lorcanito reveal-window and undo-barrier parity before ML observations rely on them.
