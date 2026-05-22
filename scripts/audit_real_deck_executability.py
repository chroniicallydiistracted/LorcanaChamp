#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

from lorcana_bot.decks.deck_loader import load_resolved_deck_dir
from lorcana_bot.decks.runtime_executability import classify_deck_runtime_support, load_current_card_defs


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit stale resolved-deck blockers against current Python runtime executability.")
    parser.add_argument("--resolved-deck-dir", default="data/decks/resolved/real_core")
    parser.add_argument("--source-json", default="data/lorcanito_extracted/cards.normalized.json")
    parser.add_argument("--out", default="data/decks/reports/real_deck_runtime_executability_audit.json")
    parser.add_argument("--print-summary", action="store_true")
    args = parser.parse_args()

    report = build_audit_report(args.resolved_deck_dir, args.source_json)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")

    if args.print_summary:
        print(f"decks audited: {report['total_decks']}")
        print(f"old fully executable decks: {report['deck_playability_before_counts'].get('fully_executable', 0)}")
        print(f"fresh fully executable decks: {report['deck_playability_after_counts'].get('fully_executable', 0)}")
        print(f"cards changed blocked->executable: {len(report['cards_changed_from_blocked_to_executable'])}")
        print(f"cards changed executable->blocked: {len(report['cards_changed_from_executable_to_blocked'])}")
        print("top remaining true blockers:")
        for row in report["remaining_true_blockers"][:10]:
            print(f"  {row['count']:3d} {row['blocker']}")


def build_audit_report(resolved_deck_dir: str | Path, source_json: str | Path) -> dict[str, Any]:
    decks = load_resolved_deck_dir(resolved_deck_dir)
    card_defs = load_current_card_defs(source_json)

    old_blockers = Counter()
    fresh_blockers = Counter()
    removed_stale = Counter()
    before_counts = Counter()
    after_counts = Counter()
    changed_blocked_to_executable: dict[str, dict[str, Any]] = {}
    changed_executable_to_blocked: dict[str, dict[str, Any]] = {}
    deck_rows = []

    for deck in decks:
        support = classify_deck_runtime_support(deck, card_defs)
        before_counts[deck.playability] += 1
        after_counts[support.playability] += 1
        deck_old = Counter()
        deck_fresh = Counter(support.blockers_by_copies)
        deck_removed = Counter(support.stale_blockers_ignored_by_copies)
        for card in deck.cards:
            for blocker in card.unsupported_blockers:
                old_blockers[blocker] += card.count
                deck_old[blocker] += card.count
        fresh_blockers.update(deck_fresh)
        removed_stale.update(deck_removed)

        result_by_id = {result.card_id: result for result in support.card_results}
        for card in deck.cards:
            result = result_by_id.get(card.card_id or card.raw_name)
            if result is None:
                continue
            was_blocked = bool(card.unsupported_blockers) or card.source_execution_status != "executable"
            is_blocked = bool(result.blockers) or result.status != "executable"
            key = result.card_id
            if was_blocked and not is_blocked:
                changed_blocked_to_executable.setdefault(
                    key,
                    {
                        "card_id": result.card_id,
                        "name": result.name,
                        "old_blockers": list(card.unsupported_blockers),
                        "fresh_blockers": list(result.blockers),
                        "decks": [],
                    },
                )["decks"].append(deck.id)
            if not was_blocked and is_blocked:
                changed_executable_to_blocked.setdefault(
                    key,
                    {
                        "card_id": result.card_id,
                        "name": result.name,
                        "old_blockers": list(card.unsupported_blockers),
                        "fresh_blockers": list(result.blockers),
                        "decks": [],
                    },
                )["decks"].append(deck.id)

        deck_rows.append(
            {
                "deck_id": deck.id,
                "deck_playability_before": deck.playability,
                "deck_playability_after": support.playability,
                "old_blockers_from_resolved_json": _counter_rows(deck_old),
                "fresh_blockers_from_current_carddef": _counter_rows(deck_fresh),
                "removed_stale_blockers": _counter_rows(deck_removed),
                "remaining_true_blockers": _counter_rows(deck_fresh),
            }
        )

    return {
        "schema_version": 1,
        "classification_source": "current_python_runtime",
        "total_decks": len(decks),
        "old_blockers_from_resolved_json": _counter_rows(old_blockers),
        "fresh_blockers_from_current_carddef": _counter_rows(fresh_blockers),
        "removed_stale_blockers": _counter_rows(removed_stale),
        "remaining_true_blockers": _counter_rows(fresh_blockers),
        "cards_changed_from_blocked_to_executable": sorted(changed_blocked_to_executable.values(), key=lambda row: row["card_id"]),
        "cards_changed_from_executable_to_blocked": sorted(changed_executable_to_blocked.values(), key=lambda row: row["card_id"]),
        "deck_playability_before_counts": dict(sorted(before_counts.items())),
        "deck_playability_after_counts": dict(sorted(after_counts.items())),
        "decks": sorted(deck_rows, key=lambda row: row["deck_id"]),
    }


def _counter_rows(counter: Counter[str]) -> list[dict[str, Any]]:
    return [{"blocker": key, "count": value} for key, value in sorted(counter.items(), key=lambda item: (-item[1], item[0]))]


if __name__ == "__main__":
    main()
