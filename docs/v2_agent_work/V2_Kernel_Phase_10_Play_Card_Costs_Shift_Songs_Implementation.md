# Phase 10 Proof: `playCard`, Costs, Shift, Songs

Status: complete.

This phase ports the Lorcanito `playCard` foundation into the headless Python v2 kernel. It does not build UI/animation behavior and does not run Lorcanito as a dependency.

## Lorcanito Source Inspected

| Lorcanito file | Confirmed source-of-truth behavior |
| --- | --- |
| `references/lorcana-simulator/packages/lorcana/lorcana-engine/src/runtime-moves/moves/core/play-card.ts` | `playCard` blocks pending effects/bag, validates hand source, validates cost mode, pays costs before movement, moves the card to play, records turn metadata, logs, emits `cardPlayed`, resolves action cards through action-effect resolution, moves resolved actions to discard, and flushes triggers. |
| `references/lorcana-simulator/packages/lorcana/lorcana-engine/src/runtime-moves/rules/play-card-rules.ts` | Available ink is ready inkwell cards; payment exerts inkwell cards in zone order; Singer/Sing Together use exert costs; Shift rules parse keyword data and target candidates. |
| `references/lorcana-simulator/packages/lorcana/lorcana-engine/src/runtime-moves/shared/execute-shift-play.ts` | Shift attaches the previous character stack under the new card and preserves inherited runtime meta. |
| `references/lorcana-simulator/packages/lorcana/lorcana-engine/src/runtime-moves/state/shift-stack.ts` | Shift targets move out of play to limbo while remaining associated under the shifted card. |
| `references/lorcana-simulator/packages/lorcana/lorcana-engine/src/runtime-moves/resolution/action-effects/play-card-effect.ts` | Action-card play and nested play-card effects use the same cost, Shift, and pending action-effect boundaries. |

## Previous v2 Mismatch

- `moves/play.py`, `moves/shift.py`, `moves/sing.py`, and `resolution/costs.py` were scaffolds.
- `playCard` was listed in flow but not registered in `lorcana_runtime_config`.
- No v2 play path paid ink, exerted singers, attached Shift stacks, emitted `cardPlayed`, or resolved action cards through pending/effect helpers.

## Implemented v2 Files

| v2 file | Completed change |
| --- | --- |
| `lorcana_engine_v2/moves/play.py` | Added registered Lorcanito-shaped `PlayCardMove` with validation, availability, cost payment, enter-play meta, action resolution, turn metadata, logs, and trigger flushing. |
| `lorcana_engine_v2/rules/play_card_rules.py` | Added available ink, spend ink, basic cost validation/payment, exert cost validation, Shift parsing, Shift target candidate resolution, song detection, Singer threshold, and Sing Together threshold. |
| `lorcana_engine_v2/resolution/costs.py` | Replaced scaffold with a thin service/export layer over the play-card cost helpers. |
| `lorcana_engine_v2/moves/shared/execute_shift_play.py` | Added Shift stack attachment and inherited meta handling. |
| `lorcana_engine_v2/moves/shift.py` and `lorcana_engine_v2/moves/sing.py` | Replaced scaffolds with aliases to the Lorcanito `playCard` cost path and exported helpers. |
| `lorcana_engine_v2/runtime_game/definition.py` | Registered `playCard` in the Lorcana runtime config. |
| `lorcana_engine_v2/resolution/action_effects.py` | Added foundational draw effect support needed by real song/action play tests. |

## Tests Added

- `tests/v2/test_play_card_lorcanito_v2.py`
- `tests/v2/test_play_card_costs_lorcanito_v2.py`
- `tests/v2/test_shift_lorcanito_v2.py`
- `tests/v2/test_songs_lorcanito_v2.py`

Real-card proof:

- Chi-Fu (`XGm`) proves standard character play, ink payment, meta, logs, and `cardPlayed`.
- Tangle (`X1Y`) proves action play resolves a foundational effect and moves to discard.
- Aladdin (`ZTM`) proves printed play triggers flush to the bag.
- Gramma Tala (`0Rd`) plus Gramma Tala (`ROE`) prove Shift rule parsing and stack attachment.
- Friends on the Other Side (`3E2`) plus Mr. Incredible (`Y1z`) prove song singing and singer exertion.

## Commands And Results

```bash
pytest -q tests/v2/test_play_card_lorcanito_v2.py tests/v2/test_play_card_costs_lorcanito_v2.py tests/v2/test_shift_lorcanito_v2.py tests/v2/test_songs_lorcanito_v2.py
pytest tests/v2 --tb=short
pytest --collect-only tests/v2 | tail -n 5
python -m compileall -q lorcana_engine_v2 tests/v2
```

Expected and observed:

```text
Phase 10 suite: 9 passed
Full v2 suite: 123 passed
Collection: 123 tests collected
Compileall: passed
```

## Parity Proof

- `playCard` now exists as a registered Lorcanito command and is legal in `mainGame/main`.
- Pending effects and bag entries block play before card-specific validation.
- Standard cost payment exerts ready inkwell cards before the played card changes zones.
- Singer and Sing Together costs exert ready, non-drying characters.
- Shift validates a Lorcanito-derived target, moves the previous stack top to limbo, and records cards under the new top card.
- Action cards enter play, emit `cardPlayed`, resolve through the action-effect foundation, and then move to discard or limbo if pending resolution remains.

## Remaining Risks

- Phase 10 does not complete the full Lorcanito action-effect corpus. That is Phase 11.
- Alternative cost modes and play-from-under permissions need additional real-card parity tests before they can be claimed broadly.
- Shift lethal inherited-damage sweep and full continuous-effect retargeting remain tied to the later challenge/lethal/effect phases.
