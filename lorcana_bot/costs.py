"""Ability cost validation and payment for activated abilities.

This module implements cost validation and payment for Lorcana's activated abilities,
separating these operations from effect resolution as per Lorcanito's architecture.

Supported costs (MVP):
- exert_source: Exert the source card
- ink: Pay ink (exert N ink cards)
- banish_self: Banish the source card (move to discard)
- discard: Discard N cards from hand (random if no choice required)

Not supported (requires pending prompts):
- choose/discard specific card
- reveal named card
- pay complex alternative costs
"""

from __future__ import annotations

import random
from typing import TYPE_CHECKING, Any

from lorcana_bot.card_logic.costs import SourceCostDef

if TYPE_CHECKING:
    from lorcana_bot.abilities import ActivatedAbility
    from lorcana_bot.state import GameState
    from lorcana_bot.engine import GameEngine


class CostValidationError(ValueError):
    """Raised when a cost cannot be paid."""
    pass


class CostPaymentError(ValueError):
    """Raised when a cost payment fails."""
    pass


# Supported cost kinds
SUPPORTED_COST_KINDS = frozenset({
    "exert_source",
    "ink",
    "banish_self",
    "discard",
    "spend_ink",
    "exert",
    "ready",
    "banish",
    "tap",
})


def validate_cost_payable(
    state: GameState,
    engine: GameEngine,
    ability: ActivatedAbility,
    cost: SourceCostDef,
) -> tuple[bool, str]:
    """Validate whether a single cost can be paid.
    
    Args:
        state: The game state
        engine: The game engine
        ability: The activated ability
        cost: The cost to validate
        
    Returns:
        Tuple of (can_pay, reason_if_not)
    """
    cost_kind = cost.kind.lower().replace("-", "_").replace(" ", "_")
    source_id = ability.source_instance_id
    
    # Check if cost kind is supported
    if cost_kind not in SUPPORTED_COST_KINDS:
        return False, f"Unsupported cost kind: {cost.kind}"
    
    # Get amount (default to 1 if not specified)
    amount = int(cost.amount) if cost.amount else 1
    
    # Handle each cost type
    if cost_kind in {"exert_source", "exert"}:
        return _validate_exert_source(state, source_id)
    elif cost_kind in {"ink", "spend_ink"}:
        return _validate_ink_cost(state, engine, ability, amount)
    elif cost_kind == "banish_self":
        return _validate_banish_self(state, source_id)
    elif cost_kind == "discard":
        return _validate_discard_cost(state, engine, ability, amount)
    elif cost_kind == "tap":
        # Tapping is equivalent to exerting in Lorcana
        return _validate_exert_source(state, source_id)
    else:
        return False, f"Cost kind {cost_kind} not implemented"
    

def _validate_exert_source(state: GameState, source_id: int) -> tuple[bool, str]:
    """Validate that the source card can be exerted."""
    card = state.cards.get(source_id)
    if card is None:
        return False, "Source card not found"
    if card.zone != "play":
        return False, "Source card not in play"
    if card.exerted:
        return False, "Source card is already exerted"
    if card.drying:
        return False, "Source card is drying"
    return True, ""


def _validate_ink_cost(
    state: GameState,
    engine: GameEngine,
    ability: ActivatedAbility,
    amount: int,
) -> tuple[bool, str]:
    """Validate that the player has enough available ink."""
    player = state.cards[ability.source_instance_id].controller
    available = engine.available_ink(state, player)
    if available < amount:
        return False, f"Not enough ink: need {amount}, have {available}"
    return True, ""


def _validate_banish_self(state: GameState, source_id: int) -> tuple[bool, str]:
    """Validate that the source card can be banished (banish-self cost)."""
    card = state.cards.get(source_id)
    if card is None:
        return False, "Source card not found"
    if card.zone != "play":
        return False, "Source card not in play"
    return True, ""


def _validate_discard_cost(
    state: GameState,
    engine: GameEngine,
    ability: ActivatedAbility,
    amount: int,
) -> tuple[bool, str]:
    """Validate that the player has enough cards to discard."""
    player = state.cards[ability.source_instance_id].controller
    hand_size = len(state.players[player].hand)
    if hand_size < amount:
        return False, f"Not enough cards to discard: need {amount}, have {hand_size}"
    return True, ""


def pay_cost(
    state: GameState,
    engine: GameEngine,
    ability: ActivatedAbility,
    cost: SourceCostDef,
) -> None:
    """Pay a single cost, updating game state.
    
    Args:
        state: The game state
        engine: The game engine  
        ability: The activated ability
        cost: The cost to pay
        
    Raises:
        CostPaymentError: If the cost cannot be paid
    """
    cost_kind = cost.kind.lower().replace("-", "_").replace(" ", "_")
    source_id = ability.source_instance_id
    amount = int(cost.amount) if cost.amount else 1
    
    if cost_kind in {"exert_source", "exert"}:
        _pay_exert_source(state, source_id, engine)
    elif cost_kind in {"ink", "spend_ink"}:
        _pay_ink_cost(state, engine, ability, amount)
    elif cost_kind == "banish_self":
        _pay_banish_self(state, source_id, engine)
    elif cost_kind == "discard":
        _pay_discard_cost(state, engine, ability, amount)
    elif cost_kind == "tap":
        _pay_exert_source(state, source_id, engine)
    else:
        raise CostPaymentError(f"Cost kind {cost_kind} not implemented for payment")


def _pay_exert_source(state: GameState, source_id: int, engine: GameEngine) -> None:
    """Pay exert-source cost by exerting the source card."""
    card = state.cards[source_id]
    card.exerted = True
    
    engine.emit_event(
        state,
        "ABILITY_COST_EXERT",
        actor=card.controller,
        source=source_id,
        payload={
            "cost_type": "exert",
            "source_id": source_id,
        },
        queue_triggers=False,  # Cost payments don't trigger abilities
    )


def _pay_ink_cost(
    state: GameState,
    engine: GameEngine,
    ability: ActivatedAbility,
    amount: int,
) -> None:
    """Pay ink cost by exerting ink cards."""
    player = state.cards[ability.source_instance_id].controller
    ready_ink = [cid for cid in state.players[player].inkwell if not state.cards[cid].exerted]
    
    if len(ready_ink) < amount:
        raise CostPaymentError("Insufficient ink available")
    
    # Exert the ink cards
    for cid in ready_ink[:amount]:
        state.cards[cid].exerted = True
    
    engine.emit_event(
        state,
        "ABILITY_COST_INK",
        actor=player,
        source=ability.source_instance_id,
        payload={
            "cost_type": "ink",
            "amount": amount,
            "ink_card_ids": ready_ink[:amount],
        },
        queue_triggers=False,
    )


def _pay_banish_self(state: GameState, source_id: int, engine: GameEngine) -> None:
    """Pay banish-self cost by moving source to discard."""
    card = state.cards[source_id]
    controller = card.controller
    
    engine.emit_event(
        state,
        "ABILITY_COST_BANISH_SELF",
        actor=controller,
        source=source_id,
        payload={
            "cost_type": "banish_self",
            "source_id": source_id,
        },
        queue_triggers=False,
    )
    
    # Move the card to discard
    state.move_card(source_id, "discard")


def _pay_discard_cost(
    state: GameState,
    engine: GameEngine,
    ability: ActivatedAbility,
    amount: int,
) -> None:
    """Pay discard cost by randomly discarding cards from hand."""
    player = state.cards[ability.source_instance_id].controller
    hand = state.players[player].hand
    
    if len(hand) < amount:
        raise CostPaymentError(f"Not enough cards to discard: need {amount}, have {len(hand)}")
    
    # Randomly select cards to discard (for MVP without choice prompts)
    discarded: list[int] = []
    hand_copy = list(hand)
    for _ in range(amount):
        idx = random.randrange(len(hand_copy))
        cid = hand_copy.pop(idx)
        discarded.append(cid)
        state.move_card(cid, "discard")
        
        engine.emit_event(
            state,
            "ABILITY_COST_DISCARD",
            actor=player,
            source=ability.source_instance_id,
            payload={
                "cost_type": "discard",
                "amount": amount,
                "discarded_id": cid,
            },
            queue_triggers=False,
        )


def validate_ability_cost_collection(
    state: GameState,
    engine: GameEngine,
    ability: ActivatedAbility,
) -> tuple[bool, list[str]]:
    """Validate all costs for an ability.
    
    Args:
        state: The game state
        engine: The game engine
        ability: The activated ability to validate
        
    Returns:
        Tuple of (all_payable, list_of_failures)
    """
    failures: list[str] = []
    
    for cost in ability.costs:
        can_pay, reason = validate_cost_payable(state, engine, ability, cost)
        if not can_pay:
            failures.append(f"{cost.kind}: {reason}")
    
    return len(failures) == 0, failures


def pay_all_costs(
    state: GameState,
    engine: GameEngine,
    ability: ActivatedAbility,
) -> tuple[str, ...]:
    """Pay all costs for an ability atomically.
    
    This function collects all costs first, validates them, and only then
    applies the payments. If any cost cannot be paid, no state changes occur.
    
    Args:
        state: The game state
        engine: The game engine
        ability: The activated ability whose costs to pay
        
    Returns:
        Tuple of cost kinds that were paid
        
    Raises:
        CostPaymentError: If any cost cannot be paid (no partial state changes)
    """
    # First validate all costs
    can_pay, failures = validate_ability_cost_collection(state, engine, ability)
    if not can_pay:
        raise CostPaymentError(f"Cannot pay costs: {', '.join(failures)}")
    
    # Collect costs to pay before modifying state (for atomic payment)
    costs_to_pay: list[SourceCostDef] = list(ability.costs)
    
    # Pay all costs
    paid: list[str] = []
    for cost in costs_to_pay:
        pay_cost(state, engine, ability, cost)
        paid.append(cost.kind)
    
    return tuple(paid)