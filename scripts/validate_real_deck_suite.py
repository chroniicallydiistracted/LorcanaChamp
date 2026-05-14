from __future__ import annotations

import argparse
import json
from pathlib import Path

from lorcana_bot.decks.deck_loader import load_resolved_deck_dir
from lorcana_bot.decks.deck_validator import validate_resolved_deck


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate resolved real Core deck suite.")
    parser.add_argument("--resolved-deck-dir", default="data/decks/resolved/real_core")
    parser.add_argument("--out", default="data/decks/reports/real_deck_suite_validation.json")
    args = parser.parse_args()
    decks = load_resolved_deck_dir(args.resolved_deck_dir)
    rows = [{"deck_id": deck.id, "validation": validate_resolved_deck(deck)} for deck in decks]
    report = {
        "schema_version": 1,
        "deck_count": len(decks),
        "valid_decks": sum(1 for row in rows if row["validation"]["valid"]),
        "invalid_decks": sum(1 for row in rows if not row["validation"]["valid"]),
        "decks": rows,
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    print(f"deck count: {report['deck_count']}")
    print(f"valid decks: {report['valid_decks']}")
    print(f"invalid decks: {report['invalid_decks']}")


if __name__ == "__main__":
    main()
