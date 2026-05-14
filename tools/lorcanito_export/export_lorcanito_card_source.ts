import { writeFileSync } from "node:fs";
import { allCards } from "../../lorcanito-full-src-code/packages/lorcana/lorcana-cards/src/cards/catalog-data";

const out = process.argv[2] ?? "data/lorcanito_extracted/cards.normalized.json";
writeFileSync(out, JSON.stringify({ schema_version: 1, cards: allCards }, null, 2));

