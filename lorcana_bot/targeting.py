"""Targeting service foundation for LorcanaChamp.

This module owns the normalized Python shape for target descriptors and the
small helpers that later engine, pending-effect, and effect-resolution code can
share.  Brief 2 adds candidate resolution (card/player enumeration) and filter
application so that callers can obtain valid target IDs from a descriptor.
Brief 3 adds target selection availability analysis and protection filtering
(Ward, cannot-be-targeted, non-public stack exclusions, duplicate rejection).
"""

from __future__ import annotations

import itertools
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
    allow_duplicate_targets: bool = False


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
    "chosen": "chosen",
    "chosen_character": "chosen_character",
    "chosen_exerted_character": "chosen_exerted_character",
    "chosen_card": "chosen_card",
    "chosen_item": "chosen_item",
    "chosen_location": "chosen_location",
    "chosen_opposing_character": "chosen_opposing_character",
    "chosen_damaged_character": "chosen_damaged_character",
    "chosen_opposing_damaged_character": "chosen_opposing_damaged_character",
    "chosen_damaged_opposing_character": "chosen_opposing_damaged_character",
    "up_to_2_chosen_characters": "up_to_2_chosen_characters",
    "chosen_opposing_character_3_strength_or_less": "chosen_opposing_character_3_strength_or_less",
    "chosen_character_in_discard": "chosen_character_in_discard",
    "chosen_card_in_discard": "chosen_card_from_discard",
    "chosen_card_from_discard": "chosen_card_from_discard",
    "chosen_card_from_hand": "chosen_card_from_hand",
    "your_chosen_character": "your_chosen_character",
    "your_chosen_damaged_character": "your_chosen_damaged_character",
    "your_chosen_item": "your_chosen_item",
    "another_chosen_character": "another_chosen_character",
    "another_chosen_character_of_yours": "another_chosen_character_of_yours",
    "all": "all",

    # Context-based targets
    "opposing_character": "opposing_character",
    "self": "self",
    "source": "self",
    "event_source": "event_source",
    "event_target": "event_target",
    "trigger_subject": "trigger_subject",
    "trigger_source": "trigger_source",
    "trigger_destination": "trigger_destination",
    "attacker": "attacker",
    "defender": "defender",
    "previous_target": "previous_target",
    "selected_first": "selected_first",
    "selected_all": "selected_all",

    # Character set targets
    "your_characters": "your_characters",
    "your_exerted_characters": "your_exerted_characters",
    "your_other_characters": "your_other_characters",
    "opposing_characters": "opposing_characters",
    "all_characters": "all_characters",
    "seven_dwarfs_characters": "seven_dwarfs_characters",
    "your_other_seven_dwarfs_characters": "your_other_seven_dwarfs_characters",

    # Character set with conditions
    "damaged_characters": "damaged_characters",
    "opposing_damaged_characters": "opposing_damaged_characters",

    # Player targets
    "chosen_player": "chosen_player",
    "you": "you",
    "controller": "you",
    "actor": "you",
    "opponent": "opponent",
    "opponents": "opponent",
    "each_player": "each_player",
    "challenging_player": "challenging_player",
}

_PLURAL_SELECTOR_MAX = None

# Selectors that resolve to a specific singleton card from context.
_SINGLETON_CARD_SELECTORS = frozenset({
    "self",
    "event_source",
    "event_target",
    "trigger_subject",
    "trigger_source",
    "trigger_destination",
    "attacker",
    "defender",
    "previous_target",
    "selected_first",
})

# Selectors that resolve to player IDs.
_PLAYER_SELECTORS = frozenset({
    "chosen_player",
    "you",
    "opponent",
    "each_player",
    "challenging_player",
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

    if descriptor.selector == "trigger_source":
        src = _first_int_payload_value(
            context.event_payload,
            ("trigger_source_card_id", "triggerSourceCardId", "source_card_id", "sourceCardId", "source_id", "source"),
        )
        return _validated_card_ids(state, engine, descriptor, context, (src,) if src is not None else ())

    if descriptor.selector == "trigger_destination":
        dst = _trigger_destination_from_context(context)
        return _validated_card_ids(state, engine, descriptor, context, (dst,) if dst is not None else ())

    if descriptor.selector == "attacker":
        attacker = _first_int_payload_value(context.event_payload, ("attacker_id", "attackerId"))
        return _validated_card_ids(state, engine, descriptor, context, (attacker,) if attacker is not None else ())

    if descriptor.selector == "defender":
        defender = _first_int_payload_value(context.event_payload, ("defender_id", "defenderId"))
        return _validated_card_ids(state, engine, descriptor, context, (defender,) if defender is not None else ())

    if descriptor.selector == "previous_target":
        previous = context.current_targets[-1] if context.current_targets else None
        return _validated_card_ids(state, engine, descriptor, context, (previous,) if previous is not None else ())

    if descriptor.selector == "selected_first":
        selected = context.current_targets[0] if context.current_targets else None
        return _validated_card_ids(state, engine, descriptor, context, (selected,) if selected is not None else ())

    if descriptor.selector == "selected_all":
        selected = context.current_targets or context.context_targets
        return _validated_card_ids(state, engine, descriptor, context, selected)

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

    if descriptor.selector == "challenging_player":
        player_id = _first_int_payload_value(
            context.event_payload,
            ("player_id", "playerId", "challenging_player", "challengingPlayer"),
        )
        if player_id in (0, 1):
            return (player_id,)

        attacker_id = _first_int_payload_value(
            context.event_payload,
            ("attacker_id", "attackerId", "challenger_id", "challengerId"),
        )
        if attacker_id is not None and attacker_id in state.cards:
            return (state.cards[attacker_id].controller,)

        return ()

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
        if selector is None and "ref" in raw:
            selector = raw.get("ref")
        if selector is None:
            return None
        normalized_selector = _normalize_selector(str(selector))
        if normalized_selector is None:
            return None

        base = _create_descriptor_for_selector(normalized_selector)
        if base is None:
            return None
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

        min_count, max_count = _normalize_count_bounds(raw.get("count"), base.min_count, base.max_count)
        min_count = int(raw.get("minCount", raw.get("min_count", raw.get("min", min_count))))
        max_count = _normalize_max_count(
            raw.get("maxCount", raw.get("max_count", raw.get("max", max_count))),
        )

        return TargetDescriptor(
            selector=normalized_selector,
            min_count=min_count,
            max_count=max_count,
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
            allow_duplicate_targets=bool(raw.get(
                "allowDuplicateTargets",
                raw.get("allow_duplicate_targets", base.allow_duplicate_targets),
            )),
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

    # Check card type restriction (requires engine for card def lookup).
    # Lorcanito uses cardTypes: ["card"] as a wildcard for any card type.
    if descriptor.card_types and engine is not None:
        card_def = engine.card_def(state, card_id)
        if "card" not in descriptor.card_types and card_def.card_type not in descriptor.card_types:
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


def _trigger_destination_from_context(context: TargetQueryContext) -> int | None:
    direct = _first_int_payload_value(
        context.event_payload,
        (
            "trigger_destination",
            "trigger_destination_id",
            "destination",
            "destination_id",
            "to_location_id",
            "location_id",
        ),
    )
    if direct is not None:
        return direct

    to_zone = context.event_payload.get("to_zone") or context.event_payload.get("toZone")
    if isinstance(to_zone, str) and to_zone.startswith("location:"):
        raw_id = to_zone.split(":", 1)[1]
        if raw_id.isdigit():
            return int(raw_id)

    return None


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
    if isinstance(value, dict):
        if "exactly" in value:
            return int(value["exactly"])
        if "upTo" in value:
            return int(value["upTo"])
        if "up_to" in value:
            return int(value["up_to"])
        if "max" in value:
            return int(value["max"])
    return int(value)


def _normalize_count_bounds(value: Any, default_min: int, default_max: int | None) -> tuple[int, int | None]:
    if value is None:
        return default_min, default_max
    if isinstance(value, dict):
        if "exactly" in value:
            exact = int(value["exactly"])
            return exact, exact
        if "upTo" in value:
            return 0, int(value["upTo"])
        if "up_to" in value:
            return 0, int(value["up_to"])
        if "min" in value or "max" in value:
            min_count = int(value.get("min", default_min))
            max_count = _normalize_max_count(value.get("max", default_max))
            return min_count, max_count
    if isinstance(value, str) and value.lower() in {"all", "any"}:
        return default_min, None
    count = int(value)
    return count, count


def _create_descriptor_for_selector(selector: str) -> TargetDescriptor | None:
    """Create a TargetDescriptor for a given selector.

    Args:
        selector: Normalized selector string

    Returns:
        TargetDescriptor with appropriate defaults for the selector
    """
    # Chosen targets
    if selector == "chosen":
        return TargetDescriptor(
            selector=selector,
            min_count=1,
            max_count=1,
            zones=(ZONE_PLAY,),
            owner="any",
        )

    if selector == "all":
        return TargetDescriptor(
            selector=selector,
            min_count=0,
            max_count=None,
            zones=(ZONE_PLAY,),
            owner="any",
        )

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

    if selector == "up_to_2_chosen_characters":
        return TargetDescriptor(
            selector=selector,
            min_count=0,
            max_count=2,
            zones=(ZONE_PLAY,),
            card_types=(CARD_CHARACTER,),
            owner="any",
        )

    if selector == "chosen_exerted_character":
        return TargetDescriptor(
            selector=selector,
            min_count=1,
            max_count=1,
            zones=(ZONE_PLAY,),
            card_types=(CARD_CHARACTER,),
            owner="any",
            filters=({"type": "exerted"},),
        )

    if selector in {"target", "current_targets"}:
        return TargetDescriptor(
            selector=selector,
            min_count=1,
            max_count=1,
            zones=(ZONE_PLAY,),
            owner="any",
        )

    if selector == "context_targets":
        return TargetDescriptor(
            selector=selector,
            min_count=1,
            max_count=None,
            zones=(ZONE_PLAY,),
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

    if selector == "chosen_opposing_character_3_strength_or_less":
        return TargetDescriptor(
            selector=selector,
            min_count=1,
            max_count=1,
            zones=(ZONE_PLAY,),
            card_types=(CARD_CHARACTER,),
            controller="opponent",
            filters=(
                {"type": "strength-comparison", "comparison": "less-or-equal", "value": 3},
            ),
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

    if selector == "chosen_opposing_damaged_character":
        return TargetDescriptor(
            selector=selector,
            min_count=1,
            max_count=1,
            zones=(ZONE_PLAY,),
            card_types=(CARD_CHARACTER,),
            controller="opponent",
            filters=({"type": "status", "status": "damaged"},),
        )

    if selector == "your_chosen_character":
        return TargetDescriptor(
            selector=selector,
            min_count=1,
            max_count=1,
            zones=(ZONE_PLAY,),
            card_types=(CARD_CHARACTER,),
            owner="you",
        )

    if selector == "your_chosen_damaged_character":
        return TargetDescriptor(
            selector=selector,
            min_count=1,
            max_count=1,
            zones=(ZONE_PLAY,),
            card_types=(CARD_CHARACTER,),
            owner="you",
            filters=({"type": "status", "status": "damaged"},),
        )

    if selector == "another_chosen_character":
        return TargetDescriptor(
            selector=selector,
            min_count=1,
            max_count=1,
            zones=(ZONE_PLAY,),
            card_types=(CARD_CHARACTER,),
            owner="any",
            exclude_self=True,
        )

    if selector == "another_chosen_character_of_yours":
        return TargetDescriptor(
            selector=selector,
            min_count=1,
            max_count=1,
            zones=(ZONE_PLAY,),
            card_types=(CARD_CHARACTER,),
            owner="you",
            exclude_self=True,
        )

    if selector == "chosen_character_in_discard":
        return TargetDescriptor(
            selector=selector,
            min_count=1,
            max_count=1,
            zones=(ZONE_DISCARD,),
            card_types=(CARD_CHARACTER,),
            owner="any",
        )

    if selector == "chosen_card_from_discard":
        return TargetDescriptor(
            selector=selector,
            min_count=1,
            max_count=1,
            zones=(ZONE_DISCARD,),
            owner="any",
        )

    if selector == "chosen_card_from_hand":
        return TargetDescriptor(
            selector=selector,
            min_count=1,
            max_count=1,
            zones=(ZONE_HAND,),
            owner="any",
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

    if selector == "your_chosen_item":
        return TargetDescriptor(
            selector=selector,
            min_count=1,
            max_count=1,
            zones=(ZONE_PLAY,),
            card_types=(CARD_ITEM,),
            owner="you",
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

    if selector == "trigger_source":
        return TargetDescriptor(
            selector=selector,
            min_count=1,
            max_count=1,
            zones=(),
        )

    if selector == "trigger_destination":
        return TargetDescriptor(
            selector=selector,
            min_count=1,
            max_count=1,
            zones=(),
        )

    if selector == "attacker":
        return TargetDescriptor(
            selector=selector,
            min_count=1,
            max_count=1,
            zones=(),
        )

    if selector == "defender":
        return TargetDescriptor(
            selector=selector,
            min_count=1,
            max_count=1,
            zones=(),
        )

    if selector in {"previous_target", "selected_first"}:
        return TargetDescriptor(
            selector=selector,
            min_count=1,
            max_count=1,
            zones=(),
        )

    if selector == "selected_all":
        return TargetDescriptor(
            selector=selector,
            min_count=0,
            max_count=None,
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

    if selector == "your_exerted_characters":
        return TargetDescriptor(
            selector=selector,
            min_count=0,
            max_count=_PLURAL_SELECTOR_MAX,
            zones=(ZONE_PLAY,),
            card_types=(CARD_CHARACTER,),
            owner="you",
            filters=({"type": "exerted"},),
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

    if selector == "seven_dwarfs_characters":
        return TargetDescriptor(
            selector=selector,
            min_count=0,
            max_count=_PLURAL_SELECTOR_MAX,
            zones=(ZONE_PLAY,),
            card_types=(CARD_CHARACTER,),
            owner="you",
            filters=({"type": "has-classification", "classification": "Seven Dwarfs"},),
        )

    if selector == "your_other_seven_dwarfs_characters":
        return TargetDescriptor(
            selector=selector,
            min_count=0,
            max_count=_PLURAL_SELECTOR_MAX,
            zones=(ZONE_PLAY,),
            card_types=(CARD_CHARACTER,),
            owner="you",
            exclude_self=True,
            filters=({"type": "has-classification", "classification": "Seven Dwarfs"},),
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

    if selector == "challenging_player":
        return TargetDescriptor(
            selector=selector,
            min_count=1,
            max_count=1,
            allow_players=True,
        )

    return None


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
    "challenged_this_turn": "challenged_this_turn",
    "challengedThisTurn": "challenged_this_turn",
    "was_challenged_this_turn": "challenged_this_turn",
    "wasChallengedThisTurn": "challenged_this_turn",
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

    if filter_type == "status":
        status = str(filter_def.get("status") or "").replace("_", "-").lower()
        if status == "damaged":
            min_damage = filter_def.get("min", 1)
            return inst.damage >= min_damage
        if status == "undamaged":
            return inst.damage <= 0
        if status == "exerted":
            return inst.exerted
        if status == "ready":
            return not inst.exerted
        return False

    if filter_type == "damaged":
        min_damage = filter_def.get("min", 1)
        return inst.damage >= min_damage

    if filter_type == "undamaged":
        return inst.damage <= 0

    if filter_type == "exerted":
        return inst.exerted

    if filter_type == "ready":
        return not inst.exerted

    if filter_type == "challenged-this-turn":
        return bool(getattr(inst, "was_challenged_this_turn", False))

    if filter_type == "drying":
        return inst.drying

    if filter_type == "has-keyword":
        if engine is None:
            return False
        keyword = filter_def.get("keyword")
        if not keyword:
            return False
        card_keywords = {kw.upper() for kw in engine.keywords_for_instance(state, card_id)}
        return str(keyword).upper() in card_keywords

    if filter_type in {"strength-comparison", "cost-comparison"}:
        if engine is None:
            return False
        comparison = str(filter_def.get("comparison", "equal"))
        raw_value = filter_def.get("value", 0)
        try:
            threshold = int(raw_value)
        except (TypeError, ValueError):
            return False
        if filter_type == "strength-comparison":
            actual = engine.effective_strength(state, card_id) if hasattr(engine, "effective_strength") else engine.card_def(state, card_id).strength
        else:
            actual = engine.card_def(state, card_id).cost
        return _compare_int(actual, comparison, threshold)

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

    if "challenged_this_turn" in normalized:
        if bool(normalized["challenged_this_turn"]) != bool(getattr(inst, "was_challenged_this_turn", False)):
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


def _compare_int(actual: int, comparison: str, threshold: int) -> bool:
    normalized = comparison.replace("_", "-").lower()
    if normalized in {"less-or-equal", "less-than-or-equal", "lte", "<="}:
        return actual <= threshold
    if normalized in {"less", "less-than", "lt", "<"}:
        return actual < threshold
    if normalized in {"greater-or-equal", "greater-than-or-equal", "gte", ">="}:
        return actual >= threshold
    if normalized in {"greater", "greater-than", "gt", ">"}:
        return actual > threshold
    if normalized in {"not-equal", "neq", "!="}:
        return actual != threshold
    return actual == threshold


# ---------------------------------------------------------------------------
# Brief 3: Target selection availability and protection filtering
# ---------------------------------------------------------------------------


def requires_explicit_target_selection(selector: str) -> bool:
    """Return True when *selector* requires a player target choice.

    Chosen selectors and enum-expanded chosen aliases require explicit target
    input. Collection aliases like your_exerted_characters do not.
    """
    return (
        selector.startswith("chosen")
        or selector.startswith("your_chosen")
        or selector.startswith("another_chosen")
        or selector.startswith("up_to_")
        or selector == "opposing_character"
    )


@dataclass(frozen=True, slots=True)
class TargetSelectionAvailability:
    """Lorcanito-aligned availability analysis for a target selection.

    Mirrors the ``TargetSelectionAvailability`` type from
    ``target-availability.ts`` (lines 28-38).
    """
    candidate_count: int
    card_candidate_count: int
    player_candidate_count: int
    min_selections: int
    max_selections: int
    allows_explicit_empty_target_selection: bool
    can_satisfy_required_selection: bool
    requires_explicit_target_selection: bool
    should_auto_reject_for_no_valid_targets: bool


def analyze_target_selection_availability(
    descriptor: TargetDescriptor,
    candidates: tuple[TargetCandidate, ...],
    *,
    is_optional: bool = False,
) -> TargetSelectionAvailability:
    """Analyze whether a target selection can be satisfied.

    Computes candidate counts, min/max selections, and whether the
    selection requires explicit player action or can be auto-rejected.

    Args:
        descriptor: The target descriptor defining the selection requirements.
        candidates: The resolved (post-protection) candidate tuple.
        is_optional: Whether the effect/ability is optional.  Optional effects
            never auto-reject for no valid targets.

    Returns:
        A ``TargetSelectionAvailability`` snapshot.
    """
    card_count = sum(1 for c in candidates if c.kind == "card")
    player_count = sum(1 for c in candidates if c.kind == "player")
    total = card_count + player_count

    min_sel = max(0, descriptor.min_count)
    max_sel = max(0, descriptor.max_count) if descriptor.max_count is not None else total

    # Chosen selectors require explicit player selection even when they are
    # "up to" selections with min_count=0.
    requires_explicit = requires_explicit_target_selection(descriptor.selector)
    allows_empty = requires_explicit and min_sel == 0

    # Can satisfy: either no explicit selection is needed, no minimum is
    # required, or enough distinct candidates exist. Duplicate-allowed target
    # selections can satisfy a multi-target minimum with one candidate.
    can_satisfy = (
        not requires_explicit
        or min_sel <= 0
        or (total > 0 and (descriptor.allow_duplicate_targets or total >= min_sel))
    )

    # Auto-reject when the effect is mandatory, requires explicit selection,
    # and cannot be satisfied.
    auto_reject = (
        not is_optional
        and requires_explicit
        and (total == 0 or not can_satisfy)
    )

    return TargetSelectionAvailability(
        candidate_count=total,
        card_candidate_count=card_count,
        player_candidate_count=player_count,
        min_selections=min_sel,
        max_selections=max_sel,
        allows_explicit_empty_target_selection=allows_empty,
        can_satisfy_required_selection=can_satisfy,
        requires_explicit_target_selection=requires_explicit,
        should_auto_reject_for_no_valid_targets=auto_reject,
    )


def enumerate_target_selections(
    candidates: tuple[TargetCandidate, ...],
    descriptor: TargetDescriptor,
    *,
    candidate_kind: str = "card",
) -> tuple[tuple[int, ...], ...]:
    """Enumerate legal target id selections for a descriptor.

    Lorcanito target inputs are submitted as arrays. This helper centralizes
    Python enumeration for action cards, activated abilities, bag input, and
    pending input so all paths share the same min/max/duplicate semantics.
    """
    ids = tuple(candidate.id for candidate in candidates if candidate.kind == candidate_kind)
    if not ids:
        return ((),) if descriptor.min_count <= 0 else ()

    min_count = max(0, int(descriptor.min_count or 0))
    if descriptor.max_count is None:
        max_count = len(ids) if not descriptor.allow_duplicate_targets else max(min_count, len(ids))
    else:
        max_count = max(0, int(descriptor.max_count))

    if not descriptor.allow_duplicate_targets:
        max_count = min(max_count, len(ids))

    if max_count < min_count:
        return ()

    selections: list[tuple[int, ...]] = []
    if min_count == 0:
        selections.append(())

    for count in range(max(1, min_count), max_count + 1):
        if descriptor.allow_duplicate_targets:
            selections.extend(tuple(choice) for choice in itertools.product(ids, repeat=count))
        else:
            selections.extend(tuple(choice) for choice in itertools.combinations(ids, count))

    return tuple(selections)


def apply_target_protections(
    state: GameState,
    engine: GameEngine,
    candidates: tuple[TargetCandidate, ...],
    descriptor: TargetDescriptor,
    context: TargetQueryContext,
    *,
    source_id: int | None = None,
) -> tuple[TargetCandidate, ...]:
    """Filter *candidates* through protection rules.

    Removes candidates that are:
    - In ZONE_UNDER or have a stack_parent_id (non-public shifted-stack cards).
    - Protected by Ward (opposing cards cannot be chosen by opponent effects).
    - Protected by cannot-be-targeted replacement effects.
    - Duplicate IDs (only the first occurrence is kept).

    Card candidates that fail protection are silently dropped.  Player
    candidates are never affected by card-level protections.

    This function operates on the candidate tuple returned by Brief 2
    helpers; it does **not** re-resolve context selectors.

    Args:
        state: Current game state.
        engine: GameEngine for keyword and replacement-effect lookups.
        candidates: Candidates from ``resolve_candidate_targets()``.
        descriptor: The target descriptor.
        context: The query context (for actor identification).
        source_id: The source card triggering the targeting requirement.
            Defaults to ``context.source_id`` when *None*.

    Returns:
        A filtered tuple of ``TargetCandidate`` with protections applied.
    """
    if source_id is None:
        source_id = context.source_id

    actor = context.actor
    seen_ids: set[tuple[str, int]] = set()
    results: list[TargetCandidate] = []

    for cand in candidates:
        key = (cand.kind, cand.id)

        # --- duplicate rejection ---
        if key in seen_ids and not descriptor.allow_duplicate_targets:
            continue
        seen_ids.add(key)

        # Player candidates pass through unaffected
        if cand.kind == "player":
            results.append(cand)
            continue

        # --- card-level protections ---
        cid = cand.id
        inst = state.cards.get(cid)

        # Card no longer exists
        if inst is None:
            continue

        # Non-public shifted-stack cards
        if inst.zone == ZONE_UNDER:
            continue
        if getattr(inst, "stack_parent_id", None) is not None:
            continue
        if descriptor.zones and inst.zone not in descriptor.zones:
            continue

        # Ward protection applies when the opponent is choosing a card target.
        if (
            requires_explicit_target_selection(descriptor.selector)
            and engine is not None
            and inst.controller != actor
            and engine.has_keyword(state, cid, "WARD")
        ):
            continue

        # Cannot-be-targeted protection
        if _is_protected_from_targeting(state, cid, actor, source_id):
            continue

        results.append(cand)

    return tuple(results)


def _is_protected_from_targeting(
    state: GameState,
    target_id: int,
    caster_controller: int,
    source_id: int | None,
) -> bool:
    """Check if a card is protected from targeting.

    Delegates to the replacement-effect registry's
    ``check_cannot_be_targeted`` when available.  Returns False if the
    registry is not present or has no applicable effects.
    """
    try:
        from .replacement_effects import check_cannot_be_targeted
        return check_cannot_be_targeted(state, target_id, caster_controller)
    except (ImportError, AttributeError):
        return False


# ---------------------------------------------------------------------------
# Brief 7: Slotted target input support
# ---------------------------------------------------------------------------

SLOTTED_TARGET_KINDS = (
    "move-damage",
    "move-to-location",
    "shift-and-choose",
    "banish-and-play",
)

SLOTTED_TARGET_SLOT_KEYS: dict[str, tuple[str, ...]] = {
    "move-damage": ("from", "to"),
    "move-to-location": ("subject", "location"),
    "shift-and-choose": ("chosenCard",),
    "banish-and-play": ("banish", "play"),
}


def is_slotted_target_input(value: Any) -> bool:
    """Return True for Lorcanito-style resolved slotted target input.

    Mirrors Lorcanito's structural guard: the value must be a non-list dict,
    its ``kind`` must be known, and every canonical slot for that kind must be
    an array-like value. Extra keys are ignored.
    """
    if not isinstance(value, dict):
        return False
    kind = value.get("kind")
    if not isinstance(kind, str) or kind not in SLOTTED_TARGET_SLOT_KEYS:
        return False
    return all(isinstance(value.get(slot), (list, tuple)) for slot in SLOTTED_TARGET_SLOT_KEYS[kind])


def flatten_slotted_targets(value: dict[str, Any]) -> tuple[int, ...]:
    """Flatten slotted target IDs in Lorcanito's canonical slot order."""
    if not is_slotted_target_input(value):
        raise ValueError("Invalid slotted target input")

    kind = str(value["kind"])
    flattened: list[int] = []
    for slot in SLOTTED_TARGET_SLOT_KEYS[kind]:
        for target_id in value.get(slot, ()):
            if not isinstance(target_id, int):
                raise ValueError(f"Slotted target {slot} contains non-integer value {target_id!r}")
            flattened.append(target_id)
    return tuple(flattened)


def normalize_slotted_target_input(value: dict[str, Any]) -> dict[str, Any]:
    """Return a canonical slotted target dict with tuple-valued slots."""
    if not is_slotted_target_input(value):
        raise ValueError("Invalid slotted target input")
    kind = str(value["kind"])
    normalized: dict[str, Any] = {"kind": kind}
    for slot in SLOTTED_TARGET_SLOT_KEYS[kind]:
        slot_values: list[int] = []
        for target_id in value.get(slot, ()):
            if not isinstance(target_id, int):
                raise ValueError(f"Slotted target {slot} contains non-integer value {target_id!r}")
            slot_values.append(target_id)
        normalized[slot] = tuple(slot_values)
    return normalized


def validate_slotted_targets(
    state: GameState,
    value: dict[str, Any],
    descriptor_by_slot: dict[str, TargetDescriptor] | None = None,
    *,
    actor: int | None = None,
    source_id: int | None = None,
    engine: GameEngine | None = None,
) -> None:
    """Validate a slotted target input against state and optional slot descriptors."""
    normalized = normalize_slotted_target_input(value)
    for target_id in flatten_slotted_targets(normalized):
        if target_id not in state.cards:
            raise ValueError(f"Slotted target card {target_id} does not exist")

    if not descriptor_by_slot:
        return

    for slot, descriptor in descriptor_by_slot.items():
        if slot == "kind":
            continue
        if slot not in normalized:
            raise ValueError(f"Unknown slotted target slot {slot!r}")
        for target_id in normalized[slot]:
            if not is_card_target_candidate(
                state,
                target_id,
                descriptor,
                actor=actor,
                source_id=source_id,
                engine=engine,
            ):
                raise ValueError(f"Slotted target {target_id} is not valid for slot {slot!r}")
