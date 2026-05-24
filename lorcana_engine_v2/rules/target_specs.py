from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class TargetSpec:
    selector: str
    zones: tuple[str, ...] = ("play",)
    card_types: tuple[str, ...] = ()
    owner: str | None = None
    controller: str | None = None
    filters: tuple[dict[str, Any], ...] = ()
    exclude_self: bool = False
    min_count: int = 1
    max_count: int | None = 1


def normalize_target_spec(raw: Any) -> TargetSpec:
    if raw is None:
        return TargetSpec("self")
    if isinstance(raw, TargetSpec):
        return raw
    if isinstance(raw, str):
        upper = raw.upper().replace("-", "_")
        if upper in {"SELF", "SOURCE", "THIS_CHARACTER", "THIS_ITEM", "THIS_LOCATION"}:
            return TargetSpec("self")
        if upper == "YOUR_HERO_CHARACTERS":
            return TargetSpec(
                selector="all",
                card_types=("character",),
                controller="you",
                filters=({"type": "has-classification", "classification": "Hero"},),
                min_count=0,
                max_count=None,
            )
        if upper == "YOUR_OTHER_CHARACTERS":
            return TargetSpec("all", card_types=("character",), controller="you", exclude_self=True, min_count=0, max_count=None)
        if upper == "YOUR_CHARACTERS":
            return TargetSpec("all", card_types=("character",), controller="you", min_count=0, max_count=None)
        if upper == "ALL_CHARACTERS":
            return TargetSpec("all", card_types=("character",), min_count=0, max_count=None)
        return TargetSpec(upper.lower())
    if isinstance(raw, dict):
        selector = str(raw.get("selector") or raw.get("type") or raw.get("kind") or "self")
        zones = raw.get("zones") or raw.get("zone") or ("play",)
        if isinstance(zones, str):
            zones = (zones,)
        card_types = raw.get("cardTypes") or raw.get("cardType") or raw.get("card_types") or raw.get("card_type") or ()
        if isinstance(card_types, str):
            card_types = (card_types,)
        filters = raw.get("filters") or raw.get("filter") or ()
        if isinstance(filters, dict):
            filters = (filters,)
        count = raw.get("count")
        max_count = None if count in {"all", "any"} else int(count) if isinstance(count, int) or (isinstance(count, str) and count.isdigit()) else None
        min_count = 0 if max_count is None else max_count
        return TargetSpec(
            selector=selector.replace("-", "_"),
            zones=tuple(str(zone) for zone in zones),
            card_types=tuple(str(t) for t in card_types),
            owner=raw.get("owner"),
            controller=raw.get("controller"),
            filters=tuple(filters),
            exclude_self=bool(raw.get("excludeSelf") or raw.get("exclude_self")),
            min_count=min_count,
            max_count=max_count,
        )
    raise TypeError(f"Unsupported target spec: {raw!r}")
