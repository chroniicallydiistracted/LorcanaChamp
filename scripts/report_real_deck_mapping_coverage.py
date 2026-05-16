from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Add repo root to path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from lorcana_bot.decks.deck_loader import load_resolved_deck_dir
from lorcana_bot.decks.deck_mapping_report import build_suite_mapping_report
from lorcana_bot.importers.lorcanito_source_importer import import_lorcanito_source_cards


def main() -> None:
    parser = argparse.ArgumentParser(description="Report real deck mapping coverage.")
    parser.add_argument("--resolved-deck-dir", default="data/decks/resolved/real_core")
    parser.add_argument("--source-json", default="data/lorcanito_extracted/cards.normalized.json")
    parser.add_argument("--out", default="data/decks/reports/real_deck_suite_mapping_coverage.json")
    parser.add_argument("--print-summary", action="store_true")
    args = parser.parse_args()

    # Load card definitions
    source_path = Path(args.source_json)
    card_defs = {}
    if source_path.exists():
        db, _ = import_lorcanito_source_cards(source_path)
        card_defs = {card.id: card for card in db.all_cards()}

    report = build_suite_mapping_report(load_resolved_deck_dir(args.resolved_deck_dir), card_defs)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    if args.print_summary:
        print(f"total decks: {report['total_decks']}")
        print(f"valid decks: {report['valid_decks']}")
        print(f"fully executable decks: {report['fully_executable_decks']}")
        print(f"recommended next milestone: {report['recommended_next_milestone']}")
        for row in report["top_blockers_by_copies"][:10]:
            print(f"{row['count']:4d} {row['blocker']}")


if __name__ == "__main__":
    main()
