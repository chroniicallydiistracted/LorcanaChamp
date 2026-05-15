"""Static effect registry for continuous card effects.

This module implements a conservative static effect system for LorcanaChamp.
Static effects are continuous modifications that apply while a source card
is in play. Unlike triggered or activated effects, static effects don't
require a trigger event - they modify game state derivatively.

Supported static effects (MVP):
- modify strength/willpower/lore
- grant keyword
- cost reduction while source is in play
- restrictions: cannot quest/challenge (simple cases only)

Applies to: self / your characters / opposing characters / characters with classification

Does NOT support (yet):
- replacement/prevention effects
- complex layer ordering
- condition-dependent modifiers
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .state import GameState


class StaticEffectType(Enum):
    """Kinds of static effects supported in the MVP."""
    MODIFY_STRENGTH = auto()
    MODIFY_WILLPOWER = auto()
    MODIFY_LORE = auto()
    GRANT_KEYWORD = auto()
    COST_REDUCTION = auto()
    QUEST_RESTRICTION = auto()
    CHALLENGE_RESTRICTION = auto()


@dataclass(frozen=True, slots=True)
class StaticEffectEntry:
    """A single static effect from a source card."""
    source_id: int  # instance_id of the card providing the effect
    effect_type: StaticEffectType
    # Target specification
    target_mode: str  # "self", "your_characters", "opposing_characters", "all_characters", "classification"
    target_classification: str | None = None  # e.g., "item", "character", or specific classification
    # Effect value
    amount: int = 0
    keyword: str | None = None
    cost_reduction_amount: int = 0
    cost_reduction_card_type: str | None = None  # None means all card types
    # Restrictions
    restriction_type: str | None = None  # "cannot_quest", "cannot_challenge"
    
    def applies_to(self, state: GameState, instance_id: int) -> bool:
        """Check if this static effect applies to a given card instance."""
        # Get the target card
        inst = state.cards.get(instance_id)
        if inst is None:
            return False
        
        # Check if source is still in play
        source_inst = state.cards.get(self.source_id)
        if source_inst is None or source_inst.zone != "play":
            return False
        
        # Determine target based on target_mode
        if self.target_mode == "self":
            return instance_id == self.source_id
        
        source_controller = source_inst.controller
        
        if self.target_mode == "your_characters":
            return inst.controller == source_controller and inst.zone == "play"
        
        if self.target_mode == "opposing_characters":
            return inst.controller != source_controller and inst.zone == "play"
        
        if self.target_mode == "all_characters":
            return inst.zone == "play"
        
        if self.target_mode == "classification":
            # For classification-based targeting, we need to check card type
            from .constants import CARD_CHARACTER, CARD_ITEM, CARD_LOCATION
            from .engine import GameEngine
            # We'll need to check the card type
            if self.target_classification == "character":
                return inst.zone == "play" and inst.card_id  # Simple check
            if self.target_classification == "item":
                return inst.zone == "play" and inst.card_id
            if self.target_classification == "location":
                return inst.zone == "play" and inst.card_id
            # Could be a more specific classification filter
            return inst.zone == "play" and inst.card_id
        
        return False


@dataclass
class StaticEffectRegistry:
    """Registry of active static effects in the game state.
    
    This registry maintains a list of static effect entries that are
    currently active. Effects are automatically registered when a card
    enters play and deregistered when the card leaves play.
    """
    effects: list[StaticEffectEntry] = field(default_factory=list)
    
    def register_effect(self, entry: StaticEffectEntry) -> None:
        """Add a static effect to the registry."""
        self.effects.append(entry)
    
    def deregister_effects_from_source(self, source_id: int) -> None:
        """Remove all static effects from a specific source card."""
        self.effects = [e for e in self.effects if e.source_id != source_id]
    
    def get_effects_for_instance(self, state: GameState, instance_id: int) -> list[StaticEffectEntry]:
        """Get all static effects that apply to a specific card instance."""
        return [e for e in self.effects if e.applies_to(state, instance_id)]
    
    def clear(self) -> None:
        """Clear all effects (used when game ends or resets)."""
        self.effects.clear()


def get_registry(state: GameState) -> StaticEffectRegistry:
    """Get the static effect registry from game state."""
    return state.static_effect_registry


# Derived-state functions

def effective_strength(state: GameState, instance_id: int, card_def) -> int:
    """Calculate effective strength for a card instance.
    
    Combines:
    - Printed strength from card definition
    - Static modifiers from active static effects
    - Temporary modifiers from CardInstance
    
    Args:
        state: Game state
        instance_id: Card instance ID
        card_def: Card definition (CardDef instance)
    """
    inst = state.cards.get(instance_id)
    if inst is None:
        return 0
    
    # Get printed strength from card definition
    base = int(card_def.strength or 0)
    
    # Get static modifiers
    registry = get_registry(state)
    modifier = 0
    for effect in registry.get_effects_for_instance(state, instance_id):
        if effect.effect_type == StaticEffectType.MODIFY_STRENGTH:
            modifier += effect.amount
    
    # Add temporary modifiers from instance state
    temp_modifier = inst.temporary_modifiers.get("strength", 0)
    
    return max(0, base + modifier + temp_modifier)


def effective_willpower(state: GameState, instance_id: int, card_def) -> int:
    """Calculate effective willpower for a card instance."""
    inst = state.cards.get(instance_id)
    if inst is None:
        return 0
    
    # Get printed willpower from card definition
    base = int(card_def.willpower or 0)
    
    # Get static modifiers
    registry = get_registry(state)
    modifier = 0
    for effect in registry.get_effects_for_instance(state, instance_id):
        if effect.effect_type == StaticEffectType.MODIFY_WILLPOWER:
            modifier += effect.amount
    
    # Add temporary modifiers
    temp_modifier = inst.temporary_modifiers.get("willpower", 0)
    
    return max(0, base + modifier + temp_modifier)


def keywords_for_instance(state: GameState, instance_id: int) -> tuple[str, ...]:
    """Get all keywords that apply to a card instance.
    
    Combines:
    - Printed keywords from card definition
    - Keywords granted by static effects
    - Keywords from temporary state
    """
    inst = state.cards.get(instance_id)
    if inst is None:
        return ()
    
    keywords: set[str] = set()
    
    # Get static keyword grants
    registry = get_registry(state)
    for effect in registry.get_effects_for_instance(state, instance_id):
        if effect.effect_type == StaticEffectType.GRANT_KEYWORD and effect.keyword:
            keywords.add(effect.keyword)
    
    # Get temporary keywords from instance state
    keywords.update(inst.temporary_keywords)
    
    return tuple(sorted(keywords))


def static_cost_reductions(state: GameState, player: int) -> list[dict[str, Any]]:
    """Get all static cost reductions for a player."""
    registry = get_registry(state)
    reductions: list[dict[str, Any]] = []
    
    # Add static cost reductions from effects
    for effect in registry.effects:
        source_inst = state.cards.get(effect.source_id)
        if source_inst is None or source_inst.controller != player:
            continue
        if source_inst.zone != "play":
            continue
        
        if effect.effect_type == StaticEffectType.COST_REDUCTION:
            reductions.append({
                "amount": effect.cost_reduction_amount,
                "card_type": effect.cost_reduction_card_type,
                "source_id": effect.source_id,
            })
    
    return reductions


def can_quest(state: GameState, instance_id: int) -> bool:
    """Check if a character can quest, considering static restrictions."""
    inst = state.cards.get(instance_id)
    if inst is None:
        return False
    
    # Check static quest restrictions
    registry = get_registry(state)
    for effect in registry.get_effects_for_instance(state, instance_id):
        if effect.effect_type == StaticEffectType.QUEST_RESTRICTION:
            return False
    
    return True


def can_challenge(state: GameState, instance_id: int) -> bool:
    """Check if a character can challenge, considering static restrictions."""
    inst = state.cards.get(instance_id)
    if inst is None:
        return False
    
    # Check static challenge restrictions
    registry = get_registry(state)
    for effect in registry.get_effects_for_instance(state, instance_id):
        if effect.effect_type == StaticEffectType.CHALLENGE_RESTRICTION:
            return False
    
    return True


# Static effect creation helpers

def create_modify_stat_effect(
    source_id: int,
    stat: str,
    amount: int,
    target_mode: str = "self",
    target_classification: str | None = None,
) -> StaticEffectEntry:
    """Create a static effect that modifies a stat."""
    if stat == "strength":
        effect_type = StaticEffectType.MODIFY_STRENGTH
    elif stat == "willpower":
        effect_type = StaticEffectType.MODIFY_WILLPOWER
    elif stat == "lore":
        effect_type = StaticEffectType.MODIFY_LORE
    else:
        raise ValueError(f"Unknown stat: {stat}")
    
    return StaticEffectEntry(
        source_id=source_id,
        effect_type=effect_type,
        target_mode=target_mode,
        target_classification=target_classification,
        amount=amount,
    )


def create_keyword_grant_effect(
    source_id: int,
    keyword: str,
    target_mode: str = "your_characters",
    target_classification: str | None = None,
) -> StaticEffectEntry:
    """Create a static effect that grants a keyword."""
    return StaticEffectEntry(
        source_id=source_id,
        effect_type=StaticEffectType.GRANT_KEYWORD,
        target_mode=target_mode,
        target_classification=target_classification,
        keyword=keyword.upper().replace(" ", "_").replace("-", "_"),
    )


def create_cost_reduction_effect(
    source_id: int,
    amount: int,
    card_type: str | None = None,
) -> StaticEffectEntry:
    """Create a static effect that reduces play cost."""
    return StaticEffectEntry(
        source_id=source_id,
        effect_type=StaticEffectType.COST_REDUCTION,
        target_mode="self",
        cost_reduction_amount=amount,
        cost_reduction_card_type=card_type,
    )


def create_quest_restriction_effect(
    source_id: int,
    target_mode: str = "self",
    target_classification: str | None = None,
) -> StaticEffectEntry:
    """Create a static effect that restricts questing."""
    return StaticEffectEntry(
        source_id=source_id,
        effect_type=StaticEffectType.QUEST_RESTRICTION,
        target_mode=target_mode,
        target_classification=target_classification,
        restriction_type="cannot_quest",
    )


def create_challenge_restriction_effect(
    source_id: int,
    target_mode: str = "self",
    target_classification: str | None = None,
) -> StaticEffectEntry:
    """Create a static effect that restricts challenging."""
    return StaticEffectEntry(
        source_id=source_id,
        effect_type=StaticEffectType.CHALLENGE_RESTRICTION,
        target_mode=target_mode,
        target_classification=target_classification,
        restriction_type="cannot_challenge",
    )


# Static effect parsing from source abilities

def parse_static_effects_from_card(
    card_abilities: tuple,
    source_id: int,
) -> list[StaticEffectEntry]:
    """Parse static effects from a card's source abilities.

    Supports both raw dict abilities and SourceAbilityDef/SourceEffectDef
    dataclasses produced by the Lorcanito source importer.
    """
    from .card_logic.effect_utils import (
        source_ability_effects,
        source_ability_kind,
        source_effect_amount,
        source_effect_kind,
        to_engine_static_kind,
    )

    effects: list[StaticEffectEntry] = []

    for ability in card_abilities:
        ability_type = source_ability_kind(ability)
        if ability_type != "static":
            continue

        for source_effect in source_ability_effects(ability):
            raw = source_effect if isinstance(source_effect, dict) else getattr(source_effect, "raw", {}) or {}
            raw_kind = source_effect_kind(source_effect) or raw.get("type") or raw.get("kind")
            if not raw_kind:
                continue

            effect_type = to_engine_static_kind(raw_kind)

            if effect_type == "modify_stat":
                stat = (
                    raw.get("attribute")
                    or raw.get("stat")
                    or raw.get("property")
                    or "strength"
                )
                amount = source_effect_amount(source_effect)
                if amount is None:
                    amount = int(raw.get("modifier") or raw.get("value") or 0)

                target_mode, target_class = _parse_target_from_static(source_effect, ability)
                effects.append(create_modify_stat_effect(
                    source_id=source_id,
                    stat=str(stat),
                    amount=int(amount),
                    target_mode=target_mode,
                    target_classification=target_class,
                ))

            elif effect_type == "gain_keyword":
                keyword_value = (
                    raw.get("keyword")
                    or raw.get("keywords")
                    or raw.get("value")
                    or raw.get("ability")
                )
                if keyword_value is None:
                    continue

                keywords = keyword_value if isinstance(keyword_value, (list, tuple)) else (keyword_value,)
                target_mode, target_class = _parse_target_from_static(source_effect, ability)
                for keyword in keywords:
                    effects.append(create_keyword_grant_effect(
                        source_id=source_id,
                        keyword=str(keyword),
                        target_mode=target_mode,
                        target_classification=target_class,
                    ))

            elif effect_type == "cost_reduction":
                amount = source_effect_amount(source_effect)
                if amount is None:
                    amount = int(raw.get("value") or raw.get("reduction") or 0)

                card_type = (
                    raw.get("cardType")
                    or raw.get("card_type")
                    or raw.get("appliesTo")
                    or raw.get("applies_to")
                )
                effects.append(create_cost_reduction_effect(
                    source_id=source_id,
                    amount=int(amount),
                    card_type=card_type,
                ))

            elif effect_type == "restriction":
                restriction = (
                    raw.get("restriction")
                    or raw.get("restriction_type")
                    or raw.get("restrictionType")
                    or raw.get("type")
                    or raw.get("kind")
                    or ""
                )
                target_mode, target_class = _parse_target_from_static(source_effect, ability)

                restriction_text = str(restriction).lower()
                if "quest" in restriction_text:
                    effects.append(create_quest_restriction_effect(
                        source_id=source_id,
                        target_mode=target_mode,
                        target_classification=target_class,
                    ))
                if "challenge" in restriction_text:
                    effects.append(create_challenge_restriction_effect(
                        source_id=source_id,
                        target_mode=target_mode,
                        target_classification=target_class,
                    ))

    return effects


def _parse_target_from_static(effect_obj: object, ability_obj: object) -> tuple[str, str | None]:
    """Parse target specification from a static effect.

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
        if normalized in {"your_items", "any_item"}:
            return ("classification", "item")
        if normalized in {"your_locations", "any_location"}:
            return ("classification", "location")

    if isinstance(alias, dict):
        selector = {**alias, **selector}

    classifications = (
        selector.get("classifications")
        or selector.get("classification")
        or selector.get("cardTypes")
        or selector.get("card_types")
        or ()
    )
    if isinstance(classifications, str):
        classifications = (classifications,)
    if classifications:
        return ("classification", str(tuple(classifications)[0]).lower())

    card_types = selector.get("card_types") or selector.get("cardTypes") or ()
    if isinstance(card_types, str):
        card_types = (card_types,)
    if card_types:
        return ("classification", str(tuple(card_types)[0]).lower())

    controller = selector.get("controller")
    if controller in {"self", "you", "controller"}:
        return ("your_characters", None)
    if controller in {"opponent", "opposing"}:
        return ("opposing_characters", None)

    if selector.get("exclude_self") or selector.get("excludeSelf"):
        return ("your_characters", None)

    return ("self", None)


def register_static_effects_for_card(
    state: GameState,
    instance_id: int,
    card_abilities: tuple,
) -> None:
    """Register all static effects for a card entering play."""
    registry = get_registry(state)
    effects = parse_static_effects_from_card(card_abilities, instance_id)
    for effect in effects:
        registry.register_effect(effect)


def deregister_static_effects_for_card(state: GameState, instance_id: int) -> None:
    """Deregister all static effects from a card leaving play."""
    registry = get_registry(state)
    registry.deregister_effects_from_source(instance_id)


def has_static_effect(state: GameState, instance_id: int, effect_type: StaticEffectType) -> bool:
    """Check if an instance has a specific type of static effect applied."""
    registry = get_registry(state)
    for effect in registry.get_effects_for_instance(state, instance_id):
        if effect.effect_type == effect_type:
            return True
    return False


def get_static_modifier(state: GameState, instance_id: int, stat: str) -> int:
    """Get the total static modifier for a stat."""
    registry = get_registry(state)
    total = 0
    for effect in registry.get_effects_for_instance(state, instance_id):
        if stat == "strength" and effect.effect_type == StaticEffectType.MODIFY_STRENGTH:
            total += effect.amount
        elif stat == "willpower" and effect.effect_type == StaticEffectType.MODIFY_WILLPOWER:
            total += effect.amount
        elif stat == "lore" and effect.effect_type == StaticEffectType.MODIFY_LORE:
            total += effect.amount
    return total