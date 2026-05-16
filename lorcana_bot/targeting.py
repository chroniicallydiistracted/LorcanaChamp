"""Targeting service foundation for LorcanaChamp.

This module owns the normalized Python shape for target descriptors and the
small helpers that later engine, pending-effect, and effect-resolution code can
share. It intentionally stops short of full candidate enumeration; that work is
handled by later Microfix 10 briefs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from .constants import (
    CARD_CHARACTER,
    CARD_ITEM,
    CARD_LOCATION,
    ZONE_DECK,
    ZONE_DISCARD,
    ZONE_HAND,
    ZONE_INKWELL,
    ZONE_LIMBO,
    ZONE_PLAY,
)

if TYPE_CHECKING:
    from .state import GameState


ACTION_SELECTION_ZONES = (ZONE_DECK, ZONE_HAND, ZONE_PLAY, ZONE_DISCARD, ZONE_INKWELL, ZONE_LIMBO)

# Zone type alias matching Lorcanito's ActionSelectionZone union.
ActionSelectionZone = str


@dataclass(frozen=True, slots=True)
class TargetDescriptor:
    """Normalized descriptor for a targeting requirement.

    This dataclass captures all parameters needed to resolve a target selection,
    including the selector type, count constraints, zone restrictions, card type
    filters, ownership constraints, and additional filter conditions.
    """
    selector: str
    min_count: int = 1
    max_count: int | None = 1
    zones: tuple[str, ...] = (ZONE_PLAY,)
    card_types: tuple[str, ...] = ()
    owner: str | None = None
    controller: str | None = None
    filters: tuple[dict[str, Any], ...] = ()
    exclude_self: bool = False
    exclude_trigger_subject: bool = False
    allow_players: bool = False


@dataclass(frozen=True, slots=True)
class TargetCandidate:
    """A potential target for a targeting requirement.

    Represents either a card instance or a player that could be selected
    as a valid target.
    """
    kind: str  # "card" or "player"
    id: int
    controller: int | None = None
    zone: str | None = None


@dataclass(frozen=True, slots=True)
class TargetQueryContext:
    """Context for target query resolution.

    Contains all the information needed to resolve a target descriptor
    against the current game state.
    """
    actor: int
    source_id: int | None = None
    event_payload: dict[str, Any] = field(default_factory=dict)
    current_targets: tuple[int, ...] = ()
    context_targets: tuple[int, ...] = ()


# Alias mapping from Lorcanito DSL selectors to normalized selectors
# These cover the Python aliases required by the brief
SELECTOR_ALIASES: dict[str, str] = {
    # Chosen targets (player selection)
    "chosen_character": "chosen_character",
    "chosen_card": "chosen_card",
    "chosen_item": "chosen_item",
    "chosen_location": "chosen_location",
    "chosen_opposing_character": "chosen_opposing_character",
    "chosen_damaged_character": "chosen_damaged_character",
    # Context-based targets
    "opposing_character": "opposing_character",
    "self": "self",
    "event_source": "event_source",
    "event_target": "event_target",
    "trigger_subject": "trigger_subject",
    # Character set targets
    "your_characters": "your_characters",
    "your_other_characters": "your_other_characters",
    "opposing_characters": "opposing_characters",
    "all_characters": "all_characters",
    # Character set with conditions
    "damaged_characters": "damaged_characters",
    "opposing_damaged_characters": "opposing_damaged_characters",
    # Player targets
    "chosen_player": "chosen_player",
    "you": "you",
    "opponent": "opponent",
    "each_player": "each_player",
}

_PLURAL_SELECTOR_MAX = None


def normalize_target_descriptor(raw: Any) -> TargetDescriptor | None:
    """Normalize a raw target descriptor into a TargetDescriptor instance.

    Accepts various input formats:
    - String selector (e.g., "chosen_character")
    - Dict with selector key and optional parameters
    - TargetDescriptor (returned as-is)
    - None (returns None)

    Args:
        raw: The raw target specification

    Returns:
        Normalized TargetDescriptor or None if input is None/invalid
    """
    if raw is None:
        return None

    # If already a TargetDescriptor, return as-is
    if isinstance(raw, TargetDescriptor):
        return raw

    # Handle string selector
    if isinstance(raw, str):
        selector = _normalize_selector(raw)
        if selector is None:
            return None
        return _create_descriptor_for_selector(selector)

    # Handle dict-like input
    if isinstance(raw, dict):
        selector = raw.get("selector") or raw.get("type") or raw.get("kind")
        if selector is None:
            return None
        normalized_selector = _normalize_selector(selector)
        if normalized_selector is None:
            return None

        base = _create_descriptor_for_selector(normalized_selector)
        zones = raw.get("zones", raw.get("zone", base.zones))
        if isinstance(zones, str):
            zones = (zones,)

        card_types = raw.get(
            "cardTypes",
            raw.get("card_types", raw.get("cardType", raw.get("card_type", base.card_types))),
        )
        if isinstance(card_types, str):
            card_types = (card_types,)

        filters = raw.get("filters", raw.get("filter", base.filters))
        if isinstance(filters, dict):
            filters = (filters,)
        elif filters is None:
            filters = ()

        return TargetDescriptor(
            selector=normalized_selector,
            min_count=int(raw.get("minCount", raw.get("min_count", raw.get("min", base.min_count)))),
            max_count=_normalize_max_count(
                raw.get("maxCount", raw.get("max_count", raw.get("max", base.max_count))),
            ),
            zones=tuple(zones),
            card_types=tuple(card_types),
            owner=raw.get("owner", base.owner),
            controller=raw.get("controller", base.controller),
            filters=tuple(filters),
            exclude_self=bool(raw.get("excludeSelf", raw.get("exclude_self", base.exclude_self))),
            exclude_trigger_subject=bool(raw.get(
                "excludeTriggerSubject",
                raw.get("exclude_trigger_subject", base.exclude_trigger_subject),
            )),
            allow_players=bool(raw.get("allowPlayers", raw.get("allow_players", base.allow_players))),
        )

    # Handle tuple/list of selectors
    if isinstance(raw, (tuple, list)) and len(raw) == 1:
        return normalize_target_descriptor(raw[0])

    return None


def normalize_target_descriptors(raw: Any) -> tuple[TargetDescriptor, ...]:
    """Normalize one or more target descriptors into a tuple.

    Args:
        raw: Single descriptor or iterable of descriptors

    Returns:
        Tuple of normalized TargetDescriptor instances
    """
    if raw is None:
        return ()

    if isinstance(raw, str):
        desc = normalize_target_descriptor(raw)
        return (desc,) if desc else ()

    if isinstance(raw, TargetDescriptor):
        return (raw,)

    if isinstance(raw, dict):
        desc = normalize_target_descriptor(raw)
        return (desc,) if desc else ()

    if isinstance(raw, (tuple, list)):
        results = []
        for item in raw:
            desc = normalize_target_descriptor(item)
            if desc:
                results.append(desc)
        return tuple(results)

    return ()


def infer_candidate_zones(candidate_ids: tuple[int, ...], state: GameState) -> tuple[str, ...]:
    """Infer the zones that contain the given candidate IDs.

    This function examines each candidate ID and determines which zones
    they occupy in the game state. This is useful for determining what
    zones are relevant for a target selection.

    Args:
        candidate_ids: Tuple of card instance IDs to check
        state: Current game state

    Returns:
        Tuple of zone names that contain the candidates
    """
    zones: set[str] = set()

    for cid in candidate_ids:
        inst = state.cards.get(cid)
        if inst is not None and inst.zone in ACTION_SELECTION_ZONES:
            zones.add(inst.zone)

    return tuple(zone for zone in ACTION_SELECTION_ZONES if zone in zones)


def is_card_target_candidate(
    state: GameState,
    card_id: int,
    descriptor: TargetDescriptor,
    *,
    actor: int | None = None,
    source_id: int | None = None,
    trigger_subject: int | None = None,
) -> bool:
    """Check if a card is a valid candidate for a target descriptor.

    This function validates a single card against a target descriptor's
    constraints including zone, card type, ownership, controller, and
    any additional filters.

    Args:
        state: Current game state
        card_id: Card instance ID to check
        descriptor: Target descriptor to validate against
        actor: The player who would be selecting the target (for owner/controller checks)
        source_id: The card/source triggering the target requirement
        trigger_subject: The card that triggered the ability (for exclude_trigger_subject)

    Returns:
        True if the card is a valid target candidate
    """
    inst = state.cards.get(card_id)
    if inst is None:
        return False

    if getattr(inst, "stack_parent_id", None) is not None:
        return False

    # Check zone restriction
    if descriptor.zones and inst.zone not in descriptor.zones:
        return False

    # Check card type restriction
    # Note: Card type verification is deferred to resolution time when GameEngine
    # is available. For now, we only check zone-based restrictions.
    # The descriptor.card_types field is used for documentation/planning purposes.

    # Check exclude_self
    if descriptor.exclude_self and source_id is not None and card_id == source_id:
        return False

    # Check exclude_trigger_subject
    if descriptor.exclude_trigger_subject and trigger_subject is not None and card_id == trigger_subject:
        return False

    # Check owner/controller restrictions
    if actor is not None:
        opponent = state.opponent(actor)

        if descriptor.owner == "you":
            if inst.owner != actor:
                return False
        elif descriptor.owner == "opponent":
            if inst.owner != opponent:
                return False
        
        if descriptor.controller == "you":
            if inst.controller != actor:
                return False
        elif descriptor.controller == "opponent":
            if inst.controller != opponent:
                return False

    # Apply additional filters (placeholder for future filter support)
    for filter_def in descriptor.filters:
        if not _apply_filter(state, card_id, filter_def, actor=actor):
            return False

    return True


def is_player_target_candidate(
    player_id: int,
    descriptor: TargetDescriptor,
    actor: int | None = None,
) -> bool:
    """Check if a player is a valid candidate for a target descriptor.

    Args:
        player_id: Player ID to check
        descriptor: Target descriptor to validate against
        actor: The player who would be selecting the target

    Returns:
        True if the player is a valid target candidate
    """
    if not descriptor.allow_players:
        return False

    if player_id not in (0, 1):
        return False

    # Player selectors
    if descriptor.selector == "chosen_player":
        return True

    if descriptor.selector == "you":
        return player_id == actor if actor is not None else True

    if descriptor.selector == "opponent":
        return player_id != actor if actor is not None else True

    if descriptor.selector == "each_player":
        return True

    return False


# Internal helper functions

def _normalize_selector(selector: str) -> str | None:
    """Normalize a selector string to its canonical form.

    Args:
        selector: Raw selector string

    Returns:
        Normalized selector or None if unknown
    """
    if not selector:
        return None

    selector = selector.strip()
    selector = selector.replace("-", "_")

    # Direct lookup in aliases
    normalized = SELECTOR_ALIASES.get(selector)
    if normalized:
        return normalized

    # Case-insensitive lookup
    selector_lower = selector.lower()
    for alias, canonical in SELECTOR_ALIASES.items():
        if alias.lower() == selector_lower:
            return canonical

    # Return as-is if not found in aliases (might be a valid selector)
    return selector


def _normalize_max_count(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, str) and value.lower() in {"any", "all", "unbounded", "unlimited", "inf", "infinity"}:
        return None
    return int(value)


def _create_descriptor_for_selector(selector: str) -> TargetDescriptor:
    """Create a TargetDescriptor for a given selector.

    Args:
        selector: Normalized selector string

    Returns:
        TargetDescriptor with appropriate defaults for the selector
    """
    # Chosen targets
    if selector == "chosen_card":
        return TargetDescriptor(
            selector=selector,
            min_count=1,
            max_count=1,
            zones=(ZONE_PLAY,),
            owner="any",
        )

    if selector == "chosen_character":
        return TargetDescriptor(
            selector=selector,
            min_count=1,
            max_count=1,
            zones=(ZONE_PLAY,),
            card_types=(CARD_CHARACTER,),
            owner="any",
        )

    if selector == "chosen_opposing_character":
        return TargetDescriptor(
            selector=selector,
            min_count=1,
            max_count=1,
            zones=(ZONE_PLAY,),
            card_types=(CARD_CHARACTER,),
            controller="opponent",
        )

    if selector == "chosen_damaged_character":
        return TargetDescriptor(
            selector=selector,
            min_count=1,
            max_count=1,
            zones=(ZONE_PLAY,),
            card_types=(CARD_CHARACTER,),
            owner="any",
            filters=({"type": "damaged", "min": 1},),
        )

    if selector == "chosen_item":
        return TargetDescriptor(
            selector=selector,
            min_count=1,
            max_count=1,
            zones=(ZONE_PLAY,),
            card_types=(CARD_ITEM,),
            owner="any",
        )

    if selector == "chosen_location":
        return TargetDescriptor(
            selector=selector,
            min_count=1,
            max_count=1,
            zones=(ZONE_PLAY,),
            card_types=(CARD_LOCATION,),
            owner="any",
        )

    # Context-based targets
    if selector == "self":
        return TargetDescriptor(
            selector=selector,
            min_count=1,
            max_count=1,
            zones=(ZONE_PLAY,),
            exclude_self=False,
        )

    if selector == "opposing_character":
        return TargetDescriptor(
            selector=selector,
            min_count=1,
            max_count=1,
            zones=(ZONE_PLAY,),
            card_types=(CARD_CHARACTER,),
            controller="opponent",
        )

    if selector == "event_source":
        return TargetDescriptor(
            selector=selector,
            min_count=1,
            max_count=1,
            zones=(),
        )

    if selector == "event_target":
        return TargetDescriptor(
            selector=selector,
            min_count=1,
            max_count=1,
            zones=(),
        )

    if selector == "trigger_subject":
        return TargetDescriptor(
            selector=selector,
            min_count=1,
            max_count=1,
            zones=(),
        )

    # Character set targets
    if selector == "your_characters":
        return TargetDescriptor(
            selector=selector,
            min_count=1,
            max_count=_PLURAL_SELECTOR_MAX,
            zones=(ZONE_PLAY,),
            card_types=(CARD_CHARACTER,),
            controller="you",
        )

    if selector == "your_other_characters":
        return TargetDescriptor(
            selector=selector,
            min_count=1,
            max_count=_PLURAL_SELECTOR_MAX,
            zones=(ZONE_PLAY,),
            card_types=(CARD_CHARACTER,),
            controller="you",
            exclude_self=True,
        )

    if selector == "opposing_characters":
        return TargetDescriptor(
            selector=selector,
            min_count=1,
            max_count=_PLURAL_SELECTOR_MAX,
            zones=(ZONE_PLAY,),
            card_types=(CARD_CHARACTER,),
            controller="opponent",
        )

    if selector == "all_characters":
        return TargetDescriptor(
            selector=selector,
            min_count=1,
            max_count=_PLURAL_SELECTOR_MAX,
            zones=(ZONE_PLAY,),
            card_types=(CARD_CHARACTER,),
            owner="any",
        )

    if selector == "damaged_characters":
        return TargetDescriptor(
            selector=selector,
            min_count=1,
            max_count=_PLURAL_SELECTOR_MAX,
            zones=(ZONE_PLAY,),
            card_types=(CARD_CHARACTER,),
            owner="any",
            filters=({"type": "damaged", "min": 1},),
        )

    if selector == "opposing_damaged_characters":
        return TargetDescriptor(
            selector=selector,
            min_count=1,
            max_count=_PLURAL_SELECTOR_MAX,
            zones=(ZONE_PLAY,),
            card_types=(CARD_CHARACTER,),
            controller="opponent",
            filters=({"type": "damaged", "min": 1},),
        )

    # Player targets
    if selector == "chosen_player":
        return TargetDescriptor(
            selector=selector,
            min_count=1,
            max_count=1,
            allow_players=True,
        )

    if selector == "you":
        return TargetDescriptor(
            selector=selector,
            min_count=1,
            max_count=1,
            allow_players=True,
        )

    if selector == "opponent":
        return TargetDescriptor(
            selector=selector,
            min_count=1,
            max_count=1,
            allow_players=True,
        )

    if selector == "each_player":
        return TargetDescriptor(
            selector=selector,
            min_count=2,
            max_count=2,
            allow_players=True,
        )

    # Default case - return a basic descriptor
    return TargetDescriptor(
        selector=selector,
        min_count=1,
        max_count=1,
    )


def _apply_filter(
    state: GameState,
    card_id: int,
    filter_def: dict[str, Any],
    actor: int | None = None,
) -> bool:
    """Apply a filter definition to a card.
    
    Args:
        state: Current game state
        card_id: Card instance ID to check
        filter_def: Filter definition dict
        actor: The player who would be selecting the target
        
    Returns:
        True if the card passes the filter
    """
    filter_type = filter_def.get("type")
    
    if filter_type == "damaged":
        min_damage = filter_def.get("min", 1)
        inst = state.cards.get(card_id)
        if inst is None:
            return False
        return inst.damage >= min_damage
    
    if filter_type == "exerted":
        inst = state.cards.get(card_id)
        if inst is None:
            return False
        return inst.exerted
    
    # Add more filter types as needed
    # zone-count-rank, cost-comparison, keyword-match, etc.
    
    # Unknown filter type - assume pass
    return True
