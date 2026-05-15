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
    CARD_CHARACTER,
    CARD_LOCATION,
    LEGACY_EVENT_MAP,
    TRIGGER_EVENT_BANISH,
    TRIGGER_EVENT_CHALLENGE,
    TRIGGER_EVENT_DAMAGE_DEALT,
    TRIGGER_EVENT_DISCARD,
    TRIGGER_EVENT_DRAW,
    TRIGGER_EVENT_END_TURN,
    TRIGGER_EVENT_EXERT,
    TRIGGER_EVENT_GAIN_LORE,
    TRIGGER_EVENT_INK,
    TRIGGER_EVENT_LEAVE_PLAY,
    TRIGGER_EVENT_MOVE,
    TRIGGER_EVENT_PLAY,
    TRIGGER_EVENT_QUEST,
    TRIGGER_EVENT_READY,
    TRIGGER_EVENT_RETURN_TO_HAND,
    TRIGGER_EVENT_SING,
    TRIGGER_EVENT_START_TURN,
    TRIGGER_EVENT_SUPPORT,
    ZONE_INKWELL,
    ZONE_PLAY,
)
from .state import BagEffectEntry, GameEvent, GameState, PendingTriggeredEvent

# Supported trigger events for B2
SUPPORTED_TRIGGER_EVENTS = frozenset({
    TRIGGER_EVENT_PLAY,
    TRIGGER_EVENT_QUEST,
    TRIGGER_EVENT_CHALLENGE,
    TRIGGER_EVENT_BANISH,
    TRIGGER_EVENT_START_TURN,
    TRIGGER_EVENT_END_TURN,
    TRIGGER_EVENT_INK,
    TRIGGER_EVENT_MOVE,
    TRIGGER_EVENT_DISCARD,
    TRIGGER_EVENT_RETURN_TO_HAND,
    TRIGGER_EVENT_DRAW,
    TRIGGER_EVENT_EXERT,
    TRIGGER_EVENT_READY,
    TRIGGER_EVENT_GAIN_LORE,
    TRIGGER_EVENT_SUPPORT,
    TRIGGER_EVENT_DAMAGE_DEALT,
    "banish-in-challenge",
})

# Supported `on` values for B2 trigger matching
SUPPORTED_ON_VALUES = frozenset({"SELF", "YOU", "CONTROLLER", "OPPONENT", "YOUR_CHARACTERS", "YOUR_OTHER_CHARACTERS", "OPPOSING_CHARACTERS", "ANY_CHARACTER"})


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
            "banish-in-challenge",
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
    """Buffer a game event as a PendingTriggeredEvent for later trigger matching."""
    canonical = canonical_trigger_event(event)
    pending = PendingTriggeredEvent(
        id=state.next_event_id(),
        event=canonical,
        player_id=event.actor,
        subject_card_id=subject_card_id or event.source,
        trigger_source_card_id=trigger_source_card_id,
        source_card_type=source_card_type,
        attacker_id=attacker_id,
        defender_id=defender_id,
        happened_in_challenge=happened_in_challenge,
        event_snapshot=event_snapshot or {},
        payload=dict(event.payload) if event.payload else {},
    )
    state.pending_trigger_events.append(pending)
    return pending


def collect_printed_trigger_candidates(
    state: GameState,
    engine: "GameEngine",  # type: ignore[name-defined]
    *,
    window: str | None = None,
) -> list[TriggerCandidate]:
    """Collect all trigger candidates from cards currently in play."""
    candidates: list[TriggerCandidate] = []
    
    for player in (0, 1):
        for instance_id in state.players[player].play:
            card = engine.card_def(state, instance_id)
            for idx, trigger in enumerate(card.triggers):
                if trigger.event not in SUPPORTED_TRIGGER_EVENTS:
                    continue
                
                candidates.append(TriggerCandidate(
                    source_instance_id=instance_id,
                    source_card=card,
                    trigger=trigger,
                    ability_id=trigger.id or f"trigger_{instance_id}_{idx}",
                    ability_key=f"{card.id}:trigger:{idx}",
                    ability_index=idx,
                    source_zones=trigger.source_zones,
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
    
    # Event type must match
    if trigger.event != pending.event:
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
    
    if on_value == "SELF":
        return subject_card_id == source_instance_id
    
    if on_value in {"YOU", "CONTROLLER"}:
        # Trigger fires when its controller performs the action
        source_controller = state.cards[source_instance_id].controller
        return pending.player_id == source_controller
    
    if on_value == "OPPONENT":
        # Trigger fires for opponent action
        source_controller = state.cards[source_instance_id].controller
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
        return subject_card.controller == state.cards[source_instance_id].controller
    
    if on_value == "YOUR_OTHER_CHARACTERS":
        # Exclude self
        if subject_card_id == source_instance_id:
            return False
        if subject_card_id is None:
            return True
        subject_card = state.cards.get(subject_card_id)
        if subject_card is None:
            return False
        source_controller = state.cards[source_instance_id].controller
        return subject_card.controller == source_controller
    
    if on_value == "OPPOSING_CHARACTERS":
        if subject_card_id is None:
            return True
        subject_card = state.cards.get(subject_card_id)
        if subject_card is None:
            return False
        source_controller = state.cards[source_instance_id].controller
        return subject_card.controller == state.opponent(source_controller)
    
    if on_value == "ANY_CHARACTER":
        if subject_card_id is None:
            return True
        subject_card = state.cards.get(subject_card_id)
        return subject_card is not None
    
    # Default: allow match
    return True


def _on_filter_matches_object(
    state: GameState,
    engine: "GameEngine",  # type: ignore[name-defined]
    candidate: TriggerCandidate,
    pending: PendingTriggeredEvent,
    on_value: dict[str, Any],
) -> bool:
    """Check if an object query `on` value matches the pending event."""
    # Handle simple object queries like {cardType: character, controller: you}
    card_type_filter = on_value.get("cardType")
    controller_filter = on_value.get("controller")
    owner_filter = on_value.get("owner")
    classification_filter = on_value.get("classification")
    
    if pending.subject_card_id is None:
        return True
    
    subject_card = state.cards.get(pending.subject_card_id)
    if subject_card is None:
        return False
    
    subject_def = engine.card_def(state, pending.subject_card_id)
    source_controller = state.cards[candidate.source_instance_id].controller
    
    # Card type filter
    if card_type_filter:
        if subject_def.card_type != card_type_filter:
            return False
    
    # Controller filter (you = source controller, opponent = opponent)
    if controller_filter == "you":
        if subject_card.controller != source_controller:
            return False
    elif controller_filter == "opponent":
        if subject_card.controller != state.opponent(source_controller):
            return False
    
    # Owner filter
    if owner_filter == "you":
        if subject_card.owner != source_controller:
            return False
    elif owner_filter == "opponent":
        if subject_card.owner != state.opponent(source_controller):
            return False
    
    # Classification filter (simplified)
    if classification_filter:
        # Check if card has the classification keyword
        if classification_filter not in subject_def.keywords:
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
    
    # Optional triggers have a chooser; mandatory triggers use controller
    is_optional = trigger.optional or (trigger.auto_resolve is False)
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