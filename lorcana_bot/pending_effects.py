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
    from lorcana_bot.engine import GameEngine
    from lorcana_bot.state import GameState
    from lorcana_bot.targeting import TargetDescriptor, TargetCandidate, TargetQueryContext


def _emit_pending_event(
    state: GameState,
    engine: GameEngine | None,
    event_type: str,
    *,
    actor: int | None = None,
    source: int | None = None,
    target: int | None = None,
    payload: dict[str, Any] | None = None,
) -> None:
    """Emit a pending-system diagnostic event without buffering gameplay triggers."""
    if engine is not None:
        engine.emit_event(
            state,
            event_type,
            actor=actor,
            source=source,
            target=target,
            payload=payload or {},
            queue_triggers=False,
        )
        return

    from lorcana_bot.state import GameEvent

    state.event_log.append(GameEvent(
        event_type=event_type,
        actor=actor,
        source=source,
        target=target,
        payload=payload or {},
    ))


def _move_pending_card(
    state: GameState,
    engine: GameEngine | None,
    card_id: int,
    destination: str,
    *,
    actor: int | None = None,
    source_id: int | None = None,
) -> None:
    """Move a card chosen by a pending requirement through the engine when available."""
    if engine is None:
        raise ValueError("Pending card movement requires a GameEngine")
    engine._move_card_eventful(
        state,
        card_id,
        destination,
        actor=actor,
        source_id=source_id,
        queue_triggers=False,
    )


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


# B5.1: Explicit pending requirement kinds for scry/search/reveal/routing

PENDING_REQUIREMENT_KINDS = frozenset({
    "choice",
    "optional",
    "named_card",
    "amount",
    "target",
    "multi_target",
    "discard_choice",
    "destination",
    "ordering",
    "opponent_choice",
    "enter_play_exerted",
    "scry_ordering",
    "reveal_routing",
    "search_selection",
    "deck_ordering",
})

SPECIAL_PENDING_REQUIREMENT_KINDS = frozenset({
    # Microfix 4 special requirements
    "scry_ordering",
    "search_selection",
    "reveal_routing",
    "named_card",
    "destination",
    # Microfix 9 general pending requirement kinds
    "amount",
    "target",
    "multi_target",
    "discard_choice",
    "choice",
    "optional",
    "opponent_choice",
    "enter_play_exerted",
})


@dataclass(slots=True)
class ScryRequirement:
    """Describes a scry ordering requirement.

    For scry N:
    - Look at top N cards of chooser's deck
    - Put any subset on top in chosen order
    - Put rest on bottom in chosen order
    - Private to chooser only
    """
    kind: str = "scry_ordering"
    amount: int = 1  # How many cards to scry
    candidate_ids: tuple[int, ...] = ()  # Top N card instance IDs (private)
    min_top: int = 0  # Minimum cards to put on top
    max_top: int | None = None  # Maximum cards to put on top (None = all)
    min_bottom: int = 0  # Minimum cards to put on bottom
    visibility: str = "private"  # "private" (chooser only) or "public"
    chooser_id: int = 0  # Who is scrying
    deck_owner: int = 0  # Whose deck is being scried

    @property
    def requires_input(self) -> bool:
        """Scry requires player to decide ordering."""
        return True


@dataclass(slots=True)
class SearchRequirement:
    """Describes a search deck selection requirement.

    For search:
    - Look at cards matching filter in hidden deck
    - Select one/more cards
    - Move to destination
    - Optional shuffle after
    """
    kind: str = "search_selection"
    candidate_ids: tuple[int, ...] = ()  # Card IDs matching filter (private to chooser)
    min_select: int = 1  # Minimum cards to select
    max_select: int = 1  # Maximum cards to select
    destination: str = "hand"  # "hand", "play", "discard", "inkwell", etc.
    reveal_policy: str = "private"  # "private" (chooser sees candidates) or "public" (all see candidates)
    shuffle_after: bool = True  # Shuffle deck after search
    filter_desc: str | None = None  # Human-readable description of filter
    chooser_id: int = 0  # Who searches
    deck_owner: int = 0  # Whose deck is searched

    @property
    def requires_input(self) -> bool:
        """Search requires player to select card(s)."""
        return len(self.candidate_ids) > self.max_select or self.max_select > 1


@dataclass(slots=True)
class RevealRoutingRequirement:
    """Describes a reveal and route requirement.

    For reveal-and-route:
    - Reveal top card(s) from deck
    - Move to destination or create pending destination choice
    """
    kind: str = "reveal_routing"
    card_ids: tuple[int, ...] = ()  # Card IDs being revealed
    reveal_policy: str = "public"  # "public" or "private"
    destination: str | None = None  # Fixed destination if deterministic, None if choice required
    destination_options: tuple[str, ...] = ()  # Available destinations if choice required
    chooser_id: int = 0  # Who makes routing choice

    @property
    def requires_input(self) -> bool:
        """Routing requires input if destination is not fixed."""
        return self.destination is None and len(self.destination_options) > 1


@dataclass(slots=True)
class DeckOrderingRequirement:
    """Describes a general deck ordering requirement."""
    kind: str = "deck_ordering"
    card_ids: tuple[int, ...] = ()  # Cards to order (private to chooser)
    min_order: int = 0  # Minimum cards to reorder
    max_order: int | None = None  # Maximum cards to reorder
    visibility: str = "private"
    chooser_id: int = 0
    deck_owner: int = 0

    @property
    def requires_input(self) -> bool:
        return len(self.card_ids) > 1


@dataclass(slots=True)
class NamedCardRequirement:
    """Describes a name-a-card requirement."""
    kind: str = "named_card"
    valid_card_def_ids: tuple[str, ...] = ()  # Valid card definition IDs to name
    chooser_id: int = 0

    @property
    def requires_input(self) -> bool:
        return len(self.valid_card_def_ids) > 1


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
    selected_targets: tuple[int, ...] = ()  # Player's selected target instance IDs (card IDs only)
    selected_player_targets: tuple[int, ...] = ()  # Player's selected player IDs (separate from card targets)
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

    # Build raw dict with requirement_kind if not provided
    final_raw = dict(raw) if raw is not None else {}
    if "requirement_kind" not in final_raw and optional:
        final_raw["requirement_kind"] = "optional"

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
        raw=final_raw,
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
        if pe.accepted is not None:
            continue  # Already resolved/declined
        if is_pending_effect_resolvable(pe):
            return pe
        # Normal case: needs resolution if not complete
        if not pe.is_complete:
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

    Delegates to the targeting service (TargetDescriptor/TargetCandidate)
    when an engine is available and the requirement kind maps to a known
    selector.  Falls back to the legacy manual board scan when the engine
    is None or the requirement kind is not mappable.

    Returns a backward-compatible ``list[int]`` of card instance IDs.
    """
    # Try targeting service first when engine is available.
    # If the requirement maps to a known targeting descriptor, service failures
    # should surface instead of falling back to a broad manual scan.
    if engine is not None:
        desc = target_descriptor_from_requirement(requirement)
        if desc is not None:
            from lorcana_bot.targeting import (
                TargetQueryContext,
                apply_target_protections,
                resolve_candidate_targets,
            )
            context = TargetQueryContext(actor=chooser_id, source_id=None)
            raw_candidates = resolve_candidate_targets(state, engine, desc, context)
            protected = apply_target_protections(state, engine, raw_candidates, desc, context)
            return [c.id for c in protected if c.kind == "card"]

    # Legacy fallback: manual board scan (no engine or unmappable kind)
    from lorcana_bot.constants import KEYWORD_WARD, ZONE_PLAY

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


def get_next_pending_effect_chooser(state: GameState) -> int | None:
    """Get the player ID who should act on the next pending effect.

    Returns the chooser_id of the first incomplete pending effect,
    or None if there are no pending effects.
    """
    for pe in state.pending_effects:
        if pe.accepted is not None:
            continue
        if is_pending_effect_resolvable(pe) or not pe.is_complete:
            return pe.chooser_id
    return None


def get_incomplete_pending_effects(state: GameState) -> list[PendingEffect]:
    """Get all incomplete pending effects."""
    return [
        pe
        for pe in state.pending_effects
        if pe.accepted is None and (is_pending_effect_resolvable(pe) or not pe.is_complete)
    ]


def is_pending_effect_resolvable(pe: PendingEffect) -> bool:
    """Return whether a pending effect has a special resolver path.

    Special pending requirement effects carry their behavior in raw metadata and
    typically have no EffectDef entries, so PendingEffect.is_complete is not a
    reliable signal for them.
    """
    return (pe.raw or {}).get("requirement_kind") in SPECIAL_PENDING_REQUIREMENT_KINDS


# B5.1: Create functions for scry/search/reveal pending requirements

def create_scry_pending_effect(
    state: GameState,
    controller_id: int,
    chooser_id: int,
    source_id: int | None,
    source_card_id: str | None,
    amount: int,
    *,
    origin: str = "scry",
) -> PendingEffect:
    """Create a scry pending effect with proper requirement tracking.

    This stores the top N card IDs privately for the chooser to order.
    Cards are NOT moved until resolution provides the ordering.

    Args:
        state: Game state
        controller_id: Who controls the effect
        chooser_id: Who makes the scry decision
        source_id: Card instance triggering scry
        source_card_id: Card definition ID
        amount: How many cards to scry
        origin: Origin string for tracking

    Returns:
        PendingEffect with ScryRequirement in raw
    """
    # Get top N cards from chooser's deck (private info)
    deck_owner = chooser_id
    deck = state.players[deck_owner].deck
    candidate_ids = tuple(deck[:min(amount, len(deck))])

    scry_req = ScryRequirement(
        kind="scry_ordering",
        amount=amount,
        candidate_ids=candidate_ids,
        min_top=0,
        max_top=amount,
        min_bottom=0,
        visibility="private",
        chooser_id=chooser_id,
        deck_owner=deck_owner,
    )

    # Create the pending effect with empty effects (resolved via scry_req)
    pending_id = f"pe_{state.next_bag_id()}"

    pending = PendingEffect(
        id=pending_id,
        controller_id=controller_id,
        chooser_id=chooser_id,
        source_id=source_id,
        source_card_id=source_card_id,
        effects=(),  # No effects - resolved via raw requirement
        required_targets=(),
        choice_options=(),
        optional=False,
        origin=origin,
        origin_id=None,
        raw={
            "requirement": scry_req,
            "requirement_kind": "scry_ordering",
        },
    )

    state.pending_effects.append(pending)
    return pending


def create_search_pending_effect(
    state: GameState,
    controller_id: int,
    chooser_id: int,
    source_id: int | None,
    source_card_id: str | None,
    candidate_ids: tuple[int, ...],
    destination: str = "hand",
    shuffle_after: bool = True,
    filter_desc: str | None = None,
    max_select: int = 1,
    *,
    origin: str = "search_deck",
) -> PendingEffect:
    """Create a search pending effect with proper requirement tracking.

    Candidate IDs are private to the chooser - opponent should not see them.

    Args:
        state: Game state
        controller_id: Who controls the effect
        chooser_id: Who makes the search selection (deck owner)
        source_id: Card instance triggering search
        source_card_id: Card definition ID
        candidate_ids: Card instance IDs matching search filter
        destination: Where selected card goes
        shuffle_after: Whether to shuffle after search
        filter_desc: Human-readable filter description
        max_select: Maximum cards to select
        origin: Origin string for tracking

    Returns:
        PendingEffect with SearchRequirement in raw
    """
    search_req = SearchRequirement(
        kind="search_selection",
        candidate_ids=candidate_ids,
        min_select=1,
        max_select=max_select,
        destination=destination,
        reveal_policy="private",  # Candidates hidden from opponent
        shuffle_after=shuffle_after,
        filter_desc=filter_desc,
        chooser_id=chooser_id,
        deck_owner=chooser_id,
    )

    pending_id = f"pe_{state.next_bag_id()}"

    pending = PendingEffect(
        id=pending_id,
        controller_id=controller_id,
        chooser_id=chooser_id,
        source_id=source_id,
        source_card_id=source_card_id,
        effects=(),
        required_targets=(),
        choice_options=candidate_ids,  # Available card IDs (private)
        optional=False,
        origin=origin,
        origin_id=None,
        raw={
            "requirement": search_req,
            "requirement_kind": "search_selection",
        },
    )

    state.pending_effects.append(pending)
    return pending


def create_reveal_routing_pending_effect(
    state: GameState,
    controller_id: int,
    chooser_id: int,
    source_id: int | None,
    source_card_id: str | None,
    card_ids: tuple[int, ...],
    destination: str | None = None,
    destination_options: tuple[str, ...] = (),
    reveal_policy: str = "public",
    *,
    origin: str = "reveal_and_route",
) -> PendingEffect:
    """Create a reveal-and-route pending effect with explicit routing.

    If destination is fixed, can auto-route. If destination is None,
    creates a pending choice.

    Args:
        state: Game state
        controller_id: Who controls the effect
        chooser_id: Who makes routing choice
        source_id: Card instance triggering reveal
        source_card_id: Card definition ID
        card_ids: Card IDs being revealed
        destination: Fixed destination or None for choice
        destination_options: Available destinations if choice required
        reveal_policy: "public" or "private"
        origin: Origin string for tracking

    Returns:
        PendingEffect with RevealRoutingRequirement in raw
    """
    routing_req = RevealRoutingRequirement(
        kind="reveal_routing",
        card_ids=card_ids,
        reveal_policy=reveal_policy,
        destination=destination,
        destination_options=destination_options,
        chooser_id=chooser_id,
    )

    pending_id = f"pe_{state.next_bag_id()}"

    pending = PendingEffect(
        id=pending_id,
        controller_id=controller_id,
        chooser_id=chooser_id,
        source_id=source_id,
        source_card_id=source_card_id,
        effects=(),
        required_targets=(),
        choice_options=destination_options if destination is None else (),
        optional=False,
        origin=origin,
        origin_id=None,
        raw={
            "requirement": routing_req,
            "requirement_kind": "reveal_routing",
        },
    )

    state.pending_effects.append(pending)
    return pending


def create_named_card_pending_effect(
    state: GameState,
    controller_id: int,
    chooser_id: int,
    source_id: int | None,
    source_card_id: str | None,
    valid_card_def_ids: tuple[str, ...] = (),
    *,
    origin: str = "name_a_card",
) -> PendingEffect:
    """Create a name-a-card pending effect with explicit requirement tracking."""
    named_req = NamedCardRequirement(
        kind="named_card",
        valid_card_def_ids=valid_card_def_ids,
        chooser_id=chooser_id,
    )

    pending_id = f"pe_{state.next_bag_id()}"
    pending = PendingEffect(
        id=pending_id,
        controller_id=controller_id,
        chooser_id=chooser_id,
        source_id=source_id,
        source_card_id=source_card_id,
        effects=(),
        required_targets=(),
        choice_options=valid_card_def_ids,
        optional=False,
        origin=origin,
        origin_id=None,
        raw={
            "requirement": named_req,
            "requirement_kind": "named_card",
        },
    )

    state.pending_effects.append(pending)
    return pending


def create_discard_choice_pending_effect(
    state: GameState,
    *,
    controller_id: int,
    chooser_id: int,
    source_id: int | None,
    source_card_id: str | None,
    target_player_id: int,
    candidate_ids: tuple[int, ...],
    min_select: int,
    max_select: int,
    origin: str = "discard_choice",
    origin_id: str | None = None,
    raw: dict[str, Any] | None = None,
) -> PendingEffect:
    """Create a discard-choice pending effect for explicit card selection.

    This creates a pending effect that requires the chooser to select cards
    from a target player's hand for discard. The selection is validated and
    then applied through GameEngine._discard_eventful.

    Args:
        state: Game state
        controller_id: Who controls the effect (effect's actor)
        chooser_id: Who makes the discard selection
        source_id: Card instance triggering discard
        source_card_id: Card definition ID
        target_player_id: Whose hand to discard from
        candidate_ids: Card instance IDs available for discard
        min_select: Minimum cards to select
        max_select: Maximum cards to select
        origin: Origin string for tracking
        origin_id: ID of originating ability/bag item
        raw: Additional raw metadata

    Returns:
        PendingEffect with discard_choice requirement_kind
    """
    pending_id = f"pe_{state.next_bag_id()}"

    # Build raw metadata for discard choice
    final_raw = dict(raw) if raw is not None else {}
    final_raw.update({
        "requirement_kind": "discard_choice",
        "discard_candidates": candidate_ids,
        "min_discard": min_select,
        "max_discard": max_select,
        "target_player_id": target_player_id,
        "candidate_ids": candidate_ids,  # Also store as candidate_ids for compatibility
        "min_targets": min_select,
        "max_targets": max_select,
    })

    pending = PendingEffect(
        id=pending_id,
        controller_id=controller_id,
        chooser_id=chooser_id,
        source_id=source_id,
        source_card_id=source_card_id,
        effects=(),  # No effects - resolved via discard_card_ids
        required_targets=(),
        choice_options=candidate_ids,  # Available card IDs for discard
        optional=False,
        origin=origin,
        origin_id=origin_id,
        raw=final_raw,
    )

    state.pending_effects.append(pending)
    return pending


def resolve_scry_ordering(
    state: GameState,
    pending_id: str,
    top_cards: tuple[int, ...],
    bottom_cards: tuple[int, ...],
    *,
    engine: GameEngine | None = None,
) -> None:
    """Resolve a scry pending effect with ordering.

    Args:
        state: Game state
        pending_id: Pending effect ID
        top_cards: Card IDs to put on top (in order)
        bottom_cards: Card IDs to put on bottom (in order)

    Raises:
        ValueError: If card IDs are not valid scry candidates or counts don't match
    """
    pe = get_pending_effect_by_id(state, pending_id)
    if pe is None:
        raise ValueError(f"Pending effect {pending_id} not found")

    req = pe.raw.get("requirement")
    if not isinstance(req, ScryRequirement):
        raise ValueError(f"Pending effect {pending_id} is not a scry")

    # Validate: top + bottom must equal the number of cards actually seen
    expected_count = len(req.candidate_ids)
    if len(top_cards) + len(bottom_cards) != expected_count:
        raise ValueError(
            f"Scry ordering count mismatch: expected {expected_count}, "
            f"got {len(top_cards)} top + {len(bottom_cards)} bottom"
        )

    # Validate all cards are valid candidates and each candidate appears once
    all_ordered = top_cards + bottom_cards
    for cid in all_ordered:
        if cid not in req.candidate_ids:
            raise ValueError(f"Card {cid} is not a valid scry candidate")
    if len(set(all_ordered)) != len(all_ordered):
        raise ValueError("Scry ordering cannot include duplicate cards")
    if set(all_ordered) != set(req.candidate_ids):
        raise ValueError("Scry ordering must include each scry candidate exactly once")

    # Apply ordering: rebuild deck with new order
    player_deck = state.players[req.deck_owner].deck

    # Remove all scried cards from deck
    for cid in req.candidate_ids:
        if cid in player_deck:
            player_deck.remove(cid)

    # Put top cards on top (in order)
    player_deck[0:0] = list(top_cards)

    # Put bottom cards on bottom (in order)
    player_deck.extend(list(bottom_cards))

    # Emit private scry event with no identity leak.
    _emit_pending_event(
        state,
        engine,
        "SCRY_RESOLVED",
        actor=req.chooser_id,
        source=req.deck_owner,
        target=None,
        payload={
            "count": req.amount,
            "top_count": len(top_cards),
            "bottom_count": len(bottom_cards),
            "private": True,  # Card identities not in public log
        },
    )


def resolve_search_selection(
    state: GameState,
    pending_id: str,
    selected_card_id: int,
    *,
    engine: GameEngine | None = None,
) -> None:
    """Resolve a search pending effect with card selection.

    Args:
        state: Game state
        pending_id: Pending effect ID
        selected_card_id: Card ID selected from deck

    Raises:
        ValueError: If card is not a valid search candidate
    """
    pe = get_pending_effect_by_id(state, pending_id)
    if pe is None:
        raise ValueError(f"Pending effect {pending_id} not found")

    req = pe.raw.get("requirement")
    if not isinstance(req, SearchRequirement):
        raise ValueError(f"Pending effect {pending_id} is not a search")

    # Validate selection
    if selected_card_id not in req.candidate_ids:
        raise ValueError(f"Card {selected_card_id} is not a valid search candidate")

    # Move card to destination through the engine event boundary when available.
    _move_pending_card(
        state,
        engine,
        selected_card_id,
        req.destination,
        actor=req.chooser_id,
        source_id=pe.source_id,
    )

    # Shuffle if required
    if req.shuffle_after:
        import random
        state.shuffle_counter += 1
        rng = random.Random(f"{state.seed}:search_shuffle:{req.deck_owner}:{state.shuffle_counter}")
        rng.shuffle(state.players[req.deck_owner].deck)

    # Emit private search event without leaking hidden filter details.
    _emit_pending_event(
        state,
        engine,
        "SEARCH_RESOLVED",
        actor=req.chooser_id,
        source=selected_card_id,
        target=None,
        payload={
            "destination": req.destination,
            "shuffled": req.shuffle_after,
            "private": True,  # Filter not revealed to opponent
        },
    )


def resolve_reveal_routing(
    state: GameState,
    pending_id: str,
    destination: str | None = None,
    *,
    engine: GameEngine | None = None,
) -> None:
    """Resolve a reveal routing pending effect.

    Args:
        state: Game state
        pending_id: Pending effect ID
        destination: Chosen destination if not fixed

    Raises:
        ValueError: If destination is required but not provided
    """
    pe = get_pending_effect_by_id(state, pending_id)
    if pe is None:
        raise ValueError(f"Pending effect {pending_id} not found")

    req = pe.raw.get("requirement")
    if not isinstance(req, RevealRoutingRequirement):
        raise ValueError(f"Pending effect {pending_id} is not a reveal routing")

    # Determine final destination
    final_dest = destination if destination else req.destination
    if final_dest is None:
        raise ValueError("Destination required but not provided")
    if req.destination is not None and final_dest != req.destination:
        raise ValueError(f"Destination {final_dest!r} does not match fixed destination {req.destination!r}")
    if req.destination is None and req.destination_options and final_dest not in req.destination_options:
        raise ValueError(f"Destination {final_dest!r} is not valid for pending effect {pending_id}")

    # Reveal and move cards
    for cid in req.card_ids:
        # Mark as revealed
        state.cards[cid].revealed = True

        # Emit reveal event through the engine diagnostic boundary when available.
        _emit_pending_event(
            state,
            engine,
            "CARD_REVEALED",
            actor=req.chooser_id,
            source=cid,
            target=None,
            payload={
                "card_id": cid,
                "card_def_id": state.cards[cid].card_id,
                "reveal_policy": req.reveal_policy,
            },
        )

        # Move to destination
        _move_pending_card(
            state,
            engine,
            cid,
            final_dest,
            actor=req.chooser_id,
            source_id=pe.source_id,
        )


def resolve_named_card(
    state: GameState,
    pending_id: str,
    named_card: str,
    *,
    engine: GameEngine | None = None,
) -> None:
    """Resolve a pending name-a-card requirement."""
    pe = get_pending_effect_by_id(state, pending_id)
    if pe is None:
        raise ValueError(f"Pending effect {pending_id} not found")

    requirement_kind = pe.raw.get("requirement_kind")
    req = pe.raw.get("requirement")
    if requirement_kind != "named_card" and not isinstance(req, NamedCardRequirement):
        raise ValueError(f"Pending effect {pending_id} is not a named-card requirement")

    if isinstance(req, NamedCardRequirement) and req.valid_card_def_ids:
        if named_card not in req.valid_card_def_ids:
            raise ValueError(f"Named card {named_card!r} is not valid for pending effect {pending_id}")

    pe.raw["named_card"] = named_card
    pe.raw.setdefault("resolution_input", {})["named_card"] = named_card
    _emit_pending_event(
        state,
        engine,
        "NAMED_CARD_CHOSEN",
        actor=pe.chooser_id,
        source=pe.source_id,
        target=None,
        payload={
            "pending_effect_id": pending_id,
            "named_card": named_card,
        },
    )


def resolve_destination_choice(
    state: GameState,
    pending_id: str,
    destination: str,
    *,
    engine: GameEngine | None = None,
) -> None:
    """Resolve a generic destination-choice pending requirement.

    This records the chosen destination. Movement is performed by the effect
    that consumes the pending resolution input unless a more specific helper
    such as resolve_reveal_routing handles movement directly.
    """
    pe = get_pending_effect_by_id(state, pending_id)
    if pe is None:
        raise ValueError(f"Pending effect {pending_id} not found")

    requirement_kind = pe.raw.get("requirement_kind")
    req = pe.raw.get("requirement")
    if requirement_kind != "destination":
        raise ValueError(f"Pending effect {pending_id} is not a destination requirement")

    options = (
        pe.raw.get("destination_options")
        or getattr(req, "destination_options", None)
        or getattr(req, "options", None)
        or ()
    )
    if options and destination not in tuple(options):
        raise ValueError(f"Destination {destination!r} is not valid for pending effect {pending_id}")

    pe.raw["destination"] = destination
    pe.raw.setdefault("resolution_input", {})["destination"] = destination
    _emit_pending_event(
        state,
        engine,
        "DESTINATION_CHOSEN",
        actor=pe.chooser_id,
        source=pe.source_id,
        target=None,
        payload={
            "pending_effect_id": pending_id,
            "destination": destination,
        },
    )


# =============================================================================
# Shared resolution_input helpers and general requirement resolvers
# Inspired by Lorcanito's PendingActionResolutionInput normalization
# =============================================================================

def get_resolution_input(pe: PendingEffect) -> dict[str, Any]:
    """Get the resolution_input dict from a pending effect, creating it if needed.

    Returns pe.raw["resolution_input"], normalized to {} if missing.
    """
    return pe.raw.setdefault("resolution_input", {})


def set_resolution_input(pe: PendingEffect, key: str, value: Any) -> None:
    """Set a key in the resolution_input dict of a pending effect."""
    get_resolution_input(pe)[key] = value


def _get_amount_bounds(pe: PendingEffect) -> tuple[int | None, int | None, tuple[int, ...]]:
    """Extract min/max/options for amount validation from pe or pe.raw['requirement']."""
    req = pe.raw.get("requirement")
    min_amount: int | None = pe.raw.get("min_amount", pe.raw.get("min"))  # type: ignore[assignment]
    max_amount: int | None = pe.raw.get("max_amount", pe.raw.get("max"))  # type: ignore[assignment]
    amount_options: tuple[int, ...] = pe.raw.get("amount_options") or pe.raw.get("options") or ()  # type: ignore[assignment]
    if min_amount is None and hasattr(req, "min_amount"):
        min_amount = req.min_amount  # type: ignore[assignment]
    if min_amount is None and hasattr(req, "min"):
        min_amount = req.min  # type: ignore[assignment]
    if max_amount is None and hasattr(req, "max_amount"):
        max_amount = req.max_amount  # type: ignore[assignment]
    if max_amount is None and hasattr(req, "max"):
        max_amount = req.max  # type: ignore[assignment]
    if not amount_options and hasattr(req, "amount_options"):
        amount_options = req.amount_options  # type: ignore[assignment]
    if not amount_options and hasattr(req, "options"):
        amount_options = req.options  # type: ignore[assignment]
    return min_amount, max_amount, tuple(amount_options)


def _get_target_bounds(pe: PendingEffect) -> tuple[int | None, int | None, tuple[int, ...]]:
    """Extract min/max targets and candidate IDs for target validation."""
    req = pe.raw.get("requirement")
    min_targets: int | None = pe.raw.get("min_targets")  # type: ignore[assignment]
    max_targets: int | None = pe.raw.get("max_targets")  # type: ignore[assignment]
    candidate_ids: tuple[int, ...] = pe.raw.get("candidate_ids") or ()  # type: ignore[assignment]
    if min_targets is None and hasattr(req, "min_targets"):
        min_targets = req.min_targets  # type: ignore[assignment]
    if max_targets is None and hasattr(req, "max_targets"):
        max_targets = req.max_targets  # type: ignore[assignment]
    if not candidate_ids and hasattr(req, "candidate_ids"):
        candidate_ids = req.candidate_ids  # type: ignore[assignment]
    return min_targets, max_targets, tuple(candidate_ids)


def _validate_amount(pe: PendingEffect, amount: int) -> None:
    """Validate an amount choice against pe constraints."""
    min_amt, max_amt, options = _get_amount_bounds(pe)
    if options and amount not in options:
        raise ValueError(f"Amount {amount} is not in allowed options {options!r}")
    if min_amt is not None and amount < min_amt:
        raise ValueError(f"Amount {amount} is below minimum {min_amt}")
    if max_amt is not None and amount > max_amt:
        raise ValueError(f"Amount {amount} is above maximum {max_amt}")


def _validate_targets(state: GameState, pe: PendingEffect, targets: tuple[int, ...]) -> None:
    """Validate a target selection against pe constraints."""
    # All IDs must exist in state.cards
    for tid in targets:
        if tid not in state.cards:
            raise ValueError(f"Target card {tid} does not exist")
    # Check count bounds
    min_tgt, max_tgt, candidates = _get_target_bounds(pe)
    if min_tgt is not None and len(targets) < min_tgt:
        raise ValueError(f"Target count {len(targets)} is below minimum {min_tgt}")
    if max_tgt is not None and len(targets) > max_tgt:
        raise ValueError(f"Target count {len(targets)} is above maximum {max_tgt}")
    # If candidates are specified, all chosen must be in candidates
    if candidates:
        for tid in targets:
            if tid not in candidates:
                raise ValueError(f"Target {tid} is not a valid candidate")


def _validate_discard(state: GameState, pe: PendingEffect, card_ids: tuple[int, ...]) -> None:
    """Validate a discard choice against pe constraints."""
    for cid in card_ids:
        if cid not in state.cards:
            raise ValueError(f"Discard card {cid} does not exist")
    candidate_ids = pe.raw.get("discard_candidates") or pe.raw.get("candidate_ids") or ()
    if candidate_ids:
        for cid in card_ids:
            if cid not in candidate_ids:
                raise ValueError(f"Card {cid} is not a valid discard candidate")
    min_discard = pe.raw.get("min_discard") or pe.raw.get("min_targets")
    max_discard = pe.raw.get("max_discard") or pe.raw.get("max_targets")
    if min_discard is not None and len(card_ids) < min_discard:
        raise ValueError(f"Discard count {len(card_ids)} is below minimum {min_discard}")
    if max_discard is not None and len(card_ids) > max_discard:
        raise ValueError(f"Discard count {len(card_ids)} is above maximum {max_discard}")


def resolve_amount_choice(
    state: GameState,
    pending_id: str,
    amount: int,
    *,
    engine: GameEngine | None = None,
) -> None:
    """Resolve a pending amount-choice requirement.

    Validates that amount is an integer and within min/max/options bounds,
    then writes into pe.raw["amount"] and pe.raw["resolution_input"]["amount"].
    """
    pe = get_pending_effect_by_id(state, pending_id)
    if pe is None:
        raise ValueError(f"Pending effect {pending_id} not found")

    if not isinstance(amount, int):
        raise ValueError(f"Amount must be an integer, got {type(amount).__name__}")

    _validate_amount(pe, amount)

    pe.raw["amount"] = amount
    pe.raw.setdefault("resolution_input", {})["amount"] = amount
    _emit_pending_event(
        state,
        engine,
        "AMOUNT_CHOSEN",
        actor=pe.chooser_id,
        source=pe.source_id,
        target=None,
        payload={
            "pending_effect_id": pending_id,
            "amount": amount,
        },
    )


def resolve_target_selection(
    state: GameState,
    pending_id: str,
    targets: tuple[int, ...],
    *,
    engine: GameEngine | None = None,
) -> None:
    """Resolve a pending single-target requirement.

    Validates that all targets exist and count is within bounds,
    then writes into pe.selected_targets and pe.raw["resolution_input"]["targets"].
    """
    pe = get_pending_effect_by_id(state, pending_id)
    if pe is None:
        raise ValueError(f"Pending effect {pending_id} not found")

    _validate_targets(state, pe, targets)

    pe.selected_targets = targets
    pe.raw.setdefault("resolution_input", {})["targets"] = targets
    _emit_pending_event(
        state,
        engine,
        "TARGET_SELECTED",
        actor=pe.chooser_id,
        source=pe.source_id,
        target=targets[0] if targets else None,
        payload={
            "pending_effect_id": pending_id,
            "targets": list(targets),
        },
    )


def resolve_multi_target_selection(
    state: GameState,
    pending_id: str,
    targets: tuple[int, ...],
    *,
    engine: GameEngine | None = None,
) -> None:
    """Resolve a pending multi-target requirement.

    Validates that all targets exist and count is within bounds,
    then writes into pe.selected_targets and pe.raw["resolution_input"]["targets"].
    """
    pe = get_pending_effect_by_id(state, pending_id)
    if pe is None:
        raise ValueError(f"Pending effect {pending_id} not found")

    _validate_targets(state, pe, targets)

    pe.selected_targets = targets
    pe.raw.setdefault("resolution_input", {})["targets"] = targets
    _emit_pending_event(
        state,
        engine,
        "MULTI_TARGET_SELECTED",
        actor=pe.chooser_id,
        source=pe.source_id,
        target=targets[0] if targets else None,
        payload={
            "pending_effect_id": pending_id,
            "targets": list(targets),
        },
    )


def resolve_slotted_target_selection(
    state: GameState,
    pending_id: str,
    slotted_targets: dict[str, Any],
    *,
    engine: GameEngine | None = None,
) -> None:
    """Resolve a pending slotted-target requirement.

    Stores both the structured slotted input and the flattened target tuple so
    existing effect resolution can continue to consume ``current_targets`` while
    future slot-aware effects can inspect ``resolution_input["slotted_targets"]``.
    """
    from lorcana_bot.targeting import (
        flatten_slotted_targets,
        normalize_slotted_target_input,
        validate_slotted_targets,
    )

    pe = get_pending_effect_by_id(state, pending_id)
    if pe is None:
        raise ValueError(f"Pending effect {pending_id} not found")

    normalized = normalize_slotted_target_input(slotted_targets)
    validate_slotted_targets(state, normalized, actor=pe.chooser_id, source_id=pe.source_id, engine=engine)
    flat_targets = flatten_slotted_targets(normalized)
    _validate_targets(state, pe, flat_targets)

    pe.selected_targets = flat_targets
    pe.raw["slotted_targets"] = normalized
    resolution_input = pe.raw.setdefault("resolution_input", {})
    resolution_input["slotted_targets"] = normalized
    resolution_input["targets"] = flat_targets
    _emit_pending_event(
        state,
        engine,
        "SLOTTED_TARGET_SELECTED",
        actor=pe.chooser_id,
        source=pe.source_id,
        target=flat_targets[0] if flat_targets else None,
        payload={
            "pending_effect_id": pending_id,
            "slotted_targets": normalized,
            "targets": list(flat_targets),
        },
    )


def resolve_discard_choice(
    state: GameState,
    pending_id: str,
    card_ids: tuple[int, ...],
    *,
    engine: GameEngine | None = None,
) -> None:
    """Resolve a pending discard-choice requirement.

    Validates that all card IDs exist and count is within bounds,
    then writes into pe.raw["discard_card_ids"] and pe.raw["resolution_input"]["targets"].
    """
    pe = get_pending_effect_by_id(state, pending_id)
    if pe is None:
        raise ValueError(f"Pending effect {pending_id} not found")

    _validate_discard(state, pe, card_ids)

    pe.raw["discard_card_ids"] = card_ids
    pe.raw.setdefault("resolution_input", {})["targets"] = card_ids
    _emit_pending_event(
        state,
        engine,
        "DISCARD_CHOSEN",
        actor=pe.chooser_id,
        source=pe.source_id,
        target=card_ids[0] if card_ids else None,
        payload={
            "pending_effect_id": pending_id,
            "card_ids": list(card_ids),
        },
    )


def resolve_choice_index(
    state: GameState,
    pending_id: str,
    choice_index: int,
    *,
    engine: GameEngine | None = None,
) -> None:
    """Resolve a pending index-choice requirement.

    Validates that choice_index is an integer in range of available options,
    then writes into pe.selected_choice and pe.raw["resolution_input"]["choice_index"].
    """
    pe = get_pending_effect_by_id(state, pending_id)
    if pe is None:
        raise ValueError(f"Pending effect {pending_id} not found")

    if not isinstance(choice_index, int):
        raise ValueError(f"Choice index must be an integer, got {type(choice_index).__name__}")

    # Validate against available options if present. Options may be labels/objects,
    # so choice_index is an index into the option list, not necessarily a member value.
    options = (
        pe.choice_options
        or pe.raw.get("choice_options")
        or pe.raw.get("options")
        or ()
    )
    if options and (choice_index < 0 or choice_index >= len(options)):
        raise ValueError(f"Choice index {choice_index} is out of range for {len(options)} options")

    pe.selected_choice = choice_index
    pe.raw.setdefault("resolution_input", {})["choice_index"] = choice_index
    _emit_pending_event(
        state,
        engine,
        "CHOICE_INDEX_CHOSEN",
        actor=pe.chooser_id,
        source=pe.source_id,
        target=None,
        payload={
            "pending_effect_id": pending_id,
            "choice_index": choice_index,
        },
    )


def resolve_optional_choice(
    state: GameState,
    pending_id: str,
    accepted: bool,
    *,
    engine: GameEngine | None = None,
) -> None:
    """Resolve a pending optional accept/decline requirement.

    Validates that accepted is a boolean,
    then writes into pe.accepted and pe.raw["resolution_input"]["resolve_optional"].
    """
    pe = get_pending_effect_by_id(state, pending_id)
    if pe is None:
        raise ValueError(f"Pending effect {pending_id} not found")

    if not isinstance(accepted, bool):
        raise ValueError(f"Accepted must be a boolean, got {type(accepted).__name__}")

    pe.accepted = accepted
    pe.raw.setdefault("resolution_input", {})["resolve_optional"] = accepted
    _emit_pending_event(
        state,
        engine,
        "OPTIONAL_RESOLVED",
        actor=pe.chooser_id,
        source=pe.source_id,
        target=None,
        payload={
            "pending_effect_id": pending_id,
            "accepted": accepted,
        },
    )


def resolve_enter_play_exerted_choice(
    state: GameState,
    pending_id: str,
    enter_play_exerted: bool,
    *,
    engine: GameEngine | None = None,
) -> None:
    """Resolve a pending enter-play-exerted choice.

    Validates that enter_play_exerted is a boolean,
    then writes into pe.raw["enter_play_exerted"] and
    pe.raw["resolution_input"]["enter_play_exerted"].
    """
    pe = get_pending_effect_by_id(state, pending_id)
    if pe is None:
        raise ValueError(f"Pending effect {pending_id} not found")

    if not isinstance(enter_play_exerted, bool):
        raise ValueError(
            f"enter_play_exerted must be a boolean, got {type(enter_play_exerted).__name__}"
        )

    pe.raw["enter_play_exerted"] = enter_play_exerted
    pe.raw.setdefault("resolution_input", {})["enter_play_exerted"] = enter_play_exerted
    _emit_pending_event(
        state,
        engine,
        "ENTER_PLAY_EXERTED_CHOSEN",
        actor=pe.chooser_id,
        source=pe.source_id,
        target=None,
        payload={
            "pending_effect_id": pending_id,
            "enter_play_exerted": enter_play_exerted,
        },
    )


# =============================================================================
# B5: Pending targeting integration helpers
# These bridge PendingEffect/TargetRequirement to the targeting service
# (TargetDescriptor/TargetCandidate) so pending target enumeration uses the
# same candidate resolution and protection filtering as action-card targeting.
# =============================================================================

# Mapping from TargetRequirement.kind to TargetDescriptor selector
_KIND_TO_SELECTOR: dict[str, str] = {
    "chosen_card": "chosen_card",
    "chosen_character": "chosen_character",
    "chosen_opposing_character": "chosen_opposing_character",
    "chosen_damaged_character": "chosen_damaged_character",
    "chosen_item": "chosen_item",
    "chosen_location": "chosen_location",
    "chosen_player": "chosen_player",
}


def target_descriptor_from_requirement(
    requirement: TargetRequirement | None,
) -> "TargetDescriptor | None":
    """Convert a TargetRequirement to a TargetDescriptor.

    Returns None if the requirement is None or its kind cannot be mapped
    to a known selector.  The conversion is deterministic and preserves
    min/max targets, card type, damage/exerted filters, and owner filter.
    """
    if requirement is None:
        return None

    from lorcana_bot.targeting import TargetDescriptor, normalize_target_descriptor

    selector = _KIND_TO_SELECTOR.get(requirement.kind)
    if selector is None:
        return None

    base = normalize_target_descriptor(selector)
    if base is None:
        return None

    # Build filters from requirement flags
    filters: list[dict[str, Any]] = list(base.filters)
    if requirement.must_be_damaged:
        # Only add if not already present
        if not any(f.get("type") == "damaged" for f in filters):
            filters.append({"type": "damaged", "min": 1})
    if requirement.must_be_exerted:
        if not any(f.get("type") == "exerted" for f in filters):
            filters.append({"type": "exerted"})

    # Map owner_filter to controller
    controller = base.controller
    if requirement.owner_filter == "opponent":
        controller = "opponent"
    elif requirement.owner_filter == "controller":
        controller = "you"

    # Map card_type to card_types
    card_types = base.card_types
    if requirement.card_type and not card_types:
        card_types = (requirement.card_type,)

    min_count = 0 if requirement.optional else requirement.min_targets
    max_count = requirement.max_targets if requirement.max_targets is not None else base.max_count

    return TargetDescriptor(
        selector=selector,
        min_count=min_count,
        max_count=max_count,
        zones=base.zones,
        card_types=card_types,
        owner=base.owner,
        controller=controller,
        filters=tuple(filters),
        exclude_self=base.exclude_self,
        exclude_trigger_subject=base.exclude_trigger_subject,
        allow_players=base.allow_players,
        allow_duplicate_targets=base.allow_duplicate_targets,
    )


# Known selectors that the targeting service can resolve.  Unknown strings
# must NOT be inferred into broad default descriptors (fail closed).
_KNOWN_SELECTORS: frozenset[str] = frozenset({
    "chosen_card", "chosen_character", "chosen_opposing_character",
    "chosen_damaged_character", "chosen_item", "chosen_location",
    "chosen_player", "opposing_character", "self", "event_source",
    "event_target", "trigger_subject", "your_characters", "your_other_characters",
    "opposing_characters", "all_characters", "damaged_characters",
    "opposing_damaged_characters", "current_targets", "context_targets",
    "you", "opponent", "each_player",
    "controller", "actor", "opposing_player", "target",
})


def _is_known_descriptor(desc: "TargetDescriptor") -> bool:
    """Return True if the descriptor's selector is a known targeting selector."""
    return desc.selector in _KNOWN_SELECTORS


def pending_target_descriptors(pe: PendingEffect) -> tuple["TargetDescriptor", ...]:
    """Extract TargetDescriptor(s) from a PendingEffect.

    Descriptor source precedence:
    1. pe.raw["target_descriptor"]
    2. pe.raw["target_dsl"]
    3. pe.raw["target"]
    4. pe.raw["selector"]
    5. pe.raw["requirement"] if descriptor-like
    6. pe.current_requirement / TargetRequirement fallback
    7. raw_requirement.kind / raw_requirement.target / raw_requirement.selector

    Returns no descriptors if no descriptor can be normalized (fail closed).
    Unknown strings are NOT inferred into broad default descriptors.
    """
    from lorcana_bot.targeting import TargetDescriptor, normalize_target_descriptor, normalize_target_descriptors

    raw = pe.raw or {}

    def _try_normalize(value) -> "TargetDescriptor | None":
        """Normalize and validate that the selector is known."""
        if value is None:
            return None
        desc = normalize_target_descriptor(value)
        if desc is not None and _is_known_descriptor(desc):
            return desc
        return None

    def _try_normalize_many(value) -> tuple["TargetDescriptor", ...]:
        """Normalize one or more descriptors and discard unknown selectors."""
        if value is None:
            return ()
        return tuple(
            desc for desc in normalize_target_descriptors(value)
            if _is_known_descriptor(desc)
        )

    def _try_requirement_like(value) -> "TargetDescriptor | None":
        """Normalize requirement-like raw objects without inventing defaults."""
        if value is None:
            return None
        if isinstance(value, TargetRequirement):
            return target_descriptor_from_requirement(value)
        if isinstance(value, TargetDescriptor):
            return value if _is_known_descriptor(value) else None
        if isinstance(value, dict):
            desc = _try_normalize(value)
            if desc is not None:
                return desc
            for key in ("target", "selector", "kind", "type"):
                desc = _try_normalize(value.get(key))
                if desc is not None:
                    return desc
            return None
        for attr in ("target", "selector", "kind", "type"):
            desc = _try_normalize(getattr(value, attr, None))
            if desc is not None:
                return desc
        return None

    # 1. pe.raw["target_descriptor"]
    descs = _try_normalize_many(raw.get("target_descriptor"))
    if descs:
        return descs

    # 2. pe.raw["target_dsl"]
    descs = _try_normalize_many(raw.get("target_dsl"))
    if descs:
        return descs

    # 3. pe.raw["target"]
    descs = _try_normalize_many(raw.get("target"))
    if descs:
        return descs

    # 4. pe.raw["selector"]
    descs = _try_normalize_many(raw.get("selector"))
    if descs:
        return descs

    # 5. pe.raw["requirement"] if descriptor-like or TargetRequirement-like
    desc = _try_requirement_like(raw.get("requirement"))
    if desc is not None:
        return (desc,)

    # 6. pe.current_requirement / TargetRequirement fallback
    requirement = pe.current_requirement
    if requirement is not None:
        desc = target_descriptor_from_requirement(requirement)
        if desc is not None:
            return (desc,)

    # 7. raw_requirement from engine (kind/target/selector if present and descriptor-like)
    desc = _try_requirement_like(raw.get("raw_requirement"))
    if desc is not None:
        return (desc,)

    return ()


def get_valid_target_candidates_for_pending(
    state: GameState,
    pe: PendingEffect,
    chooser_id: int,
    engine: "GameEngine",
) -> tuple["TargetCandidate", ...]:
    """Resolve valid target candidates for a pending effect using the targeting service.

    This is the central pending-target candidate resolver.  It:
    1. Resolves descriptors from the pending effect.
    2. Resolves candidates through resolve_candidate_targets().
    3. Applies apply_target_protections().
    4. Narrows card candidates by raw candidate_ids / card_candidate_ids / target_candidate_ids.
    5. Narrows player candidates by raw player_candidate_ids / player_candidates.
    6. Returns only valid, protected, narrowed candidates.

    Returns no candidates if no descriptor can be determined (fail closed).
    """
    from lorcana_bot.targeting import (
        TargetCandidate,
        TargetQueryContext,
        apply_target_protections,
        resolve_candidate_targets,
    )

    descriptors = pending_target_descriptors(pe)
    if not descriptors:
        return ()

    raw = pe.raw or {}
    context = TargetQueryContext(
        actor=chooser_id,
        source_id=pe.source_id,
        event_payload=raw.get("event_payload", {}) or {},
        current_targets=tuple(raw.get("current_targets", ()) or ()),
        context_targets=tuple(raw.get("context_targets", ()) or ()),
    )

    all_candidates: list[TargetCandidate] = []
    for desc in descriptors:
        raw_candidates = resolve_candidate_targets(state, engine, desc, context)
        protected = apply_target_protections(state, engine, raw_candidates, desc, context)
        all_candidates.extend(protected)

    # Deduplicate by (kind, id)
    seen: set[tuple[str, int]] = set()
    deduped: list[TargetCandidate] = []
    for cand in all_candidates:
        key = (cand.kind, cand.id)
        if key not in seen:
            seen.add(key)
            deduped.append(cand)

    # Separate card and player candidates
    card_candidates = [c for c in deduped if c.kind == "card"]
    player_candidates = [c for c in deduped if c.kind == "player"]

    # Narrow card candidates by raw candidate lists
    narrowing_card_ids = (
        raw.get("card_candidate_ids")
        or raw.get("target_candidate_ids")
        or raw.get("candidate_ids")
        or ()
    )
    if narrowing_card_ids:
        narrowing_set = set(narrowing_card_ids)
        card_candidates = [c for c in card_candidates if c.id in narrowing_set]

    # Narrow player candidates by raw player candidate lists
    narrowing_player_ids = (
        raw.get("player_candidate_ids")
        or raw.get("player_candidates")
        or ()
    )
    if narrowing_player_ids:
        narrowing_set = set(narrowing_player_ids)
        player_candidates = [c for c in player_candidates if c.id in narrowing_set]

    # Reassemble: cards first, then players
    return tuple(card_candidates + player_candidates)


def resolve_player_target_selection(
    state: GameState,
    pending_id: str,
    player_targets: tuple[int, ...],
    *,
    engine: "GameEngine | None" = None,
) -> None:
    """Resolve a pending player-target requirement.

    Validates that player IDs exist in the current game,
    then writes into pe.selected_player_targets and
    pe.raw["resolution_input"]["player_targets"].

    Player targets are stored separately from card targets.
    """
    pe = get_pending_effect_by_id(state, pending_id)
    if pe is None:
        raise ValueError(f"Pending effect {pending_id} not found")

    # Validate player IDs
    for pid in player_targets:
        if pid < 0 or pid >= len(state.players):
            raise ValueError(f"Invalid player ID {pid}")

    pe.selected_player_targets = player_targets
    pe.raw["selected_player_targets"] = player_targets
    pe.raw.setdefault("resolution_input", {})["player_targets"] = player_targets
    _emit_pending_event(
        state,
        engine,
        "PLAYER_TARGET_SELECTED",
        actor=pe.chooser_id,
        source=pe.source_id,
        target=None,
        payload={
            "pending_effect_id": pending_id,
            "player_targets": list(player_targets),
        },
    )
