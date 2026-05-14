from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lorcana_bot.cards import load_card_database
from lorcana_bot.importers.lorcanito_source_importer import import_lorcanito_source_cards


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare text/official import coverage against Lorcanito source import.")
    parser.add_argument("--text-card-data", type=Path, default=Path("data/cards"))
    parser.add_argument("--source-json", type=Path, default=Path("data/lorcanito_extracted/cards.normalized.json"))
    parser.add_argument("--out", type=Path, default=Path("data/lorcanito_extracted/text_vs_source_comparison.json"))
    args = parser.parse_args()
    data = compare(args.text_card_data, args.source_json)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
    print(f"text cards: {data['text_card_count']}")
    print(f"source cards: {data['source_card_count']}")
    print(f"source-only cards: {len(data['source_only_card_ids'])}")
    print(f"text-only cards: {len(data['text_only_card_ids'])}")


def compare(text_card_data: Path, source_json: Path) -> dict:
    try:
        text_db = load_card_database("imported", card_data_path=text_card_data)
        text_cards = {card.id: card for card in text_db.all_cards()}
        text_error = None
    except Exception as exc:
        text_cards = {}
        text_error = str(exc)
    source_db, _ = import_lorcanito_source_cards(source_json)
    source_cards = {card.id: card for card in source_db.all_cards()}
    common = sorted(set(text_cards) & set(source_cards))
    metadata_diffs = []
    structured_advantages = []
    blockers_not_visible_from_text = []
    for card_id in common:
        text_card = text_cards[card_id]
        source_card = source_cards[card_id]
        diffs = {}
        for field in ("full_name", "cost", "inkable", "card_type"):
            if getattr(text_card, field) != getattr(source_card, field):
                diffs[field] = {"text": getattr(text_card, field), "source": getattr(source_card, field)}
        if diffs:
            metadata_diffs.append({"id": card_id, "diffs": diffs})
        if text_card.unsupported_abilities and source_card.source_abilities:
            structured_advantages.append(card_id)
        if source_card.unsupported_abilities:
            blockers_not_visible_from_text.append(
                {
                    "id": card_id,
                    "blockers": sorted({record.get("reason", "unknown") for record in source_card.unsupported_abilities}),
                }
            )
    return {
        "schema_version": 1,
        "text_import_error": text_error,
        "text_card_count": len(text_cards),
        "source_card_count": len(source_cards),
        "text_only_card_ids": sorted(set(text_cards) - set(source_cards)),
        "source_only_card_ids": sorted(set(source_cards) - set(text_cards)),
        "metadata_differences": metadata_diffs[:200],
        "text_unsupported_but_source_structured": structured_advantages[:500],
        "source_blockers_not_visible_from_text": blockers_not_visible_from_text[:500],
    }


if __name__ == "__main__":
    main()
