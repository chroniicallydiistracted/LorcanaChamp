from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class RawDeckCard:
    name: str
    count: int
    type: str | None = None


@dataclass(frozen=True)
class RawDeck:
    schema_version: int
    id: str
    name: str
    format: str
    source_site: str | None
    source_deck_id: int | str | None
    player: str | None
    placement: str | None
    event: str | None
    event_date: str | None
    ink_colors: tuple[str, ...]
    archetype: str | None
    purpose: tuple[str, ...]
    deck_total: int
    cards: tuple[RawDeckCard, ...]
    raw: dict[str, Any]


@dataclass(frozen=True)
class ResolvedDeckCard:
    raw_name: str
    count: int
    raw_type: str | None
    resolved: bool
    resolution_status: str
    resolution_error: str | None = None
    card_id: str | None = None
    canonical_id: str | None = None
    name: str | None = None
    version: str | None = None
    full_name: str | None = None
    ink: str | None = None
    colors: tuple[str, ...] = ()
    card_type: str | None = None
    cost: int | None = None
    inkable: bool | None = None
    source_mapping_status: str | None = None
    source_execution_status: str | None = None
    keyword_defs: tuple[dict[str, Any], ...] = ()
    ability_type_counts: dict[str, int] = field(default_factory=dict)
    effect_type_counts: dict[str, int] = field(default_factory=dict)
    trigger_event_counts: dict[str, int] = field(default_factory=dict)
    condition_type_counts: dict[str, int] = field(default_factory=dict)
    cost_type_counts: dict[str, int] = field(default_factory=dict)
    unsupported_blockers: tuple[str, ...] = ()
    candidate_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class ResolvedDeck:
    schema_version: int
    id: str
    name: str
    format: str
    source_site: str | None
    source_deck_id: int | str | None
    player: str | None
    placement: str | None
    event: str | None
    event_date: str | None
    raw_ink_colors: tuple[str, ...]
    resolved_ink_colors: tuple[str, ...]
    archetype: str | None
    purpose: tuple[str, ...]
    deck_total_declared: int
    deck_total_resolved: int
    cards: tuple[ResolvedDeckCard, ...]
    playable_decklist_ids: tuple[str, ...]
    validation: dict[str, Any]
    mapping_summary: dict[str, Any]
    playability: str
