from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from .constants import ZONE_DECK, ZONE_DISCARD, ZONE_HAND, ZONE_INKWELL, ZONE_PLAY
from .actions import Action
from .pending_effects import PendingEffect
from .static_effects import StaticEffectRegistry

if TYPE_CHECKING:
    from .replacement_effects import ReplacementEffectRegistry


def _default_static_effect_registry() -> StaticEffectRegistry:
    """Factory for default static effect registry."""
    return StaticEffectRegistry()


def _default_replacement_effect_registry() -> "ReplacementEffectRegistry":
    """Factory for default replacement effect registry.
    
    Import is done lazily to avoid circular imports. The actual class
    is defined in replacement_effects.py.
    """
    from .replacement_effects import ReplacementEffectRegistry as RER
    return RER()


@dataclass(slots=True)
class CardInstance:
    instance_id: int
    card_id: str
    owner: int
    controller: int
    zone: str = ZONE_DECK
    exerted: bool = False
    drying: bool = False
    damage: int = 0
    revealed: bool = False
    facedown: bool = False
    just_played: bool = False
    added_to_ink_this_turn: bool = False
    has_quested_this_turn: bool = False
    location_instance_id: int | None = None
    used_abilities_this_turn: list[str] = field(default_factory=list)
    last_damage_source: int | str | None = None
    last_damage_was_challenge: bool = False
    was_challenged_this_turn: bool = False
    temporary_keywords: list[str] = field(default_factory=list)
    temporary_modifiers: dict[str, int] = field(default_factory=dict)


@dataclass(slots=True)
class PlayerTurnFlags:
    drew_for_turn: bool = False
    played_ink: bool = False
    passed_turn: bool = False
    took_manual_action: bool = False


@dataclass(slots=True)
class PlayerState:
    lore: int = 0
    deck: list[int] = field(default_factory=list)
    hand: list[int] = field(default_factory=list)
    play: list[int] = field(default_factory=list)
    discard: list[int] = field(default_factory=list)
    inkwell: list[int] = field(default_factory=list)
    has_kept_opening_hand: bool = False
    has_mulliganed: bool = False
    mulliganed_card_ids: list[int] = field(default_factory=list)
    turn_flags: PlayerTurnFlags = field(default_factory=PlayerTurnFlags)
    cost_reductions: list[dict[str, Any]] = field(default_factory=list)


@dataclass(slots=True)
class PendingTriggeredEvent:
    """Buffered trigger event waiting for resolution boundary.
    
    This dataclass mirrors Lorcanito's PendingTriggeredEvent with rich payload
    data for comprehensive trigger matching across SELF, YOU, OPPONENT, and
    challenge/banish/ink contexts.
    """
    id: str
    event: str
    # Core identifiers
    player_id: int | None = None
    subject_card_id: int | None = None
    trigger_source_card_id: int | None = None
    source_card_type: str | None = None
    # Zone tracking
    from_zone: str | None = None
    to_zone: str | None = None
    # Challenge context
    attacker_id: int | None = None
    defender_id: int | None = None
    defender_card_type: str | None = None
    happened_in_challenge: bool = False
    # Event snapshot for delayed trigger evaluation
    event_snapshot: dict[str, Any] = field(default_factory=dict)
    # Extended payload (Lorcanito-aligned event-specific data)
    payload: dict[str, Any] = field(default_factory=dict)
    
    @property
    def card_played(self) -> dict[str, Any] | None:
        """Get CardPlayedPayload if this event has play data."""
        return self.payload.get("card_played")
    
    @property
    def damage_dealt(self) -> dict[str, Any] | None:
        """Get damage information from the payload."""
        return self.payload.get("damage_dealt")
    
    @property
    def lore_gained(self) -> int | None:
        """Get lore gained from quest/lore events."""
        return self.payload.get("lore")


@dataclass(slots=True)
class BagEffectEntry:
    """A trigger's effect queued in the resolution bag (Lorcanito-aligned)."""
    id: str
    kind: str
    ability_id: str
    ability_index: int | None
    ability_key: str
    ability_name: str | None
    auto_resolve: bool | None
    controller_id: int
    chooser_id: int
    source_id: int
    source_card_id: str
    trigger: dict[str, Any]
    condition: dict[str, Any] | None
    effects: tuple[Any, ...]
    occurrence_index: int
    resolution_input: dict[str, Any] = field(default_factory=dict)
    event: PendingTriggeredEvent | None = None
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def source(self) -> int:
        """Backward-compatible alias for source_id."""
        return self.source_id

    @property
    def controller(self) -> int:
        """Backward-compatible alias for controller_id."""
        return self.controller_id

    @property
    def event_type(self) -> str | None:
        """Get the canonical trigger event from the pending event."""
        return self.event.event if self.event else None
    
    @property
    def optional(self) -> bool:
        """Check if this bag entry is optional (for trigger decline)."""
        return self.auto_resolve is False or self.trigger.get("optional", False)


# B2: Backwards-compatible alias for existing tests
PendingTrigger = BagEffectEntry


@dataclass(slots=True)
class GameEvent:
    event_type: str
    actor: int | None = None
    source: int | None = None
    target: int | None = None
    payload: dict[str, Any] = field(default_factory=dict)
    id: str | None = None
    turn: int | None = None
    ply: int | None = None
    controller: int | None = None
    source_card_id: str | None = None
    target_card_id: str | None = None


@dataclass(slots=True)
class ActionLogEntry:
    turn_number: int
    phase: str
    action: Action
    manual: bool = False


@dataclass(slots=True)
class GameState:
    players: list[PlayerState]
    cards: dict[int, CardInstance]
    active_player: int = 0
    first_player: int = 0
    turn_number: int = 1
    phase: str = "MAIN"
    seed: int | None = None
    shuffle_counter: int = 0
    turn_player_has_inked: bool = False
    bag: list[BagEffectEntry] = field(default_factory=list)
    event_log: list[GameEvent] = field(default_factory=list)
    action_log: list[ActionLogEntry] = field(default_factory=list)
    has_first_player_skipped_first_draw: bool = False
    manually_modified: bool = False
    winner: int | None = None
    loss_reason: str | None = None

    # B2: Trigger pipeline state
    pending_trigger_events: list[PendingTriggeredEvent] = field(default_factory=list)
    trigger_registrations: list[dict[str, Any]] = field(default_factory=list)
    bag_next_seq: int = 1
    last_bag_resolver: int | None = None
    trigger_occurrences: dict[str, int] = field(default_factory=dict)
    trigger_resolutions: dict[str, int] = field(default_factory=dict)
    event_counter: int = 0  # For deterministic event IDs
    
    # B3: Pending effect layer for target/choice resolution
    pending_effects: list[PendingEffect] = field(default_factory=list)
    pending_effect_next_seq: int = 1

    # B5: Static effect registry for continuous card effects
    static_effect_registry: StaticEffectRegistry = field(default_factory=_default_static_effect_registry)

    # B6: Replacement effect registry for damage/banish interception
    replacement_effect_registry: ReplacementEffectRegistry = field(default_factory=_default_replacement_effect_registry)

    def opponent(self, player: int) -> int:
        return 1 - player

    def zone_of(self, card_instance_id: int) -> str:
        return self.cards[card_instance_id].zone

    def find_zone_list(self, player: int, zone: str) -> list[int]:
        ps = self.players[player]
        if zone == ZONE_DECK:
            return ps.deck
        if zone == ZONE_HAND:
            return ps.hand
        if zone == ZONE_PLAY:
            return ps.play
        if zone == ZONE_DISCARD:
            return ps.discard
        if zone == ZONE_INKWELL:
            return ps.inkwell
        raise ValueError(f"Unknown zone {zone}")

    def next_event_id(self) -> str:
        """Generate a deterministic event ID."""
        self.event_counter += 1
        return f"evt_{self.turn_number}_{self.event_counter}"

    def next_bag_id(self) -> str:
        """Generate a deterministic bag item ID."""
        bag_id = f"bag_{self.bag_next_seq}"
        self.bag_next_seq += 1
        return bag_id

    def move_card(self, card_instance_id: int, destination: str, controller: int | None = None) -> None:
        card = self.cards[card_instance_id]
        source_owner = card.controller
        source_zone = card.zone
        source_list = self.find_zone_list(source_owner, source_zone)
        if card_instance_id in source_list:
            source_list.remove(card_instance_id)

        if controller is not None:
            card.controller = controller
        dest_owner = card.controller
        dest_list = self.find_zone_list(dest_owner, destination)
        dest_list.append(card_instance_id)
        card.zone = destination

        if destination not in {ZONE_PLAY, ZONE_INKWELL}:
            card.exerted = False
            card.drying = False
            card.damage = 0
            card.just_played = False
            card.added_to_ink_this_turn = False
            card.has_quested_this_turn = False
            card.used_abilities_this_turn.clear()
            card.last_damage_source = None
            card.last_damage_was_challenge = False
            card.was_challenged_this_turn = False
            card.temporary_keywords.clear()
            card.temporary_modifiers.clear()
            card.location_instance_id = None
        if destination == ZONE_INKWELL:
            card.damage = 0
            card.drying = False
            card.revealed = False
            card.facedown = True
            card.just_played = False
            card.has_quested_this_turn = False
        if destination == ZONE_PLAY:
            card.revealed = True
            card.facedown = False
