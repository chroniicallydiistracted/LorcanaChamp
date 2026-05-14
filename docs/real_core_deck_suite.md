# Real Core Deck Suite

Milestone B1.5 resolves the local `data/decks/real_core/*.json` fixtures against `data/lorcanito_extracted/cards.normalized.json`. The workflow uses only Python JSON artifacts and the Python-native Lorcanito source importer; it does not execute Lorcanito TypeScript.

## Workflow

```bash
python3 scripts/resolve_real_deck_suite.py \
  --deck-dir data/decks/real_core \
  --source-json data/lorcanito_extracted/cards.normalized.json \
  --out-dir data/decks/resolved/real_core

python3 scripts/validate_real_deck_suite.py \
  --resolved-deck-dir data/decks/resolved/real_core \
  --out data/decks/reports/real_deck_suite_validation.json

python3 scripts/report_real_deck_mapping_coverage.py \
  --resolved-deck-dir data/decks/resolved/real_core \
  --out data/decks/reports/real_deck_suite_mapping_coverage.json \
  --print-summary

python3 scripts/run_real_deck_gauntlet.py \
  --resolved-deck-dir data/decks/resolved/real_core \
  --strategy-a deck-aware-lore-race \
  --strategy-b board-control \
  --only-fully-executable \
  --games-per-pair 2 \
  --max-actions 300 \
  --out data/decks/reports/real_deck_suite_gauntlet.json
```

The safe gauntlet runs only fully executable decks by default. Partial diagnostic runs require `--allow-partial` and are marked `not_strength_valid`.

## Current Outcome

The suite currently resolves 11 of 12 decks completely. One raw card row remains unresolved: `Malicious, Mean, and Scary` in `es_control_i_hate_dogs_imola_2026_04_11`.

No deck is marked fully executable. The highest-priority blocker category is real bag and trigger execution.
