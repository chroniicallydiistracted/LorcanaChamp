from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class LorcanitoSourceImportReport:
    schema_version: int = 1
    cards_loaded: int = 0
    ability_records_loaded: int = 0
    source_files_loaded: int = 0
    ability_type_counts: dict[str, int] = field(default_factory=dict)
    effect_type_counts: dict[str, int] = field(default_factory=dict)
    trigger_event_counts: dict[str, int] = field(default_factory=dict)
    trigger_on_counts: dict[str, int] = field(default_factory=dict)
    condition_type_counts: dict[str, int] = field(default_factory=dict)
    target_alias_counts: dict[str, int] = field(default_factory=dict)
    target_selector_counts: dict[str, int] = field(default_factory=dict)
    cost_type_counts: dict[str, int] = field(default_factory=dict)
    mapping_status_counts: dict[str, int] = field(default_factory=dict)
    execution_status_counts: dict[str, int] = field(default_factory=dict)
    fully_structured_cards: int = 0
    partially_structured_cards: int = 0
    executable_cards: int = 0
    mapped_not_executable_cards: int = 0
    unsupported_cards: int = 0
    unsupported_by_reason: dict[str, int] = field(default_factory=dict)
    top_unsupported_patterns: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def normalized_cards_payload(cards: list[dict[str, Any]]) -> dict[str, Any]:
    return {"schema_version": 1, "cards": cards}

