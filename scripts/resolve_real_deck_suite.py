from __future__ import annotations

import argparse

from lorcana_bot.decks.deck_resolver import resolve_deck_suite


def main() -> None:
    parser = argparse.ArgumentParser(description="Resolve real Core deck suite against Lorcanito source cards.")
    parser.add_argument("--deck-dir", default="data/decks/real_core")
    parser.add_argument("--source-json", default="data/lorcanito_extracted/cards.normalized.json")
    parser.add_argument("--out-dir", default="data/decks/resolved/real_core")
    args = parser.parse_args()
    summary = resolve_deck_suite(args.deck_dir, args.source_json, args.out_dir)
    print(f"deck count: {summary['deck_count']}")
    print(f"resolved decks: {summary['resolved_decks']}")
    print(f"invalid decks: {summary['invalid_decks']}")
    print(f"unresolved cards: {len(summary['unresolved_cards'])}")
    print(f"ambiguous cards: {len(summary['ambiguous_cards'])}")


if __name__ == "__main__":
    main()
