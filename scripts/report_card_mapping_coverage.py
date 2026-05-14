from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lorcana_bot.cards import load_card_database
from lorcana_bot.importers.ability_mapper import build_ability_mapping_report


def main() -> None:
    parser = argparse.ArgumentParser(description="Report card ability mapping coverage.")
    parser.add_argument("--database", choices=["demo", "imported"], default="imported")
    parser.add_argument("--card-data-path", default="data/cards")
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()

    db = load_card_database("demo" if args.database == "demo" else "imported", card_data_path=args.card_data_path)
    report = build_ability_mapping_report(db)
    data = report.to_dict()
    print(f"total cards: {report.total_cards}")
    print(f"fully mapped cards: {report.fully_mapped_cards}")
    print(f"partially mapped cards: {report.partially_mapped_cards}")
    print(f"classified-only cards: {report.classified_only_cards}")
    print(f"unsupported ability records: {report.unsupported_records}")
    print("top unsupported patterns:")
    for item in report.top_unsupported_patterns[:10]:
        print(f"- {item['count']}: {item['pattern']}")
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(data, sort_keys=True, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
