"""Activated ability execution for LorcanaChamp.

This module implements the activated ability system, separating cost validation/payment
from effect resolution as per Lorcanito's architecture.

Supported costs (MVP):
- exert source
- ink cost
- banish self
- discard N cards (if no choice prompt required)
- once per turn per source

Not supported (requires pending prompts):
- choose/discard specific card
- reveal named card
- pay complex alternative costs
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from lorcana_bot.card_logic import SourceAbilityDef
from lorcana_bot.card_logic.costs import SourceCostDef
from lorcana_bot.cards import EffectDef

if TYPE_CHECKING:
    from lorcana_bot.state import GameState
    from lorcana_bot.engine import GameEngine


class AbilityCostError(ValueError):
    """Raised when an ability cost cannot be paid."""
    pass


class AbilityExecutionError(ValueError):
    """Raised when an ability cannot be executed."""
    pass


@dataclass(frozen=True)
class AbilityUseRecord:
    """Records a single use of an activated ability for once-per-turn tracking."""
    source_instance_id: int
    ability_id: str
    turn_number: int


@dataclass
class ActivatedAbility:
    """An activated ability on a card with its costs and effects."""
    source_instance_id: int
    source_card_id: str
    ability_id: str
    ability_index: int
    name: str | None
    costs: tuple[SourceCostDef, ...]
    effects: tuple[Any, ...]  # SourceEffectDef
    condition: Any | None
    raw: dict[str, Any] = field(default_factory=dict)
    
    @property
    def unique_use_key(self) -> str:
        """Key for tracking once-per-turn limitation."""
        return f"{self.source_instance_id}:{self.ability_id}"


@dataclass
class AbilityUseResult:
    """Result of attempting to use an activated ability."""
    success: bool
    costs_paid: tuple[str, ...] = ()
    effects_resolved: bool = False
    error_message: str | None = None
    

def get_activated_abilities_for_card(
    state: GameState,
    card_instance_id: int,
    card_def: Any,
) -> list[ActivatedAbility]:
    """Get all activated abilities on a card.
    
    Args:
        state: The game state
        card_instance_id: The card instance ID
        card_def: The card definition
        
    Returns:
        List of ActivatedAbility objects for this card
    """
    abilities: list[ActivatedAbility] = []
    
    # Get source abilities (from Lorcanito extraction)
    for idx, src_ability in enumerate(getattr(card_def, 'source_abilities', []) or []):
        if src_ability.kind == "activated":
            ability = ActivatedAbility(
                source_instance_id=card_instance_id,
                source_card_id=card_def.id,
                ability_id=src_ability.id or f"ability_{idx}",
                ability_index=idx,
                name=src_ability.name,
                costs=src_ability.costs,
                effects=src_ability.effects,
                condition=src_ability.condition,
                raw=dict(src_ability.raw),
            )
            abilities.append(ability)
    
    # Also check legacy activated_abilities attribute
    for idx, legacy in enumerate(getattr(card_def, 'activated_abilities', []) or []):
        # Skip if already added from source_abilities
        if any(a.ability_index == idx and a.source_card_id == card_def.id for a in abilities):
            continue
        
        ability = ActivatedAbility(
            source_instance_id=card_instance_id,
            source_card_id=card_def.id,
            ability_id=legacy.get("id", f"legacy_ability_{idx}"),
            ability_index=idx,
            name=legacy.get("name"),
            costs=tuple(),  # Legacy format doesn't have structured costs
            effects=tuple(),
            condition=None,
            raw=dict(legacy),
        )
        abilities.append(ability)
    
    return abilities


def can_use_ability_this_turn(state: GameState, ability: ActivatedAbility) -> bool:
    """Check if the ability has been used this turn (once-per-turn tracking).
    
    Args:
        state: The game state
        ability: The activated ability to check
        
    Returns:
        True if the ability can be used this turn
    """
    card = state.cards.get(ability.source_instance_id)
    if card is None:
        return False
    
    use_key = ability.unique_use_key
    return use_key not in card.used_abilities_this_turn


def get_available_abilities_for_player(
    state: GameState,
    engine: GameEngine,
    player: int,
) -> list[ActivatedAbility]:
    """Get all activated abilities available to a player on cards they control.
    
    Args:
        state: The game state
        engine: The game engine
        player: The player ID
        
    Returns:
        List of ActivatedAbility objects that can potentially be used
    """
    abilities: list[ActivatedAbility] = []
    
    for cid in state.players[player].play:
        card = state.cards.get(cid)
        if card is None or card.zone != "play":
            continue
        
        card_def = engine.card_def(state, cid)
        card_abilities = get_activated_abilities_for_card(state, cid, card_def)
        
        for ability in card_abilities:
            # Check once-per-turn restriction
            if not can_use_ability_this_turn(state, ability):
                continue
            abilities.append(ability)
    
    return abilities


def validate_ability_costs(
    state: GameState,
    engine: GameEngine,
    ability: ActivatedAbility,
) -> tuple[bool, list[str]]:
    """Validate that all costs of an ability can be paid.
    
    Args:
        state: The game state
        engine: The game engine
        ability: The activated ability to validate
        
    Returns:
        Tuple of (can_pay, list_of_payable_costs)
    """
    from lorcana_bot.costs import validate_cost_payable
    
    payable: list[str] = []
    for cost in ability.costs:
        is_payable, reason = validate_cost_payable(state, engine, ability, cost)
        if is_payable:
            payable.append(cost.kind)
        else:
            # Early exit - if any cost is not payable, ability cannot be used
            return False, []
    
    return True, payable


def pay_ability_costs(
    state: GameState,
    engine: GameEngine,
    ability: ActivatedAbility,
) -> tuple[str, ...]:
    """Pay all costs for an activated ability atomically.
    
    Args:
        state: The game state
        engine: The game engine
        ability: The activated ability whose costs to pay
        
    Returns:
        Tuple of cost kinds that were paid
        
    Raises:
        AbilityCostError: If costs cannot be paid
    """
    from lorcana_bot.costs import pay_cost
    
    paid_costs: list[str] = []
    
    for cost in ability.costs:
        pay_cost(state, engine, ability, cost)
        paid_costs.append(cost.kind)
    
    # Mark ability as used this turn
    card = state.cards[ability.source_instance_id]
    card.used_abilities_this_turn.append(ability.unique_use_key)
    
    return tuple(paid_costs)


def execute_ability_effects(
    state: GameState,
    engine: GameEngine,
    ability: ActivatedAbility,
) -> None:
    """Execute the effects of an activated ability.
    
    Args:
        state: The game state
        engine: The game engine
        ability: The activated ability to execute
    """
    from lorcana_bot.effect_types import EffectResolutionContext
    from lorcana_bot.effects import EffectResolver
    from lorcana_bot.cards import EffectDef
    
    if not ability.effects:
        return
    
    context = EffectResolutionContext(
        actor=state.cards[ability.source_instance_id].controller,
        source=ability.source_instance_id,
        target=None,
        choice=None,
        optional_choices={},
        event=None,
        event_payload={},
        pending_trigger_id=None,
        trigger_source=None,
        trigger_subject=None,
        current_targets=(),  # Empty tuple for activated abilities
    )
    
    # Convert source effects to EffectDef if needed
    effect_defs = _convert_source_effects(ability.effects)
    
    resolver = EffectResolver(engine)
    resolver.resolve_many(state, effect_defs, context)


def _convert_source_effects(source_effects: tuple[Any, ...]) -> tuple["EffectDef", ...]:
    """Convert SourceEffectDef objects to EffectDef objects.
    
    Args:
        source_effects: Tuple of SourceEffectDef objects
        
    Returns:
        Tuple of EffectDef objects
    """
    from lorcana_bot.cards import EffectDef
    
    effect_defs: list[EffectDef] = []
    
    for src_effect in source_effects:
        if isinstance(src_effect, EffectDef):
            effect_defs.append(src_effect)
        else:
            # Convert from SourceEffectDef
            # Note: EffectDef doesn't have branches - use effects for conditional branches
            effect_def = EffectDef(
                kind=src_effect.kind,
                target=src_effect.target.selector if src_effect.target else None,
                amount=src_effect.amount,
                value=src_effect.value,
                keyword=src_effect.keyword,
                effects=tuple(_convert_source_effects(src_effect.effects)) if src_effect.effects else (),
                optional=src_effect.optional,
                condition=src_effect.condition,
                duration=src_effect.duration if hasattr(src_effect, 'duration') else None,
            )
            effect_defs.append(effect_def)
    
    return tuple(effect_defs)


def use_ability(
    state: GameState,
    engine: GameEngine,
    ability: ActivatedAbility,
) -> AbilityUseResult:
    """Execute an activated ability: validate costs, pay costs, resolve effects.
    
    Args:
        state: The game state
        engine: The game engine
        ability: The activated ability to use
        
    Returns:
        AbilityUseResult indicating success or failure
    """
    from lorcana_bot.costs import validate_cost_payable
    
    # Validate costs are payable
    for cost in ability.costs:
        can_pay, reason = validate_cost_payable(state, engine, ability, cost)
        if not can_pay:
            return AbilityUseResult(
                success=False,
                error_message=f"Cannot pay cost {cost.kind}: {reason}",
            )
    
    # Check once-per-turn
    if not can_use_ability_this_turn(state, ability):
        return AbilityUseResult(
            success=False,
            error_message="Ability has already been used this turn",
        )
    
    # Pay costs atomically
    try:
        paid_costs = pay_ability_costs(state, engine, ability)
    except AbilityCostError as e:
        return AbilityUseResult(
            success=False,
            error_message=str(e),
        )
    
    # Execute effects
    try:
        execute_ability_effects(state, engine, ability)
        return AbilityUseResult(
            success=True,
            costs_paid=paid_costs,
            effects_resolved=True,
        )
    except Exception as e:
        return AbilityUseResult(
            success=True,  # Costs were paid even if effects failed
            costs_paid=paid_costs,
            effects_resolved=False,
            error_message=str(e),
        )