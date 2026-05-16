#!/usr/bin/env python3
"""Report trigger blockers for real deck suite."""

import argparse
import json
import sys
from pathlib import Path
from typing import Any

# Add repo root to path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from lorcana_bot.decks.deck_loader import load_resolved_deck_dir
from lorcana_bot.decks.trigger_blocker_report import (
    build_milestone_recommendation,
    build_projection_failures,
    build_trigger_audit_rows,
    build_trigger_summary,
)
from lorcana_bot.importers.lorcanito_source_importer import import_lorcanito_source_cards


def resolved_deck_to_dict(deck) -> dict[str, Any]:
    """Convert ResolvedDeck dataclass to dict for reporting."""
    from dataclasses import asdict
    result = asdict(deck)
    # Convert nested dataclasses
    result["cards"] = [
        _resolved_card_to_dict(card) for card in deck.cards
    ]
    return result


def _resolved_card_to_dict(card) -> dict[str, Any]:
    """Convert ResolvedDeckCard dataclass to dict."""
    from dataclasses import asdict
    return asdict(card)


def main():
    parser = argparse.ArgumentParser(description="Report trigger blockers for real decks")
    parser.add_argument(
        "--resolved-deck-dir",
        type=str,
        default="data/decks/resolved/real_core",
        help="Path to resolved deck directory",
    )
    parser.add_argument(
        "--source-json",
        type=str,
        default="data/lorcanito_extracted/cards.normalized.json",
        help="Path to source card JSON",
    )
    parser.add_argument(
        "--audit-out",
        type=str,
        default="data/decks/reports/trigger_blocker_audit.json",
        help="Output path for audit JSON",
    )
    parser.add_argument(
        "--summary-out",
        type=str,
        default="data/decks/reports/trigger_blocker_summary.json",
        help="Output path for summary JSON",
    )
    parser.add_argument(
        "--failures-out",
        type=str,
        default="data/decks/reports/trigger_projection_failures.json",
        help="Output path for failures JSON",
    )
    parser.add_argument(
        "--recommendation-out",
        type=str,
        default="data/decks/reports/next_engine_milestone_recommendation.json",
        help="Output path for recommendation JSON",
    )
    parser.add_argument(
        "--print-summary",
        action="store_true",
        help="Print summary to stdout",
    )

    args = parser.parse_args()

    # Load source database
    source_path = Path(args.source_json)
    if not source_path.exists():
        print(f"Error: Source JSON not found: {source_path}")
        return 1

    print(f"Loading source cards from {source_path}...")
    db, _ = import_lorcanito_source_cards(source_path)
    card_defs = {card.id: card for card in db.all_cards()}
    print(f"  Loaded {len(card_defs)} card definitions")

    # Load resolved decks
    resolved_path = Path(args.resolved_deck_dir)
    if not resolved_path.exists():
        print(f"Error: Resolved deck directory not found: {resolved_path}")
        return 1

    print(f"Loading resolved decks from {resolved_path}...")
    resolved_decks_raw = load_resolved_deck_dir(resolved_path)
    # Convert ResolvedDeck dataclasses to dicts for the report
    resolved_decks = [resolved_deck_to_dict(deck) for deck in resolved_decks_raw]
    print(f"  Loaded {len(resolved_decks)} resolved decks")

    # Build audit rows
    print("Building trigger audit rows...")
    audit_rows = build_trigger_audit_rows(resolved_decks, card_defs)
    print(f"  Found {len(audit_rows)} trigger rows")

    # Build audit report
    audit_report = {
        "schema_version": 1,
        "generated_from": {
            "resolved_deck_dir": str(resolved_path),
            "source_json": str(source_path),
            "mapping_report": "data/decks/reports/real_deck_suite_mapping_coverage.json",
        },
        "summary": {
            "deck_count": len(resolved_decks),
            "trigger_blocked_unique_cards": 0,
            "trigger_blocked_card_copies": 0,
            "broad_unsupported_trigger_copies": 0,
            "specific_trigger_blocker_copies": 0,
            "unclassified_trigger_blocker_copies": 0,
        },
        "rows": audit_rows,
    }

    # Update summary with actual counts
    blocked_rows = [r for r in audit_rows if r["projection_status"] != "projected"]
    audit_report["summary"]["trigger_blocked_unique_cards"] = len(set(r["card_id"] for r in blocked_rows))
    audit_report["summary"]["trigger_blocked_card_copies"] = sum(r["copy_weight"] for r in blocked_rows)
    audit_report["summary"]["broad_unsupported_trigger_copies"] = sum(
        r["copy_weight"] for r in blocked_rows
        if r.get("primary_blocker", "").startswith("unsupported_trigger")
        and ":" not in r.get("primary_blocker", "")
    )
    audit_report["summary"]["specific_trigger_blocker_copies"] = sum(
        r["copy_weight"] for r in blocked_rows
        if r.get("primary_blocker", "").startswith("unsupported_trigger:")
    )
    audit_report["summary"]["unclassified_trigger_blocker_copies"] = sum(
        r["copy_weight"] for r in blocked_rows
        if not r.get("primary_blocker")
    )

    # Write audit report
    audit_out_path = Path(args.audit_out)
    audit_out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(audit_out_path, "w", encoding="utf-8") as f:
        json.dump(audit_report, f, indent=2, sort_keys=True)
    print(f"  Written: {audit_out_path}")

    # Build summary report
    print("Building trigger summary...")
    summary_report = build_trigger_summary(audit_rows)
    summary_report["schema_version"] = 1

    summary_out_path = Path(args.summary_out)
    with open(summary_out_path, "w", encoding="utf-8") as f:
        json.dump(summary_report, f, indent=2, sort_keys=True)
    print(f"  Written: {summary_out_path}")

    # Build projection failures report
    print("Building projection failures report...")
    failures_report = build_projection_failures(audit_rows)
    failures_report["schema_version"] = 1

    failures_out_path = Path(args.failures_out)
    with open(failures_out_path, "w", encoding="utf-8") as f:
        json.dump(failures_report, f, indent=2, sort_keys=True)
    print(f"  Written: {failures_out_path}")

    # Build milestone recommendation
    print("Building milestone recommendation...")
    recommendation = build_milestone_recommendation(summary_report.get("summary", {}), audit_rows)

    recommendation_out_path = Path(args.recommendation_out)
    with open(recommendation_out_path, "w", encoding="utf-8") as f:
        json.dump(recommendation, f, indent=2, sort_keys=True)
    print(f"  Written: {recommendation_out_path}")

    # Print summary if requested
    if args.print_summary:
        print("\n" + "=" * 60)
        print("TRIGGER BLOCKER REPORT SUMMARY")
        print("=" * 60)

        summ = summary_report.get("summary", {})
        print(f"\nTotal trigger rows: {summ.get('total_trigger_rows', 0)}")
        print(f"Projected trigger rows: {summ.get('projected_trigger_rows', 0)}")
        print(f"Blocked trigger rows: {summ.get('blocked_trigger_rows', 0)}")
        print(f"Blocked trigger copies: {summ.get('blocked_trigger_copies', 0)}")
        print(f"Broad unsupported_trigger copies: {summ.get('broad_unsupported_trigger_copies', 0)}")

        print("\nTop blockers by copies:")
        for item in summary_report.get("by_primary_blocker_copies", [])[:10]:
            print(f"  {item['blocker']}: {item['copies']} copies, {item['unique_cards']} unique, {item['deck_presence']} decks")

        print("\nBy recommended engine work:")
        for item in summary_report.get("by_recommended_engine_work", [])[:10]:
            print(f"  {item['recommended_engine_work']}: {item['copies']} copies")

        print("\n" + "-" * 60)
        print(f"Recommended next milestone: {recommendation.get('recommended_next_milestone', 'unknown')}")
        print(f"Confidence: {recommendation.get('confidence', 'unknown')}")
        print(f"Reason: {recommendation.get('reason', 'unknown')}")
        print("=" * 60)

    print("\nDone!")
    return 0


if __name__ == "__main__":
    exit(main())