"""Runtime condition evaluation for trigger conditions and effect conditions.

This module evaluates conditions at trigger matching time and at resolution time.
Unsupported conditions raise UnsupportedConditionError rather than being assumed true.

B2: Expanded with all conditions appearing in real decks including:
- target-query, resource-count, banished-in-challenge-this-turn
- lore comparison, card type comparison
- has-character-with-strength, has-location-in-play
- and more advanced conditions
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .constants import (
    CARD_CHARACTER,
    CARD_ITEM,
    CARD_LOCATION,
    ZONE_PLAY,
)
from .effect_types import ConditionContext
from .state import GameEvent, GameState, PendingTriggeredEvent

if TYPE_CHECKING:
    from .engine import GameEngine


class UnsupportedConditionError(ValueError):
    """Raised when a condition cannot be evaluated because its kind is not supported."""
    pass


def create_condition_context(
    state: GameState,
    source_instance_id: int,
    event: PendingTriggeredEvent | GameEvent | None = None,
    target: int | None = None,
) -> ConditionContext:
    """Create a ConditionContext from game state and trigger event.

    This is the canonical way to create a condition context for evaluation.
    """
    from .effect_types import ConditionContext

    source_card = state.cards.get(source_instance_id)
    actor = source_card.controller if source_card else state.active_player

    subject_id = None
    attacker_id = None
    defender_id = None
    happened_in_challenge = False
    payload: dict[str, Any] = {}

    if isinstance(event, PendingTriggeredEvent):
        subject_id = event.subject_card_id
        attacker_id = event.attacker_id
        defender_id = event.defender_id
        happened_in_challenge = event.happened_in_challenge
        payload = event.payload
    elif isinstance(event, GameEvent):
        subject_id = event.source
        payload = event.payload or {}

    return ConditionContext(
        actor=actor,
        controller=actor,
        source=source_instance_id,
        target=target,
        event=event,
        event_payload=payload,
        turn_player=state.active_player,
        subject_card_id=subject_id,
        attacker_id=attacker_id,
        defender_id=defender_id,
        happened_in_challenge=happened_in_challenge,
    )


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
        raise UnsupportedConditionError(
            f"Non-dict condition received: {type(condition).__name__}. "
            "Conditions must be dicts with 'type' or 'kind' key."
        )

    kind = str(condition.get("type") or condition.get("kind") or "unknown")

    # Handle nested condition structures
    if kind in ("and", "or", "not", "if"):
        return _evaluate_logical_condition(kind, condition, state, event, source_instance_id, engine)

    # Handle simple conditions
    if kind == "always":
        return True

    if kind in ("your-turn", "turn"):
        return state.active_player == state.cards[source_instance_id].controller

    if kind == "opponent-turn":
        return state.active_player == state.opponent(state.cards[source_instance_id].controller)

    if kind == "during-turn":
        return state.active_player == state.cards[source_instance_id].controller

    if kind == "has-character-count":
        return _evaluate_has_count_condition(condition, state, source_instance_id, engine, zone=ZONE_PLAY, card_type=CARD_CHARACTER)

    if kind == "has-item-count":
        return _evaluate_has_count_condition(condition, state, source_instance_id, engine, zone=ZONE_PLAY, card_type=CARD_ITEM)

    if kind == "has-location-count":
        return _evaluate_has_count_condition(condition, state, source_instance_id, engine, zone=ZONE_PLAY, card_type=CARD_LOCATION)

    if kind == "has-location-in-play":
        return _evaluate_has_location_in_play(condition, state, source_instance_id, engine)

    if kind == "has-another-character":
        return _evaluate_has_another_character(condition, state, source_instance_id, engine)

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

    if kind == "has-character-with-strength":
        return _evaluate_has_character_with_strength(condition, state, source_instance_id, engine)

    if kind == "has-named-character":
        return _evaluate_has_named_character(condition, state, source_instance_id, engine)

    if kind == "has-named-item":
        return _evaluate_has_named_item(condition, state, source_instance_id, engine)

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

    if kind == "resource-count":
        return _evaluate_resource_count(condition, state, source_instance_id)

    if kind in ("target_damaged", "target-damaged"):
        return _evaluate_target_damaged(condition, state, event)

    # B2: Advanced conditions
    if kind == "target-query":
        return _evaluate_target_query(condition, state, source_instance_id, engine, event)

    if kind == "comparison":
        return _evaluate_comparison(condition, state, source_instance_id, engine)

    if kind == "lore-comparison":
        return _evaluate_lore_comparison(condition, state, source_instance_id)

    if kind == "card-type-comparison":
        return _evaluate_card_type_comparison(condition, state, source_instance_id, engine)

    if kind == "banished-in-challenge-this-turn":
        return _evaluate_banished_in_challenge(condition, state, source_instance_id)

    if kind == "in-challenge":
        return _evaluate_in_challenge(condition, state, source_instance_id)

    if kind == "being-challenged":
        return _evaluate_being_challenged(condition, state, source_instance_id)

    if kind == "has-card-under":
        return _evaluate_has_card_under(condition, state, source_instance_id)

    if kind == "at-location":
        return _evaluate_at_location(condition, state, source_instance_id)

    if kind == "play-context":
        return _evaluate_play_context(condition, state, source_instance_id, event)

    if kind == "used-shift":
        return _evaluate_used_shift(event)

    if kind == "opponent-has-damaged-character":
        return _evaluate_opponent_has_damaged_character(condition, state, source_instance_id)

    if kind == "first-turn-non-otp":
        return _evaluate_first_turn_non_otp(condition, state)

    if kind == "has-granted-ability":
        return _evaluate_has_granted_ability(condition, state, source_instance_id, engine)

    if kind == "is-named":
        return _evaluate_is_named(condition, state, source_instance_id, engine)

    if kind == "stat-threshold":
        return _evaluate_stat_threshold(condition, state, source_instance_id, engine)

    if kind == "target-aggregate-comparison":
        return _evaluate_target_aggregate(condition, state, source_instance_id, engine)

    if kind == "trigger-subject-had-card-under":
        return _evaluate_trigger_subject_had_card_under(condition, state, source_instance_id, event)

    if kind == "put-card-under-any-this-turn":
        return _evaluate_put_card_under_any_this_turn(condition, state, source_instance_id)

    if kind == "put-card-under-self-this-turn":
        return _evaluate_put_card_under_self_this_turn(condition, state, source_instance_id)

    if kind == "turn-metric":
        return _evaluate_turn_metric(condition, state, source_instance_id, engine)

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
    """Evaluate logical conditions (and, or, not, if).

    Errors from nested conditions propagate upward - they are NOT swallowed.
    """
    if kind == "not":
        # Handle "condition" key first, then "conditions" array
        inner_condition = condition.get("condition")
        if inner_condition is None:
            conditions_list = condition.get("conditions") or condition.get("operands") or []
            if conditions_list:
                inner_condition = conditions_list[0]
        if inner_condition is None:
            return True
        # Error propagates if inner condition is unsupported
        result = evaluate_condition(inner_condition, state, event, source_instance_id, engine)
        return not result

    if kind == "and":
        operands = condition.get("conditions") or condition.get("operands") or []
        if not operands:
            return True
        # Each operand must be evaluated; errors propagate
        for op in operands:
            result = evaluate_condition(op, state, event, source_instance_id, engine)
            if not result:
                return False
        return True

    if kind == "or":
        operands = condition.get("conditions") or condition.get("operands") or []
        if not operands:
            return False
        # Each operand must be evaluated; errors propagate
        for op in operands:
            result = evaluate_condition(op, state, event, source_instance_id, engine)
            if result:
                return True
        return False

    if kind == "if":
        if_cond = condition.get("condition") or condition.get("expression")
        if if_cond is None:
            return True
        # Error propagates if condition is unsupported
        return evaluate_condition(if_cond, state, event, source_instance_id, engine)

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

    cond_controller = condition.get("controller")
    if cond_controller == "opponent":
        controller = state.opponent(controller)

    count = 0
    for instance_id in state.players[controller].play:
        card_def = engine.card_def(state, instance_id)
        if card_def.card_type == card_type:
            classification = condition.get("classification")
            if classification:
                if classification not in card_def.subtypes:
                    continue
            count += 1

    comparison = condition.get("comparison") or condition.get("operator") or ">="
    value = int(condition.get("value") or condition.get("count") or condition.get("amount") or 0)

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

    cond_controller = condition.get("controller")
    if cond_controller == "opponent":
        controller = state.opponent(controller)

    check_players: tuple[int, ...] = (controller,)
    if cond_controller == "any":
        check_players = (0, 1)

    for player in check_players:
        for instance_id in state.players[player].play:
            card_def = engine.card_def(state, instance_id)
            if card_def.card_type != CARD_CHARACTER:
                continue

            if condition.get("excludeSelf") and instance_id == source_instance_id:
                continue

            if property_name == "keyword":
                if property_value in card_def.keywords:
                    return True
            elif property_name == "classification":
                if property_value in card_def.subtypes:
                    return True
                if property_value in card_def.keywords:
                    return True

    return False


def _evaluate_has_character_with_strength(
    condition: dict,
    state: GameState,
    source_instance_id: int,
    engine: "GameEngine",  # type: ignore[name-defined]
) -> bool:
    """Evaluate has-character-with-strength conditions."""
    controller = state.cards[source_instance_id].controller

    cond_controller = condition.get("controller")
    if cond_controller == "opponent":
        controller = state.opponent(controller)

    comparison = condition.get("comparison") or ">="
    threshold = int(condition.get("value") or condition.get("strength") or 0)

    for instance_id in state.players[controller].play:
        card_def = engine.card_def(state, instance_id)
        if card_def.card_type != CARD_CHARACTER:
            continue

        if _compare(card_def.strength, comparison, threshold):
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

    cond_controller = condition.get("controller")
    if cond_controller == "opponent":
        controller = state.opponent(controller)

    target_name = condition.get("name") or condition.get("value")

    if not target_name:
        return False

    target_name_lower = str(target_name).lower()

    for instance_id in state.players[controller].play:
        card_def = engine.card_def(state, instance_id)
        if card_def.card_type != CARD_CHARACTER:
            continue

        if condition.get("excludeSelf") and instance_id == source_instance_id:
            continue

        card_name = (card_def.full_name or card_def.name or "").lower()
        if target_name_lower in card_name:
            return True

    return False


def _evaluate_has_named_item(
    condition: dict,
    state: GameState,
    source_instance_id: int,
    engine: "GameEngine",  # type: ignore[name-defined]
) -> bool:
    """Evaluate has-named-item conditions."""
    controller = state.cards[source_instance_id].controller

    cond_controller = condition.get("controller")
    if cond_controller == "opponent":
        controller = state.opponent(controller)

    target_name = condition.get("name") or condition.get("value")

    if not target_name:
        return False

    target_name_lower = str(target_name).lower()

    for instance_id in state.players[controller].play:
        card_def = engine.card_def(state, instance_id)
        if card_def.card_type != CARD_ITEM:
            continue

        card_name = (card_def.full_name or card_def.name or "").lower()
        if target_name_lower in card_name:
            return True

    return False


def _evaluate_has_location_in_play(
    condition: dict,
    state: GameState,
    source_instance_id: int,
    engine: "GameEngine",  # type: ignore[name-defined]
) -> bool:
    """Evaluate has-location-in-play condition."""
    controller = state.cards[source_instance_id].controller

    cond_controller = condition.get("controller")
    if cond_controller == "opponent":
        controller = state.opponent(controller)

    for instance_id in state.players[controller].play:
        card_def = engine.card_def(state, instance_id)
        if card_def.card_type == CARD_LOCATION:
            return True

    return False


def _evaluate_has_another_character(
    condition: dict,
    state: GameState,
    source_instance_id: int,
    engine: "GameEngine",  # type: ignore[name-defined]
) -> bool:
    """Evaluate has-another-character conditions."""
    controller = state.cards[source_instance_id].controller

    count = 0
    for instance_id in state.players[controller].play:
        if instance_id == source_instance_id:
            continue
        card_def = engine.card_def(state, instance_id)
        if card_def.card_type == CARD_CHARACTER:
            count += 1

    comparison = condition.get("comparison") or ">="
    value = int(condition.get("value") or condition.get("count") or 1)

    return _compare(count, comparison, value)


def _evaluate_is_exerted(
    condition: dict,
    state: GameState,
    source_instance_id: int,
    engine: "GameEngine",  # type: ignore[name-defined]
) -> bool:
    """Evaluate is-exerted conditions."""
    subject_id = condition.get("target") or condition.get("subject")
    if subject_id is None:
        subject_id = source_instance_id
    else:
        subject_id = int(subject_id) if isinstance(subject_id, (int, str)) else source_instance_id

    subject_inst = state.cards.get(subject_id)
    return subject_inst is not None and subject_inst.exerted


def _evaluate_has_damage(
    condition: dict,
    state: GameState,
    source_instance_id: int,
    engine: "GameEngine",  # type: ignore[name-defined]
    min_damage: int | None = None,
    max_damage: int | None = None,
) -> bool:
    """Evaluate has-damage conditions."""
    subject_id = condition.get("target") or condition.get("subject")
    if subject_id is None:
        subject_id = source_instance_id
    else:
        subject_id = int(subject_id) if isinstance(subject_id, (int, str)) else source_instance_id

    subject_inst = state.cards.get(subject_id)
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

    cond_controller = condition.get("controller")
    if cond_controller == "opponent":
        controller = state.opponent(controller)

    ink_count = len(state.players[controller].inkwell)

    comparison = condition.get("comparison") or condition.get("operator") or ">="
    value = int(condition.get("value") or condition.get("count") or 0)

    return _compare(ink_count, comparison, value)


def _evaluate_resource_count(
    condition: dict,
    state: GameState,
    source_instance_id: int,
) -> bool:
    """Evaluate resource-count conditions (hand size, ink count, etc.)."""
    controller = state.cards[source_instance_id].controller

    cond_controller = condition.get("controller")
    if cond_controller == "opponent":
        controller = state.opponent(controller)

    what = condition.get("what") or condition.get("resource")

    if what == "cards-in-hand":
        count = len(state.players[controller].hand)
    elif what == "ink-in-well":
        count = len(state.players[controller].inkwell)
    elif what == "characters-in-play":
        count = len([c for c in state.players[controller].play if state.cards[c].zone == ZONE_PLAY])
    else:
        count = len(state.players[controller].inkwell)

    comparison = condition.get("comparison") or ">="
    value = int(condition.get("value") or 0)

    return _compare(count, comparison, value)


def _evaluate_target_damaged(
    condition: dict,
    state: GameState,
    event: PendingTriggeredEvent | GameEvent | None,
) -> bool:
    """Evaluate target_damaged condition used in effects."""
    if event is None:
        return False

    target_id: int | None = None

    if isinstance(event, PendingTriggeredEvent):
        target_id = event.defender_id or event.subject_card_id
    elif isinstance(event, GameEvent):
        target_id = event.target

    if target_id is None:
        return False

    target_inst = state.cards.get(target_id)
    if target_inst is None:
        return False

    return target_inst.damage > 0


def _evaluate_target_query(
    condition: dict,
    state: GameState,
    source_instance_id: int,
    engine: "GameEngine",  # type: ignore[name-defined]
    event: PendingTriggeredEvent | GameEvent | None,
) -> bool:
    """Evaluate target-query conditions (complex card selections with filters)."""
    query = condition.get("query") or condition.get("target")
    if not query:
        raise UnsupportedConditionError("target-query requires a query object")

    comparison = condition.get("comparison", {})
    operator = comparison.get("operator") or comparison.get("value") or ">="
    threshold = int(comparison.get("value") or 0) if isinstance(comparison, dict) else 1

    owner = query.get("owner")
    zones = query.get("zones") or [ZONE_PLAY]
    card_types = query.get("cardTypes") or query.get("cardType")
    classifications = query.get("classifications") or query.get("filters", [])
    filters = query.get("filters") or []
    exclude_self = query.get("excludeSelf", False)

    source_controller = state.cards[source_instance_id].controller
    if owner == "opponent":
        check_players = (state.opponent(source_controller),)
    elif owner == "any":
        check_players = (0, 1)
    else:
        check_players = (source_controller,)

    count = 0
    for player in check_players:
        for zone in zones:
            if zone == ZONE_PLAY:
                card_list = state.players[player].play
            elif zone == "hand":
                card_list = state.players[player].hand
            else:
                continue

            for instance_id in card_list:
                if exclude_self and instance_id == source_instance_id:
                    continue

                card_def = engine.card_def(state, instance_id)
                card_inst = state.cards[instance_id]

                if card_types:
                    if isinstance(card_types, list):
                        if card_def.card_type not in card_types:
                            continue
                    elif card_def.card_type != card_types:
                        continue

                if classifications:
                    if isinstance(classifications, list):
                        if not any(c in card_def.subtypes or c in card_def.keywords for c in classifications):
                            continue
                    else:
                        if classifications not in card_def.subtypes and classifications not in card_def.keywords:
                            continue

                if not _apply_query_filters(filters, card_def, card_inst, state):
                    continue

                count += 1

    return _compare(count, operator, threshold)


def _apply_query_filters(
    filters: list[dict],
    card_def,  # CardDef
    card_inst,  # CardInstance
    state: GameState,
) -> bool:
    """Apply filter conditions from a target-query."""
    for filter_def in filters:
        filter_type = filter_def.get("type")

        if filter_type == "has-classification":
            classification = filter_def.get("classification")
            if classification and classification not in card_def.subtypes:
                return False

        elif filter_type == "has-keyword":
            keyword = filter_def.get("keyword")
            if keyword and keyword not in card_def.keywords:
                return False

        elif filter_type == "exerted":
            if not card_inst.exerted:
                return False

        elif filter_type == "status":
            status = filter_def.get("status")
            if status == "damaged" and card_inst.damage == 0:
                return False

        elif filter_type == "strength-comparison":
            comparison = filter_def.get("comparison") or ">="
            value = int(filter_def.get("value") or 0)
            if not _compare(card_def.strength, comparison, value):
                return False

        elif filter_type == "cost-comparison":
            comparison = filter_def.get("comparison") or ">="
            value = int(filter_def.get("value") or 0)
            if not _compare(card_def.cost, comparison, value):
                return False

        elif filter_type == "ink-type":
            ink_type = filter_def.get("inkType")
            if ink_type and ink_type not in card_def.ink_color:
                return False

        elif filter_type == "at-location":
            location = filter_def.get("location")
            if location == "this" and card_inst.location_instance_id is None:
                return False

    return True


def _evaluate_comparison(
    condition: dict,
    state: GameState,
    source_instance_id: int,
    engine: "GameEngine",  # type: ignore[name-defined]
) -> bool:
    """Evaluate comparison conditions with left/right operands."""
    left = condition.get("left")
    right = condition.get("right")
    comparison = condition.get("comparison") or ">="

    if not left or not right:
        return _evaluate_numeric_comparison(condition, state, source_instance_id, engine)

    left_value = _evaluate_metric(left, state, source_instance_id, engine)
    right_value = _evaluate_metric(right, state, source_instance_id, engine)

    return _compare(left_value, comparison, right_value)


def _evaluate_metric(
    metric: dict,
    state: GameState,
    source_instance_id: int,
    engine: "GameEngine",  # type: ignore[name-defined]
) -> int:
    """Evaluate a metric specification."""
    metric_type = metric.get("type")
    controller = state.cards[source_instance_id].controller

    if metric.get("controller") == "opponent":
        controller = state.opponent(controller)

    if metric_type == "cards-in-hand":
        return len(state.players[controller].hand)
    elif metric_type == "ink-in-well":
        return len(state.players[controller].inkwell)
    elif metric_type == "lore":
        return state.players[controller].lore
    elif metric_type == "characters-in-play":
        return len(state.players[controller].play)
    else:
        return 0


def _evaluate_lore_comparison(
    condition: dict,
    state: GameState,
    source_instance_id: int,
) -> bool:
    """Evaluate lore comparison conditions."""
    controller = state.cards[source_instance_id].controller

    cond_controller = condition.get("controller")
    if cond_controller == "opponent":
        controller = state.opponent(controller)

    lore = state.players[controller].lore

    comparison = condition.get("comparison") or condition.get("operator") or ">="
    value = int(condition.get("value") or condition.get("lore") or 0)

    return _compare(lore, comparison, value)


def _evaluate_card_type_comparison(
    condition: dict,
    state: GameState,
    source_instance_id: int,
    engine: "GameEngine",  # type: ignore[name-defined]
) -> bool:
    """Evaluate card type comparison conditions."""
    controller = state.cards[source_instance_id].controller

    cond_controller = condition.get("controller")
    if cond_controller == "opponent":
        controller = state.opponent(controller)

    card_type = condition.get("cardType") or condition.get("type")
    comparison = condition.get("comparison") or ">="
    value = int(condition.get("value") or 0)

    count = 0
    for instance_id in state.players[controller].play:
        card_def = engine.card_def(state, instance_id)
        if card_def.card_type == card_type:
            count += 1

    return _compare(count, comparison, value)


def _evaluate_banished_in_challenge(
    condition: dict,
    state: GameState,
    source_instance_id: int,
) -> bool:
    """Evaluate banished-in-challenge-this-turn conditions.

    True when state.turn_metadata["banished_characters_in_challenge_by_owner_this_turn"][owner] is non-empty.
    """
    owner = condition.get("owner")
    source_controller = state.cards[source_instance_id].controller

    if owner == "opponent":
        check_owner = state.opponent(source_controller)
    else:
        check_owner = source_controller

    owner_banishes = state.turn_metadata.get("banished_characters_in_challenge_by_owner_this_turn", {})
    return len(owner_banishes.get(check_owner, [])) > 0


def _evaluate_in_challenge(
    condition: dict,
    state: GameState,
    source_instance_id: int,
) -> bool:
    """Evaluate in-challenge conditions."""
    role = condition.get("role")
    card_inst = state.cards.get(source_instance_id)

    if card_inst is None:
        return False

    if hasattr(card_inst, 'was_challenged_this_turn'):
        if role == "defender":
            return card_inst.was_challenged_this_turn

    return False


def _evaluate_being_challenged(
    condition: dict,
    state: GameState,
    source_instance_id: int,
) -> bool:
    """Evaluate being-challenged conditions."""
    card_inst = state.cards.get(source_instance_id)

    if card_inst is None:
        return False

    return getattr(card_inst, 'was_challenged_this_turn', False)


def _evaluate_has_card_under(
    condition: dict,
    state: GameState,
    source_instance_id: int,
) -> bool:
    """Evaluate has-card-under conditions.

    True when the source/target/context card has non-empty cards_under.
    """
    target_id = condition.get("target") or condition.get("card") or source_instance_id
    if isinstance(target_id, str):
        target_id = int(target_id) if target_id.isdigit() else source_instance_id
    elif not isinstance(target_id, int):
        target_id = source_instance_id

    card_inst = state.cards.get(target_id)
    if card_inst is None:
        return False

    return len(card_inst.cards_under) > 0


def _evaluate_at_location(
    condition: dict,
    state: GameState,
    source_instance_id: int,
) -> bool:
    """Evaluate at-location conditions."""
    # Location tracking is not fully implemented yet
    return False


def _evaluate_play_context(
    condition: dict,
    state: GameState,
    source_instance_id: int,
    event: PendingTriggeredEvent | GameEvent | None,
) -> bool:
    """Evaluate play-context conditions."""
    context = condition.get("context")

    if context == "used-shift":
        return _evaluate_used_shift(event)

    return False


def _event_lookup(event: PendingTriggeredEvent | GameEvent | None, key: str) -> Any:
    """Read event evidence from snapshot, payload, and card_played payloads."""
    if event is None:
        return None

    event_snapshot = getattr(event, "event_snapshot", None)
    if isinstance(event_snapshot, dict) and key in event_snapshot:
        return event_snapshot[key]

    payload = getattr(event, "payload", None)
    if isinstance(payload, dict):
        if key in payload:
            return payload[key]
        card_played = payload.get("card_played") or payload.get("cardPlayed")
        if isinstance(card_played, dict) and key in card_played:
            return card_played[key]

    card_played_attr = getattr(event, "card_played", None)
    if isinstance(card_played_attr, dict) and key in card_played_attr:
        return card_played_attr[key]
    return None


def _event_bool(event: PendingTriggeredEvent | GameEvent | None, *keys: str) -> bool:
    for key in keys:
        value = _event_lookup(event, key)
        if isinstance(value, bool):
            if value:
                return True
            continue
        if isinstance(value, (int, float)):
            if value != 0:
                return True
            continue
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"true", "yes", "1"}:
                return True
    return False


def _evaluate_used_shift(event: PendingTriggeredEvent | GameEvent | None) -> bool:
    """Evaluate Lorcanito used-shift from play payload or event snapshot."""
    return _event_bool(
        event,
        "used_shift",
        "usedShift",
        "playedCardUsedShift",
        "played_card_used_shift",
    )


def _evaluate_opponent_has_damaged_character(
    condition: dict,
    state: GameState,
    source_instance_id: int,
) -> bool:
    """Evaluate opponent-has-damaged-character conditions."""
    source_controller = state.cards[source_instance_id].controller
    opponent = state.opponent(source_controller)

    for instance_id in state.players[opponent].play:
        card_inst = state.cards.get(instance_id)
        if card_inst and card_inst.damage > 0:
            return True

    return False


def _evaluate_first_turn_non_otp(
    condition: dict,
    state: GameState,
) -> bool:
    """Evaluate first-turn-non-otp conditions."""
    return state.turn_number == 1 and state.active_player != state.first_player


def _evaluate_has_granted_ability(
    condition: dict,
    state: GameState,
    source_instance_id: int,
    engine: "GameEngine",  # type: ignore[name-defined]
) -> bool:
    """Evaluate has-granted-ability conditions."""
    # Granted abilities are not currently tracked
    return False


def _evaluate_is_named(
    condition: dict,
    state: GameState,
    source_instance_id: int,
    engine: "GameEngine",  # type: ignore[name-defined]
) -> bool:
    """Evaluate is-named conditions."""
    name = condition.get("name")
    if not name:
        return False

    card_def = engine.card_def(state, source_instance_id)
    card_name = (card_def.full_name or card_def.name or "").lower()
    target_name = str(name).lower()

    return target_name in card_name


def _evaluate_stat_threshold(
    condition: dict,
    state: GameState,
    source_instance_id: int,
    engine: "GameEngine",  # type: ignore[name-defined]
) -> bool:
    """Evaluate stat-threshold conditions."""
    card_def = engine.card_def(state, source_instance_id)

    stat = condition.get("stat")
    comparison = condition.get("comparison") or ">="
    value = int(condition.get("value") or 0)

    stat_value = 0
    if stat == "strength":
        stat_value = card_def.strength
    elif stat == "willpower":
        stat_value = card_def.willpower
    elif stat == "lore":
        stat_value = card_def.lore
    elif stat == "cost":
        stat_value = card_def.cost

    return _compare(stat_value, comparison, value)


def _evaluate_target_aggregate(
    condition: dict,
    state: GameState,
    source_instance_id: int,
    engine: "GameEngine",  # type: ignore[name-defined]
) -> bool:
    """Evaluate target-aggregate-comparison conditions."""
    raise UnsupportedConditionError("target-aggregate-comparison requires more complex implementation")


def _evaluate_trigger_subject_had_card_under(
    condition: dict,
    state: GameState,
    source_instance_id: int,
    event: PendingTriggeredEvent | GameEvent | None,
) -> bool:
    """Evaluate trigger-subject-had-card-under conditions.

    True when event_snapshot cardsUnderCountBeforeBanish > 0 or
    cardsUnderIdsBeforeBanish is non-empty.
    """
    if "cardsUnderCountBeforeBanish" in condition:
        return condition.get("cardsUnderCountBeforeBanish", 0) > 0
    if "cardsUnderIdsBeforeBanish" in condition:
        return len(condition.get("cardsUnderIdsBeforeBanish", [])) > 0

    event_snapshot = getattr(event, "event_snapshot", {}) if event is not None else {}
    if event_snapshot:
        if int(event_snapshot.get("cardsUnderCountBeforeBanish") or 0) > 0:
            return True
        if event_snapshot.get("cardsUnderIdsBeforeBanish"):
            return True

    return False


def _evaluate_put_card_under_any_this_turn(
    condition: dict,
    state: GameState,
    source_instance_id: int,
) -> bool:
    """Evaluate put-card-under-any-this-turn conditions.

    True when state.turn_metadata["cards_put_under_this_turn_by_player"][player] > 0.
    """
    controller = state.cards[source_instance_id].controller

    cond_controller = condition.get("controller")
    if cond_controller == "opponent":
        controller = state.opponent(controller)

    player_puts = state.turn_metadata.get("cards_put_under_this_turn_by_player", {})
    return player_puts.get(controller, 0) > 0


def _evaluate_put_card_under_self_this_turn(
    condition: dict,
    state: GameState,
    source_instance_id: int,
) -> bool:
    """Evaluate put-card-under-self-this-turn conditions.

    True when state.turn_metadata["cards_put_under_self_this_turn_by_card"][source_id] > 0.
    """
    card_puts = state.turn_metadata.get("cards_put_under_self_this_turn_by_card", {})
    return card_puts.get(source_instance_id, 0) > 0


def _evaluate_numeric_comparison(
    condition: dict,
    state: GameState,
    source_instance_id: int,
    engine: "GameEngine",  # type: ignore[name-defined]
) -> bool:
    """Evaluate numeric comparison conditions (legacy)."""
    comparison = condition.get("comparison") or condition.get("operator") or ">="
    value = int(condition.get("value") or condition.get("amount") or 0)

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

    raise UnsupportedConditionError(f"Unsupported numeric comparison metric: {metric}")


def _evaluate_turn_metric(
    condition: dict,
    state: GameState,
    source_instance_id: int,
    engine: "GameEngine",  # type: ignore[name-defined]
) -> bool:
    """Evaluate turn-metric conditions.

    Supports metrics:
    - cards-drawn-by-player
    - challenges-by-player
    - banished-characters
    - banished-characters-in-challenge
    - cards-put-under-by-player

    Comparison operators: eq, equals, gte, greater-than-or-equal, gt, greater-than,
                          lte, less-than-or-equal, lt, less-than
    """
    metric_name = condition.get("metric")
    if not metric_name:
        raise UnsupportedConditionError("turn-metric requires a 'metric' field")

    controller = state.cards[source_instance_id].controller

    scope = (
        condition.get("playerScope")
        or condition.get("player_scope")
        or condition.get("ownerScope")
        or condition.get("owner_scope")
        or condition.get("controller")
    )
    scoped_players = _resolve_condition_player_scope(state, controller, scope)

    comparison_raw = condition.get("comparison") or condition.get("operator") or ">="
    if isinstance(comparison_raw, dict):
        comparison = comparison_raw.get("operator") or comparison_raw.get("comparison") or ">="
        value = int(comparison_raw.get("value") or condition.get("value") or condition.get("amount") or 0)
    else:
        comparison = comparison_raw
        value = int(condition.get("value") or condition.get("amount") or 0)

    # Map metric names to turn metadata paths
    metric_value = 0

    if metric_name == "cards-drawn-by-player":
        player_draws = state.turn_metadata.get("cards_drawn_this_turn_by_player", {})
        metric_value = _sum_scoped_turn_record(player_draws, scoped_players)

    elif metric_name == "challenges-by-player":
        player_challenges = state.turn_metadata.get("challenges_by_player_this_turn", {})
        metric_value = _sum_scoped_turn_record(player_challenges, scoped_players)

    elif metric_name == "banished-characters":
        banished_list = state.turn_metadata.get("banished_characters_this_turn", [])
        metric_value = _count_banished_turn_metric(condition, state, engine, banished_list, scoped_players)

    elif metric_name == "banished-characters-in-challenge":
        owner_banishes = state.turn_metadata.get("banished_characters_in_challenge_by_owner_this_turn", {})
        metric_value = _sum_scoped_turn_record(owner_banishes, scoped_players)

    elif metric_name == "cards-put-under-by-player":
        player_puts = state.turn_metadata.get("cards_put_under_this_turn_by_player", {})
        metric_value = _sum_scoped_turn_record(player_puts, scoped_players)

    else:
        raise UnsupportedConditionError(f"turn-metric: unknown metric '{metric_name}'")

    return _compare(metric_value, comparison, value)


def _resolve_condition_player_scope(state: GameState, controller: int, scope: Any) -> tuple[int, ...]:
    if scope == "you":
        return (controller,)
    if scope == "opponent":
        return (state.opponent(controller),)
    if scope == "active":
        return (state.active_player,)
    if scope == "any":
        return tuple(range(len(state.players)))
    return tuple(range(len(state.players)))


def _turn_record_value(value: Any) -> int:
    if isinstance(value, int):
        return value
    if isinstance(value, (list, tuple, set)):
        return len(value)
    return 0


def _sum_scoped_turn_record(record: Any, players: tuple[int, ...]) -> int:
    if not isinstance(record, dict):
        return 0
    return sum(_turn_record_value(record.get(player, 0)) for player in players)


def _count_banished_turn_metric(
    condition: dict,
    state: GameState,
    engine: "GameEngine",  # type: ignore[name-defined]
    banished_list: Any,
    scoped_players: tuple[int, ...],
) -> int:
    if not isinstance(banished_list, list):
        return 0

    target_name = condition.get("name")
    target_classification = condition.get("classification")
    count = 0
    for card_id in banished_list:
        card_inst = state.cards.get(card_id)
        if card_inst is None or card_inst.owner not in scoped_players:
            continue
        card_def = engine.card_def(state, card_id)
        if target_name and target_name not in {
            card_def.full_name,
            card_def.name,
            card_def.simple_name,
        }:
            continue
        if target_classification and target_classification not in card_def.subtypes:
            continue
        count += 1
    return count


def _compare(value: int, comparison: str, threshold: int) -> bool:
    """Compare a value against a threshold using the specified comparison operator."""
    comparison = str(comparison).strip().lower()

    if comparison in (">=", "gte", "at-least", "greater-or-equal", "greater-than-or-equal", "or-more"):
        return value >= threshold
    if comparison in (">", "gt", "more-than", "greater", "greater-than"):
        return value > threshold
    if comparison in ("<=", "lte", "at-most", "less-or-equal", "less-than-or-equal"):
        return value <= threshold
    if comparison in ("<", "lt", "less-than", "less"):
        return value < threshold
    if comparison in ("==", "=", "eq", "exactly", "equal", "equals"):
        return value == threshold
    if comparison in ("!=", "<>", "ne", "not", "not-equal"):
        return value != threshold

    return value >= threshold
