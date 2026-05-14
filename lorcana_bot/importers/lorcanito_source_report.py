from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .lorcanito_source_importer import import_lorcanito_source_cards


def build_mapping_coverage(source_json: str | Path) -> dict[str, Any]:
    db, report = import_lorcanito_source_cards(source_json)
    data = report.to_dict()
    data.update(
        {
            "total_cards": report.cards_loaded,
            "total_ability_records": report.ability_records_loaded,
            "target_type_counts": {
                **{f"alias:{key}": value for key, value in report.target_alias_counts.items()},
                **{f"selector:{key}": value for key, value in report.target_selector_counts.items()},
            },
            "top_engine_blockers": report.top_unsupported_patterns,
            "cards_by_status": _cards_by_status(db),
        }
    )
    return data


def write_mapping_coverage(source_json: str | Path, out: str | Path) -> dict[str, Any]:
    data = build_mapping_coverage(source_json)
    path = Path(out)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
    return data


def _cards_by_status(db) -> dict[str, list[str]]:
    statuses: dict[str, list[str]] = {}
    for card in db.all_cards():
        statuses.setdefault(card.source_execution_status, []).append(card.id)
    return {key: sorted(value) for key, value in sorted(statuses.items())}
