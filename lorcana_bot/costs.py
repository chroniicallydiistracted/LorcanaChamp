"""Ability cost validation and payment for activated abilities.

This module implements cost validation and payment for Lorcana's activated
abilities, separating cost validation/payment from effect resolution as in
Lorcanito's activated ability architecture.

Supported direct payment costs:
- exert_source: Exert the source card
- ink: Pay ink by exerting ready inkwell cards
- banish_self: Banish the source card through the engine event boundary
- discard: Random discard only when the source explicitly marks it random

Non-random discard costs are not paid directly here. They must be resolved
through the activated-cost pending discard-choice path so the player-selected
card IDs are validated before any payment occurs.
"""

from __future__ import annotations

import random
from typing import TYPE_CHECKING, Any

from lorcana_bot.card_logic.costs import SourceCostDef
from lorcana_bot.card_logic.effect_utils import to_engine_cost_kind

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
    "discard_chosen",
    "spend_ink",
    "exert",
    "ready",
    "banish",
    "tap",
})

def cost_requires_pending_discard_choice(
    ability: ActivatedAbility,
    cost: SourceCostDef,
) -> bool:
    """Return True when a discard cost must be paid through pending choice.

    Lorcanito models chosen discard costs as selected cost input. LorcanaChamp's
    direct cost helper may only random-discard when the source explicitly marks
    the ability as random.
    """
    if to_engine_cost_kind(cost.kind) != "discard":
        return False
    raw = getattr(ability, "raw", {}) or {}
    return not bool(raw.get("random_discard"))


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
    cost_kind = to_engine_cost_kind(cost.kind)
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
    elif cost_kind == "discard_chosen":
        return _validate_discard_chosen_marker(ability)
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
    """Validate that the player has enough cards to discard.

    Chosen discard costs are paid through an activated-cost pending effect.
    Random discard is supported only when the source explicitly marks it random.
    """
    raw = getattr(ability, 'raw', {}) or {}
    if ability.source_instance_id not in state.cards:
        return False, "Source card not found"
    player = state.cards[ability.source_instance_id].controller
    hand_size = len(state.players[player].hand)
    if hand_size < amount:
        return False, f"Not enough cards to discard: need {amount}, have {hand_size}"

    if raw.get('random_discard'):
        return True, ""

    # Non-random discard is payable, but payment must be deferred to a pending
    # cost-selection path so no card is discarded before all costs/effects pass.
    return True, ""


def _validate_discard_chosen_marker(ability: ActivatedAbility) -> tuple[bool, str]:
    has_discard_amount = any(to_engine_cost_kind(cost.kind) == "discard" for cost in ability.costs)
    if not has_discard_amount:
        return False, "discardChosen requires discardCards"
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
    cost_kind = to_engine_cost_kind(cost.kind)
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
    elif cost_kind == "discard_chosen":
        return
    elif cost_kind == "tap":
        _pay_exert_source(state, source_id, engine)
    else:
        raise CostPaymentError(f"Cost kind {cost_kind} not implemented for payment")


def _pay_exert_source(state: GameState, source_id: int, engine: GameEngine) -> None:
    """Pay exert-source cost by exerting the source card."""
    card = state.cards[source_id]
    engine._exert_eventful(
        state,
        source_id,
        actor=card.controller,
        source_id=source_id,
        reason="ability_cost",
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
        engine._exert_eventful(
            state,
            cid,
            actor=player,
            source_id=ability.source_instance_id,
            reason="ability_ink_cost",
            emit_event=False,
        )

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
    engine._banish_eventful(
        state,
        source_id,
        actor=card.controller,
        source_id=source_id,
        reason="ability_cost",
    )


def _pay_discard_cost(
    state: GameState,
    engine: GameEngine,
    ability: ActivatedAbility,
    amount: int,
) -> None:
    """Pay an explicitly random discard cost.

    Non-random discard costs must resolve through the activated-cost pending
    discard-choice path. This prevents direct helpers from silently choosing a
    random card when Lorcanito source expects the player to choose.
    """
    player = state.cards[ability.source_instance_id].controller
    hand = state.players[player].hand

    if len(hand) < amount:
        raise CostPaymentError(f"Not enough cards to discard: need {amount}, have {len(hand)}")

    raw = getattr(ability, "raw", {}) or {}
    if not raw.get("random_discard"):
        raise CostPaymentError(
            "Non-random discard costs must resolve through pending discard choice"
        )

    hand_copy = list(hand)
    for _ in range(amount):
        idx = random.randrange(len(hand_copy))
        cid = hand_copy.pop(idx)
        engine._discard_eventful(
            state,
            cid,
            actor=player,
            source_id=ability.source_instance_id,
            reason="ability_cost",
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
    """Pay all directly payable costs for an ability atomically.

    Non-random discard costs are not directly payable. They must be routed
    through the activated-cost pending discard-choice path before any cost is
    paid, otherwise an earlier cost could mutate state before discard choice is
    available.
    """
    can_pay, failures = validate_ability_cost_collection(state, engine, ability)
    if not can_pay:
        raise CostPaymentError(f"Cannot pay costs: {', '.join(failures)}")

    costs_to_pay: list[SourceCostDef] = list(ability.costs)

    pending_discard_costs = [
        cost.kind
        for cost in costs_to_pay
        if cost_requires_pending_discard_choice(ability, cost)
    ]
    if pending_discard_costs:
        raise CostPaymentError(
            "Non-random discard costs must resolve through pending discard choice"
        )

    paid: list[str] = []
    for cost in costs_to_pay:
        pay_cost(state, engine, ability, cost)
        paid.append(cost.kind)

    return tuple(paid)
