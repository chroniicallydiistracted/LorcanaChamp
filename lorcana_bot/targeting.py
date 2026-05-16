"""Targeting service foundation for LorcanaChamp.

This module owns the normalized Python shape for target descriptors and the
small helpers that later engine, pending-effect, and effect-resolution code can
share.  Brief 2 adds candidate resolution (card/player enumeration) and filter
application so that callers can obtain valid target IDs from a descriptor.
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
    ZONE_UNDER,
)

if TYPE_CHECKING:
    from .engine import GameEngine
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

# Selectors that resolve to a specific singleton card from context.
_SINGLETON_CARD_SELECTORS = frozenset({
    "self",
    "event_source",
    "event_target",
    "trigger_subject",
})

# Selectors that resolve to player IDs.
_PLAYER_SELECTORS = frozenset({
    "chosen_player",
    "you",
    "opponent",
    "each_player",
})


# ---------------------------------------------------------------------------
# Public candidate resolution API
# ---------------------------------------------------------------------------

def resolve_candidate_targets(
    state: GameState,
    engine: GameEngine,
    descriptor: TargetDescriptor,
    context: TargetQueryContext,
) -> tuple[TargetCandidate, ...]:
    """Resolve all valid TargetCandidate objects for *descriptor*.

    Returns a mixed tuple of card and player candidates.  Card candidates
    appear before player candidates when both are present.
    """
    card_ids = resolve_candidate_card_ids(state, engine, descriptor, context)
    player_ids = resolve_candidate_player_ids(state, descriptor, context)

    candidates: list[TargetCandidate] = []
    for cid in card_ids:
        inst = state.cards[cid]
        candidates.append(
            TargetCandidate(kind="card", id=cid, controller=inst.controller, zone=inst.zone),
        )
    for pid in player_ids:
        candidates.append(TargetCandidate(kind="player", id=pid))
    return tuple(candidates)


def resolve_candidate_card_ids(
    state: GameState,
    engine: GameEngine,
    descriptor: TargetDescriptor,
    context: TargetQueryContext,
) -> tuple[int, ...]:
    """Return card instance IDs that satisfy *descriptor*.

    Singleton selectors (self, event_source, etc.) return at most one ID.
    Plural selectors iterate all game cards.  ZONE_UNDER is always excluded
    from public candidate resolution.
    """
    # --- singleton context-based selectors ---
    if descriptor.selector == "self":
        sid = context.source_id
        return _validated_card_ids(state, engine, descriptor, context, (sid,) if sid is not None else ())

    if descriptor.selector == "event_source":
        src = _first_int_payload_value(
            context.event_payload,
            ("source", "source_id", "source_card_id", "trigger_source_card_id"),
        )
        return _validated_card_ids(state, engine, descriptor, context, (src,) if src is not None else ())

    if descriptor.selector == "event_target":
        tgt = _first_int_payload_value(
            context.event_payload,
            ("target", "target_id", "target_card_id", "event_target_id", "defender_id", "subject_card_id"),
        )
        return _validated_card_ids(state, engine, descriptor, context, (tgt,) if tgt is not None else ())

    if descriptor.selector == "trigger_subject":
        subj = _trigger_subject_from_context(context)
        return _validated_card_ids(state, engine, descriptor, context, (subj,) if subj is not None else ())

    # --- player selectors produce no card candidates ---
    if descriptor.selector in _PLAYER_SELECTORS:
        return ()

    # --- current_targets / context_targets pass-through ---
    if descriptor.selector == "current_targets":
        return _validated_card_ids(state, engine, descriptor, context, context.current_targets)

    if descriptor.selector == "context_targets":
        return _validated_card_ids(state, engine, descriptor, context, context.context_targets)

    # --- generic card iteration for all other selectors ---
    results: list[int] = []
    for cid, inst in state.cards.items():
        if not is_card_target_candidate(
            state,
            cid,
            descriptor,
            actor=context.actor,
            source_id=context.source_id,
            trigger_subject=_trigger_subject_from_context(context),
            engine=engine,
        ):
            continue
        results.append(cid)
    return tuple(results)


def resolve_candidate_player_ids(
    state: GameState,
    descriptor: TargetDescriptor,
    context: TargetQueryContext,
) -> tuple[int, ...]:
    """Return player IDs that satisfy *descriptor*.

    Returns an empty tuple when the descriptor does not target players.
    """
    if not descriptor.allow_players:
        return ()

    if descriptor.selector == "chosen_player":
        return (0, 1)

    if descriptor.selector == "you":
        return (context.actor,)

    if descriptor.selector == "opponent":
        return (state.opponent(context.actor),)

    if descriptor.selector == "each_player":
        return (0, 1)

    return ()


# ---------------------------------------------------------------------------
# Single-card / player validation
# ---------------------------------------------------------------------------

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
    engine: GameEngine | None = None,
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
        engine: GameEngine instance for keyword/classification lookups

    Returns:
        True if the card is a valid target candidate
    """
    inst = state.cards.get(card_id)
    if inst is None:
        return False

    # Cards under Shift stacks are not public candidates
    if getattr(inst, "stack_parent_id", None) is not None:
        return False

    # ZONE_UNDER must stay excluded from public candidate resolution
    if inst.zone == ZONE_UNDER:
        return False

    # Check zone restriction
    if descriptor.zones and inst.zone not in descriptor.zones:
        return False

    # Check card type restriction (requires engine for card def lookup)
    if descriptor.card_types and engine is not None:
        card_def = engine.card_def(state, card_id)
        if card_def.card_type not in descriptor.card_types:
            return False

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

    # Apply additional filters
    for filter_def in descriptor.filters:
        if not _apply_filter(state, card_id, filter_def, actor=actor, engine=engine):
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

def _first_int_payload_value(payload: dict[str, Any], keys: tuple[str, ...]) -> int | None:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, int):
            return value
    return None


def _trigger_subject_from_context(context: TargetQueryContext) -> int | None:
    return _first_int_payload_value(
        context.event_payload,
        ("subject", "trigger_subject", "subject_id", "subject_card_id", "defender_id", "target_id"),
    )


def _validated_card_ids(
    state: GameState,
    engine: GameEngine,
    descriptor: TargetDescriptor,
    context: TargetQueryContext,
    candidate_ids: tuple[int | None, ...],
) -> tuple[int, ...]:
    results: list[int] = []
    trigger_subject = _trigger_subject_from_context(context)

    for cid in candidate_ids:
        if not isinstance(cid, int):
            continue
        if cid in results:
            continue
        if not is_card_target_candidate(
            state,
            cid,
            descriptor,
            actor=context.actor,
            source_id=context.source_id,
            trigger_subject=trigger_subject,
            engine=engine,
        ):
            continue
        results.append(cid)

    return tuple(results)


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


# ---------------------------------------------------------------------------
# Filter application
# ---------------------------------------------------------------------------

# Field aliases for filter dict keys — maps variant names to canonical keys.
_FILTER_FIELD_ALIASES: dict[str, str] = {
    "card_type": "card_type",
    "cardType": "card_type",
    "card_types": "card_type",
    "cardTypes": "card_type",
    "classification": "classification",
    "classifications": "classification",
    "keyword": "keyword",
    "keywords": "keyword",
    "ink": "ink",
    "color": "ink",
    "owner": "owner",
    "controller": "controller",
    "location_instance_id": "location_instance_id",
    "locationInstanceId": "location_instance_id",
    "at_location": "location_instance_id",
    "atLocation": "location_instance_id",
    "damaged": "damaged",
    "exerted": "exerted",
    "ready": "ready",
    "drying": "drying",
}


def _normalize_filter_aliases(filter_def: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of *filter_def* with aliased keys normalized.

    The ``type`` key is left untouched so existing ``{"type": "damaged"}``
    style filters keep working.
    """
    out: dict[str, Any] = {}
    for key, value in filter_def.items():
        canonical = _FILTER_FIELD_ALIASES.get(key, key)
        out[canonical] = value
    return out


def _apply_filter(
    state: GameState,
    card_id: int,
    filter_def: dict[str, Any],
    *,
    actor: int | None = None,
    engine: GameEngine | None = None,
) -> bool:
    """Apply a filter definition to a card.

    Supports both the ``{"type": "damaged"}`` style and the field-alias style
    (e.g. ``{"damaged": True}``, ``{"keyword": "EVASIVE"}``).

    Args:
        state: Current game state
        card_id: Card instance ID to check
        filter_def: Filter definition dict
        actor: The player who would be selecting the target
        engine: GameEngine for keyword/classification lookups

    Returns:
        True if the card passes the filter
    """
    inst = state.cards.get(card_id)
    if inst is None:
        return False

    # --- style 1: explicit "type" key (existing behavior) ---
    filter_type = filter_def.get("type")

    if filter_type == "damaged":
        min_damage = filter_def.get("min", 1)
        return inst.damage >= min_damage

    if filter_type == "exerted":
        return inst.exerted

    if filter_type == "ready":
        return not inst.exerted

    if filter_type == "drying":
        return inst.drying

    # --- style 2: field-alias based filters ---
    normalized = _normalize_filter_aliases(filter_def)

    # card_type filter
    if "card_type" in normalized:
        if engine is None:
            return False
        card_def = engine.card_def(state, card_id)
        required = normalized["card_type"]
        if isinstance(required, str):
            required = (required,)
        if card_def.card_type not in required:
            return False

    # classification / subtypes filter
    if "classification" in normalized:
        if engine is None:
            return False
        card_def = engine.card_def(state, card_id)
        required = normalized["classification"]
        if isinstance(required, str):
            required = (required,)
        card_subtypes = set(card_def.subtypes)
        if not any(sub.lower() in {s.lower() for s in card_subtypes} for sub in required):
            return False

    # keyword filter
    if "keyword" in normalized:
        if engine is None:
            return False
        required = normalized["keyword"]
        if isinstance(required, str):
            required = (required,)
        card_keywords = {kw.upper() for kw in engine.keywords_for_instance(state, card_id)}
        if not any(kw.upper() in card_keywords for kw in required):
            return False

    # ink / color filter
    if "ink" in normalized:
        if engine is None:
            return False
        card_def = engine.card_def(state, card_id)
        required = normalized["ink"]
        if isinstance(required, str):
            required = (required,)
        card_colors = set(card_def.colors) if card_def.colors else {card_def.ink.lower()}
        if not any(c.lower() in card_colors for c in required):
            return False

    # damaged filter (field-alias style)
    if "damaged" in normalized:
        val = normalized["damaged"]
        if val is True:
            if inst.damage < 1:
                return False
        elif isinstance(val, (int, float)):
            if inst.damage < val:
                return False
        elif val is False:
            if inst.damage > 0:
                return False

    # exerted filter (field-alias style)
    if "exerted" in normalized:
        if bool(normalized["exerted"]) != inst.exerted:
            return False

    # ready filter (field-alias style)
    if "ready" in normalized:
        desired = bool(normalized["ready"])
        if desired and inst.exerted:
            return False
        if not desired and not inst.exerted:
            return False

    # drying filter (field-alias style)
    if "drying" in normalized:
        if bool(normalized["drying"]) != inst.drying:
            return False

    # location_instance_id filter
    if "location_instance_id" in normalized:
        loc = normalized["location_instance_id"]
        if loc is None:
            # Must not be at a location
            if inst.location_instance_id is not None:
                return False
        else:
            if inst.location_instance_id != loc:
                return False

    # owner filter (within filter dict, overrides descriptor-level)
    if "owner" in normalized:
        owner_val = normalized["owner"]
        if actor is not None:
            opponent = state.opponent(actor)
            if owner_val == "you" and inst.owner != actor:
                return False
            if owner_val == "opponent" and inst.owner != opponent:
                return False

    # controller filter (within filter dict)
    if "controller" in normalized:
        ctrl_val = normalized["controller"]
        if actor is not None:
            opponent = state.opponent(actor)
            if ctrl_val == "you" and inst.controller != actor:
                return False
            if ctrl_val == "opponent" and inst.controller != opponent:
                return False

    return True
