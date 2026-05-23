"""Lorcanito-inspired trigger resolution pipeline.

This module implements the core trigger matching and bag resolution logic
inspired by the Lorcanito trigger pipeline. It provides:

- canonical_trigger_event(): Map legacy event names to canonical form
- buffer_trigger_event(): Buffer a game event as a PendingTriggeredEvent
- flush_triggered_events_to_bag(): Resolution boundary - scan and enqueue matching triggers
- collect_printed_trigger_candidates(): Collect triggers from cards in play
- trigger_matches_event(): Check if a trigger matches the pending event
- enqueue_bag_effect(): Add a matching trigger to the resolution bag
- get_next_bag_resolver(): Get the player who should resolve next bag item
- get_bag_items_for_current_resolver(): Get all bag items for the current resolver
- has_pending_bag_items(): Check if any bag items are pending
- remove_bag_effect(): Remove and return a bag entry
- can_resolve_bag_effect_by_restrictions(): Check trigger restrictions
- record_bag_effect_resolution(): Update occurrence/resolution ledgers
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .cards import CardDef, TriggerDef
from .constants import (
    CARD_ACTION,
    CARD_CHARACTER,
    CARD_ITEM,
    CARD_LOCATION,
    LEGACY_EVENT_MAP,
    TRIGGER_EVENT_BANISH,
    TRIGGER_EVENT_BANISH_IN_CHALLENGE,
    TRIGGER_EVENT_BE_CHOSEN,
    TRIGGER_EVENT_CHALLENGE,
    TRIGGER_EVENT_CHALLENGED_AND_BANISHED,
    TRIGGER_EVENT_DAMAGE_DEALT,
    TRIGGER_EVENT_REMOVE_DAMAGE,
    TRIGGER_EVENT_DISCARD,
    TRIGGER_EVENT_DRAW,
    TRIGGER_EVENT_END_TURN,
    TRIGGER_EVENT_EXERT,
    TRIGGER_EVENT_GAIN_LORE,
    TRIGGER_EVENT_INK,
    TRIGGER_EVENT_LEAVE_PLAY,
    TRIGGER_EVENT_LEAVE_DISCARD,
    TRIGGER_EVENT_LOSE_LORE,
    TRIGGER_EVENT_MOVE,
    TRIGGER_EVENT_PLAY,
    TRIGGER_EVENT_PUT_CARD_UNDER,
    TRIGGER_EVENT_QUEST,
    TRIGGER_EVENT_READY,
    TRIGGER_EVENT_RETURN_TO_HAND,
    TRIGGER_EVENT_SING,
    TRIGGER_EVENT_START_TURN,
    TRIGGER_EVENT_SUPPORT,
    ZONE_DISCARD,
    ZONE_INKWELL,
    ZONE_PLAY,
)
from .state import BagEffectEntry, GameEvent, GameState, PendingTriggeredEvent

# Supported trigger events for trigger matching.
SUPPORTED_TRIGGER_EVENTS = frozenset({
    TRIGGER_EVENT_PLAY,
    TRIGGER_EVENT_QUEST,
    TRIGGER_EVENT_CHALLENGE,
    TRIGGER_EVENT_CHALLENGED_AND_BANISHED,
    TRIGGER_EVENT_BANISH,
    TRIGGER_EVENT_BANISH_IN_CHALLENGE,
    TRIGGER_EVENT_LEAVE_PLAY,
    TRIGGER_EVENT_START_TURN,
    TRIGGER_EVENT_END_TURN,
    TRIGGER_EVENT_INK,
    TRIGGER_EVENT_SING,
    TRIGGER_EVENT_MOVE,
    TRIGGER_EVENT_DISCARD,
    TRIGGER_EVENT_LEAVE_DISCARD,
    TRIGGER_EVENT_RETURN_TO_HAND,
    TRIGGER_EVENT_DRAW,
    TRIGGER_EVENT_EXERT,
    TRIGGER_EVENT_READY,
    TRIGGER_EVENT_GAIN_LORE,
    TRIGGER_EVENT_LOSE_LORE,
    TRIGGER_EVENT_SUPPORT,
    TRIGGER_EVENT_DAMAGE_DEALT,
    TRIGGER_EVENT_REMOVE_DAMAGE,
    TRIGGER_EVENT_BE_CHOSEN,
    TRIGGER_EVENT_PUT_CARD_UNDER,
})

# Supported `on` values for B2 trigger matching
SUPPORTED_ON_VALUES = frozenset({
    "SELF",
    "YOU",
    "CONTROLLER",
    "OPPONENT",
    "ANY_PLAYER",
    "YOUR_CHARACTERS",
    "YOUR_OTHER_CHARACTERS",
    "OPPOSING_CHARACTERS",
    "OPPONENT_CHARACTERS",
    "ANY_CHARACTER",
    "YOUR_ITEMS",
    "ANY_ITEM",
    "YOUR_LOCATIONS",
    "YOUR_ACTIONS",
    "YOUR_SONGS",
    "CHARACTERS_HERE",
    "CHARACTER_HERE",
    "YOUR_CHARACTERS_OR_LOCATIONS",
    "YOUR_CHARACTERS_OR_LOCATIONS_WITH_CARD_UNDER",
})


def _norm(value: Any) -> str:
    return str(value).strip().lower()


def _card_classifications(card: CardDef) -> tuple[str, ...]:
    values: list[str] = []
    for value in card.subtypes or ():
        if isinstance(value, str) and value.strip():
            values.append(value.strip())
    for raw_source in (card.raw_lorcanito_source, card.raw):
        if isinstance(raw_source, dict):
            for value in raw_source.get("classifications", ()) or ():
                if isinstance(value, str) and value.strip():
                    values.append(value.strip())
    return tuple(dict.fromkeys(values))


def _card_keywords(card: CardDef) -> tuple[str, ...]:
    values: list[str] = []
    for value in card.keywords or ():
        if isinstance(value, str) and value.strip():
            values.append(value.strip())
    for keyword_def in card.keyword_defs or ():
        value = getattr(keyword_def, "keyword", None)
        if isinstance(value, str) and value.strip():
            values.append(value.strip())
    return tuple(dict.fromkeys(values))


def _card_names(card: CardDef) -> tuple[str, ...]:
    names = []
    for attr in ("full_name", "name", "simple_name"):
        value = getattr(card, attr, None)
        if isinstance(value, str) and value.strip():
            names.append(value.strip())
    return tuple(dict.fromkeys(names))


def _card_matches_type(card: CardDef, card_type: Any) -> bool:
    wanted = _norm(card_type)
    if wanted == "song":
        return card.card_type == CARD_ACTION and _norm(card.action_subtype or "") == "song"
    return _norm(card.card_type) == wanted


@dataclass(frozen=True)
class TriggerCandidate:
    """A trigger candidate for matching against a pending event."""
    source_instance_id: int
    source_card: CardDef
    trigger: TriggerDef
    ability_id: str
    ability_key: str
    ability_index: int
    source_zones: tuple[str, ...]


def canonical_trigger_event(event: GameEvent | str) -> str:
    """Map a legacy event name or GameEvent to canonical trigger event name.

    Uses LEGACY_EVENT_MAP from constants.py (which has been expanded to cover
    all gameplay events including INKED, CARD_DRAWN, DAMAGE_DEALT, etc.).
    """
    if isinstance(event, GameEvent):
        event_type = event.event_type
    else:
        event_type = str(event)

    return LEGACY_EVENT_MAP.get(event_type, event_type)


def expand_trigger_event(event: str) -> tuple[str, ...]:
    """Expand a canonical event into the full set of trigger event names to check.

    lorcanito-style leave-play expansion: when a card leaves play, it can trigger
    on banish, banish-in-challenge, return-to-hand, or ink events.
    """
    if event == TRIGGER_EVENT_LEAVE_PLAY:
        return (
            TRIGGER_EVENT_BANISH,
            TRIGGER_EVENT_BANISH_IN_CHALLENGE,
            TRIGGER_EVENT_RETURN_TO_HAND,
            TRIGGER_EVENT_INK,
        )
    return (event,)


def buffer_trigger_event(
    state: GameState,
    event: GameEvent,
    *,
    source_card_type: str | None = None,
    subject_card_id: int | None = None,
    trigger_source_card_id: int | None = None,
    attacker_id: int | None = None,
    defender_id: int | None = None,
    happened_in_challenge: bool = False,
    event_snapshot: dict[str, Any] | None = None,
) -> PendingTriggeredEvent:
    """Buffer a game event as a PendingTriggeredEvent for later trigger matching.

    Payload values emitted by GameEngine.emit_event() are authoritative. Explicit
    function arguments remain fallback values for tests and older call sites.
    """
    canonical = canonical_trigger_event(event)
    payload: dict[str, Any] = dict(event.payload or {})

    def first_present(*values: Any) -> Any:
        for value in values:
            if value is not None:
                return value
        return None

    resolved_player_id = first_present(
        payload.get("player_id"),
        payload.get("playerId"),
        event.actor,
    )
    resolved_subject_card_id = first_present(
        payload.get("subject_card_id"),
        payload.get("subjectCardId"),
        subject_card_id,
        event.source,
    )
    resolved_trigger_source_card_id = first_present(
        payload.get("trigger_source_card_id"),
        payload.get("triggerSourceCardId"),
        trigger_source_card_id,
    )
    resolved_source_card_type = first_present(
        payload.get("source_card_type"),
        payload.get("sourceCardType"),
        payload.get("card_type"),
        payload.get("cardType"),
        payload.get("banished_card_type"),
        payload.get("banishedCardType"),
        source_card_type,
    )
    resolved_attacker_id = first_present(
        payload.get("attacker_id"),
        payload.get("attackerId"),
        attacker_id,
    )
    resolved_defender_id = first_present(
        payload.get("defender_id"),
        payload.get("defenderId"),
        defender_id,
        event.target,
    )
    resolved_defender_card_type = first_present(
        payload.get("defender_card_type"),
        payload.get("defenderCardType"),
    )
    resolved_happened_in_challenge = bool(first_present(
        payload.get("happened_in_challenge"),
        payload.get("happenedInChallenge"),
        happened_in_challenge,
    ))
    resolved_from_zone = first_present(
        payload.get("from_zone"),
        payload.get("fromZone"),
    )
    resolved_to_zone = first_present(
        payload.get("to_zone"),
        payload.get("toZone"),
    )
    resolved_damage_dealt = first_present(
        payload.get("damage_dealt"),
        payload.get("damageDealt"),
        payload.get("attacker_damage_dealt"),
        payload.get("attackerDamageDealt"),
    )
    resolved_damage_removed = first_present(
        payload.get("damage_removed"),
        payload.get("damageRemoved"),
        payload.get("healedAmount"),
        payload.get("healed_amount"),
    )
    resolved_lore_gained = first_present(
        payload.get("lore_gained"),
        payload.get("loreGained"),
        payload.get("lore"),
    )

    snapshot: dict[str, Any] = dict(payload)
    if event_snapshot:
        snapshot.update(event_snapshot)

    snapshot.update({
        "event": canonical,
        "player_id": resolved_player_id,
        "subject_card_id": resolved_subject_card_id,
        "trigger_source_card_id": resolved_trigger_source_card_id,
        "source_card_type": resolved_source_card_type,
        "attacker_id": resolved_attacker_id,
        "defender_id": resolved_defender_id,
        "defender_card_type": resolved_defender_card_type,
        "happened_in_challenge": resolved_happened_in_challenge,
        "from_zone": resolved_from_zone,
        "to_zone": resolved_to_zone,
        "damage_dealt": resolved_damage_dealt,
        "damage_removed": resolved_damage_removed,
        "healedAmount": resolved_damage_removed,
        "triggerAmount": resolved_damage_removed,
        "lore_gained": resolved_lore_gained,
    })

    pending = PendingTriggeredEvent(
        id=state.next_event_id(),
        event=canonical,
        player_id=resolved_player_id,
        subject_card_id=resolved_subject_card_id,
        trigger_source_card_id=resolved_trigger_source_card_id,
        source_card_type=resolved_source_card_type,
        from_zone=resolved_from_zone,
        to_zone=resolved_to_zone,
        attacker_id=resolved_attacker_id,
        defender_id=resolved_defender_id,
        defender_card_type=resolved_defender_card_type,
        happened_in_challenge=resolved_happened_in_challenge,
        event_snapshot=snapshot,
        payload=payload,
    )
    state.pending_trigger_events.append(pending)
    return pending


def collect_printed_trigger_candidates(
    state: GameState,
    engine: "GameEngine",  # type: ignore[name-defined]
    *,
    window: str | None = None,
) -> list[TriggerCandidate]:
    """Collect trigger candidates from cards in zones that can legally observe.

    Lorcanito snapshots leave-play trigger candidates before movement. The
    current Python trigger pipeline collects candidates at flush time, so it must
    also consider cards that have moved to discard when their projected trigger
    explicitly allows discard/source leave-play windows.
    """
    candidates: list[TriggerCandidate] = []

    for instance_id in sorted(state.cards):
        inst = state.cards[instance_id]
        if inst.zone not in {ZONE_PLAY, ZONE_DISCARD}:
            continue

        card = engine.card_def(state, instance_id)
        for idx, trigger in enumerate(card.triggers):
            if trigger.event not in SUPPORTED_TRIGGER_EVENTS:
                continue

            source_zones = trigger.source_zones or (ZONE_PLAY,)
            if inst.zone not in source_zones:
                continue

            candidates.append(TriggerCandidate(
                source_instance_id=instance_id,
                source_card=card,
                trigger=trigger,
                ability_id=trigger.id or f"trigger_{instance_id}_{idx}",
                ability_key=f"{card.id}:trigger:{idx}",
                ability_index=idx,
                source_zones=source_zones,
            ))

    return candidates


def trigger_matches_event(
    state: GameState,
    engine: "GameEngine",  # type: ignore[name-defined]
    candidate: TriggerCandidate,
    pending: PendingTriggeredEvent,
) -> bool:
    """Check if a trigger candidate matches the pending event."""
    trigger = candidate.trigger

    if pending.event not in expand_trigger_event(trigger.event):
        return False

    # Check source zone restrictions
    if trigger.source_zones:
        source_zone = state.cards[candidate.source_instance_id].zone
        if source_zone not in trigger.source_zones:
            return False

    # Check `on` filter (subject of the trigger)
    on_value = trigger.on

    # Handle string aliases
    if isinstance(on_value, str):
        if not _on_filter_matches_string(state, engine, candidate, pending, on_value):
            return False
    elif isinstance(on_value, dict):
        if not _on_filter_matches_object(state, engine, candidate, pending, on_value):
            return False
    # None means match any subject

    # Self-entry rule: A card cannot observe its own play/ink event unless on == SELF
    if pending.trigger_source_card_id == candidate.source_instance_id:
        if trigger.event in {TRIGGER_EVENT_PLAY, TRIGGER_EVENT_INK}:
            if on_value != "SELF":
                return False

    # Check defender-is-character restriction
    for restriction in trigger.restrictions:
        if not _restriction_satisfied(state, engine, candidate, pending, restriction):
            return False

    return True


def _on_filter_matches_string(
    state: GameState,
    engine: "GameEngine",  # type: ignore[name-defined]
    candidate: TriggerCandidate,
    pending: PendingTriggeredEvent,
    on_value: str,
) -> bool:
    """Check if a string `on` value matches the pending event."""
    source_instance_id = candidate.source_instance_id
    subject_card_id = pending.subject_card_id
    source_controller = state.cards[source_instance_id].controller

    if on_value == "SELF":
        return subject_card_id == source_instance_id

    if on_value in {"YOU", "CONTROLLER"}:
        # Trigger fires when its controller performs the action
        return pending.player_id == source_controller

    if on_value == "OPPONENT":
        # Trigger fires for opponent action
        return pending.player_id is not None and pending.player_id != source_controller

    if on_value == "ANY_PLAYER":
        # Trigger fires for any player action
        return pending.player_id is not None

    if on_value == "YOUR_CHARACTERS":
        # Trigger fires for any character you control
        if subject_card_id is None:
            return True
        subject_card = state.cards.get(subject_card_id)
        if subject_card is None:
            return False
        subject_def = engine.card_def(state, subject_card_id)
        return subject_card.controller == source_controller and subject_def.card_type == CARD_CHARACTER

    if on_value == "YOUR_OTHER_CHARACTERS":
        # Exclude self
        if subject_card_id == source_instance_id:
            return False
        if subject_card_id is None:
            return True
        subject_card = state.cards.get(subject_card_id)
        if subject_card is None:
            return False
        subject_def = engine.card_def(state, subject_card_id)
        return subject_card.controller == source_controller and subject_def.card_type == CARD_CHARACTER

    if on_value == "OPPOSING_CHARACTERS":
        if subject_card_id is None:
            return True
        subject_card = state.cards.get(subject_card_id)
        if subject_card is None:
            return False
        subject_def = engine.card_def(state, subject_card_id)
        return subject_card.controller == state.opponent(source_controller) and subject_def.card_type == CARD_CHARACTER

    if on_value == "OPPONENT_CHARACTERS":
        # Trigger fires for opponent's characters
        if subject_card_id is None:
            return True
        subject_card = state.cards.get(subject_card_id)
        if subject_card is None:
            return False
        subject_def = engine.card_def(state, subject_card_id)
        return subject_card.controller == state.opponent(source_controller) and subject_def.card_type == CARD_CHARACTER

    if on_value == "ANY_CHARACTER":
        if subject_card_id is None:
            return True
        subject_card = state.cards.get(subject_card_id)
        if subject_card is None:
            return False
        subject_def = engine.card_def(state, subject_card_id)
        return subject_def.card_type == CARD_CHARACTER

    if on_value == "YOUR_ITEMS":
        # Trigger fires for items you control
        if subject_card_id is None:
            return True
        subject_card = state.cards.get(subject_card_id)
        if subject_card is None:
            return False
        subject_def = engine.card_def(state, subject_card_id)
        return subject_card.controller == source_controller and subject_def.card_type == CARD_ITEM

    if on_value == "ANY_ITEM":
        if subject_card_id is None:
            return True
        subject_card = state.cards.get(subject_card_id)
        if subject_card is None:
            return False
        subject_def = engine.card_def(state, subject_card_id)
        return subject_def.card_type == CARD_ITEM

    if on_value == "YOUR_LOCATIONS":
        # Trigger fires for locations you control
        if subject_card_id is None:
            return True
        subject_card = state.cards.get(subject_card_id)
        if subject_card is None:
            return False
        subject_def = engine.card_def(state, subject_card_id)
        return subject_card.controller == source_controller and subject_def.card_type == CARD_LOCATION

    if on_value == "YOUR_ACTIONS":
        # Trigger fires for actions you control
        if subject_card_id is None:
            return True
        subject_card = state.cards.get(subject_card_id)
        if subject_card is None:
            return False
        subject_def = engine.card_def(state, subject_card_id)
        return subject_card.controller == source_controller and subject_def.card_type == CARD_ACTION

    if on_value == "YOUR_SONGS":
        # Trigger fires for song actions you control
        if subject_card_id is None:
            return True
        subject_card = state.cards.get(subject_card_id)
        if subject_card is None:
            return False
        if subject_card.controller != source_controller:
            return False
        subject_def = engine.card_def(state, subject_card_id)
        return _card_matches_type(subject_def, "song")

    if on_value in {"CHARACTERS_HERE", "CHARACTER_HERE"}:
        # Match only when subject is a character at the same location as the trigger source
        if subject_card_id is None:
            return False
        subject_card = state.cards.get(subject_card_id)
        if subject_card is None:
            return False
        subject_def = engine.card_def(state, subject_card_id)
        if subject_def.card_type != CARD_CHARACTER:
            return False
        # Prefer subjectAtLocationId from event snapshot, fall back to location_instance_id
        location_id = pending.event_snapshot.get("subjectAtLocationId")
        if location_id is None:
            location_id = pending.event_snapshot.get("subject_at_location_id")
        if location_id is None:
            location_id = subject_card.location_instance_id
        return location_id == source_instance_id

    if on_value == "YOUR_CHARACTERS_OR_LOCATIONS":
        # Trigger fires for characters or locations you control
        if subject_card_id is None:
            return True
        subject_card = state.cards.get(subject_card_id)
        if subject_card is None:
            return False
        if subject_card.controller != source_controller:
            return False
        subject_def = engine.card_def(state, subject_card_id)
        return subject_def.card_type in {"character", "location"}

    if on_value == "YOUR_CHARACTERS_OR_LOCATIONS_WITH_CARD_UNDER":
        # Trigger fires for controlled character/location subjects with cards under them
        if subject_card_id is None:
            return True
        subject_card = state.cards.get(subject_card_id)
        if subject_card is None:
            return False
        if subject_card.controller != source_controller:
            return False
        subject_def = engine.card_def(state, subject_card_id)
        if subject_def.card_type not in {"character", "location"}:
            return False
        return len(subject_card.cards_under) > 0

    # Unknown string filter: fail closed per Microfix 11 rule 3
    return False


def _on_filter_matches_object(
    state: GameState,
    engine: "GameEngine",  # type: ignore[name-defined]
    candidate: TriggerCandidate,
    pending: PendingTriggeredEvent,
    on_value: dict[str, Any],
) -> bool:
    """Check if an object query `on` value matches the pending event.

    Implements exact object `on` filter matching per MICROFIX_11_BRIEF_2B.

    Object keys supported:
    - controller: "you" | "opponent" | "any"
    - owner: "you" | "opponent" | "any"
    - cardType: exact match (with special handling for "song")
    - cardTypes: array of card types to match
    - classification: single classification match
    - classifications: array of classifications (any match)
    - name: card name match (case-insensitive)
    - hasKeyword: keyword match
    - excludeSelf: exclude the trigger source from matching
    - filters: array of runtime filters
    """
    supported_keys = {
        "controller",
        "owner",
        "cardType",
        "cardTypes",
        "classification",
        "classifications",
        "name",
        "hasKeyword",
        "excludeSelf",
        "filters",
    }
    if any(key not in supported_keys for key in on_value):
        return False

    source_instance_id = candidate.source_instance_id
    subject_card_id = pending.subject_card_id

    if subject_card_id is None:
        return True

    # excludeSelf: block the source card from matching itself
    if on_value.get("excludeSelf") is True:
        if subject_card_id == source_instance_id:
            return False

    subject_card = state.cards.get(subject_card_id)
    if subject_card is None:
        return False

    subject_def = engine.card_def(state, subject_card_id)
    source_controller = state.cards[source_instance_id].controller

    # Controller filter
    controller_filter = on_value.get("controller")
    if controller_filter:
        if controller_filter == "you":
            if subject_card.controller != source_controller:
                return False
        elif controller_filter == "opponent":
            if subject_card.controller != state.opponent(source_controller):
                return False
        elif controller_filter == "any":
            pass  # any controller matches
        else:
            return False  # Unknown controller value fails closed

    # Owner filter
    owner_filter = on_value.get("owner")
    if owner_filter:
        if owner_filter == "you":
            if subject_card.owner != source_controller:
                return False
        elif owner_filter == "opponent":
            if subject_card.owner != state.opponent(source_controller):
                return False
        elif owner_filter == "any":
            pass  # any owner matches
        else:
            return False  # Unknown owner value fails closed

    # cardType filter - exact match with song special handling
    card_type_filter = on_value.get("cardType")
    if card_type_filter:
        if not _card_matches_type(subject_def, card_type_filter):
            return False

    # cardTypes filter - array of card types (any match)
    card_types_filter = on_value.get("cardTypes")
    if card_types_filter is not None:
        if isinstance(card_types_filter, list):
            if not any(_card_matches_type(subject_def, ct) for ct in card_types_filter):
                return False
        else:
            return False  # cardTypes must be array

    # classification filter - single classification
    classification_filter = on_value.get("classification")
    if classification_filter:
        cls_lower = _norm(classification_filter)
        if cls_lower not in {_norm(value) for value in _card_classifications(subject_def)}:
            return False

    # classifications filter - array of classifications (any match)
    classifications_filter = on_value.get("classifications")
    if classifications_filter is not None:
        if isinstance(classifications_filter, list):
            available = {_norm(value) for value in _card_classifications(subject_def)}
            if not any(_norm(cls) in available for cls in classifications_filter):
                return False
        else:
            return False  # classifications must be array

    # name filter
    name_filter = on_value.get("name")
    if name_filter:
        wanted_name = _norm(name_filter)
        if wanted_name not in {_norm(name) for name in _card_names(subject_def)}:
            return False

    # hasKeyword filter
    has_keyword_filter = on_value.get("hasKeyword")
    if has_keyword_filter:
        if _norm(has_keyword_filter) not in {_norm(keyword) for keyword in _card_keywords(subject_def)}:
            return False

    # filters[] runtime filters
    filters = on_value.get("filters")
    if filters is not None:
        if not isinstance(filters, list):
            return False

        for f in filters:
            if not isinstance(f, dict) or "type" not in f:
                return False

            filter_type = f.get("type")

            if filter_type == "ink-type":
                ink_type = f.get("inkType")
                if not ink_type:
                    return False
                # Check CardDef.ink field for ink type matching
                card_inks = { _norm(subject_def.ink), *{_norm(color) for color in subject_def.colors} }
                if _norm(ink_type) not in card_inks:
                    return False

            elif filter_type == "damaged":
                damage = getattr(subject_card, "damage", 0) or 0
                if damage <= 0:
                    return False

            elif filter_type == "exerted":
                # CardInstance uses exerted boolean field
                if not getattr(subject_card, "exerted", False):
                    return False

            elif filter_type == "ready":
                # CardInstance uses exerted boolean field (ready = not exerted)
                if getattr(subject_card, "exerted", False):
                    return False

            elif filter_type == "has-keyword":
                keyword = f.get("keyword")
                if not keyword:
                    return False
                if _norm(keyword) not in {_norm(value) for value in _card_keywords(subject_def)}:
                    return False

            elif filter_type == "has-classification":
                classification = f.get("classification")
                if not classification:
                    return False
                if _norm(classification) not in {_norm(value) for value in _card_classifications(subject_def)}:
                    return False

            elif filter_type == "at-location":
                location = f.get("location")
                if not location:
                    return False
                # "source" means the trigger source's location (its location_instance_id)
                source_card = state.cards.get(source_instance_id)
                if source_card is None:
                    return False
                if location == "source":
                    expected_location = getattr(source_card, "location_instance_id", source_instance_id)
                    # If source has no location set, default to source instance id
                    if expected_location is None:
                        expected_location = source_instance_id
                else:
                    expected_location = location
                subject_location = getattr(subject_card, "location_instance_id", None)
                # If no location is set on subject, it's not at any specific location
                if subject_location is None:
                    return False
                if subject_location != expected_location:
                    return False

            else:
                # Unknown filter type must return False (fail closed)
                return False

    return True


def _restriction_satisfied(
    state: GameState,
    engine: "GameEngine",  # type: ignore[name-defined]
    candidate: TriggerCandidate,
    pending: PendingTriggeredEvent,
    restriction: dict[str, Any],
) -> bool:
    """Check if a trigger restriction is satisfied."""
    restriction_type = restriction.get("type") or restriction.get("kind")

    if restriction_type == "defender-is-character":
        # Only fires when defender in challenge is a character
        if pending.event == TRIGGER_EVENT_CHALLENGE:
            if pending.defender_id is None:
                return True  # No defender means restriction not violated
            defender_card = state.cards.get(pending.defender_id)
            if defender_card:
                defender_def = engine.card_def(state, pending.defender_id)
                if defender_def.card_type != CARD_CHARACTER:
                    return False

    # Default: restriction satisfied
    return True


def enqueue_bag_effect(
    state: GameState,
    engine: "GameEngine",  # type: ignore[name-defined]
    candidate: TriggerCandidate,
    pending: PendingTriggeredEvent,
) -> BagEffectEntry | None:
    """Create a BagEffectEntry and enqueue it for resolution."""
    trigger = candidate.trigger

    # Determine occurrence index for per-occurrence tracking
    trigger_key = candidate.ability_key
    occurrence_index = state.trigger_occurrences.get(trigger_key, 0) + 1
    state.trigger_occurrences[trigger_key] = occurrence_index

    # Determine chooser (controller by default for most triggers)
    source_card = state.cards[candidate.source_instance_id]
    controller_id = source_card.controller

    # Optional triggers have a chooser; mandatory triggers use controller.
    # Lorcanito also models some mandatory triggers with an optional top-level
    # effect (for example Tigger's "you may" return). Treat those bag entries
    # as decline-capable so the choice is resolved through RESOLVE_BAG.
    is_optional = (
        trigger.optional
        or (trigger.auto_resolve is False)
        or any(getattr(effect, "kind", None) == "optional" for effect in trigger.effects)
    )
    chooser_id = controller_id  # Could be different for opponent-triggered effects

    entry = BagEffectEntry(
        id=state.next_bag_id(),
        kind="triggered_ability",
        ability_id=candidate.ability_id,
        ability_index=candidate.ability_index,
        ability_key=candidate.ability_key,
        ability_name=trigger.id,
        auto_resolve=trigger.auto_resolve if trigger.auto_resolve is not None else True,
        controller_id=controller_id,
        chooser_id=chooser_id,
        source_id=candidate.source_instance_id,
        source_card_id=candidate.source_card.id,
        trigger={
            "event": trigger.event,
            "on": trigger.on,
            "timing": trigger.timing,
            "source_zones": list(trigger.source_zones),
            "restrictions": [dict(r) for r in trigger.restrictions],
            "optional": is_optional,
        },
        condition=dict(trigger.condition) if trigger.condition else None,
        effects=tuple(trigger.effects),
        occurrence_index=occurrence_index,
        event=pending,
        raw={},
    )

    state.bag.append(entry)
    return entry


def flush_triggered_events_to_bag(
    state: GameState,
    engine: "GameEngine",  # type: ignore[name-defined]
    *,
    window: str | None = None,
) -> int:
    """Flush pending trigger events to bag entries at resolution boundary.

    Returns the number of bag entries added.
    """
    if not state.pending_trigger_events:
        return 0

    enqueued_count = 0

    # Collect candidates from cards currently in play
    candidates = collect_printed_trigger_candidates(state, engine, window=window)

    # Process each buffered event
    for pending in list(state.pending_trigger_events):
        for candidate in candidates:
            if trigger_matches_event(state, engine, candidate, pending):
                entry = enqueue_bag_effect(state, engine, candidate, pending)
                if entry:
                    enqueued_count += 1

    # Clear the pending events after flushing
    state.pending_trigger_events.clear()

    return enqueued_count


def get_next_bag_resolver(state: GameState) -> int | None:
    """Get the player who should resolve the next bag item.

    Uses rotation based on last_bag_resolver when multiple players have bag items.
    """
    if not state.bag:
        return None

    # Get the set of controllers who have pending bag items
    resolver_counts: dict[int, int] = {}
    for entry in state.bag:
        resolver_counts[entry.controller_id] = resolver_counts.get(entry.controller_id, 0) + 1

    if not resolver_counts:
        return None

    # If only one player has items, they resolve
    if len(resolver_counts) == 1:
        return list(resolver_counts.keys())[0]

    # Multiple players: rotate based on last resolver
    last = state.last_bag_resolver

    # Try to find a player who has items and isn't the last resolver
    for player in (0, 1):
        if player != last and player in resolver_counts:
            return player

    # Fallback: use the player after last (wrapping)
    if last is not None:
        return state.opponent(last)

    # No last resolver: return player 0
    return 0


def get_bag_items_for_current_resolver(state: GameState) -> list[BagEffectEntry]:
    """Get all bag items that the current resolver can act on."""
    resolver = get_next_bag_resolver(state)
    if resolver is None:
        return []

    # Return items where the resolver is the controller or chooser
    return [
        entry for entry in state.bag
        if entry.controller_id == resolver or entry.chooser_id == resolver
    ]


def has_pending_bag_items(state: GameState) -> bool:
    """Check if any bag items are pending resolution."""
    return len(state.bag) > 0


def remove_bag_effect(state: GameState, bag_id: str) -> BagEffectEntry | None:
    """Remove and return a bag entry by ID."""
    for idx, entry in enumerate(state.bag):
        if entry.id == bag_id:
            return state.bag.pop(idx)
    return None


def can_resolve_bag_effect_by_restrictions(state: GameState, entry: BagEffectEntry) -> bool:
    """Check if a bag effect can be resolved based on trigger restrictions."""
    # Check once-per-turn and occurrence limits
    trigger_key = entry.ability_key

    # Check if this is a once-per-turn trigger and if it already resolved
    # (simplified - full implementation would check trigger_resolutions ledger)

    return True


def record_bag_effect_resolution(state: GameState, entry: BagEffectEntry) -> None:
    """Record that a bag effect was resolved, updating occurrence and resolution ledgers."""
    trigger_key = entry.ability_key
    state.trigger_resolutions[trigger_key] = state.trigger_resolutions.get(trigger_key, 0) + 1


def set_last_bag_resolver(state: GameState, player: int) -> None:
    """Set the last player who resolved a bag item."""
    state.last_bag_resolver = player


def get_trigger_occurrences(state: GameState, ability_key: str) -> int:
    """Get the number of times a trigger has occurred."""
    return state.trigger_occurrences.get(ability_key, 0)


def get_trigger_resolutions(state: GameState, ability_key: str) -> int:
    """Get the number of times a trigger has been resolved."""
    return state.trigger_resolutions.get(ability_key, 0)
