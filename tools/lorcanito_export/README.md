# Optional Lorcanito TypeScript Export

The Python runtime does not use this script. It is a build-time aid for environments
where the Lorcanito monorepo can execute with Bun/TypeScript.

Milestone B0 uses `scripts/extract_lorcanito_source_cards.py` as the required path
because it scans TypeScript source without importing or executing Lorcanito packages.
