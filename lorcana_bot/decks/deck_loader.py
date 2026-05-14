from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any

from .deck_schema import RawDeck, RawDeckCard, ResolvedDeck


def load_raw_deck(path: str | Path) -> RawDeck:
    deck_path = Path(path)
    if not deck_path.exists():
        raise ValueError(f"Deck file does not exist: {deck_path}")
    try:
        raw = json.loads(deck_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Malformed JSON in {deck_path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise ValueError(f"Malformed deck file {deck_path}: root must be an object")
    for key in ("id", "name", "format", "deck_total", "cards"):
        if key not in raw:
            raise ValueError(f"Malformed deck file {deck_path}: missing required field {key!r}")
    if not isinstance(raw["cards"], list):
        raise ValueError(f"Malformed deck file {deck_path}: cards must be a list")
    cards: list[RawDeckCard] = []
    for index, item in enumerate(raw["cards"]):
        if not isinstance(item, dict) or "name" not in item or "count" not in item:
            raise ValueError(f"Malformed deck file {deck_path}: cards[{index}] needs name and count")
        try:
            count = int(item["count"])
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Malformed deck file {deck_path}: cards[{index}].count must be an integer") from exc
        cards.append(RawDeckCard(name=str(item["name"]), count=count, type=str(item["type"]) if item.get("type") is not None else None))
    return RawDeck(
        schema_version=int(raw.get("schema_version", 1)),
        id=str(raw["id"]),
        name=str(raw["name"]),
        format=str(raw["format"]),
        source_site=str(raw["source_site"]) if raw.get("source_site") is not None else None,
        source_deck_id=raw.get("source_deck_id"),
        player=str(raw["player"]) if raw.get("player") is not None else None,
        placement=str(raw["placement"]) if raw.get("placement") is not None else None,
        event=str(raw["event"]) if raw.get("event") is not None else None,
        event_date=str(raw["event_date"]) if raw.get("event_date") is not None else None,
        ink_colors=tuple(str(color).lower() for color in raw.get("ink_colors", ()) if color),
        archetype=str(raw["archetype"]) if raw.get("archetype") is not None else None,
        purpose=tuple(str(item) for item in raw.get("purpose", ()) if item),
        deck_total=int(raw["deck_total"]),
        cards=tuple(cards),
        raw=dict(raw),
    )


def load_raw_deck_dir(path: str | Path) -> list[RawDeck]:
    deck_dir = Path(path)
    if not deck_dir.exists():
        raise ValueError(f"Deck directory does not exist: {deck_dir}")
    decks = [load_raw_deck(file) for file in sorted(deck_dir.glob("*.json")) if file.name != "manifest.json"]
    return sorted(decks, key=lambda deck: deck.id)


def load_resolved_deck(path: str | Path) -> ResolvedDeck:
    from .deck_resolver import resolved_deck_from_dict

    deck_path = Path(path)
    if not deck_path.exists():
        raise ValueError(f"Resolved deck file does not exist: {deck_path}")
    try:
        raw = json.loads(deck_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Malformed JSON in {deck_path}: {exc}") from exc
    return resolved_deck_from_dict(raw)


def load_resolved_deck_dir(path: str | Path) -> list[ResolvedDeck]:
    deck_dir = Path(path)
    if not deck_dir.exists():
        raise ValueError(f"Resolved deck directory does not exist: {deck_dir}")
    decks = [load_resolved_deck(file) for file in sorted(deck_dir.glob("*.resolved.json"))]
    return sorted(decks, key=lambda deck: deck.id)


def raw_deck_to_dict(deck: RawDeck) -> dict[str, Any]:
    return _jsonable_dataclass(deck)


def resolved_deck_to_dict(deck: ResolvedDeck) -> dict[str, Any]:
    return _jsonable_dataclass(deck)


def write_resolved_deck(deck: ResolvedDeck, out_path: str | Path) -> None:
    path = Path(out_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(resolved_deck_to_dict(deck), indent=2, sort_keys=True), encoding="utf-8")


def _jsonable_dataclass(value: Any) -> Any:
    if is_dataclass(value):
        return _jsonable_dataclass(asdict(value))
    if isinstance(value, dict):
        return {str(key): _jsonable_dataclass(item) for key, item in sorted(value.items(), key=lambda item: str(item[0]))}
    if isinstance(value, tuple):
        return [_jsonable_dataclass(item) for item in value]
    if isinstance(value, list):
        return [_jsonable_dataclass(item) for item in value]
    return value
