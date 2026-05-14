from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from ..cards import CardDatabase, CardDef


@dataclass(frozen=True, slots=True)
class ImportValidationReport:
    files_loaded: int = 0
    cards_loaded: int = 0
    type_counts: dict[str, int] = field(default_factory=dict)
    keyword_counts: dict[str, int] = field(default_factory=dict)
    unsupported_ability_count: int = 0
    missing_required_fields: tuple[dict[str, Any], ...] = ()
    duplicate_ids: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()

    @property
    def is_valid(self) -> bool:
        return not self.missing_required_fields and not self.duplicate_ids

    def fail_if_invalid(self) -> None:
        if self.is_valid:
            return
        details: list[str] = []
        if self.duplicate_ids:
            details.append(f"duplicate ids: {', '.join(self.duplicate_ids[:20])}")
        if self.missing_required_fields:
            sample = self.missing_required_fields[0]
            details.append(f"missing required fields, first={sample}")
        raise ValueError("Invalid Lorcanito import: " + "; ".join(details))


@dataclass(frozen=True, slots=True)
class LorcanitoImportResult:
    cards: tuple[CardDef, ...]
    report: ImportValidationReport

    def to_database(self) -> CardDatabase:
        self.report.fail_if_invalid()
        return CardDatabase(self.cards)


def load_lorcanito_database(path: str | Path = "data/cards") -> CardDatabase:
    """Load Lorcanito-style `setdata.*.json` files into a CardDatabase."""

    return import_lorcanito_cards(path).to_database()


def import_lorcanito_cards(path: str | Path = "data/cards") -> LorcanitoImportResult:
    """Normalize all Lorcanito-style set data files under path.

    Unknown ability/effect text is intentionally retained on each CardDef as
    structured `unsupported_abilities` records for future scripting.
    """

    files = _resolve_setdata_files(path)
    cards: list[CardDef] = []
    raw_ids: list[str] = []
    missing: list[dict[str, Any]] = []
    warnings: list[str] = []

    for file in files:
        raw_set = json.loads(file.read_text(encoding="utf-8"))
        if not isinstance(raw_set, dict):
            raise ValueError(f"{file} is not a JSON object")
        raw_cards = raw_set.get("cards")
        if not isinstance(raw_cards, list):
            raise ValueError(f"{file} is not a setdata object with a cards list")

        for index, raw_card in enumerate(raw_cards):
            if not isinstance(raw_card, dict):
                missing.append({"file": str(file), "index": index, "card": None, "fields": ["card_object"]})
                continue
            card_missing = _missing_required_fields(raw_card)
            if card_missing:
                missing.append(
                    {
                        "file": str(file),
                        "index": index,
                        "card": raw_card.get("fullName") or raw_card.get("id"),
                        "fields": card_missing,
                    }
                )
                continue

            try:
                card = CardDef.from_official_card(raw_card, raw_set)
            except Exception as exc:
                missing.append(
                    {
                        "file": str(file),
                        "index": index,
                        "card": raw_card.get("fullName") or raw_card.get("id"),
                        "fields": [f"normalization_error:{exc}"],
                    }
                )
                continue
            cards.append(card)
            raw_ids.append(card.id)

    id_counts = Counter(raw_ids)
    duplicate_ids = tuple(sorted(card_id for card_id, count in id_counts.items() if count > 1))
    if not files:
        warnings.append(f"No setdata JSON files found at {path}")

    report = _build_report(
        files=files,
        cards=cards,
        missing_required_fields=tuple(missing),
        duplicate_ids=duplicate_ids,
        warnings=tuple(warnings),
    )
    return LorcanitoImportResult(cards=tuple(cards), report=report)


def _resolve_setdata_files(path: str | Path) -> list[Path]:
    root = Path(path)
    if root.is_dir():
        files = sorted(root.glob("setdata.*.json"), key=_setdata_sort_key)
    else:
        files = [root]
    if not files:
        raise FileNotFoundError(f"No setdata JSON files found at {root}")
    return files


def _setdata_sort_key(path: Path) -> tuple[int, str]:
    token = path.name.removeprefix("setdata.").removesuffix(".json")
    if token.isdigit():
        return (0, f"{int(token):04d}")
    return (1, token)


def _missing_required_fields(raw: dict[str, Any]) -> list[str]:
    fields = ["id", "fullName", "type", "cost", "inkwell"]
    missing = [field for field in fields if field not in raw]
    card_type = str(raw.get("type", "")).strip().lower()
    if card_type == "character":
        for field in ("strength", "willpower", "lore"):
            if raw.get(field) is None:
                missing.append(field)
    elif card_type == "location":
        for field in ("willpower", "lore", "moveCost"):
            if raw.get(field) is None:
                missing.append(field)
    return missing


def _build_report(
    *,
    files: Iterable[Path],
    cards: Iterable[CardDef],
    missing_required_fields: tuple[dict[str, Any], ...],
    duplicate_ids: tuple[str, ...],
    warnings: tuple[str, ...],
) -> ImportValidationReport:
    card_list = list(cards)
    type_counts = Counter(card.card_type for card in card_list)
    keyword_counts = Counter(keyword for card in card_list for keyword in card.keywords)
    unsupported_ability_count = sum(len(card.unsupported_abilities) for card in card_list)
    return ImportValidationReport(
        files_loaded=len(list(files)),
        cards_loaded=len(card_list),
        type_counts=dict(sorted(type_counts.items())),
        keyword_counts=dict(sorted(keyword_counts.items())),
        unsupported_ability_count=unsupported_ability_count,
        missing_required_fields=missing_required_fields,
        duplicate_ids=duplicate_ids,
        warnings=warnings,
    )
