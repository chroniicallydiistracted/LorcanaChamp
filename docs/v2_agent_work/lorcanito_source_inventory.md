# Lorcanito Source Inventory For v2 Kernel Parity

Workspace commit: `1c0e49ff938a2f3e4bf9a9d26773b7c32e173a1a`

Reference root: `references/lorcana-simulator`

The reference checkout has no nested `.git` metadata in this workspace, so the source lock is the parent LorcanaChamp workspace commit plus these explicit paths.

## Package Roots

| Path | Package | Confirmed role |
| --- | --- | --- |
| `references/lorcana-simulator/package.json` | root workspace | `lorcana-engine` workspace using `pnpm@10.33.0`, Node `24.12.0`, and shared scripts for lint/typecheck/test/build. |
| `references/lorcana-simulator/packages/lorcana/lorcana-engine/package.json` | `@tcg/lorcana-engine` | Runtime engine package. Exports the engine, automation, testing, support probe, and runtime internals. |
| `references/lorcana-simulator/packages/lorcana/lorcana-cards/package.json` | `@tcg/lorcana-cards` | Card definition/data package. Exports card data, generated sets, sync tools, and deck-list resolver. |
| `references/lorcana-simulator/packages/lorcana/lorcana-simulator` | simulator app | UI, tests, strategy tests, regression tests, and behavior corpus. |

## Phase 0 And Phase 1 Source Files

| File | Confirmed behavior |
| --- | --- |
| `references/lorcana-simulator/packages/lorcana/lorcana-engine/src/index.ts` | Public engine package entry point. |
| `references/lorcana-simulator/packages/lorcana/lorcana-engine/src/engine-initialization.ts` | Resolves static resources from card maps, card catalog, card instances, and Lorcana zones before runtime creation. |
| `references/lorcana-simulator/packages/lorcana/lorcana-engine/src/core/runtime/static-resources.ts` | Defines `CardsMaps`, immutable card catalog/instance registry/resource refs, Lorcanito `cards-maps` ref hashing, validation, and round-trip conversion. |
| `references/lorcana-simulator/packages/lorcana/lorcana-engine/src/runtime-game/definition.ts` | Wires static resources into Lorcana runtime config and board setup. |
| `references/lorcana-simulator/packages/lorcana/lorcana-engine/src/zones/runtime-zone-config.ts` | Defines Lorcana runtime zones used by static resource initialization. |
| `references/lorcana-simulator/packages/lorcana/lorcana-cards/src/index.ts` | Card package entry point. |
| `references/lorcana-simulator/packages/lorcana/lorcana-cards/src/cards/catalog-data.ts` | Catalog construction source. |
| `references/lorcana-simulator/packages/lorcana/lorcana-cards/src/cards/sync.ts` | Card sync/normalization boundary. |
| `references/lorcana-simulator/packages/lorcana/lorcana-cards/src/cards/types.ts` | Source card definition schema. |
| `references/lorcana-simulator/packages/lorcana/lorcana-cards/src/data/canonical-cards.json` | Canonical normalized card data source in Lorcanito. |
| `references/lorcana-simulator/packages/lorcana/lorcana-cards/src/utils/fromDeckToCardInstances.ts` | Converts deck inputs to Lorcanito-style instance maps. |

## Confirmed Static Resource Contract

Lorcanito `CardsMaps` raw shape:

```json
{
  "cardInstances": {
    "instance-id": "definition-id"
  },
  "owners": {
    "player-id": ["instance-id"]
  }
}
```

Confirmed rules from `static-resources.ts`:

- `cardInstances` maps immutable runtime instance IDs to immutable card definition IDs.
- `owners` maps each owner ID to the ordered instance IDs owned by that player.
- Duplicate ownership is invalid.
- An owner reference to an unknown instance ID is invalid.
- An instance without an owner is invalid.
- Static resources are invalid when a card instance references a definition missing from the catalog.
- Mutable card state never belongs in card definitions or static resources.
- `cards-maps` refs are computed from sorted `cardInstances` entries and sorted owner entries, while preserving each owner's instance order.

## v2 Phase 0/1 Files

| File | Purpose |
| --- | --- |
| `tests/v2/parity_fixtures/README.md` | Fixture policy for real-card parity data. |
| `tests/v2/parity_fixtures/cards_maps_two_players.json` | Minimal two-player Lorcanito-style real-card fixture. |
| `tests/v2/test_parity_fixtures_v2.py` | Ensures the fixture uses real normalized/Lorcanito-derived card IDs and builds static resources. |
| `tests/v2/test_static_resources_lorcanito_contract_v2.py` | Ensures v2 static resource behavior matches Lorcanito's contract. |
| `lorcana_engine_v2/core/static_resources.py` | Python static resource implementation aligned to Lorcanito's `static-resources.ts`. |

