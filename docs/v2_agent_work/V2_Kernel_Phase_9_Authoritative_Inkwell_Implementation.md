# Phase 9 Proof: Authoritative `putCardIntoInkwell`

Status: complete.

This phase replaces the interim v2 inkwell move with Lorcanito-aligned resource turn action behavior. It remains headless Python kernel logic only. It does not build UI/animation behavior and does not run Lorcanito as a dependency.

## Lorcanito Source Inspected

| Lorcanito file | Confirmed source-of-truth behavior |
| --- | --- |
| `references/lorcana-simulator/packages/lorcana/lorcana-engine/src/runtime-moves/moves/core/resources.ts` | `putCardIntoInkwell` validates no pending effects, uses the priority holder as current player, checks turn ink allowance, accepts hand/discard candidates, requires runtime `canBePutInInkwell`, moves the card to inkwell, patches ready/face-down meta, reveals until `_stateID + 3`, logs `lorcana.card.inked`, records turn metadata, emits `cardInked`, emits triggered `ink`, and flushes triggers to the bag. |
| `references/lorcana-simulator/packages/lorcana/lorcana-engine/src/runtime-moves/state/turn-action-ink.ts` | Base turn-action ink limit is one. Extra allowance comes from temporary `additionalInkwellActions` and static `additional-inkwell` effects on controlled in-play cards. |
| `references/lorcana-simulator/packages/lorcana/lorcana-engine/src/runtime-moves/state/turn-metrics.ts` | Cards put into the inkwell are recorded once in turn metadata. |
| `references/lorcana-simulator/packages/lorcana/lorcana-engine/src/runtime-moves/state/runtime-card-derived.ts` | Inkwell candidate query uses chosen count one, owner `you`, and zones `hand` plus `discard`. |
| `references/lorcana-simulator/packages/lorcana/lorcana-engine/src/rules/derived-state.ts` | `canBePutInInkwell` is derived from source zone, actor/owner, turn ink limit, raw inkability, hand inkability grants, and discard inkability grants. |
| `references/lorcana-simulator/packages/lorcana/lorcana-engine/src/runtime-moves/effects/triggered-abilities.ts` | Triggered domain events are buffered and flushed into bag items at a resolution boundary. |
| `references/lorcana-simulator/packages/lorcana/lorcana-engine/src/runtime-moves/resolution/action-effects/pending-action-effects.ts` | Moves such as inking are blocked while pending action effects or bag entries are unresolved. |

## Previous v2 Mismatch

- `lorcana_engine_v2/moves/ink.py` only considered hand cards.
- It checked raw `definition.inkable` instead of Lorcanito-derived `runtimeCard.canBePutInInkwell`.
- It did not block on pending action effects or bag entries from validation/enumeration contexts.
- It did not include static `additional-inkwell` effects in the turn ink limit.
- It did not support Lorcanito discard inking grants.
- It emitted legacy `card.inked` behavior instead of Lorcanito `cardInked` plus triggered `ink` event flushing.
- It did not prove real-card trigger bag handoff from an actual printed ink trigger.

## Implemented v2 Files

| v2 file | Completed change |
| --- | --- |
| `lorcana_engine_v2/moves/ink.py` | Replaced the move with Lorcanito-aligned `PutCardIntoInkwellMove`, candidate lookup, turn-action ink helpers, metadata recording, logging, `cardInked` emission, and triggered bag flush. |
| `lorcana_engine_v2/resolution/pending.py` | Extended pending-effect checks so validation/enumeration contexts with `G` and `framework.state` are handled, matching move-context use. |
| `lorcana_engine_v2/rules/derived_state.py` | Added static `additional-inkwell` allowance to `derive_can_be_put_in_inkwell`, so runtime cards agree with the move turn-limit helper. |
| `lorcana_engine_v2/effects/triggered_abilities.py` | Corrected resolution-boundary finalization so runtime execution contexts retain card APIs while printed triggers are scanned. |
| `tests/v2/test_put_card_into_inkwell_move_v2.py` | Updated the existing inkwell command tests to assert Lorcanito `cardInked` payloads and metadata. |
| `tests/v2/test_put_card_into_inkwell_lorcanito_v2.py` | Added real-card Lorcanito parity tests for pending guard, Belle extra inkwell action, Hidden Inkcaster hand ink grant, Moana discard ink grant, and Gramma Tala ink trigger bag flush. |

## Exact Functions And Blocks Added Or Replaced

- `PUT_CARD_INTO_INKWELL`
- `BASE_TURN_ACTION_INK_LIMIT`
- `INKWELL_CANDIDATE_QUERY_DSL`
- `build_turn_action_ink_state`
- `get_temporary_additional_turn_action_ink_allowance`
- `get_static_additional_turn_action_ink_allowance`
- `get_additional_turn_action_ink_allowance`
- `get_turn_action_ink_limit`
- `can_ink_this_turn`
- `record_card_put_into_inkwell_this_turn`
- `PutCardIntoInkwellMove.available`
- `PutCardIntoInkwellMove.validate`
- `PutCardIntoInkwellMove.execute`
- `has_any_pending_effects` context support
- `validate_no_pending_effects` context support
- `derive_can_be_put_in_inkwell` static additional-inkwell support
- `finalize_resolution_boundary` runtime-context trigger scan fix

## Why The Fix Is Required

Lorcanito treats inking as a resource turn action that depends on runtime card derivation, pending-resolution state, turn metadata, static effects, zone ownership, and the triggered ability pipeline. A smaller hand-only patch would pass old tests but would be wrong for real cards such as Belle, Hidden Inkcaster, Moana, and Gramma Tala. The v2 kernel must therefore refactor the move around Lorcanito's runtime model instead of preserving the interim API shape.

## Parity Tests Added

`tests/v2/test_put_card_into_inkwell_lorcanito_v2.py` proves:

- Pending action effects reject inking with `EFFECT_PENDING` before card validation.
- Belle - Strange but Special (`6qy`) grants an additional inkwell action through a real static `additional-inkwell` effect.
- Hidden Inkcaster (`RqX`) grants hand inkability to a real non-inkable card (`5XS`).
- Moana - Curious Explorer (`wRv`) grants discard inking for a normally inkable card (`XGm`).
- Gramma Tala - Spirit of the Ocean (`0Rd`) sees an `ink` trigger from a real `cardInked` action and creates a bag item.

`tests/v2/test_put_card_into_inkwell_move_v2.py` proves:

- Main-phase legal move enumeration exposes `putCardIntoInkwell` when a real inkable card is in hand.
- Execution moves the card to `inkwell:<player>`, records both turn-metadata ledgers, patches `ready` plus `faceDown`, creates a reveal window, logs `lorcana.card.inked`, and emits `cardInked`.
- Second ink is rejected without extra allowance.
- Non-priority players and missing card input are rejected through the command envelope path.

## Commands And Expected Results

```bash
pytest -q tests/v2/test_put_card_into_inkwell_move_v2.py tests/v2/test_put_card_into_inkwell_lorcanito_v2.py
```

Expected and observed:

```text
12 passed
```

```bash
pytest -q tests/v2/test_triggered_abilities_lorcanito_v2.py tests/v2/test_resolve_bag_lorcanito_v2.py tests/v2/test_put_card_into_inkwell_move_v2.py tests/v2/test_put_card_into_inkwell_lorcanito_v2.py
```

Expected and observed:

```text
15 passed
```

```bash
pytest -q tests/v2
pytest --collect-only tests/v2 | tail -n 5
python -m compileall -q lorcana_engine_v2 tests/v2
```

Expected and observed:

```text
114 passed
114 tests collected
Compileall passed
```

## Parity Proof

- Source zones match Lorcanito's inkwell candidate query: hand plus discard.
- Inking is unavailable when pending effects or bag entries exist.
- Card legality uses the runtime card's derived `canBePutInInkwell`.
- Turn ink limit matches Lorcanito's base-one plus additional allowances model.
- Zone movement, card meta, reveal window, public log key, turn metadata, `cardInked` domain event, triggered `ink` event, and bag flush all happen in one command execution boundary.
- Real normalized Lorcanito card data proves the behavior. No Phase 9 parity claim is based only on synthetic cards.

## Edge Cases And Risks

- This phase proves one core turn action, not broad card support.
- The action-effect resolver remains foundational. Later cards may need more Lorcanito effect variants before their triggered inkwell abilities can fully resolve.
- Trigger filtering is still not exhaustive across all Lorcanito variants. Phase 10 and Phase 11 must continue extending generic trigger/effect support from Lorcanito source and real-card tests.
- Do not move unsupported-card reports based only on a card loading or entering an inkwell. Reports move only after real gameplay behavior is proven end to end.
