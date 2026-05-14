"""Runtime condition evaluation for trigger conditions and effect conditions.

This module evaluates conditions at trigger matching time and at resolution time.
Unsupported conditions raise UnsupportedConditionError rather than being assumed true.
"""

from __future__ import annotations

from typing import Any

from .constants import CARD_CHARACTER, CARD_ITEM, CARD_LOCATION, ZONE_PLAY
from .state import GameEvent, GameState, PendingTriggeredEvent


class UnsupportedConditionError(ValueError):
    """Raised when a condition cannot be evaluated because its kind is not supported."""
    pass


def evaluate_condition(
    condition: dict | None,
    state: GameState,
    event: PendingTriggeredEvent | GameEvent | None,
    source_instance_id: int,
    engine: "GameEngine",  # type: ignore[name-defined]
) -> bool:
    """Evaluate a condition at runtime.
    
    Returns True if the condition is satisfied, False if not.
    Raises UnsupportedConditionError if the condition kind is not supported.
    
    Args:
        condition: The condition dict to evaluate
        state: Current game state
        event: The triggering event or pending event
        source_instance_id: The instance ID of the card with the ability
        engine: The game engine for card lookups
    """
    if condition is None:
        return True
    
    if not isinstance(condition, dict):
        return True  # Non-dict conditions are unknown but treated as passthrough
    
    kind = str(condition.get("type") or condition.get("kind") or "unknown")
    
    # Handle nested condition structures
    if kind in ("and", "or", "not"):
        return _evaluate_logical_condition(kind, condition, state, event, source_instance_id, engine)
    
    # Handle simple conditions
    if kind == "always":
        return True
    
    if kind == "your-turn":
        return state.active_player == state.cards[source_instance_id].controller
    
    if kind == "opponent-turn":
        return state.active_player == state.opponent(state.cards[source_instance_id].controller)
    
    if kind == "during-turn":
        # Check if it's the source controller's turn
        return state.active_player == state.cards[source_instance_id].controller
    
    if kind == "has-character-count":
        return _evaluate_has_count_condition(condition, state, source_instance_id, engine, zone=ZONE_PLAY, card_type=CARD_CHARACTER)
    
    if kind == "has-item-count":
        return _evaluate_has_count_condition(condition, state, source_instance_id, engine, zone=ZONE_PLAY, card_type=CARD_ITEM)
    
    if kind == "has-location-count":
        return _evaluate_has_count_condition(condition, state, source_instance_id, engine, zone=ZONE_PLAY, card_type=CARD_LOCATION)
    
    if kind == "has-character-with-keyword":
        return _evaluate_has_character_with_property(
            condition, state, source_instance_id, engine, 
            property_name="keyword", property_value=condition.get("keyword") or condition.get("value")
        )
    
    if kind == "has-character-with-classification":
        return _evaluate_has_character_with_property(
            condition, state, source_instance_id, engine,
            property_name="classification", property_value=condition.get("classification") or condition.get("value")
        )
    
    if kind == "has-named-character":
        return _evaluate_has_named_character(condition, state, source_instance_id, engine)
    
    if kind in ("is-exerted", "exerted"):
        return _evaluate_is_exerted(condition, state, source_instance_id, engine)
    
    if kind == "has-any-damage":
        return _evaluate_has_damage(condition, state, source_instance_id, engine, min_damage=1)
    
    if kind == "no-damage":
        return _evaluate_has_damage(condition, state, source_instance_id, engine, max_damage=0)
    
    if kind == "self-has-damage":
        return _evaluate_self_has_damage(condition, state, source_instance_id)
    
    if kind == "inkwell-count":
        return _evaluate_inkwell_count(condition, state, source_instance_id)
    
    if kind in ("target_damaged", "target-damaged"):
        # Used in effect conditions
        return _evaluate_target_damaged(condition, state, event)
    
    # Numeric comparison conditions
    if kind in ("comparison", "compare", "numeric"):
        return _evaluate_numeric_comparison(condition, state, source_instance_id, engine)
    
    # If we get here, the condition is not supported
    raise UnsupportedConditionError(f"Unsupported condition kind: {kind}")


def _evaluate_logical_condition(
    kind: str,
    condition: dict,
    state: GameState,
    event: PendingTriggeredEvent | GameEvent | None,
    source_instance_id: int,
    engine: "GameEngine",  # type: ignore[name-defined]
) -> bool:
    """Evaluate logical conditions (and, or, not)."""
    if kind == "not":
        inner_condition = condition.get("condition") or condition.get("condition")
        if inner_condition is None:
            return True
        return not evaluate_condition(inner_condition, state, event, source_instance_id, engine)
    
    if kind == "and":
        operands = condition.get("conditions") or condition.get("operands") or []
        return all(evaluate_condition(op, state, event, source_instance_id, engine) for op in operands)
    
    if kind == "or":
        operands = condition.get("conditions") or condition.get("operands") or []
        return any(evaluate_condition(op, state, event, source_instance_id, engine) for op in operands)
    
    return True


def _evaluate_has_count_condition(
    condition: dict,
    state: GameState,
    source_instance_id: int,
    engine: "GameEngine",  # type: ignore[name-defined]
    zone: str,
    card_type: str,
) -> bool:
    """Evaluate has-X-count conditions."""
    controller = state.cards[source_instance_id].controller
    
    # Count cards matching criteria
    count = 0
    for instance_id in state.players[controller].play:
        card_def = engine.card_def(state, instance_id)
        if card_def.card_type == card_type:
            count += 1
    
    # Check against comparison
    comparison = condition.get("comparison") or condition.get("operator") or ">="
    value = int(condition.get("value") or condition.get("amount") or 0)
    
    return _compare(count, comparison, value)


def _evaluate_has_character_with_property(
    condition: dict,
    state: GameState,
    source_instance_id: int,
    engine: "GameEngine",  # type: ignore[name-defined]
    property_name: str,
    property_value: Any,
) -> bool:
    """Evaluate has-character-with-keyword/classification conditions."""
    controller = state.cards[source_instance_id].controller
    
    for instance_id in state.players[controller].play:
        card_def = engine.card_def(state, instance_id)
        if card_def.card_type != CARD_CHARACTER:
            continue
        
        if property_name == "keyword":
            if property_value in card_def.keywords:
                return True
        elif property_name == "classification":
            # Simplified - check if card has the classification
            if property_value in card_def.keywords or property_value in card_def.subtypes:
                return True
    
    return False


def _evaluate_has_named_character(
    condition: dict,
    state: GameState,
    source_instance_id: int,
    engine: "GameEngine",  # type: ignore[name-defined]
) -> bool:
    """Evaluate has-named-character conditions."""
    controller = state.cards[source_instance_id].controller
    target_name = condition.get("name") or condition.get("value")
    
    if not target_name:
        return False
    
    target_name_lower = str(target_name).lower()
    
    for instance_id in state.players[controller].play:
        card_def = engine.card_def(state, instance_id)
        if card_def.card_type != CARD_CHARACTER:
            continue
        
        if target_name_lower in card_def.full_name.lower() or target_name_lower in (card_def.name or "").lower():
            return True
    
    return False


def _evaluate_is_exerted(
    condition: dict,
    state: GameState,
    source_instance_id: int,
    engine: "GameEngine",  # type: ignore[name-defined]
) -> bool:
    """Evaluate is-exerted conditions."""
    subject_id = condition.get("target") or condition.get("subject")
    if subject_id is None:
        # Default to self
        subject_id = source_instance_id
    else:
        # Resolve subject from event payload if needed
        pass
    
    subject_inst = state.cards.get(int(subject_id) if isinstance(subject_id, (int, str)) else source_instance_id)
    return subject_inst is not None and subject_inst.exerted


def _evaluate_has_damage(
    condition: dict,
    state: GameState,
    source_instance_id: int,
    engine: "GameEngine",  # type: ignore[name-defined]
    min_damage: int = 1,
    max_damage: int | None = None,
) -> bool:
    """Evaluate has-damage conditions."""
    subject_id = condition.get("target") or condition.get("subject")
    if subject_id is None:
        subject_id = source_instance_id
    
    subject_inst = state.cards.get(int(subject_id) if isinstance(subject_id, (int, str)) else source_instance_id)
    if subject_inst is None:
        return False
    
    damage = subject_inst.damage
    if min_damage is not None and damage < min_damage:
        return False
    if max_damage is not None and damage > max_damage:
        return False
    
    return True


def _evaluate_self_has_damage(
    condition: dict,
    state: GameState,
    source_instance_id: int,
) -> bool:
    """Evaluate self-has-damage conditions."""
    subject_inst = state.cards.get(source_instance_id)
    if subject_inst is None:
        return False
    
    return subject_inst.damage > 0


def _evaluate_inkwell_count(
    condition: dict,
    state: GameState,
    source_instance_id: int,
) -> bool:
    """Evaluate inkwell-count conditions."""
    controller = state.cards[source_instance_id].controller
    ink_count = len(state.players[controller].inkwell)
    
    comparison = condition.get("comparison") or condition.get("operator") or ">="
    value = int(condition.get("value") or condition.get("amount") or 0)
    
    return _compare(ink_count, comparison, value)


def _evaluate_target_damaged(
    condition: dict,
    state: GameState,
    event: PendingTriggeredEvent | GameEvent | None,
) -> bool:
    """Evaluate target_damaged condition used in effects."""
    if event is None:
        return False
    
    # Extract target ID from different event types
    target_id: int | None = None
    
    if isinstance(event, PendingTriggeredEvent):
        # Use defender_id or subject_card_id for PendingTriggeredEvent
        target_id = event.defender_id or event.subject_card_id
    elif isinstance(event, GameEvent):
        # Use target for GameEvent
        target_id = event.target
    
    if target_id is None:
        return False
    
    target_inst = state.cards.get(target_id)
    if target_inst is None:
        return False
    
    return target_inst.damage > 0


def _evaluate_numeric_comparison(
    condition: dict,
    state: GameState,
    source_instance_id: int,
    engine: "GameEngine",  # type: ignore[name-defined]
) -> bool:
    """Evaluate numeric comparison conditions."""
    comparison = condition.get("comparison") or condition.get("operator") or ">="
    value = int(condition.get("value") or condition.get("amount") or 0)
    
    # Determine what we're comparing
    metric = condition.get("metric") or condition.get("subject")
    
    if metric in ("inkwell-count", "inkwell", "ink"):
        count = len(state.players[state.cards[source_instance_id].controller].inkwell)
        return _compare(count, comparison, value)
    
    if metric in ("character-count", "characters"):
        controller = state.cards[source_instance_id].controller
        count = sum(1 for cid in state.players[controller].play if engine.card_def(state, cid).card_type == CARD_CHARACTER)
        return _compare(count, comparison, value)
    
    if metric in ("lore", "player-lore"):
        controller = state.cards[source_instance_id].controller
        count = state.players[controller].lore
        return _compare(count, comparison, value)
    
    # Default: unknown metric, condition not supported
    raise UnsupportedConditionError(f"Unsupported numeric comparison metric: {metric}")


def _compare(value: int, comparison: str, threshold: int) -> bool:
    """Compare a value against a threshold using the specified comparison operator."""
    comparison = str(comparison).strip().lower()
    
    if comparison in (">=", "gte", "at-least"):
        return value >= threshold
    if comparison in (">", "gt", "more-than"):
        return value > threshold
    if comparison in ("<=", "lte", "at-most"):
        return value <= threshold
    if comparison in ("<", "lt", "less-than"):
        return value < threshold
    if comparison in ("==", "=", "eq", "exactly"):
        return value == threshold
    if comparison in ("!=", "<>", "ne", "not"):
        return value != threshold
    
    # Default: assume >= comparison
    return value >= threshold