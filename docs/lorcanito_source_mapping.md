# Lorcanito Source Mapping

## Purpose

Milestone B0 imports Lorcanito card source logic into Python-native data models. Lorcanito TypeScript is treated as build-time/reference input only. Python bot execution and ML training consume generated JSON artifacts plus Python modules; they do not import or execute Lorcanito packages.

## Source Paths Used

The extractor scans these source categories:

- `packages/lorcana/lorcana-cards/src/cards/**/*.ts`
- `packages/lorcana/lorcana-cards/src/helpers/**/*.ts`
- `packages/lorcana/lorcana-types/src/**/*.ts`
- `packages/lorcana/lorcana-engine/src/runtime-moves/**/*.ts`
- `packages/lorcana/lorcana-engine/src/runtime-moves/resolution/**/*.ts`
- `packages/lorcana/lorcana-engine/src/rules/**/*.ts`
- `packages/lorcana/lorcana-engine/src/targeting/**/*.ts`
- `packages/lorcana/lorcana-engine/src/triggered-abilities/**/*.ts`
- `packages/lorcana/lorcana-engine/src/automation/**/*.ts`

`data/lorcanito_extracted/source_file_index.json` records every examined file category and extraction summary.

## Extraction Architecture

`scripts/extract_lorcanito_source_cards.py` is the required path. It statically scans TypeScript, extracts exported card object literals, resolves simple object-spread reprints from already extracted base cards, normalizes keyword helper calls such as `singer(5)`, and writes deterministic JSON.

`tools/lorcanito_export/export_lorcanito_card_source.ts` is optional for environments that can execute Lorcanito with Bun/TypeScript. The Python runtime does not use it.

## Generated Artifacts

Artifacts are written under `data/lorcanito_extracted/`:

- `manifest.json`
- `cards.normalized.json`
- `abilities.schema_inventory.json`
- `effects.schema_inventory.json`
- `targets.schema_inventory.json`
- `conditions.schema_inventory.json`
- `costs.schema_inventory.json`
- `triggers.schema_inventory.json`
- `mapping_coverage.json`
- `unsupported_patterns.json`
- `source_file_index.json`
- `unknown_ability_audit.json`
- `unknown_ability_patterns.json`
- `helper_call_inventory.json`
- `parser_gap_report.json`
- `extraction_fidelity_report.json`

## Python Source DSL Model

The source truth lives in `lorcana_bot/card_logic/`:

- `SourceAbilityDef`
- `SourceEffectDef`
- `SourceTargetDef`
- `SourceConditionDef`
- `SourceCostDef`
- `SourceTriggerDef`
- `SourceStaticEffectDef`
- `SourceReplacementEffectDef`
- `MappingStatus`
- `ExecutionStatus`

`CardDef` now has source fields (`source_abilities`, `source_effects`, `source_triggers`, `source_static_abilities`, `source_replacement_abilities`, `raw_lorcanito_source`) and executable projection fields (`keywords`, `keyword_defs`, `effects`, `triggers`, `activated_abilities`, `unsupported_abilities`).

## Status Terms

`structurally_mapped` means a Lorcanito object was converted into a Python source dataclass with raw data preserved.

`executable` means the current Python engine has a compatible resolver path for the ability/effect/target/condition/cost and its resolution requirements.

`mapped_not_executable` means the object is understood structurally but is deliberately source-only because engine behavior is not implemented.

`unsupported` means the mapper does not yet understand that DSL node shape. The raw object remains attached with a reason.

## Text Mapping Is Fallback Only

The previous importer inferred effects from card text. That remains useful as a compatibility report, but source mapping now reads Lorcanito structured ability/effect/target/condition/cost/trigger objects first. Text patterns are not authoritative for gameplay legality.

## Regenerate Artifacts

```bash
python scripts/extract_lorcanito_source_cards.py \
  --source-root /home/andre/LorcanaChamp/lorcanito-full-src-code \
  --out-dir data/lorcanito_extracted
```

## Run Mapping Report

```bash
python scripts/report_lorcanito_source_mapping.py \
  --source-json data/lorcanito_extracted/cards.normalized.json \
  --out data/lorcanito_extracted/mapping_coverage.json \
  --print-summary
```

## Milestone B1 Extraction Fidelity Audit

Milestone B1 audits extraction fidelity before any new gameplay execution work. It classifies every preserved unknown ability shape, inventories helper calls, reports parser gaps, and produces a gate report for the next milestone.

Run the full B1 workflow after regenerating extraction artifacts:

```bash
python scripts/audit_unknown_lorcanito_abilities.py \
  --source-json data/lorcanito_extracted/cards.normalized.json \
  --source-root /home/andre/LorcanaChamp/lorcanito-full-src-code \
  --out data/lorcanito_extracted/unknown_ability_audit.json \
  --patterns-out data/lorcanito_extracted/unknown_ability_patterns.json \
  --print-summary

python scripts/report_lorcanito_extraction_fidelity.py \
  --source-json data/lorcanito_extracted/cards.normalized.json \
  --unknown-audit data/lorcanito_extracted/unknown_ability_audit.json \
  --patterns data/lorcanito_extracted/unknown_ability_patterns.json \
  --parser-gaps data/lorcanito_extracted/parser_gap_report.json \
  --out data/lorcanito_extracted/extraction_fidelity_report.json \
  --print-summary
```

B1 normalizes repeated keyword helper shorthands such as bare `evasive`, `bodyguard`, `ward`, `support`, `rush`, `reckless`, `vanish`, and `alert`, plus helper calls such as `singer(5)`, `resist(2)`, `challenger(3)`, `shift(3)`, `shift("Name", 3)`, `singTogether(10)`, and `boost(1)`. Static helper objects discovered in Lorcanito helper files, such as `stoneByDay` and `underdog`, are preserved structurally as source-only static abilities.

The audit reports classification, confidence, recommended action, raw object, raw snippet, helper calls, and pattern fingerprint. It does not make static, triggered, activated, replacement, or unsupported mechanics executable.

## Add Support For A New `effect.type`

Add the source kind to `KNOWN_EFFECT_KINDS` in `lorcana_bot/importers/lorcanito_source_mapper.py`. If the Python engine can execute it, add a conservative entry to `ENGINE_EFFECT_MAP`, implement resolver behavior if needed, and add projection-policy tests plus at least one mapper test.

## Add Support For A New `condition.type`

Extend `map_raw_condition` to preserve the condition-specific fields. Add it to `EXECUTABLE_CONDITIONS` only after the Python condition evaluator can execute it correctly. Unsupported conditions must keep the parent ability source-only.

## Add Support For A New Target Selector

Extend `map_raw_target` for structural preservation first. Add an executable alias or selector mapping only when target owner/controller/chooser semantics are implemented by the engine. Do not collapse those actor concepts into one field.

## Add Support For A New Cost Type

Extend `map_raw_cost` structurally. Add projection to `AbilityCostDef` only after the engine can validate and pay the cost. Composite costs should remain `SourceCostDef(kind="components")` until every component is executable.

## Future Milestones

- Milestone B: activated ability cost validation and payment.
- Milestone C: real bag and trigger ordering/resolution.
- Milestone D: Shift, Singer, Songs, and song-specific strategic handling.
- Milestone E: dynamic static effects and replacement/prevention layers.
- Milestone F: ML training that consumes Python-native card logic and generated JSON without Lorcanito runtime dependencies.
