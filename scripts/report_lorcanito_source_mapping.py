from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lorcana_bot.importers.lorcanito_source_report import write_mapping_coverage


def main() -> None:
    parser = argparse.ArgumentParser(description="Report Lorcanito source-structured mapping coverage.")
    parser.add_argument("--source-json", type=Path, default=Path("data/lorcanito_extracted/cards.normalized.json"))
    parser.add_argument("--out", type=Path, default=Path("data/lorcanito_extracted/mapping_coverage.json"))
    parser.add_argument("--print-summary", action="store_true")
    args = parser.parse_args()
    data = write_mapping_coverage(args.source_json, args.out)
    if args.print_summary:
        print(f"total cards: {data['total_cards']}")
        print(f"total abilities: {data['total_ability_records']}")
        print(f"ability type counts: {data['ability_type_counts']}")
        print(f"effect type counts: {data['effect_type_counts']}")
        print(f"trigger event counts: {data['trigger_event_counts']}")
        print(f"condition type counts: {data['condition_type_counts']}")
        print(f"target selector/alias counts: {data['target_type_counts']}")
        print(f"cost type counts: {data['cost_type_counts']}")
        print(f"fully structured cards: {data['fully_structured_cards']}")
        print(f"executable cards: {data['executable_cards']}")
        print(f"mapped-not-executable cards: {data['mapped_not_executable_cards']}")
        print(f"unsupported cards: {data['unsupported_cards']}")
        print(f"top unsupported reasons: {data['unsupported_by_reason']}")
        print(f"top engine blockers: {data['top_engine_blockers'][:10]}")


if __name__ == "__main__":
    main()
