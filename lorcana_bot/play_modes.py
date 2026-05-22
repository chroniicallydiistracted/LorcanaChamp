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

from typing import TYPE_CHECKING, Any

from dataclasses import dataclass

from lorcana_bot.constants import CARD_CHARACTER, EVENT_PUT_CARD_UNDER, ZONE_PLAY, ZONE_UNDER

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
class ShiftDiscardCost:
    """Non-ink shift cost requiring discards."""
    discard_cards: int
    discard_card_type: str | None = None


@dataclass(frozen=True, slots=True)
class ShiftTargetMode:
    """How a shifted character can target cards to shift onto."""
    type: str  # "universal", "classification", or "name"
    classification: str | None = None
    name: str | None = None


@dataclass(frozen=True, slots=True)
class ShiftRules:
    """Lorcanito-aligned Shift rules extracted from card definitions.

    Includes ink/discard costs, target mode, and unsupported reason
    for non-ink shift costs that are not yet implemented.
    """
    ink_cost: int | None = None
    discard_cost: ShiftDiscardCost | None = None
    raw_label: str | None = None
    target_mode: ShiftTargetMode | None = None
    unsupported_reason: str | None = None


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

    rules = get_shift_rules(card)
    if rules is None or rules.unsupported_reason or rules.discard_cost is not None:
        return None
    if rules.ink_cost is not None:
        return rules.ink_cost
    return 1


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


def get_sing_together_threshold(state: GameState, engine: GameEngine, song_card_id: int) -> int | None:
    song = engine.card_def(state, song_card_id)
    if not is_song_card(engine, song_card_id, state):
        return None
    threshold = _parse_sing_together_threshold(tuple(getattr(song, "keywords", ()) or ()))
    if threshold is not None:
        return threshold
    for keyword in getattr(song, "keyword_defs", ()) or ():
        if str(getattr(keyword, "keyword", "")).upper() in {"SINGTOGETHER", "SING_TOGETHER"}:
            value = getattr(keyword, "value", None)
            if value is not None:
                return int(value)
    text = " ".join(str(part) for part in (getattr(song, "text", "") or "", getattr(song, "rules_text", "") or ""))
    import re
    match = re.search(r"\bSing Together\s+(\d+)\b", text, re.IGNORECASE)
    return int(match.group(1)) if match else None


def singer_threshold_for_song(state: GameState, engine: GameEngine, singer_id: int) -> int | None:
    inst = state.cards.get(singer_id)
    if inst is None or inst.zone != "play" or inst.exerted or inst.drying:
        return None
    card = engine.card_def(state, singer_id)
    if card.card_type != CARD_CHARACTER:
        return None
    singer_info = get_singer_info(state, engine, singer_id)
    return max(int(card.cost or 0), singer_info.threshold if singer_info else 0)


def sing_together_groups(state: GameState, engine: GameEngine, player: int, song_card_id: int) -> tuple[tuple[int, ...], ...]:
    threshold = get_sing_together_threshold(state, engine, song_card_id)
    if threshold is None:
        return ()
    ready = []
    for cid in state.players[player].play:
        value = singer_threshold_for_song(state, engine, cid)
        if value is not None and value > 0:
            ready.append((cid, value))
    groups: list[tuple[int, ...]] = []
    from itertools import combinations
    for size in range(1, len(ready) + 1):
        for combo in combinations(ready, size):
            if sum(value for _, value in combo) >= threshold:
                groups.append(tuple(cid for cid, _ in combo))
    return tuple(groups)


def execute_sing_together_song(
    state: GameState,
    engine: GameEngine,
    singer_ids: tuple[int, ...],
    song_card_id: int,
) -> None:
    if not singer_ids:
        raise ValueError("Sing Together requires at least one singer")
    player = state.cards[song_card_id].controller
    legal_groups = sing_together_groups(state, engine, player, song_card_id)
    if singer_ids not in legal_groups:
        raise ValueError("Invalid Sing Together singer group")

    for singer_id in singer_ids:
        engine._exert_eventful(state, singer_id, actor=player, source_id=singer_id, emit_event=False)

    from_zone = state.cards[song_card_id].zone
    engine._move_card_eventful(state, song_card_id, "discard", actor=player)
    engine._resolve_effects(state, player, song_card_id, None)
    engine.emit_event(
        state,
        "CARD_PLAYED",
        actor=player,
        source=song_card_id,
        target=singer_ids[0],
        payload={
            "player_id": player,
            "subject_card_id": song_card_id,
            "card_type": "action",
            "played_from": from_zone,
            "played_to": "discard",
            "sung": True,
            "cost_type": "singTogether",
            "singer_ids": list(singer_ids),
        },
    )


# B12: Shift stack helpers

def is_card_under(state: GameState, card_id: int) -> bool:
    """Check if a card is under another card in a shift stack.

    A card is "under" if it has a stack_parent_id pointing to another card.

    Args:
        state: The game state
        card_id: The card instance ID to check

    Returns:
        True if the card is under another card in a shift stack
    """
    inst = state.cards.get(card_id)
    return inst is not None and inst.stack_parent_id is not None


def is_publicly_in_play(state: GameState, card_id: int) -> bool:
    """Check if a card is publicly visible in the play zone.

    A card is publicly in play if it's in the play zone and not under another card.

    Args:
        state: The game state
        card_id: The card instance ID to check

    Returns:
        True if the card is publicly in the play zone
    """
    inst = state.cards.get(card_id)
    return inst is not None and inst.zone == ZONE_PLAY and inst.stack_parent_id is None


# Lorcanito-aligned shift rules extraction

UNSUPPORTED_SHIFT_COST_TODO = "TODO: Non-ink Shift costs are not supported in playCard yet"

# Classification-based shift name patterns
_SHIFT_LABEL_PATTERN = r'\b(?:([A-Za-z][A-Za-z \-\']+)\s+)?Shift\s+(\d+)\b'
_UNIVERSAL_SHIFT_PATTERNS = [
    r'Universal Shift',
    r'on top of any one of your characters',
    r'on top of any of your characters',
]
_SHIFT_NAME_PATTERNS = [
    r'on top of (?:one of )?your characters named ([^)]+)',
    r'on top of a character named ([^)]+)',
]
_SHIFT_CLASSIFICATION_PATTERN = r'on top of (?:one of )?your ([A-Za-z][A-Za-z \-\']+?) characters'


def _normalize_word(value: str) -> str:
    """Normalize a word for comparison."""
    return value.strip().lower()


def _same_word(left: str, right: str) -> bool:
    """Check if two words are the same (case-insensitive)."""
    return _normalize_word(left) == _normalize_word(right)


def _resolve_shift_target_names(name: str) -> list[str]:
    """Split a shift target name by 'or'/'and' for multiple targets."""
    import re
    return [part.strip() for part in re.split(r'\s+(?:or|and)\s+', name, flags=re.IGNORECASE) if part.strip()]


def _card_name_candidates(card) -> tuple[str, ...]:
    """Return names that can satisfy name-based Shift matching."""
    names: list[str] = []
    for attr in ("name", "full_name", "simple_name"):
        value = getattr(card, attr, None)
        if isinstance(value, str) and value.strip() and value not in names:
            names.append(value.strip())
    return tuple(names)


def _card_classifications(card) -> tuple[str, ...]:
    """Return Lorcanito classifications represented in Python card data."""
    values: list[str] = []
    for value in getattr(card, "subtypes", ()) or ():
        if isinstance(value, str) and value.strip():
            values.append(value.strip())
    raw_source = getattr(card, "raw_lorcanito_source", None)
    if isinstance(raw_source, dict):
        for value in raw_source.get("classifications", ()) or ():
            if isinstance(value, str) and value.strip():
                values.append(value.strip())
    raw = getattr(card, "raw", None)
    if isinstance(raw, dict):
        for value in raw.get("classifications", ()) or ():
            if isinstance(value, str) and value.strip():
                values.append(value.strip())
    return tuple(dict.fromkeys(values))


def _shift_target_matches(rules: ShiftRules, target_card) -> bool:
    """Return whether a target card satisfies Lorcanito Shift target rules."""
    mode = rules.target_mode
    if mode is None:
        return False
    if getattr(target_card, "card_type", None) != CARD_CHARACTER:
        return False
    if mode.type == "universal":
        return True
    if mode.type == "classification":
        if not mode.classification:
            return False
        return any(_same_word(value, mode.classification) for value in _card_classifications(target_card))
    if mode.type == "name":
        if not mode.name:
            return False
        wanted_names = _resolve_shift_target_names(mode.name)
        return any(
            _same_word(candidate, wanted)
            for candidate in _card_name_candidates(target_card)
            for wanted in wanted_names
        )
    return False


def _get_shift_keyword(card) -> dict | None:
    """Get Shift keyword ability from card definition.

    Args:
        card: CardDef to check

    Returns:
        Shift keyword ability dict if found, None otherwise
    """
    for ability in getattr(card, 'abilities', ()):
        if isinstance(ability, dict):
            keyword = ability.get('keyword', '')
            if str(keyword).lower() == 'shift':
                return ability
    return None


def _infer_shift_label(card) -> str | None:
    """Infer Shift label from card text and keywords.

    Args:
        card: CardDef to check

    Returns:
        Shift label text if found, None otherwise
    """
    shift_keyword = _get_shift_keyword(card)
    if shift_keyword and shift_keyword.get('text'):
        return shift_keyword['text']

    # Check card text for Shift patterns - try both 'text' and 'rules_text'
    import re
    card_text = getattr(card, 'text', '') or getattr(card, 'rules_text', '') or ''
    for text in [card_text] if isinstance(card_text, str) else card_text:
        if re.search(_SHIFT_LABEL_PATTERN, text, re.IGNORECASE):
            return text

    # Also check keywords directly
    for keyword in getattr(card, 'keywords', ()):
        upper = str(keyword).upper()
        if 'SHIFT' in upper:
            return keyword  # Return the full keyword as label

    return None


def _parse_shift_mode_from_label(label: str | None) -> ShiftTargetMode | None:
    """Parse shift target mode from a label string.

    Args:
        label: The shift label text

    Returns:
        ShiftTargetMode if parsing succeeds, None otherwise
    """
    if not label:
        return None

    import re
    match = re.match(_SHIFT_LABEL_PATTERN, label, re.IGNORECASE)
    if not match:
        return None

    prefix = match.group(1)
    if not prefix:
        return None

    # Check for Universal Shift
    if _same_word(prefix, "Universal"):
        return ShiftTargetMode(type="universal")

    # Otherwise it's a classification-based shift
    return ShiftTargetMode(type="classification", classification=prefix.strip())


def _parse_shift_name_target_from_text(card) -> str | None:
    """Parse explicit shift name target from card text.

    Args:
        card: CardDef to check

    Returns:
        Target name if found in text, None otherwise
    """
    import re

    card_text = getattr(card, 'text', '') or ''
    rules_text = getattr(card, 'rules_text', '') or ''
    texts = []
    if isinstance(card_text, str) and card_text.strip():
        texts.append(card_text)
    elif not isinstance(card_text, str):
        texts.extend(str(entry) for entry in card_text)
    if isinstance(rules_text, str) and rules_text.strip():
        texts.append(rules_text)

    # Also check shift keyword text
    shift_keyword = _get_shift_keyword(card)
    if shift_keyword and shift_keyword.get('text'):
        texts.append(shift_keyword['text'])

    for text in texts:
        for pattern in _SHIFT_NAME_PATTERNS:
            match = re.search(pattern, text, re.IGNORECASE)
            if match and match.group(1):
                # Strip only a sentence-ending period; names like "Mr. Incredible" keep punctuation.
                return re.sub(r'\.\s*$', '', match.group(1)).strip()

    return None


def _parse_shift_classification_from_text(card) -> str | None:
    """Parse shift classification from card text.

    Args:
        card: CardDef to check

    Returns:
        Classification name if found, None otherwise
    """
    import re

    # Check both 'text' and 'rules_text' fields
    card_text = getattr(card, 'text', '') or ''
    rules_text = getattr(card, 'rules_text', '') or ''
    combined_text = card_text + " " + rules_text

    texts: list[str] = []
    if combined_text.strip():
        texts.append(combined_text)

    # Also check shift keyword text
    shift_keyword = _get_shift_keyword(card)
    if shift_keyword and shift_keyword.get('text'):
        texts.append(shift_keyword['text'])

    for text in texts:
        match = re.search(_SHIFT_CLASSIFICATION_PATTERN, text, re.IGNORECASE)
        if match and match.group(1):
            classification = match.group(1).strip()
            if not _same_word(classification, "any"):
                return classification

    return None


def _parse_universal_shift_from_text(card) -> bool:
    """Check if card has universal shift from text.

    Args:
        card: CardDef to check

    Returns:
        True if card has Universal Shift
    """
    import re

    card_text = getattr(card, 'text', '') or ''
    rules_text = getattr(card, 'rules_text', '') or ''
    texts = []
    if isinstance(card_text, str) and card_text.strip():
        texts.append(card_text)
    elif not isinstance(card_text, str):
        texts.extend(str(entry) for entry in card_text)
    if isinstance(rules_text, str) and rules_text.strip():
        texts.append(rules_text)

    # Also check shift keyword text
    shift_keyword = _get_shift_keyword(card)
    if shift_keyword and shift_keyword.get('text'):
        texts.append(shift_keyword['text'])

    for text in texts:
        for pattern in _UNIVERSAL_SHIFT_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                return True

    return False


def _parse_shift_cost_from_label(label: str | None) -> int | None:
    """Parse shift cost from a label string.

    Args:
        label: The shift label text

    Returns:
        Shift cost if found in label, None otherwise
    """
    if not label:
        return None

    import re
    match = re.search(_SHIFT_LABEL_PATTERN, label, re.IGNORECASE)
    if match and match.group(2):
        return int(match.group(2))

    return None


def _resolve_shift_cost_support(card) -> tuple[int | None, ShiftDiscardCost | None, str | None]:
    """Resolve shift cost support from card definition.

    Args:
        card: CardDef to check

    Returns:
        Tuple of (ink_cost, discard_cost, unsupported_reason)
    """
    shift_keyword = _get_shift_keyword(card)

    if shift_keyword and isinstance(shift_keyword, dict):
        cost_data = shift_keyword.get('cost', {})

        # Check for discard-based shift cost
        if isinstance(cost_data, dict):
            discard_cards = cost_data.get('discardCards')
            if isinstance(discard_cards, int) and discard_cards > 0:
                return (
                    None,
                    ShiftDiscardCost(
                        discard_cards=discard_cards,
                        discard_card_type=cost_data.get('discardCardType'),
                    ),
                    UNSUPPORTED_SHIFT_COST_TODO,
                )

            # Check for unsupported non-ink costs
            non_ink_keys = [k for k in cost_data.keys() if k != 'ink' and cost_data.get(k) is not None]
            if non_ink_keys:
                return None, None, UNSUPPORTED_SHIFT_COST_TODO

            ink = cost_data.get('ink')
            if isinstance(ink, int):
                return ink, None, None

    # Fall back to parsing from label
    label = _infer_shift_label(card)
    return _parse_shift_cost_from_label(label), None, None


def _resolve_shift_target_mode(card) -> ShiftTargetMode:
    """Resolve shift target mode from card definition.

    Args:
        card: CardDef to check

    Returns:
        ShiftTargetMode with resolved target type
    """
    # Check for explicit shiftTarget from keyword data
    shift_keyword = _get_shift_keyword(card)
    if shift_keyword and isinstance(shift_keyword, dict):
        shift_target = shift_keyword.get('shiftTarget')
        if isinstance(shift_target, str) and shift_target.strip():
            return ShiftTargetMode(type="name", name=shift_target.strip())

    label = _infer_shift_label(card)

    # Check label for mode
    mode_from_label = _parse_shift_mode_from_label(label)
    if mode_from_label:
        return mode_from_label

    # Check for universal shift
    if _parse_universal_shift_from_text(card):
        return ShiftTargetMode(type="universal")

    # Check for classification shift
    classification = _parse_shift_classification_from_text(card)
    if classification:
        return ShiftTargetMode(type="classification", classification=classification)

    # Check for name-based shift
    explicit_name = _parse_shift_name_target_from_text(card)
    if explicit_name:
        return ShiftTargetMode(type="name", name=explicit_name)

    # Default to same-name shift
    return ShiftTargetMode(type="name", name=getattr(card, 'full_name', None))


def get_shift_rules(card) -> ShiftRules | None:
    """Extract Lorcanito-aligned Shift rules from a card definition.

    Returns explicit unsupported reason for non-ink Shift costs that
    are not yet implemented.

    Args:
        card: CardDef to check

    Returns:
        ShiftRules if card has Shift keyword, None otherwise
    """
    if card is None:
        return None

    if getattr(card, 'card_type', None) != 'character':
        return None

    # Check if card has shift keyword in keywords tuple
    has_shift = False
    shift_cost_from_keyword = None
    for keyword in getattr(card, 'keywords', ()):
        upper = str(keyword).upper()
        # Look for SHIFT anywhere in the keyword (handles "SHIFT(5)", "Sorcerer SHIFT(4)", "UNIVERSAL SHIFT")
        if 'SHIFT' in upper:
            has_shift = True
            # Parse shift cost from keyword like "SHIFT(5)" or "SHIFT:3" or "Sorcerer SHIFT:4"
            import re
            cost_match = re.search(r'SHIFT[:\(](\d+)', upper)
            if cost_match:
                shift_cost_from_keyword = int(cost_match.group(1))
            break

    shift_keyword = _get_shift_keyword(card)
    if not has_shift and not shift_keyword:
        return None

    label = _infer_shift_label(card)

    ink_cost, discard_cost, unsupported_reason = _resolve_shift_cost_support(card)

    # If ink_cost wasn't found but we have shift_cost_from_keyword, use it
    if ink_cost is None and shift_cost_from_keyword is not None:
        ink_cost = shift_cost_from_keyword

    return ShiftRules(
        ink_cost=ink_cost,
        discard_cost=discard_cost,
        raw_label=label,
        unsupported_reason=unsupported_reason,
        target_mode=_resolve_shift_target_mode(card),
    )


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

    Lorcanito Shift targets may be same-name, classification-based, or universal.
    Only publicly visible controlled characters in play are valid targets.

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

    rules = get_shift_rules(shifted_card)
    if rules is None or rules.unsupported_reason or rules.discard_cost is not None:
        return targets

    player = shifted_inst.controller
    shift_cost = rules.ink_cost if rules.ink_cost is not None else 1

    # Look for matching publicly visible characters in play.
    for target_id in state.players[player].play:
        target_inst = state.cards.get(target_id)
        if target_inst is None or not is_publicly_in_play(state, target_id):
            continue
        target_card = engine.card_def(state, target_id)
        if _shift_target_matches(rules, target_card):
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
    rules = get_shift_rules(shifted_card)
    if rules is None:
        return False, "Shifted card does not have Shift"
    if rules.unsupported_reason:
        return False, rules.unsupported_reason
    if rules.discard_cost is not None:
        return False, UNSUPPORTED_SHIFT_COST_TODO
    shift_cost = rules.ink_cost if rules.ink_cost is not None else 1

    # Check target is in play
    target_inst = state.cards.get(target_character_id)
    if target_inst is None:
        return False, "Target character not found"
    if not is_publicly_in_play(state, target_character_id):
        return False, "Target character must be publicly in play"

    # Check same controller
    if target_inst.controller != shifted_inst.controller:
        return False, "Target must be controlled by the same player"

    # Check Shift target mode.
    target_card = engine.card_def(state, target_character_id)
    if not _shift_target_matches(rules, target_card):
        return False, "Target does not match shift requirement"

    # Check shift cost
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
    shifted_card = engine.card_def(state, shifted_card_id)
    rules = get_shift_rules(shifted_card)
    if rules is None or rules.unsupported_reason or rules.discard_cost is not None:
        raise ValueError("Cannot play shifted: unsupported Shift rules")

    # Get shift cost
    shift_cost = rules.ink_cost if rules.ink_cost is not None else 1

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

    attach_shift_stack(state, engine, shifted_card_id, target_character_id, player)

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


def attach_shift_stack(
    state: GameState,
    engine: GameEngine,
    new_top_id: int,
    old_top_id: int,
    player: int,
) -> list[int]:
    """Attach an existing public character and its stack under a shifted card.

    The shifted target leaves the public play zone, moves to ZONE_UNDER, and
    the new top receives the old top followed by the old top's previous stack.
    """
    new_top_inst = state.cards[new_top_id]
    old_top_inst = state.cards[old_top_id]
    existing_under = list(old_top_inst.cards_under)

    engine._move_card_eventful(
        state,
        old_top_id,
        ZONE_UNDER,
        actor=player,
        controller=player,
        queue_triggers=False,
        include_stack=False,
    )

    stack_ids = [old_top_id] + existing_under
    new_top_inst.cards_under = stack_ids
    new_top_inst.stack_parent_id = None

    for under_id in stack_ids:
        if under_id in state.cards:
            state.cards[under_id].stack_parent_id = new_top_id
            state.cards[under_id].cards_under.clear()

    for under_id in stack_ids:
        if under_id not in state.cards:
            continue
        engine.emit_event(
            state,
            EVENT_PUT_CARD_UNDER,
            actor=player,
            source=under_id,
            target=new_top_id,
            payload={
                "player_id": player,
                "card_id": under_id,
                "subject_card_id": under_id,
                "target_id": new_top_id,
                "trigger_source_card_id": new_top_id,
            },
        )

    # B13: Record put-card-under for turn metadata
    if "cards_put_under_this_turn_by_player" not in state.turn_metadata:
        state.turn_metadata["cards_put_under_this_turn_by_player"] = {}
    player_puts = state.turn_metadata["cards_put_under_this_turn_by_player"]
    player_puts[player] = player_puts.get(player, 0) + len(stack_ids)

    # Record by target card ID
    if "cards_put_under_self_this_turn_by_card" not in state.turn_metadata:
        state.turn_metadata["cards_put_under_self_this_turn_by_card"] = {}
    card_puts = state.turn_metadata["cards_put_under_self_this_turn_by_card"]
    card_puts[new_top_id] = card_puts.get(new_top_id, 0) + len(stack_ids)

    return stack_ids


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


def get_play_zone_cards(state: GameState, player: int) -> list[int]:
    """Get all publicly visible cards in the play zone for a player.

    Cards that are under another card in a shift stack are NOT included
    because they cannot be targeted for normal play actions.

    Args:
        state: The game state
        player: The player index

    Returns:
        List of card instance IDs that are publicly in play
    """
    return [cid for cid in state.players[player].play if is_publicly_in_play(state, cid)]


def is_legal_play_zone_target(state: GameState, card_id: int, player: int) -> bool:
    """Check if a card is a legal target from the play zone.

    Cards under another card in a shift stack are not legal play-zone targets.

    Args:
        state: The game state
        card_id: The card instance ID to check
        player: The player index

    Returns:
        True if the card is publicly in play and can be targeted
    """
    inst = state.cards.get(card_id)
    if inst is None:
        return False
    if inst.zone != ZONE_PLAY:
        return False
    if inst.stack_parent_id is not None:
        return False  # Card is under - not publicly in play
    return inst.owner == player or inst.controller == player
