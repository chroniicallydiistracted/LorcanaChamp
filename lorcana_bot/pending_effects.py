"""Pending effect layer for target-choice and multi-step resolution.

This module implements the pending effect system that allows the engine to
pause resolution when an effect requires player input (target choice, index choice,
optional accept/decline, etc.) and resume when the player provides that input.

Inspired by Lorcanito's pending resolution input system in:
- runtime-moves/resolution/action-effects/pending-action-effects.ts
- runtime-moves/resolution/action-effects/selection-context.ts
- runtime-moves/resolution/action-effects/selection-state.ts
- targeting/runtime/index.ts
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from lorcana_bot.cards import EffectDef

if TYPE_CHECKING:
    from lorcana_bot.state import GameState


@dataclass(slots=True)
class TargetRequirement:
    """Describes a required target for a pending effect."""
    kind: str  # "chosen_character", "chosen_opposing_character", "chosen_damaged_character",
               # "chosen_item", "chosen_location", "chosen_player", "choice_index"
    min_targets: int = 1
    max_targets: int = 1
    optional: bool = False
    # For filtering
    card_type: str | None = None  # "character", "item", "location"
    must_be_damaged: bool = False
    must_be_exerted: bool = False
    owner_filter: str | None = None  # "opponent", "controller", "any"


@dataclass(slots=True)
class PendingEffect:
    """A pending effect awaiting player input for target/choice resolution.
    
    This dataclass models Lorcanito's pending action effects with rich metadata
    for comprehensive target selection and multi-step effect resolution.
    """
    id: str
    controller_id: int
    chooser_id: int
    source_id: int | None  # Card instance that triggered this effect
    source_card_id: str | None  # Card definition ID
    effects: tuple[EffectDef, ...]  # Effects to resolve (multi-step)
    current_effect_index: int = 0  # Index of current effect in sequence
    required_targets: tuple[TargetRequirement, ...] = ()  # Target requirements for current effect
    selected_targets: tuple[int, ...] = ()  # Player's selected target instance IDs
    choice_options: tuple[Any, ...] = ()  # Available choices (card instances, indices, etc.)
    selected_choice: int | None = None  # Player's selected choice index
    optional: bool = False  # Whether accepting is optional
    accepted: bool | None = None  # True=accepted, False=declined, None=pending
    origin: str = "action|bag|activated"  # Where this pending effect originated
    origin_id: str | None = None  # ID of originating bag item / ability
    raw: dict[str, Any] = field(default_factory=dict)
    
    @property
    def current_effect(self) -> EffectDef | None:
        """Get the current effect being resolved."""
        if 0 <= self.current_effect_index < len(self.effects):
            return self.effects[self.current_effect_index]
        return None
    
    @property
    def is_complete(self) -> bool:
        """Check if all effects have been resolved."""
        return self.current_effect_index >= len(self.effects)
    
    @property
    def current_requirement(self) -> TargetRequirement | None:
        """Get the current target requirement."""
        if 0 <= self.current_effect_index < len(self.required_targets):
            return self.required_targets[self.current_effect_index]
        return None
    
    @property
    def requires_choice_input(self) -> bool:
        """Check if the current effect requires a choice (index)."""
        if not self.choice_options:
            return False
        return self.current_requirement is None or self.current_requirement.kind == "choice_index"
    
    @property
    def requires_target_input(self) -> bool:
        """Check if the current effect requires a target selection."""
        return self.current_requirement is not None and self.current_requirement.kind.startswith("chosen_")


def create_pending_effect(
    state: GameState,
    controller_id: int,
    chooser_id: int,
    source_id: int | None,
    source_card_id: str | None,
    effects: tuple[EffectDef, ...],
    *,
    optional: bool = False,
    origin: str = "action",
    origin_id: str | None = None,
    raw: dict[str, Any] | None = None,
) -> PendingEffect:
    """Create a new pending effect and add it to the game state."""
    pending_id = f"pe_{state.next_bag_id()}"
    
    # Analyze effects to determine target requirements
    requirements = _analyze_effect_requirements(effects)
    
    # Collect choice options if needed
    choice_options = _collect_choice_options(state, effects, controller_id, source_id)
    
    pending = PendingEffect(
        id=pending_id,
        controller_id=controller_id,
        chooser_id=chooser_id,
        source_id=source_id,
        source_card_id=source_card_id,
        effects=effects,
        required_targets=tuple(requirements),
        choice_options=tuple(choice_options),
        optional=optional,
        origin=origin,
        origin_id=origin_id,
        raw=raw or {},
    )
    
    state.pending_effects.append(pending)
    return pending


def _analyze_effect_requirements(effects: tuple[EffectDef, ...]) -> list[TargetRequirement]:
    """Analyze effects to determine target requirements."""
    requirements = []
    
    for effect in effects:
        requirement = _analyze_single_effect_requirement(effect)
        if requirement:
            requirements.append(requirement)
    
    return requirements


def _analyze_single_effect_requirement(effect: EffectDef) -> TargetRequirement | None:
    """Analyze a single effect to determine its target requirement."""
    target = effect.target
    
    if target is None:
        return None
    
    # CHOSEN targets require player selection
    if target in {"chosen_character", "chosen_card"}:
        return TargetRequirement(
            kind="chosen_character",
            min_targets=1,
            max_targets=1,
            card_type="character",
        )
    
    if target == "chosen_opposing_character":
        return TargetRequirement(
            kind="chosen_opposing_character",
            min_targets=1,
            max_targets=1,
            card_type="character",
            owner_filter="opponent",
        )
    
    if target == "chosen_damaged_character":
        return TargetRequirement(
            kind="chosen_damaged_character",
            min_targets=1,
            max_targets=1,
            card_type="character",
            must_be_damaged=True,
        )
    
    if target == "chosen_item":
        return TargetRequirement(
            kind="chosen_item",
            min_targets=1,
            max_targets=1,
            card_type="item",
        )
    
    if target == "chosen_location":
        return TargetRequirement(
            kind="chosen_location",
            min_targets=1,
            max_targets=1,
            card_type="location",
        )
    
    if target == "chosen_player":
        return TargetRequirement(
            kind="chosen_player",
            min_targets=1,
            max_targets=1,
        )
    
    return None


def _collect_choice_options(
    state: GameState,
    effects: tuple[EffectDef, ...],
    controller_id: int,
    source_id: int | None,
) -> list[Any]:
    """Collect available choice options for choice-type effects."""
    options = []
    
    for effect in effects:
        if effect.kind == "choice":
            # Choice effects - the player picks which branch to execute
            # Store the choice index options (0, 1, 2, ...)
            options.extend(range(len(effect.effects) if effect.effects else 0))
        elif effect.kind == "optional":
            # Optional effects - the player can accept or decline
            # No specific options needed, just the boolean accept/decline
            pass
    
    return options


def get_pending_effects_for_chooser(state: GameState, chooser_id: int) -> list[PendingEffect]:
    """Get all pending effects that a player can act on."""
    return [pe for pe in state.pending_effects if pe.chooser_id == chooser_id]


def get_current_pending_effect(state: GameState, chooser_id: int) -> PendingEffect | None:
    """Get the current pending effect that a chooser must resolve."""
    effects = get_pending_effects_for_chooser(state, chooser_id)
    if not effects:
        return None
    # Return the first one that needs input or is incomplete
    for pe in effects:
        if pe.accepted is None and not pe.is_complete:
            return pe
    return None


def resolve_pending_effect_target(
    state: GameState,
    pending_id: str,
    selected_targets: tuple[int, ...],
) -> None:
    """Record target selection for a pending effect."""
    for pe in state.pending_effects:
        if pe.id == pending_id:
            pe.selected_targets = selected_targets
            return


def resolve_pending_effect_choice(
    state: GameState,
    pending_id: str,
    choice_index: int,
) -> None:
    """Record choice selection for a pending effect."""
    for pe in state.pending_effects:
        if pe.id == pending_id:
            pe.selected_choice = choice_index
            return


def resolve_pending_effect_optional(
    state: GameState,
    pending_id: str,
    accepted: bool,
) -> None:
    """Record optional accept/decline for a pending effect."""
    for pe in state.pending_effects:
        if pe.id == pending_id:
            pe.accepted = accepted
            return


def advance_pending_effect(state: GameState, pending_id: str) -> None:
    """Advance to the next effect in a pending effect sequence."""
    for pe in state.pending_effects:
        if pe.id == pending_id:
            pe.current_effect_index += 1
            return


def complete_pending_effect(state: GameState, pending_id: str) -> PendingEffect | None:
    """Mark a pending effect as complete and remove it from the state."""
    for idx, pe in enumerate(state.pending_effects):
        if pe.id == pending_id:
            return state.pending_effects.pop(idx)
    return None


def get_valid_targets_for_requirement(
    state: GameState,
    requirement: TargetRequirement,
    chooser_id: int,
    engine: "GameEngine | None" = None,  # type: ignore[name-defined]
) -> list[int]:
    """Get valid target instance IDs for a target requirement.
    
    Applies normal targeting rules:
    - Ward protects opposing targets (requires engine)
    - Only public board targets are valid
    - Damaged targets must have damage > 0
    - Opposing targets must be opponent of chooser
    
    Args:
        state: The game state
        requirement: The target requirement
        chooser_id: The player who is choosing
        engine: Optional engine for keyword checking. If None, skip Ward checks.
    """
    from lorcana_bot.constants import KEYWORD_WARD, ZONE_PLAY, CARD_CHARACTER, CARD_ITEM, CARD_LOCATION
    
    valid_targets: list[int] = []
    
    # Determine which players to search
    if requirement.owner_filter == "opponent":
        search_players = (state.opponent(chooser_id),)
    elif requirement.owner_filter == "controller":
        search_players = (chooser_id,)
    else:
        search_players = (chooser_id, state.opponent(chooser_id))
    
    # Determine card type filter
    card_type = requirement.card_type
    
    # Search each player's play area
    for player in search_players:
        for instance_id in state.players[player].play:
            inst = state.cards[instance_id]
            
            # Must be in play
            if inst.zone != ZONE_PLAY:
                continue
            
            # Check card type filter (skip if no engine available)
            if engine is not None and card_type:
                try:
                    card_def = engine.card_def(state, instance_id)
                    if card_def.card_type != card_type:
                        continue
                except KeyError:
                    # Card not in database - skip this validation
                    pass
            
            # Check damaged filter
            if requirement.must_be_damaged and inst.damage == 0:
                continue
            
            # Check exerted filter
            if requirement.must_be_exerted and not inst.exerted:
                continue
            
            # Apply Ward protection for opposing targets (requires engine)
            if engine is not None:
                try:
                    if requirement.kind == "chosen_opposing_character":
                        if player != chooser_id and engine.has_keyword(state, instance_id, KEYWORD_WARD):
                            continue
                    
                    # Also apply Ward protection for general chosen targets when targeting opponent
                    if requirement.kind == "chosen_character" and player != chooser_id:
                        if engine.has_keyword(state, instance_id, KEYWORD_WARD):
                            continue
                except KeyError:
                    # Card not in database - skip Ward check
                    pass
            
            valid_targets.append(instance_id)
    
    return valid_targets


def has_pending_effects(state: GameState) -> bool:
    """Check if any pending effects exist."""
    return len(state.pending_effects) > 0


def get_pending_effect_by_id(state: GameState, pending_id: str) -> PendingEffect | None:
    """Get a pending effect by ID."""
    for pe in state.pending_effects:
        if pe.id == pending_id:
            return pe
    return None