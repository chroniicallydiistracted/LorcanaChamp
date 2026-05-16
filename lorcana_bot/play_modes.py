"""Play modes for Songs and Shift mechanics.

This module provides the core logic for alternative play modes:
- Songs: Action cards with actionSubtype="song" that can be sung by characters with Singer keyword
- Shift: Characters with Shift keyword that can be played on matching named characters

Lorcana rules:
- Singer X: A character with Singer X can sing songs with cost <= X. Singing exerts the character.
- Sing Together: Allows multiple characters to sing (not implemented - requires multi-character prompts)
- Shift N: A character with Shift N can be played on a character with the same full name by paying N ink instead of the normal cost.
- Shifted cards transfer certain state but not damage or exerted status conservatively.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from lorcana_bot.constants import ZONE_LIMBO, ZONE_PLAY

if TYPE_CHECKING:
    from lorcana_bot.state import GameState
    from lorcana_bot.engine import GameEngine


@dataclass(frozen=True, slots=True)
class ShiftTarget:
    """Represents a valid shift target character."""
    instance_id: int
    card_name: str
    shift_cost: int


@dataclass(frozen=True, slots=True)
class SingerInfo:
    """Information about a Singer character's singing ability."""
    threshold: int  # Maximum song cost the character can sing
    sing_together: bool = False  # Whether this is Sing Together (multi-character)


def get_singer_info(state: GameState, engine: GameEngine, instance_id: int) -> SingerInfo | None:
    """Get Singer info for a character if it has the Singer keyword.
    
    Args:
        state: The game state
        engine: The game engine
        instance_id: The character instance to check
        
    Returns:
        SingerInfo if the character has Singer keyword, None otherwise
    """
    inst = state.cards.get(instance_id)
    if inst is None or inst.zone != "play":
        return None
    
    card = engine.card_def(state, instance_id)
    if card.card_type != "character":
        return None
    
    # Check for Singer keyword with threshold
    singer_threshold = _parse_singer_threshold(card.keywords)
    if singer_threshold is not None:
        return SingerInfo(threshold=singer_threshold, sing_together=False)
    
    # Check for Sing Together keyword with threshold
    sing_together_threshold = _parse_sing_together_threshold(card.keywords)
    if sing_together_threshold is not None:
        return SingerInfo(threshold=sing_together_threshold, sing_together=True)
    
    return None


def _parse_singer_threshold(keywords: tuple[str, ...]) -> int | None:
    """Parse Singer X threshold from keywords.
    
    Args:
        keywords: Card keywords tuple
        
    Returns:
        Singer threshold if found, None otherwise
    """
    for keyword in keywords:
        upper = keyword.upper()
        if upper.startswith("SINGER"):
            # Format: "SINGER" or "SINGER:3" or "SINGER(3)"
            parts = upper.replace("(", ":").replace(")", ":").split(":")
            if len(parts) >= 2 and parts[1].isdigit():
                return int(parts[1])
            return 1  # Singer with no value defaults to 1
    return None


def _parse_sing_together_threshold(keywords: tuple[str, ...]) -> int | None:
    """Parse Sing Together X threshold from keywords.
    
    Args:
        keywords: Card keywords tuple
        
    Returns:
        Sing Together threshold if found, None otherwise
    """
    for keyword in keywords:
        upper = keyword.upper()
        if upper.startswith("SINGTOGETHER") or "SING_TOGETHER" in upper:
            # Format: "SINGTOGETHER" or "SINGTOGETHER:8" or "SING_TOGETHER(8)"
            parts = upper.replace("_", "").replace("(", ":").replace(")", ":").split(":")
            if len(parts) >= 2 and parts[1].isdigit():
                return int(parts[1])
            return 1  # Sing Together with no value defaults to 1
    return None


def get_shift_info(state: GameState, engine: GameEngine, instance_id: int) -> int | None:
    """Get Shift cost for a character if it has the Shift keyword.
    
    Args:
        state: The game state
        engine: The game engine
        instance_id: The character instance to check
        
    Returns:
        Shift cost if the character has Shift keyword, None otherwise
    """
    inst = state.cards.get(instance_id)
    if inst is None:
        return None
    
    card = engine.card_def(state, instance_id)
    if card.card_type != "character":
        return None
    
    # Check for Shift keyword with cost
    for keyword in card.keywords:
        upper = keyword.upper()
        if upper.startswith("SHIFT"):
            # Format: "SHIFT" or "SHIFT:3" or "SHIFT(3)"
            parts = upper.replace("(", ":").replace(")", ":").split(":")
            if len(parts) >= 2 and parts[1].isdigit():
                return int(parts[1])
            return 1  # Shift with no value defaults to 1
    return None


def can_sing_song(
    state: GameState,
    engine: GameEngine,
    singer_instance_id: int,
    song_card_id: int,
) -> tuple[bool, str]:
    """Check if a singer character can sing a song card.
    
    Lorcanito-aligned rules: Singing does NOT pay ink. The singer exerts instead.
    
    Args:
        state: The game state
        engine: The game engine
        singer_instance_id: The singing character's instance ID
        song_card_id: The song card instance ID from hand
        
    Returns:
        Tuple of (can_sing, reason_if_not)
    """
    # Check singer is in play and not exerted
    singer_inst = state.cards.get(singer_instance_id)
    if singer_inst is None:
        return False, "Singer not found"
    if singer_inst.zone != "play":
        return False, "Singer must be in play"
    if singer_inst.exerted:
        return False, "Singer is already exerted"
    if singer_inst.drying:
        return False, "Singer is drying"
    
    # Check singer has Singer keyword
    singer_info = get_singer_info(state, engine, singer_instance_id)
    if singer_info is None:
        return False, "Character does not have Singer ability"
    
    # Check song is in hand
    song_inst = state.cards.get(song_card_id)
    if song_inst is None:
        return False, "Song card not found"
    if song_inst.zone != "hand":
        return False, "Song card must be in hand"
    
    # Check song card definition
    song_card = engine.card_def(state, song_card_id)
    if song_card.card_type != "action":
        return False, "Song card must be an action"
    
    # Check actionSubtype is "song"
    action_subtype = _get_action_subtype(song_card)
    if action_subtype != "song":
        return False, "Card is not a song"
    
    # Check song cost is within singer's threshold (no ink needed)
    song_cost = song_card.cost
    if song_cost > singer_info.threshold:
        return False, f"Song cost {song_cost} exceeds Singer threshold {singer_info.threshold}"
    
    # B11: NO ink requirement for singing — singer exerts instead
    return True, ""


def _get_action_subtype(card) -> str | None:
    """Get actionSubtype from card definition.
    
    Args:
        card: CardDef to check
        
    Returns:
        Action subtype if present, None otherwise
    """
    # Check the direct field first (most reliable)
    if hasattr(card, 'action_subtype') and card.action_subtype is not None:
        return card.action_subtype
    # Check raw_lorcanito_source
    if hasattr(card, 'raw_lorcanito_source') and card.raw_lorcanito_source:
        return card.raw_lorcanito_source.get('actionSubtype')
    # Check raw data
    if hasattr(card, 'raw') and card.raw:
        return card.raw.get('actionSubtype')
    return None


def is_song_card(engine: GameEngine, card_id: int | str, state: GameState | None = None) -> bool:
    """Check if a card definition represents a song.
    
    Args:
        engine: The game engine (to access card database)
        card_id: Card ID (string) or instance ID (int)
        state: Optional game state to resolve instance IDs
        
    Returns:
        True if the card is a song action
    """
    card = None
    
    # If we have state and card_id is an instance ID, use engine.card_def
    if isinstance(card_id, int) and state is not None:
        if card_id in state.cards:
            card = engine.card_def(state, card_id)
        else:
            # Try to find as card ID in database
            try:
                card = engine.db.get(str(card_id))
            except (KeyError, ValueError):
                return False
    elif isinstance(card_id, int):
        # No state provided - try to find as card ID in database
        try:
            card = engine.db.get(str(card_id))
        except (KeyError, ValueError):
            return False
    else:
        card = engine.db.get(card_id)
    
    if card is None:
        return False
    if hasattr(card, 'card_type') and card.card_type == "action":
        action_subtype = _get_action_subtype(card)
        if action_subtype == "song":
            return True
    return False


def get_shift_targets(
    state: GameState,
    engine: GameEngine,
    shifted_card_id: int,
) -> list[ShiftTarget]:
    """Find valid shift targets for a shifted character.
    
    A shifted character can be played on any character with the same full name
    that is in play and belongs to the same player.
    
    Args:
        state: The game state
        engine: The game engine
        shifted_card_id: The shifted character card instance ID from hand
        
    Returns:
        List of valid ShiftTarget instances
    """
    targets: list[ShiftTarget] = []
    
    shifted_inst = state.cards.get(shifted_card_id)
    if shifted_inst is None or shifted_inst.zone != "hand":
        return targets
    
    shifted_card = engine.card_def(state, shifted_card_id)
    if shifted_card.card_type != "character":
        return targets
    
    # Get the target name (the name we need to match)
    shift_name = _get_shift_target_name(shifted_card)
    if shift_name is None:
        return targets
    
    player = shifted_inst.controller
    shift_cost = get_shift_info(state, engine, shifted_card_id) or 1
    
    # Look for matching characters in play
    for target_id in state.players[player].play:
        target_card = engine.card_def(state, target_id)
        # Match by full name
        if target_card.full_name == shift_name:
            targets.append(ShiftTarget(
                instance_id=target_id,
                card_name=target_card.full_name,
                shift_cost=shift_cost,
            ))
    
    return targets


def _get_shift_target_name(card) -> str | None:
    """Get the shift target name from a card.
    
    For characters with Shift N, the target name is their own full name.
    For characters with Shift("Name", N), the target name is "Name".
    
    Args:
        card: CardDef to check
        
    Returns:
        The shift target name if found, None otherwise
    """
    # Check for shift with specific name in keywords
    for keyword in getattr(card, 'keywords', ()):
        upper = keyword.upper()
        # Check for SHIFT with a name before it (like "Genie_SHIFT(2)")
        # or SHIFT with name inside (like "SHIFT(Genie, 2)")
        if upper.startswith("SHIFT(") and "," in upper:
            # Format: SHIFT("Name", N) or SHIFT(Name, N)
            inner = upper.split("(", 1)[1].split(")")[0]
            parts = inner.split(",")
            if len(parts) >= 1:
                name = parts[0].strip().strip('"').strip("'")
                if name and name.upper() != "NAME":
                    return name
        elif "_SHIFT" in upper and "," in upper:
            # Format: Name,SHIFT:3 or similar
            parts = upper.split(",")
            name = parts[0].strip().strip('"').strip("'")
            if name and name.upper() != "SHIFT":
                return name
    
    # Default: shift onto character with the same full name
    return getattr(card, 'full_name', None)


def can_play_as_shift(
    state: GameState,
    engine: GameEngine,
    shifted_card_id: int,
    target_character_id: int,
) -> tuple[bool, str]:
    """Check if a shifted character can be played on a target.
    
    Args:
        state: The game state
        engine: The game engine
        shifted_card_id: The shifted character card instance ID from hand
        target_character_id: The target character instance ID in play
        
    Returns:
        Tuple of (can_play, reason_if_not)
    """
    # Check shifted card is in hand
    shifted_inst = state.cards.get(shifted_card_id)
    if shifted_inst is None:
        return False, "Shifted card not found"
    if shifted_inst.zone != "hand":
        return False, "Shifted card must be in hand"
    
    shifted_card = engine.card_def(state, shifted_card_id)
    if shifted_card.card_type != "character":
        return False, "Shifted card must be a character"
    
    # Check target is in play
    target_inst = state.cards.get(target_character_id)
    if target_inst is None:
        return False, "Target character not found"
    if target_inst.zone != "play":
        return False, "Target character must be in play"
    
    # Check same controller
    if target_inst.controller != shifted_inst.controller:
        return False, "Target must be controlled by the same player"
    
    # Check names match
    target_name = _get_shift_target_name(shifted_card)
    target_card = engine.card_def(state, target_character_id)
    if target_card.full_name != target_name:
        return False, f"Target name '{target_card.full_name}' does not match shift requirement '{target_name}'"
    
    # Check shift cost
    shift_cost = get_shift_info(state, engine, shifted_card_id) or 1
    player = shifted_inst.controller
    if engine.available_ink(state, player) < shift_cost:
        return False, f"Not enough ink to pay shift cost {shift_cost}"
    
    return True, ""


def execute_sing_song(
    state: GameState,
    engine: GameEngine,
    singer_id: int,
    song_card_id: int,
) -> None:
    """Execute singing a song.
    
    Lorcanito-aligned: Singing does NOT pay ink. The singer exerts instead.
    
    This performs the song singing action:
    1. Exert the singer character (no ink payment)
    2. Move the song to discard
    3. Resolve song effects
    4. Emit CARD_PLAYED event with sung=True, cost_type="sing"
    
    Args:
        state: The game state
        engine: The game engine
        singer_id: The singing character's instance ID
        song_card_id: The song card instance ID from hand
        
    Raises:
        ValueError: If the action cannot be performed
    """
    can_sing, reason = can_sing_song(state, engine, singer_id, song_card_id)
    if not can_sing:
        raise ValueError(f"Cannot sing song: {reason}")
    
    player = state.cards[singer_id].controller
    
    # B11: Singer exerts — NO ink payment for singing
    # Use engine helper for exert to enable proper trigger buffering
    engine._exert_eventful(state, singer_id, actor=player, source_id=singer_id, emit_event=False)

    # Store pre-move state for event
    from_zone = state.cards[song_card_id].zone

    # Move song to discard via engine helper
    engine._move_card_eventful(state, song_card_id, "discard", actor=player)
    
    # Resolve song effects
    engine._resolve_effects(state, player, song_card_id, None)
    
    # Emit CARD_PLAYED with sung=True and cost_type="sing"
    engine.emit_event(
        state,
        "CARD_PLAYED",
        actor=player,
        source=song_card_id,
        target=singer_id,
        payload={
            "player_id": player,
            "subject_card_id": song_card_id,
            "card_type": "action",
            "played_from": from_zone,
            "played_to": "discard",
            "sung": True,
            "cost_type": "sing",
            "singer_id": singer_id,
            "singer_card_id": state.cards[singer_id].card_id,
        },
    )


def execute_shift_play(
    state: GameState,
    engine: GameEngine,
    shifted_card_id: int,
    target_character_id: int,
) -> None:
    """Execute playing a shifted character on a target.
    
    Lorcanito-aligned: The target character goes UNDER the shifted card (shift stack),
    NOT to discard. The shifted card is placed in play on top of the stack.
    
    This performs the shift play action:
    1. Pay shift cost
    2. Move shifted card to play
    3. Attach target under shifted card (cards_under / stack_parent_id)
    4. Mark shifted card played_via_shift=True, played_cost_type="shift"
    5. Emit CARD_PLAYED event with used_shift=True
    
    Args:
        state: The game state
        engine: The game engine
        shifted_card_id: The shifted character card instance ID from hand
        target_character_id: The target character instance ID in play
        
    Raises:
        ValueError: If the action cannot be performed
    """
    can_play, reason = can_play_as_shift(state, engine, shifted_card_id, target_character_id)
    if not can_play:
        raise ValueError(f"Cannot play shifted: {reason}")
    
    player = state.cards[shifted_card_id].controller
    
    # Get shift cost
    shift_cost = get_shift_info(state, engine, shifted_card_id) or 1
    
    # Pay shift cost
    engine._pay_ink(state, player, shift_cost)
    
    # Store pre-move state
    from_zone = state.cards[shifted_card_id].zone
    target_def = engine.card_def(state, target_character_id)
    
    # B12: Move shifted card to play via engine helper
    engine._move_card_eventful(state, shifted_card_id, ZONE_PLAY, actor=player)
    
    # Set conservative state for shifted card
    inst = state.cards[shifted_card_id]
    engine._ready_eventful(state, shifted_card_id, actor=player, source_id=shifted_card_id, emit_event=False)
    if inst.damage:
        engine._remove_damage_eventful(state, shifted_card_id, inst.damage, actor=player, source_id=shifted_card_id)
    inst.drying = False
    inst.just_played = True
    inst.location_instance_id = None
    # B12: Mark as played via shift
    inst.played_via_shift = True
    inst.played_cost_type = "shift"
    
    # B12: Attach target UNDER shifted card — NOT to discard
    target_inst = state.cards[target_character_id]
    
    # Preserve any existing cards_under chain from target
    existing_under = list(target_inst.cards_under)

    # Shift targets leave the public play area while remaining associated under the new top.
    engine._move_card_eventful(
        state,
        target_character_id,
        ZONE_LIMBO,
        actor=player,
        controller=player,
        queue_triggers=False,
        include_stack=False,
    )
    
    # Link target and any existing stack into shifted card's cards_under.
    inst.cards_under = [target_character_id] + existing_under
    
    # Link each card in the stack to the new top card.
    for under_id in inst.cards_under:
        if under_id in state.cards:
            state.cards[under_id].stack_parent_id = shifted_card_id
            state.cards[under_id].cards_under.clear()
    
    # Mark target's stack_parent
    target_inst.stack_parent_id = shifted_card_id
    
    # Emit CARD_PLAYED with used_shift=True
    engine.emit_event(
        state,
        "CARD_PLAYED",
        actor=player,
        source=shifted_card_id,
        target=target_character_id,
        payload={
            "player_id": player,
            "subject_card_id": shifted_card_id,
            "card_type": "character",
            "played_from": from_zone,
            "played_to": "play",
            "used_shift": True,
            "shift_cost": shift_cost,
            "shift_target_id": target_character_id,
            "shift_target_name": target_def.full_name,
            "cost_type": "shift",
        },
    )


def get_stacked_card_ids(state: GameState, top_id: int) -> list[int]:
    """Get all card instance IDs in the shift stack under a given top card.
    
    Args:
        state: The game state
        top_id: The instance ID of the top card in the shift stack
        
    Returns:
        List of all card IDs in the stack (top first, then cards_under chain)
    """
    inst = state.cards.get(top_id)
    if inst is None:
        return []
    return [top_id, *[cid for cid in inst.cards_under if cid in state.cards]]


def move_card_out_of_play_with_stack(
    state: GameState,
    engine: GameEngine,
    top_id: int,
    destination: str,
    controller: int | None = None,
) -> None:
    """Move a shifted card and its entire stack to a destination.
    
    B12: When a shifted top card leaves play, all cards_under move with it.
    
    Args:
        state: The game state
        top_id: The instance ID of the top card in the shift stack
        destination: The destination zone
        controller: Optional new controller
    """
    # Get all cards in the stack
    stack_ids = get_stacked_card_ids(state, top_id)
    
    for cid in stack_ids:
        engine._move_card_eventful(
            state,
            cid,
            destination,
            controller=controller,
            include_stack=False,
            queue_triggers=False,
        )
    for cid in stack_ids:
        if cid in state.cards:
            state.cards[cid].cards_under.clear()
            state.cards[cid].stack_parent_id = None
            state.cards[cid].played_via_shift = False
            state.cards[cid].played_cost_type = None
