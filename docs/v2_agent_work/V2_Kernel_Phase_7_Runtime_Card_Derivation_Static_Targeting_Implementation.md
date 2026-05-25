# V2 Kernel Phase 7 Runtime Card Derivation And Static Targeting

Status: complete.

## Lorcanito Source Inspected

| Lorcanito file | Confirmed behavior ported |
| --- | --- |
| `references/lorcana-simulator/packages/lorcana/lorcana-engine/src/core/runtime/card-runtime.ts` | Runtime card views are built from instance record, card definition, zone index, owner/controller, meta, and derived fields. Base fields win over derived fields. Query APIs expose `get`, `require`, `getDefinition`, `getDefinitionById`, `getMeta`, `inZone`, and `queryRuntime`. |
| `references/lorcana-simulator/packages/lorcana/lorcana-engine/src/runtime-moves/state/runtime-card-derived.ts` | Lorcana runtime card derivation uses a static effect registry and returns strength, willpower, lore, costs, damage, exerted/drying, inkability, keyword flags, classifications, temporary effects, and granted abilities. |
| `references/lorcana-simulator/packages/lorcana/lorcana-engine/src/rules/derived-state.ts` | Derived stats combine printed values, static modifiers, floors, cost modifiers, damage/meta, inkwell eligibility, keyword/classification grants, and temporary effects. |
| `references/lorcana-simulator/packages/lorcana/lorcana-engine/src/rules/static-effect-registry.ts` | Static effects are materialized into `byTarget`, `byPlayer`, `global`, and `bySource` indexes from active in-play source cards. |
| `references/lorcana-simulator/packages/lorcana/lorcana-engine/src/runtime-moves/rules/static-ability-utils.ts` | Static conditions and target matching route through shared condition and target resolver logic. |
| `references/lorcana-simulator/packages/lorcana/lorcana-engine/src/rules/condition-evaluator.ts` | Conditions are typed runtime variants, including logical, turn, resource, count, damage, status, target-query, and stat-threshold variants. |
| `references/lorcana-simulator/packages/lorcana/lorcana-engine/src/targeting/runtime/target-resolver.ts` | Target descriptors resolve using actor, source, owner/controller, zones, card types, filters, selected targets, and strict unknown-filter policy. |
| `references/lorcana-simulator/packages/lorcana/lorcana-engine/src/targeting/runtime/target-availability.ts` | Target availability is derived from target analysis and explicit selection requirements. Full prompt availability remains later effect-resolution work. |

## v2 State Before Phase 7

| v2 file | Previous behavior |
| --- | --- |
| `lorcana_engine_v2/rules/queries.py` | Returned mostly static definitions plus raw meta and used snake-case runtime card fields. |
| `lorcana_engine_v2/rules/derived_state.py` | Read legacy flat static materialization and exposed only strength, willpower, lore, and uppercase keyword helper output. |
| `lorcana_engine_v2/registries/static_registry.py` | Returned a tuple of materialized effects instead of Lorcanito indexed registries. |
| `lorcana_engine_v2/rules/condition_evaluator.py` | Supported only a small subset of logical and damage conditions. |
| `lorcana_engine_v2/rules/target_resolver.py` | Resolved a narrow play-zone-only target subset and used legacy runtime card fields. |
| `lorcana_engine_v2/core/context.py` | Card runtime APIs returned non-derived query cards. |

## Implemented v2 Files

| v2 file | Phase 7 implementation |
| --- | --- |
| `lorcana_engine_v2/rules/queries.py` | Added Lorcanito-shaped `RuntimeCardBase`, `RuntimeCard`, `RuntimeCardDeriver`, `create_lorcana_runtime_card_deriver`, derived runtime-card construction, zone query helpers, and `queryRuntime`. |
| `lorcana_engine_v2/rules/derived_state.py` | Added `derive_runtime_card_fields`, `derive_can_be_put_in_inkwell`, and helper projections for effective stats, play/move cost, damage, exerted/drying, keywords, classifications, restrictions, and inkwell eligibility. |
| `lorcana_engine_v2/registries/static_registry.py` | Added `StaticEffectRegistry` with `byTarget`, `byPlayer`, `globalEffects`, `bySource`, accessors, and `StaticRegistry.build`. |
| `lorcana_engine_v2/rules/condition_evaluator.py` | Expanded condition support for foundational Lorcanito variants used by real static cards and target queries. |
| `lorcana_engine_v2/rules/target_resolver.py` | Expanded target resolution over owner-scoped zones, owner/controller gates, card types, filters, source/self, exclude-self, and strict unknown filters. |
| `lorcana_engine_v2/core/context.py` | Card runtime read/write APIs now return derived Lorcanito-shaped runtime cards and receive actor context. |
| `lorcana_engine_v2/runtime_game/definition.py` | Runtime config now exposes the Lorcanito runtime-card deriver. |

## Behavior Proven

- Runtime card projection uses `instanceId`, `definitionId`, `ownerID`, `controllerID`, `zoneID`, `zoneIndex`, meta, and definition as Lorcanito-shaped base fields.
- Runtime card projection derives full name, effective stats, damage, exerted state, drying state, keywords, classifications, and inkwell eligibility.
- Static registry indexes real source effects by target and source with source definition ID, ability index/name, kind, and payload.
- Real static abilities from normalized Lorcanito data materialize correctly for:
  - Chi-Fu lore modifier.
  - Mr. Incredible filtered-count strength modifier.
  - Tamatoa item-count lore modifier.
  - Ling classification-target strength modifier.
  - Aurora keyword grant excluding self.
  - Donald Duck damage-on-self lore modifier.
- Condition evaluator reads play-zone card counts, classifications, target queries, and meta damage.
- Target resolver matches owner, zones, card type, filters, exclude-self, and opponent ownership using real cards.

## Tests

Added:

- `tests/v2/test_runtime_card_derived_lorcanito_phase7_v2.py`
- `tests/v2/test_static_effect_registry_lorcanito_phase7_v2.py`
- `tests/v2/test_conditions_and_targeting_lorcanito_phase7_v2.py`

Updated:

- `tests/v2/test_card_runtime_query_api_v2.py`
- `tests/v2/test_first_real_card_parity_v2.py`
- `tests/v2/test_lorcanito_runtime_contexts_v2.py`
- `tests/v2/test_static_registry_v2.py`

Commands run:

```bash
pytest -q tests/v2/test_card_runtime_query_api_v2.py tests/v2/test_first_real_card_parity_v2.py tests/v2/test_lorcanito_runtime_contexts_v2.py tests/v2/test_runtime_card_derived_lorcanito_phase7_v2.py tests/v2/test_static_effect_registry_lorcanito_phase7_v2.py tests/v2/test_conditions_and_targeting_lorcanito_phase7_v2.py
pytest -q tests/v2
python -m compileall -q lorcana_engine_v2 tests/v2
pytest --collect-only tests/v2 | tail -n 5
```

Observed:

```text
19 passed
98 passed
98 tests collected
```

## Parity Proof

Phase 7 moves v2 away from legacy static helper assumptions and into Lorcanito's runtime-card model:

1. Static resources and zone index produce the runtime card base view.
2. Static registry scans active in-play source cards.
3. Registry indexes effects by target/player/global/source.
4. Derived state consumes that registry to project effective runtime card fields.
5. Conditions and targets share the same query/zone/meta context as static derivation.

This remains headless engine logic. No Lorcanito runtime instance is imported or executed.

## Remaining Risks

- Condition and target variant support is foundational, not exhaustive. Later effect and move phases must add missing variants only against Lorcanito source and parity tests.
- Static registry does not yet implement Lorcanito's full multi-pass suppression, keyword-augmented retargeting, replacement, and all property/cost edge cases.
- Runtime card derivation now supports the fields needed by upcoming move work, but real cards must not be moved to supported gameplay status until their effects execute in integration/parity tests.
