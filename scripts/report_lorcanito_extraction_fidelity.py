from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1
HIGH_COUNT_THRESHOLD = 5


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate Lorcanito source extraction fidelity report.")
    parser.add_argument("--source-json", type=Path, default=Path("data/lorcanito_extracted/cards.normalized.json"))
    parser.add_argument("--unknown-audit", type=Path, default=Path("data/lorcanito_extracted/unknown_ability_audit.json"))
    parser.add_argument("--patterns", type=Path, default=Path("data/lorcanito_extracted/unknown_ability_patterns.json"))
    parser.add_argument("--parser-gaps", type=Path, default=Path("data/lorcanito_extracted/parser_gap_report.json"))
    parser.add_argument("--out", type=Path, default=Path("data/lorcanito_extracted/extraction_fidelity_report.json"))
    parser.add_argument("--print-summary", action="store_true")
    args = parser.parse_args()

    report = build_extraction_fidelity_report(args.source_json, args.unknown_audit, args.patterns, args.parser_gaps)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    if args.print_summary:
        print(f"cards normalized: {report['cards_normalized']}")
        print(f"ability records: {report['ability_records']}")
        print(f"unknown ability records: {report['unknown_ability_records']} ({report['unknown_percentage']:.2f}%)")
        print(f"safe to proceed to B2: {report['safe_to_proceed_to_B2']}")
        for reason in report["blocking_reasons"]:
            print(f"blocker: {reason}")


def build_extraction_fidelity_report(
    source_json: str | Path,
    unknown_audit: str | Path,
    patterns: str | Path,
    parser_gaps: str | Path,
) -> dict[str, Any]:
    source = _read_json(source_json)
    audit = _read_json(unknown_audit)
    pattern_payload = _read_json(patterns)
    gap_payload = _read_json(parser_gaps)

    cards = source.get("cards", source if isinstance(source, list) else [])
    ability_records = sum(len(card.get("abilities", [])) for card in cards if isinstance(card, dict))
    unknown_count = int(audit.get("summary", {}).get("total_unknowns", 0))
    unknown_percentage = round((unknown_count / ability_records * 100.0) if ability_records else 0.0, 4)
    over_threshold = [item for item in pattern_payload.get("patterns", []) if int(item.get("count", 0)) >= HIGH_COUNT_THRESHOLD]
    gap_counts = gap_payload.get("summary", {}).get("by_gap_type", {})
    high_count_gaps = _high_count_blocking_gaps(gap_payload)
    recommended_extractor_fixes = _recommended_extractor_fixes(over_threshold, high_count_gaps)
    recommended_mapper_fixes = _recommended_mapper_fixes(over_threshold)
    blocking_reasons = _blocking_reasons(unknown_count, over_threshold, high_count_gaps)
    return {
        "schema_version": SCHEMA_VERSION,
        "cards_normalized": len(cards),
        "ability_records": ability_records,
        "unknown_ability_records": unknown_count,
        "unknown_percentage": unknown_percentage,
        "patterns_over_threshold": over_threshold,
        "recommended_extractor_fixes": recommended_extractor_fixes,
        "recommended_mapper_fixes": recommended_mapper_fixes,
        "safe_to_proceed_to_B2": not blocking_reasons,
        "blocking_reasons": blocking_reasons,
        "summary": {
            "unknowns_by_category": audit.get("summary", {}).get("by_inferred_category", {}),
            "unknowns_by_action": audit.get("summary", {}).get("by_recommended_action", {}),
            "parser_gaps_by_type": dict(sorted(gap_counts.items())),
            "parser_gaps_by_impact": gap_payload.get("summary", {}).get("by_impact", {}),
            "source_files_with_parser_gaps": gap_payload.get("summary", {}).get("source_files_with_gaps", 0),
        },
    }


def _recommended_extractor_fixes(patterns: list[dict[str, Any]], high_count_gaps: dict[str, int]) -> list[str]:
    fixes: set[str] = set()
    for pattern in patterns:
        action = pattern.get("recommended_action")
        category = pattern.get("inferred_category")
        if action == "scanner_fix" or category in {"parser_gap", "helper_unresolved", "spread_unresolved"}:
            fixes.add(f"Address {pattern['pattern_fingerprint']} ({pattern['count']} records).")
    for gap, count in high_count_gaps.items():
        fixes.add(f"Address parser gap {gap} ({count} records).")
    return sorted(fixes)


def _recommended_mapper_fixes(patterns: list[dict[str, Any]]) -> list[str]:
    fixes: set[str] = set()
    for pattern in patterns:
        if pattern.get("recommended_action") == "mapper_fix":
            fixes.add(f"Map {pattern['pattern_fingerprint']} as {pattern.get('inferred_category', 'unknown')} ({pattern['count']} records).")
    return sorted(fixes)


def _high_count_blocking_gaps(gap_payload: dict[str, Any]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for gap in gap_payload.get("gaps", []):
        if gap.get("impact") in {"lost_card", "lost_ability", "lost_effect", "lost_cost", "lost_target", "lost_condition"}:
            key = str(gap.get("gap_type") or "unknown")
            counts[key] = counts.get(key, 0) + 1
    return {key: value for key, value in sorted(counts.items()) if value >= HIGH_COUNT_THRESHOLD}


def _blocking_reasons(unknown_count: int, patterns: list[dict[str, Any]], high_count_gaps: dict[str, int]) -> list[str]:
    reasons: list[str] = []
    if unknown_count:
        unexplained = [
            pattern
            for pattern in patterns
            if pattern.get("inferred_category") == "unknown" or pattern.get("recommended_action") == "manual_review"
        ]
        if unexplained:
            reasons.append(f"{sum(int(item.get('count', 0)) for item in unexplained)} unknown ability records still require manual review.")
    for gap, count in sorted(high_count_gaps.items()):
        reasons.append(f"High-count parser gap remains: {gap} ({count}).")
    return reasons


def _read_json(path: str | Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
