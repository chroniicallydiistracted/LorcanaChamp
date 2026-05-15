"""Replacement and Prevention Effects Layer.

This module implements the first replacement/prevention effect layer for LorcanaChamp.
It intercepts state-changing operations before mutation, allowing replacement effects
to modify the outcome.

Architecture:
- All state-changing operations pass through eventful helpers:
  - deal_damage(...)
  - banish_card(...)
  - move_card(...)
  - discard_card(...)
- The replacement layer inspects the event before mutation
- Replacement effects can:
  - Prevent damage (partial or full)
  - Replace banish with return to hand/discard
  - Apply once-per-turn usage restrictions

Inspired by Lorcanito's replacement effect system in:
- runtime-moves/resolution/action-effects/
- rules/static-effect-registry.ts
- triggered-abilities/index.ts
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .state import GameState, CardInstance


class ReplacementEffectType(Enum):
    """Types of replacement effects."""
    PREVENT_DAMAGE = auto()
    PREVENT_ALL_DAMAGE_SOURCE = auto()
    REPLACE_BANISH_RETURN_TO_HAND = auto()
    REPLACE_BANISH_DISCARD = auto()
    REPLACE_DAMAGE = auto()
    CANNOT_BE_CHALLENGED = auto()
    CANNOT_BE_TARGETED = auto()


@dataclass(frozen=True, slots=True)
class ReplacementEffectEntry:
    """A single replacement effect from a source card."""
    source_id: int  # instance_id of the card providing the effect
    effect_type: ReplacementEffectType
    # Target specification
    target_mode: str  # "self", "your_characters", "opposing_characters", "all_characters"
    # Condition for activation (optional)
    condition: dict[str, Any] | None = None
    # Effect value
    amount: int = 0  # For PREVENT_DAMAGE: how much to prevent
    # Once-per-turn tracking
    once_per_turn: bool = False
    # Replacement effect to execute instead
    replacement_effect: str | None = None  # "return_to_hand", "discard", "ready"
    # Usage tracking key
    usage_key: str | None = None  # e.g., "prevent_next_1"
    
    @property
    def identifier(self) -> str:
        """Unique identifier for this effect."""
        return f"{self.effect_type.name}:{self.source_id}"


@dataclass
class ReplacementEffectRegistry:
    """Registry of active replacement effects in the game state."""
    effects: list[ReplacementEffectEntry] = field(default_factory=list)
    # Once-per-turn usage ledger: key -> {"player": int, "used": bool, "turn": int}
    usage_ledger: dict[str, dict[str, Any]] = field(default_factory=dict)
    
    def register_effect(self, entry: ReplacementEffectEntry) -> None:
        """Add a replacement effect to the registry."""
        self.effects.append(entry)
    
    def deregister_effects_from_source(self, source_id: int) -> None:
        """Remove all replacement effects from a specific source card."""
        self.effects = [e for e in self.effects if e.source_id != source_id]
    
    def get_effects_for_instance(self, state: GameState, instance_id: int) -> list[ReplacementEffectEntry]:
        """Get all replacement effects that apply to a specific card instance."""
        return [e for e in self.effects if self._applies_to(state, instance_id, e)]
    
    def _applies_to(self, state: GameState, instance_id: int, effect: ReplacementEffectEntry) -> bool:
        """Check if a replacement effect applies to an instance."""
        inst = state.cards.get(instance_id)
        if inst is None:
            return False
        
        source_inst = state.cards.get(effect.source_id)
        if source_inst is None or source_inst.zone != "play":
            return False
        
        if effect.target_mode == "self":
            return instance_id == effect.source_id
        
        source_controller = source_inst.controller
        
        if effect.target_mode == "your_characters":
            return inst.controller == source_controller and inst.zone == "play"
        
        if effect.target_mode == "opposing_characters":
            return inst.controller != source_controller and inst.zone == "play"
        
        if effect.target_mode == "all_characters":
            return inst.zone == "play"
        
        return False
    
    def check_and_use_once_per_turn(
        self,
        state: GameState,
        effect: ReplacementEffectEntry,
        player: int | None = None,
    ) -> bool:
        """Check if a once-per-turn effect can be used and mark it as used.
        
        Returns True if the effect can be used (not used this turn or not once_per_turn).
        Returns False if already used this turn.
        """
        if not effect.once_per_turn:
            return True
        
        usage_key = effect.usage_key or effect.identifier
        entry = self.usage_ledger.get(usage_key)
        
        if entry is None:
            # Not used yet
            self.usage_ledger[usage_key] = {
                "player": player or 0,
                "used": True,
                "turn": state.turn_number,
            }
            return True
        
        # Check if same turn
        if entry["turn"] == state.turn_number:
            # Already used this turn
            return False
        
        # Reset for new turn
        self.usage_ledger[usage_key] = {
            "player": player or 0,
            "used": True,
            "turn": state.turn_number,
        }
        return True
    
    def reset_usage_for_turn(self, state: GameState, turn_number: int) -> None:
        """Reset usage ledger for a specific turn number."""
        keys_to_remove = [
            key for key, entry in self.usage_ledger.items()
            if entry["turn"] < turn_number
        ]
        for key in keys_to_remove:
            del self.usage_ledger[key]
    
    def clear(self) -> None:
        """Clear all effects and usage tracking."""
        self.effects.clear()
        self.usage_ledger.clear()


@dataclass
class DamageEvent:
    """A damage event that can be intercepted by replacement effects."""
    target_id: int
    source_id: int | None
    original_amount: int
    current_amount: int
    was_challenge: bool = False
    was_replaced: bool = False
    replacement_description: str | None = None


@dataclass
class BanishEvent:
    """A banish event that can be intercepted by replacement effects."""
    target_id: int
    source_id: int | None
    original_destination: str = "discard"
    actual_destination: str = "discard"
    was_replaced: bool = False
    replacement_description: str | None = None


# Global registry instance (created on-demand)
_global_registry: ReplacementEffectRegistry | None = None


def get_registry(state: GameState) -> ReplacementEffectRegistry:
    """Get the replacement effect registry from game state."""
    return state.replacement_effect_registry


def register_replacement_effect(
    state: GameState,
    entry: ReplacementEffectEntry,
) -> None:
    """Register a replacement effect."""
    registry = get_registry(state)
    registry.register_effect(entry)


def deregister_replacement_effects_from_card(
    state: GameState,
    source_id: int,
) -> None:
    """Deregister all replacement effects from a card."""
    registry = get_registry(state)
    registry.deregister_effects_from_source(source_id)


def evaluate_prevention(
    state: GameState,
    damage_event: DamageEvent,
    target_controller: int,
) -> tuple[int, str | None]:
    """Evaluate if damage can be prevented and by how much.
    
    Returns (prevented_amount, replacement_description).
    If no prevention applies, returns (0, None).
    """
    registry = get_registry(state)
    total_prevented = 0
    description = None
    
    # Check all replacement effects for the target
    for effect in registry.effects:
        if effect.effect_type == ReplacementEffectType.PREVENT_DAMAGE:
            if registry._applies_to(state, damage_event.target_id, effect):
                # Check once-per-turn
                if not registry.check_and_use_once_per_turn(state, effect, target_controller):
                    continue
                
                # Prevent up to the effect amount
                prevent_amount = min(effect.amount, damage_event.current_amount)
                total_prevented += prevent_amount
                description = f"prevent {prevent_amount} damage"
    
    return total_prevented, description


def evaluate_banish_replacement(
    state: GameState,
    banish_event: BanishEvent,
    target_controller: int,
) -> tuple[str, str | None]:
    """Evaluate if banish can be replaced.
    
    Returns (destination, replacement_description).
    If no replacement applies, returns ("discard", None).
    """
    registry = get_registry(state)
    
    # Check all replacement effects for the target
    for effect in registry.effects:
        if effect.effect_type == ReplacementEffectType.REPLACE_BANISH_RETURN_TO_HAND:
            if registry._applies_to(state, banish_event.target_id, effect):
                if not registry.check_and_use_once_per_turn(state, effect, target_controller):
                    continue
                return ("hand", "return to hand instead of banish")
        
        if effect.effect_type == ReplacementEffectType.REPLACE_BANISH_DISCARD:
            if registry._applies_to(state, banish_event.target_id, effect):
                if not registry.check_and_use_once_per_turn(state, effect, target_controller):
                    continue
                return ("discard", "discard instead of banish")
    
    return banish_event.original_destination, None


def check_cannot_be_challenged(
    state: GameState,
    target_id: int,
    challenger_controller: int,
) -> bool:
    """Check if a character cannot be challenged."""
    registry = get_registry(state)
    
    for effect in registry.effects:
        if effect.effect_type == ReplacementEffectType.CANNOT_BE_CHALLENGED:
            if registry._applies_to(state, target_id, effect):
                # Check condition if present
                if effect.condition:
                    if not _evaluate_simple_condition(state, effect.condition, target_id):
                        continue
                return True
    
    return False


def check_cannot_be_targeted(
    state: GameState,
    target_id: int,
    caster_controller: int,
) -> bool:
    """Check if a character cannot be targeted."""
    registry = get_registry(state)
    
    for effect in registry.effects:
        if effect.effect_type == ReplacementEffectType.CANNOT_BE_TARGETED:
            if registry._applies_to(state, target_id, effect):
                # Check condition if present
                if effect.condition:
                    if not _evaluate_simple_condition(state, effect.condition, target_id):
                        continue
                return True
    
    return False


def _evaluate_simple_condition(
    state: GameState,
    condition: dict[str, Any],
    target_id: int,
) -> bool:
    """Evaluate a simple condition for replacement effect activation."""
    kind = condition.get("kind", "always")
    
    if kind == "always":
        return True
    
    if kind == "has_keyword":
        from .static_effects import keywords_for_instance
        inst = state.cards.get(target_id)
        if inst is None:
            return False
        card_def = state.cards.get(target_id)
        if card_def is None:
            return False
        keywords = keywords_for_instance(state, target_id)
        keyword = condition.get("keyword", "")
        return keyword.upper().replace(" ", "_") in keywords
    
    if kind == "damaged":
        inst = state.cards.get(target_id)
        if inst is None:
            return False
        return inst.damage > 0
    
    if kind == "exerted":
        inst = state.cards.get(target_id)
        if inst is None:
            return False
        return inst.exerted
    
    if kind == "controller_has_lore_at_least":
        inst = state.cards.get(target_id)
        if inst is None:
            return False
        required_lore = int(condition.get("amount", 0))
        return state.players[inst.controller].lore >= required_lore
    
    if kind == "opponent_has_lore_at_least":
        inst = state.cards.get(target_id)
        if inst is None:
            return False
        required_lore = int(condition.get("amount", 0))
        return state.players[state.opponent(inst.controller)].lore >= required_lore
    
    return True


# Eventful helpers for state changes

def deal_damage(
    state: GameState,
    target_id: int,
    source_id: int | None,
    amount: int,
    *,
    is_challenge: bool = False,
) -> DamageEvent:
    """Apply damage to a target, intercepting with replacement effects.
    
    Returns a DamageEvent describing what happened.
    """
    from .constants import ZONE_PLAY
    
    # Create the damage event
    event = DamageEvent(
        target_id=target_id,
        source_id=source_id,
        original_amount=amount,
        current_amount=amount,
        was_challenge=is_challenge,
    )
    
    # Check for prevention
    inst = state.cards.get(target_id)
    if inst is None:
        return event
    
    controller = inst.controller
    prevented, description = evaluate_prevention(state, event, controller)
    
    if prevented > 0:
        event.current_amount = max(0, event.current_amount - prevented)
        event.was_replaced = True
        event.replacement_description = description
    
    # Apply remaining damage
    if event.current_amount > 0 and target_id in state.cards:
        state.cards[target_id].damage += event.current_amount
        state.cards[target_id].last_damage_source = source_id
        state.cards[target_id].last_damage_was_challenge = is_challenge

    # Do not emit gameplay events here.
    # Damage event emission belongs to GameEngine._deal_damage_eventful(), where
    # the real engine context, actor, source/target card metadata, and trigger
    # buffering are available. This helper only applies replacement/prevention
    # and returns a DamageEvent describing the mutation.
    return event


def banish_card(
    state: GameState,
    target_id: int,
    source_id: int | None = None,
    *,
    default_destination: str = "discard",
) -> BanishEvent:
    """Banish a card, intercepting with replacement effects.
    
    Returns a BanishEvent describing what happened.
    """
    from .constants import ZONE_DISCARD, ZONE_HAND
    
    # Create the banish event
    event = BanishEvent(
        target_id=target_id,
        source_id=source_id,
        original_destination=default_destination,
        actual_destination=default_destination,
    )
    
    # Check for replacement
    inst = state.cards.get(target_id)
    if inst is None:
        return event
    
    controller = inst.controller
    new_destination, description = evaluate_banish_replacement(state, event, controller)
    
    if new_destination != event.original_destination:
        event.actual_destination = new_destination
        event.was_replaced = True
        event.replacement_description = description
    
    # Perform the move
    if target_id in state.cards:
        state.move_card(target_id, event.actual_destination)
    
    return event


def move_card_eventful(
    state: GameState,
    card_instance_id: int,
    destination: str,
    controller: int | None = None,
) -> None:
    """Move a card with full event emission and replacement checking.
    
    This is the recommended way to move cards as it supports replacement effects.
    """
    inst = state.cards.get(card_instance_id)
    if inst is None:
        return
    
    # Track source info for events
    from_zone = inst.zone
    source_controller = inst.controller
    
    # Move the card using state method
    state.move_card(card_instance_id, destination, controller)


def discard_card(
    state: GameState,
    card_instance_id: int,
    source_id: int | None = None,
) -> bool:
    """Discard a card from hand.
    
    Returns True if the card was discarded, False if it couldn't be (not in hand).
    """
    from .constants import ZONE_DISCARD, ZONE_HAND
    
    inst = state.cards.get(card_instance_id)
    if inst is None:
        return False
    
    if inst.zone != ZONE_HAND:
        return False
    
    state.move_card(card_instance_id, ZONE_DISCARD)
    return True


# Helper to create replacement effects from card abilities

def parse_replacement_effects_from_card(
    card_abilities: tuple,
    source_id: int,
) -> list[ReplacementEffectEntry]:
    """Parse replacement/prevention effects from card source abilities.

    Supports both raw dict abilities and SourceAbilityDef/SourceEffectDef
    dataclasses produced by the Lorcanito source importer.
    """
    from .card_logic.effect_utils import (
        source_ability_effects,
        source_ability_kind,
        source_effect_amount,
        source_effect_condition,
        source_effect_kind,
        to_engine_replacement_kind,
    )

    effects: list[ReplacementEffectEntry] = []

    for ability in card_abilities:
        ability_type = source_ability_kind(ability)
        if ability_type not in {"replacement", "static"}:
            continue

        for source_effect in source_ability_effects(ability):
            raw = source_effect if isinstance(source_effect, dict) else getattr(source_effect, "raw", {}) or {}
            raw_kind = source_effect_kind(source_effect) or raw.get("type") or raw.get("kind")
            if not raw_kind:
                continue

            effect_type_str = to_engine_replacement_kind(raw_kind)

            if effect_type_str == "prevent_damage":
                amount = source_effect_amount(source_effect)
                if amount is None:
                    amount = int(raw.get("value") or raw.get("prevent") or 1)

                once_per_turn = bool(raw.get("oncePerTurn") or raw.get("once_per_turn") or False)
                target_mode, _ = _parse_target_from_replacement(source_effect, ability)
                condition = source_effect_condition(source_effect) or raw.get("condition")

                effects.append(ReplacementEffectEntry(
                    source_id=source_id,
                    effect_type=ReplacementEffectType.PREVENT_DAMAGE,
                    target_mode=target_mode,
                    amount=int(amount),
                    once_per_turn=once_per_turn,
                    condition=condition,
                    usage_key=f"prevent_damage_{source_id}" if once_per_turn else None,
                ))

            elif effect_type_str == "replace_banish":
                replacement = (
                    raw.get("replacement")
                    or raw.get("replacement_effect")
                    or raw.get("replacementEffect")
                    or "return_to_hand"
                )
                normalized_replacement = str(replacement).replace("-", "_")
                target_mode, _ = _parse_target_from_replacement(source_effect, ability)
                once_per_turn = bool(raw.get("oncePerTurn") or raw.get("once_per_turn") or False)
                condition = source_effect_condition(source_effect) or raw.get("condition")

                if normalized_replacement == "return_to_hand":
                    effect_type = ReplacementEffectType.REPLACE_BANISH_RETURN_TO_HAND
                else:
                    effect_type = ReplacementEffectType.REPLACE_BANISH_DISCARD

                effects.append(ReplacementEffectEntry(
                    source_id=source_id,
                    effect_type=effect_type,
                    target_mode=target_mode,
                    once_per_turn=once_per_turn,
                    replacement_effect=normalized_replacement,
                    condition=condition,
                    usage_key=f"replace_banish_{source_id}" if once_per_turn else None,
                ))

            elif effect_type_str in {"cannot_be_challenged", "cannot-be-challenged"}:
                target_mode, _ = _parse_target_from_replacement(source_effect, ability)
                condition = source_effect_condition(source_effect) or raw.get("condition")
                effects.append(ReplacementEffectEntry(
                    source_id=source_id,
                    effect_type=ReplacementEffectType.CANNOT_BE_CHALLENGED,
                    target_mode=target_mode,
                    condition=condition,
                ))

            elif effect_type_str in {"cannot_be_targeted", "cannot-be-targeted"}:
                target_mode, _ = _parse_target_from_replacement(source_effect, ability)
                condition = source_effect_condition(source_effect) or raw.get("condition")
                effects.append(ReplacementEffectEntry(
                    source_id=source_id,
                    effect_type=ReplacementEffectType.CANNOT_BE_TARGETED,
                    target_mode=target_mode,
                    condition=condition,
                ))

    return effects


def _parse_target_from_replacement(effect_obj: object, ability_obj: object) -> tuple[str, str | None]:
    """Parse target specification from a replacement/prevention effect.

    Accepts SourceEffectDef/SourceTargetDef dataclasses and raw dicts.
    """
    from .card_logic.effect_utils import (
        source_target_alias,
        source_target_selector,
    )

    alias = source_target_alias(effect_obj) or source_target_alias(ability_obj)
    selector = source_target_selector(effect_obj) or source_target_selector(ability_obj) or {}

    if isinstance(alias, str):
        normalized = alias.lower()
        if normalized in {"self", "source"}:
            return ("self", None)
        if normalized in {"your_characters", "your_other_characters", "controller"}:
            return ("your_characters", None)
        if normalized in {"opposing_characters", "opponent"}:
            return ("opposing_characters", None)
        if normalized in {"all_characters", "any_character"}:
            return ("all_characters", None)

    if isinstance(alias, dict):
        selector = {**alias, **selector}

    controller = selector.get("controller")
    if controller in {"self", "you", "controller"}:
        return ("your_characters", None)
    if controller in {"opponent", "opposing"}:
        return ("opposing_characters", None)

    if selector.get("exclude_self") or selector.get("excludeSelf"):
        return ("your_characters", None)

    classifications = (
        selector.get("classifications")
        or selector.get("classification")
        or selector.get("cardTypes")
        or selector.get("card_types")
        or ()
    )
    if classifications:
        return ("all_characters", None)

    return ("self", None)


def register_replacement_effects_for_card(
    state: GameState,
    instance_id: int,
    card_abilities: tuple,
) -> None:
    """Register all replacement effects for a card entering play."""
    effects = parse_replacement_effects_from_card(card_abilities, instance_id)
    for effect in effects:
        register_replacement_effect(state, effect)


def cleanup_replacement_effects_on_turn_end(state: GameState) -> None:
    """Clean up replacement effect usage at the end of a turn."""
    registry = get_registry(state)
    registry.reset_usage_for_turn(state, state.turn_number)