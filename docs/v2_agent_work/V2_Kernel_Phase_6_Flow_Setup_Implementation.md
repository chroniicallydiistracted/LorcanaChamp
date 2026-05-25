# V2 Kernel Phase 6 Flow And Setup Implementation

Status: complete.

## Lorcanito Source Inspected

| Lorcanito file | Confirmed behavior ported |
| --- | --- |
| `references/lorcana-simulator/packages/lorcana/lorcana-engine/src/flow/runtime-flow-config.ts` | Initial segment is `startingAGame`; `chooseFirstPlayer` valid move is `chooseWhoGoesFirst` and ends when `ctx.status.otp != null`; mulligan `onEnter` shuffles each deck and draws 7; mulligan ends when `pendingMulligan` is empty; `mainGame.onEnter` increments turn and opens priority for OTP; beginning auto-advances when no pending transition, bag, choice, or effects exist. |
| `references/lorcana-simulator/packages/lorcana/lorcana-engine/src/core/runtime/match-runtime.flow.ts` | Flow resolver invokes lifecycle hooks, checks phase `endIf`, advances `nextPhase`, transitions segments when no next phase exists, invokes next segment/turn/phase hooks, and checks segment game-end condition. |
| `references/lorcana-simulator/packages/lorcana/lorcana-engine/src/runtime-moves/moves/setup/choose-who-goes-first.ts` | Validates selected runtime player, sets `otp`, `turnOwnerId`, ordered `pendingMulligan`, opens priority for chosen player, shuffles pending players' decks, and logs `lorcana.setup.firstPlayerChosen`. |
| `references/lorcana-simulator/packages/lorcana/lorcana-engine/src/runtime-moves/moves/setup/alter-hand.ts` | Validates player is real and pending, validates all selected cards are in hand, moves selected cards to deck bottom at index `0`, draws the same count, logs public count/private detail, removes pending player, opens next pending priority, and logs `lorcana.setup.done`. |
| `references/lorcana-simulator/packages/lorcana/lorcana-engine/src/runtime-moves/moves/setup/resolve-player-ids.ts` | Resolves player IDs from `framework.state.playerIds`, then scoped zone IDs, then card index owner IDs. |
| `references/lorcana-simulator/packages/lorcana/lorcana-engine/src/runtime-moves/state/game-state-check.ts` | Lore win condition uses default threshold 20 and per-player `G.loreToWin` override. |

## v2 State Before Phase 6

| v2 file | Previous behavior |
| --- | --- |
| `lorcana_engine_v2/flow/runtime_flow_config.py` | Declared flow phases and valid moves, but lacked `endIf`, lifecycle hooks, and game-end checks. |
| `lorcana_engine_v2/core/runtime.py` | Executed reducers and advanced `_stateID`, but did not resolve phase/segment transitions after a move. |
| `lorcana_engine_v2/core/validation.py` | Had local flow gate helpers, not a reusable flow resolver module. |
| `lorcana_engine_v2/runtime_game/definition.py` | Registered only `putCardIntoInkwell`. |
| `lorcana_engine_v2/moves/available_moves.py` | Compatibility registry exposed only inkwell. |
| `lorcana_engine_v2/moves/` | No setup move module existed. |

## Implemented v2 Files

| v2 file | Phase 6 implementation |
| --- | --- |
| `lorcana_engine_v2/flow/runtime_flow.py` | Added flow legality helpers, transition resolver, lifecycle hook invocation, game-end check, and game-end application. |
| `lorcana_engine_v2/flow/runtime_flow_config.py` | Added Lorcanito setup `endIf` hooks, mulligan `onEnter`, main-game `onEnter`, beginning auto-advance gate, and main-game end condition. |
| `lorcana_engine_v2/moves/setup.py` | Added `ChooseWhoGoesFirstMove`, `AlterHandMove`, constants, and `resolve_runtime_player_ids`. |
| `lorcana_engine_v2/core/runtime.py` | Runs `resolve_flow_transitions` and `check_game_end_condition` after successful reducer execution and before `_stateID` advancement. |
| `lorcana_engine_v2/core/validation.py` | Uses shared flow legality helpers from `flow/runtime_flow.py`. |
| `lorcana_engine_v2/runtime_game/definition.py` | Registers `chooseWhoGoesFirst`, `alterHand`, and `putCardIntoInkwell`. |
| `lorcana_engine_v2/moves/available_moves.py` | Compatibility registry now includes setup moves. |
| `lorcana_engine_v2/moves/__init__.py` and `lorcana_engine_v2/flow/__init__.py` | Export setup and flow helpers. |

## Behavior Proven

- Initial setup legal move is only `chooseWhoGoesFirst` for the choosing player.
- Non-setup moves are flow-disallowed in `chooseFirstPlayer`.
- Invalid first-player selection returns `INVALID_PLAYER` and leaves state unchanged.
- Choosing first player sets OTP, turn owner, pending mulligan order, priority holder, logs setup, enters mulligan, shuffles, and draws seven for each player.
- Invalid mulligan card selection returns `CARD_NOT_IN_HAND`.
- Altering hand moves selected cards to deck bottom, draws replacements, advances pending mulligan priority, and logs Lorcanito mulligan messages.
- A player who already mulliganed returns `MULLIGAN_ALREADY_DONE`.
- Completing both mulligans transitions to `mainGame/main`, increments turn to 1, and opens priority for OTP.

## Tests

Added:

- `tests/v2/test_lorcanito_setup_flow_phase6_v2.py`

Commands run:

```bash
pytest -q tests/v2/test_lorcanito_setup_flow_phase6_v2.py
pytest -q tests/v2
python -m compileall -q lorcana_engine_v2 tests/v2
pytest --collect-only tests/v2 | tail -n 5
```

Observed:

```text
8 passed
91 passed
91 tests collected
```

## Parity Proof

Phase 6 now follows Lorcanito's setup and flow order:

1. `startingAGame/chooseFirstPlayer`
2. `chooseWhoGoesFirst` command sets OTP and pending mulligan
3. phase `endIf` transitions to `mulligan`
4. mulligan `onEnter` shuffles and draws opening hands
5. `alterHand` command resolves each pending player
6. empty pending mulligan triggers segment transition
7. `mainGame.onEnter` increments turn and opens priority for OTP
8. beginning phase auto-advances to `main` only when no pending flow work exists

This is headless engine logic only. No Lorcanito runtime is injected or run, and no visual simulator behavior is implemented.

## Remaining Risks

- Lorcanito beginning-phase ready/drying behavior is intentionally not complete yet because it depends on Phase 7 derived cards/static restrictions and Phase 12 turn pipeline.
- `putCardIntoInkwell` remains interim until Phases 7-9 port derived inkability, pending-effect guards, triggers, and bag handoff.
- Patch capture, runtime clocks, move registry warm-up, and full history snapshots remain later runtime infrastructure tasks.
