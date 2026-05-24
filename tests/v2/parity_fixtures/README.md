# v2 Parity Fixtures

Fixtures in this directory must use Lorcanito-style raw data and real normalized/Lorcanito-derived card definition IDs.

Rules:

- `cardInstances` maps runtime instance IDs to real card definition IDs from `data/lorcanito_runtime_extracted/cards.normalized.json`.
- `owners` maps player IDs to the ordered instance IDs owned by that player.
- Synthetic cards are not allowed in this directory.
- Loading a fixture proves only static/card-map integrity. It does not prove gameplay support for the cards.
- Unsupported card reports may move only after an integration/parity test proves the card loads, maps, classifies, materializes, and affects gameplay through implemented Lorcanito engine logic.

