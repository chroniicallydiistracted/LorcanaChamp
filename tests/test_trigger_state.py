"""B2 tests for trigger state and bag resolution."""

import pytest

from lorcana_bot.state import BagEffectEntry, GameState, PendingTriggeredEvent
from lorcana_bot.triggers import (
    canonical_trigger_event,
    buffer_trigger_event,
    enqueue_bag_effect,
    flush_triggered_events_to_bag,
    get_next_bag_resolver,
    has_pending_bag_items,
    remove_bag_effect,
    record_bag_effect_resolution,
    set_last_bag_resolver,
    TriggerCandidate,
)


@pytest.fixture
def simple_engine():
    """Create a minimal engine mock for trigger tests."""
    from lorcana_bot.engine import GameEngine
    from lorcana_bot.cards import CardDatabase, CardDef
    
    cards = [
        CardDef("test_char", "Test Char", "amber", 2, True, "character", 2, 2, 1),
        CardDef("test_char2", "Test Char 2", "amber", 2, True, "character", 2, 2, 1),
    ]
    db = CardDatabase(cards)
    return GameEngine(db)


@pytest.fixture
def state_with_cards():
    """Create a game state with cards in play."""
    from lorcana_bot.state import CardInstance, PlayerState
    
    state = GameState(
        players=[PlayerState(), PlayerState()],
        cards={},
    )
    # Add character in play
    card1 = CardInstance(instance_id=1, card_id="test_char", owner=0, controller=0, zone="play")
    card2 = CardInstance(instance_id=2, card_id="test_char2", owner=1, controller=1, zone="play")
    state.cards[1] = card1
    state.cards[2] = card2
    state.players[0].play = [1]
    state.players[1].play = [2]
    return state


def test_pending_triggered_event_structure():
    """Test PendingTriggeredEvent dataclass."""
    event = PendingTriggeredEvent(
        id="evt_1_1",
        event="quest",
        player_id=0,
        subject_card_id=1,
        trigger_source_card_id=1,
    )
    assert event.id == "evt_1_1"
    assert event.event == "quest"
    assert event.player_id == 0


def test_bag_effect_entry_properties():
    """Test BagEffectEntry backward-compatible properties."""
    from lorcana_bot.state import PendingTriggeredEvent
    pending_event = PendingTriggeredEvent(id="evt_1", event="quest")
    entry = BagEffectEntry(
        id="bag_1",
        kind="triggered_ability",
        ability_id="test_ability",
        ability_index=0,
        ability_key="test_key",
        ability_name="Test Ability",
        auto_resolve=True,
        controller_id=0,
        chooser_id=0,
        source_id=1,
        source_card_id="test_char",
        trigger={"event": "quest"},
        condition=None,
        effects=(),
        occurrence_index=1,
        event=pending_event,
    )
    # Test backward-compatible properties
    assert entry.source == 1
    assert entry.controller == 0
    assert entry.event_type == "quest"
    # Test optional property
    assert entry.optional is False


def test_bag_next_seq_increments(state_with_cards):
    """Test that bag IDs are deterministic and increment."""
    id1 = state_with_cards.next_bag_id()
    id2 = state_with_cards.next_bag_id()
    assert id1 == "bag_1"
    assert id2 == "bag_2"


def test_trigger_occurrences_ledger(state_with_cards):
    """Test trigger occurrence tracking."""
    state_with_cards.trigger_occurrences["test_key"] = 1
    assert state_with_cards.trigger_occurrences["test_key"] == 1


def test_trigger_resolutions_ledger(state_with_cards):
    """Test trigger resolution tracking."""
    state_with_cards.trigger_resolutions["test_key"] = 1
    assert state_with_cards.trigger_resolutions["test_key"] == 1


def test_last_bag_resolver_persists(state_with_cards):
    """Test last_bag_resolver is set correctly."""
    state_with_cards.last_bag_resolver = 0
    assert state_with_cards.last_bag_resolver == 0
    set_last_bag_resolver(state_with_cards, 1)
    assert state_with_cards.last_bag_resolver == 1


def test_has_pending_bag_items(state_with_cards):
    """Test has_pending_bag_items."""
    assert has_pending_bag_items(state_with_cards) is False
    entry = BagEffectEntry(
        id=state_with_cards.next_bag_id(),
        kind="triggered_ability",
        ability_id="test",
        ability_index=0,
        ability_key="key",
        ability_name="Test",
        auto_resolve=True,
        controller_id=0,
        chooser_id=0,
        source_id=1,
        source_card_id="test_char",
        trigger={},
        condition=None,
        effects=(),
        occurrence_index=1,
    )
    state_with_cards.bag.append(entry)
    assert has_pending_bag_items(state_with_cards) is True


def test_canonical_trigger_event():
    """Test canonical event name mapping."""
    from lorcana_bot.state import GameEvent
    
    # String input
    assert canonical_trigger_event("TURN_START") == "start-turn"
    assert canonical_trigger_event("play") == "play"
    
    # GameEvent input
    event = GameEvent(event_type="QUESTED")
    assert canonical_trigger_event(event) == "quest"


def test_buffer_trigger_event(state_with_cards):
    """Test buffering a trigger event."""
    from lorcana_bot.state import GameEvent
    
    game_event = GameEvent(event_type="QUESTED", actor=0, source=1)
    pending = buffer_trigger_event(
        state_with_cards,
        game_event,
        subject_card_id=1,
        trigger_source_card_id=1,
    )
    assert pending.event == "quest"
    assert pending.player_id == 0
    assert pending.subject_card_id == 1
    assert len(state_with_cards.pending_trigger_events) == 1


def test_remove_bag_effect(state_with_cards):
    """Test removing a bag entry by ID."""
    entry = BagEffectEntry(
        id=state_with_cards.next_bag_id(),
        kind="triggered_ability",
        ability_id="test",
        ability_index=0,
        ability_key="key",
        ability_name="Test",
        auto_resolve=True,
        controller_id=0,
        chooser_id=0,
        source_id=1,
        source_card_id="test_char",
        trigger={},
        condition=None,
        effects=(),
        occurrence_index=1,
    )
    state_with_cards.bag.append(entry)
    bag_id = entry.id
    
    removed = remove_bag_effect(state_with_cards, bag_id)
    assert removed is not None
    assert removed.id == bag_id
    assert len(state_with_cards.bag) == 0


def test_record_bag_effect_resolution(state_with_cards):
    """Test recording a bag resolution."""
    entry = BagEffectEntry(
        id="bag_1",
        kind="triggered_ability",
        ability_id="test",
        ability_index=0,
        ability_key="test_key",
        ability_name="Test",
        auto_resolve=True,
        controller_id=0,
        chooser_id=0,
        source_id=1,
        source_card_id="test_char",
        trigger={},
        condition=None,
        effects=(),
        occurrence_index=1,
    )
    record_bag_effect_resolution(state_with_cards, entry)
    assert state_with_cards.trigger_resolutions["test_key"] == 1