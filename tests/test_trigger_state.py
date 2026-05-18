"""B2 tests for trigger state and bag resolution."""

import pytest

from lorcana_bot.state import BagEffectEntry, GameState, PendingTriggeredEvent
from lorcana_bot.cards import TriggerDef
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
    trigger_matches_event,
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
    from lorcana_bot.constants import (
        EVENT_BANISH_IN_CHALLENGE,
        EVENT_CARD_DISCARDED,
        EVENT_CARD_DRAWN,
        EVENT_CARD_EXERTED,
        EVENT_CARD_READIED,
        EVENT_CARD_RETURNED_TO_HAND,
        EVENT_DAMAGE_DEALT,
        EVENT_INKED,
        EVENT_PUT_CARD_UNDER,
    )
    from lorcana_bot.state import GameEvent

    # String input
    assert canonical_trigger_event("TURN_START") == "start-turn"
    assert canonical_trigger_event("play") == "play"
    assert canonical_trigger_event(EVENT_INKED) == "ink"
    assert canonical_trigger_event(EVENT_CARD_DRAWN) == "draw"
    assert canonical_trigger_event(EVENT_DAMAGE_DEALT) == "deal-damage"
    assert canonical_trigger_event(EVENT_CARD_DISCARDED) == "discard"
    assert canonical_trigger_event(EVENT_CARD_RETURNED_TO_HAND) == "return-to-hand"
    assert canonical_trigger_event(EVENT_CARD_READIED) == "ready"
    assert canonical_trigger_event(EVENT_CARD_EXERTED) == "exert"
    assert canonical_trigger_event(EVENT_BANISH_IN_CHALLENGE) == "banish-in-challenge"
    assert canonical_trigger_event(EVENT_PUT_CARD_UNDER) == "put-card-under"

    # GameEvent input
    event = GameEvent(event_type="QUESTED")
    assert canonical_trigger_event(event) == "quest"


def test_buffer_trigger_event_hydrates_basic_payload_fields(state_with_cards):
    """Buffering must prefer payload fields over fallback arguments."""
    from lorcana_bot.state import GameEvent

    game_event = GameEvent(
        event_type="QUESTED",
        actor=1,
        source=2,
        payload={
            "player_id": 0,
            "subject_card_id": 1,
            "trigger_source_card_id": 1,
            "card_type": "character",
            "lore": 2,
        },
    )
    pending = buffer_trigger_event(
        state_with_cards,
        game_event,
        subject_card_id=2,
        trigger_source_card_id=2,
        source_card_type="item",
    )

    assert pending.event == "quest"
    assert pending.player_id == 0
    assert pending.subject_card_id == 1
    assert pending.trigger_source_card_id == 1
    assert pending.source_card_type == "character"
    assert pending.lore_gained == 2
    assert pending.event_snapshot["player_id"] == 0
    assert pending.event_snapshot["subject_card_id"] == 1
    assert pending.event_snapshot["trigger_source_card_id"] == 1
    assert pending.event_snapshot["source_card_type"] == "character"
    assert pending.event_snapshot["lore_gained"] == 2
    assert len(state_with_cards.pending_trigger_events) == 1


def test_buffer_trigger_event_hydrates_challenge_payload_fields(state_with_cards):
    """Challenge events must preserve attacker, defender, and damage snapshot data."""
    from lorcana_bot.state import GameEvent

    game_event = GameEvent(
        event_type="CHALLENGE_STARTED",
        actor=0,
        source=1,
        target=2,
        payload={
            "player_id": 0,
            "subject_card_id": 1,
            "attacker_id": 1,
            "defender_id": 2,
            "defender_card_type": "character",
            "attacker_damage_dealt": 3,
            "defender_damage_dealt": 2,
        },
    )
    pending = buffer_trigger_event(state_with_cards, game_event)

    assert pending.event == "challenge"
    assert pending.player_id == 0
    assert pending.subject_card_id == 1
    assert pending.attacker_id == 1
    assert pending.defender_id == 2
    assert pending.defender_card_type == "character"
    assert pending.event_snapshot["attacker_id"] == 1
    assert pending.event_snapshot["defender_id"] == 2
    assert pending.event_snapshot["defender_card_type"] == "character"
    assert pending.event_snapshot["damage_dealt"] == 3


def test_buffer_trigger_event_hydrates_banish_in_challenge_payload_fields(state_with_cards):
    """Banish-in-challenge events must preserve leave-play and challenge context."""
    from lorcana_bot.state import GameEvent

    game_event = GameEvent(
        event_type="BANISH_IN_CHALLENGE",
        actor=0,
        source=2,
        payload={
            "player_id": 0,
            "subject_card_id": 2,
            "banished_card_type": "character",
            "from_zone": "play",
            "to_zone": "discard",
            "happened_in_challenge": True,
        },
    )
    pending = buffer_trigger_event(state_with_cards, game_event)

    assert pending.event == "banish-in-challenge"
    assert pending.player_id == 0
    assert pending.subject_card_id == 2
    assert pending.source_card_type == "character"
    assert pending.from_zone == "play"
    assert pending.to_zone == "discard"
    assert pending.happened_in_challenge is True
    assert pending.event_snapshot["from_zone"] == "play"
    assert pending.event_snapshot["to_zone"] == "discard"
    assert pending.event_snapshot["happened_in_challenge"] is True


def test_buffer_trigger_event_hydrates_put_card_under_payload_fields(state_with_cards):
    """Put-card-under events must preserve shift card and target references."""
    from lorcana_bot.state import GameEvent
    from lorcana_bot.constants import EVENT_PUT_CARD_UNDER

    # Use card instance IDs from state_with_cards fixture
    moved_card_id = 1
    top_card_id = 2

    game_event = GameEvent(
        event_type=EVENT_PUT_CARD_UNDER,
        actor=0,
        source=moved_card_id,
        payload={
            "player_id": 0,
            "subject_card_id": moved_card_id,
            "target_id": top_card_id,
            "from_zone": "play",
            "to_zone": "under",
        },
    )
    pending = buffer_trigger_event(state_with_cards, game_event)

    assert pending.event == "put-card-under"
    assert pending.player_id == 0
    assert pending.subject_card_id == moved_card_id
    assert pending.event_snapshot["target_id"] == top_card_id


def test_leave_play_trigger_matches_expanded_events(simple_engine, state_with_cards):
    """A leave-play trigger must match each Lorcanito leave-play event variant."""
    trigger = TriggerDef(id="leave_play", event="leave-play", on="SELF")
    candidate = TriggerCandidate(
        source_instance_id=1,
        source_card=simple_engine.card_def(state_with_cards, 1),
        trigger=trigger,
        ability_id="leave_play",
        ability_key="1:leave_play:0",
        ability_index=0,
        source_zones=("play",),
    )

    for event_name in ("banish", "banish-in-challenge", "return-to-hand", "ink"):
        pending = PendingTriggeredEvent(
            id=f"evt_{event_name}",
            event=event_name,
            player_id=0,
            subject_card_id=1,
            trigger_source_card_id=1,
            source_card_type="character",
        )
        assert trigger_matches_event(state_with_cards, simple_engine, candidate, pending) is True


def test_leave_play_trigger_flushes_to_bag(simple_engine, state_with_cards):
    """leave-play must be collected and enqueued for expanded leave-play events."""
    source_card = simple_engine.db.get("test_char")
    object.__setattr__(
        source_card,
        "triggers",
        (TriggerDef(id="leave_play", event="leave-play", on="SELF"),),
    )
    pending = PendingTriggeredEvent(
        id="evt_banish",
        event="banish",
        player_id=0,
        subject_card_id=1,
        trigger_source_card_id=1,
        source_card_type="character",
    )
    state_with_cards.pending_trigger_events.append(pending)

    enqueued = flush_triggered_events_to_bag(state_with_cards, simple_engine)

    assert enqueued == 1
    assert state_with_cards.bag[0].event_type == "banish"
    assert state_with_cards.bag[0].trigger["event"] == "leave-play"


def test_buffer_trigger_event_hydrates_ink_payload_fields(state_with_cards):
    """Ink events must preserve source and destination zones."""
    from lorcana_bot.state import GameEvent

    game_event = GameEvent(
        event_type="INKED",
        actor=0,
        source=3,
        payload={
            "player_id": 0,
            "subject_card_id": 3,
            "from_zone": "hand",
            "to_zone": "inkwell",
        },
    )
    pending = buffer_trigger_event(state_with_cards, game_event)

    assert pending.event == "ink"
    assert pending.subject_card_id == 3
    assert pending.from_zone == "hand"
    assert pending.to_zone == "inkwell"
    assert pending.event_snapshot["from_zone"] == "hand"
    assert pending.event_snapshot["to_zone"] == "inkwell"


def test_buffer_trigger_event_preserves_private_draw_payload(state_with_cards):
    """Draw events must preserve private/public payload fields without losing canonical event data."""
    from lorcana_bot.state import GameEvent

    game_event = GameEvent(
        event_type="CARD_DRAWN",
        actor=1,
        payload={
            "player_id": 1,
            "count": 1,
            "private": True,
        },
    )
    pending = buffer_trigger_event(state_with_cards, game_event)

    assert pending.event == "draw"
    assert pending.player_id == 1
    assert pending.payload["count"] == 1
    assert pending.payload["private"] is True
    assert pending.event_snapshot["event"] == "draw"
    assert pending.event_snapshot["player_id"] == 1


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


def test_unknown_string_on_filter_fails_closed():
    """Unknown string filters must return False to fail closed."""
    from lorcana_bot.engine import GameEngine
    from lorcana_bot.cards import CardDatabase, CardDef, TriggerDef
    from lorcana_bot.state import GameState, CardInstance, PlayerState

    cards = [
        CardDef("trigger_char", "Trigger Char", "amber", 2, True, "character", 2, 2, 1),
    ]
    db = CardDatabase(cards)
    engine = GameEngine(db)

    state = GameState(players=[PlayerState(), PlayerState()], cards={})
    state.cards[1] = CardInstance(1, "trigger_char", owner=0, controller=0, zone="play")
    state.players[0].play = [1]

    trigger = TriggerDef(id="unknown_on_test", event="quest", on="UNKNOWN_FILTER_VALUE")
    candidate = TriggerCandidate(
        source_instance_id=1,
        source_card=db.get("trigger_char"),
        trigger=trigger,
        ability_id="unknown_on_test",
        ability_key="trigger_char:trigger:0",
        ability_index=0,
        source_zones=("play",),
    )

    pending = PendingTriggeredEvent(
        id="evt_1",
        event="quest",
        player_id=0,
        subject_card_id=1,
    )

    # Unknown filter must return False (fail closed)
    result = trigger_matches_event(state, engine, candidate, pending)
    assert result is False


def test_characters_here_matches_subject_at_source_location():
    """CHARACTERS_HERE must match when subject is at same location as trigger source."""
    from lorcana_bot.engine import GameEngine
    from lorcana_bot.cards import CardDatabase, CardDef, TriggerDef
    from lorcana_bot.state import GameState, CardInstance, PlayerState

    cards = [
        CardDef("trigger_char", "Trigger Char", "amber", 2, True, "character", 2, 2, 1),
        CardDef("neighbor_char", "Neighbor Char", "amber", 2, True, "character", 2, 2, 1),
    ]
    db = CardDatabase(cards)
    engine = GameEngine(db)

    state = GameState(players=[PlayerState(), PlayerState()], cards={})
    # Trigger source at location 1 (same card acts as location marker)
    state.cards[1] = CardInstance(1, "trigger_char", owner=0, controller=0, zone="play", location_instance_id=1)
    # Subject character also at location 1
    state.cards[2] = CardInstance(2, "neighbor_char", owner=0, controller=0, zone="play", location_instance_id=1)
    state.players[0].play = [1, 2]

    trigger = TriggerDef(id="characters_here_test", event="quest", on="CHARACTERS_HERE")
    candidate = TriggerCandidate(
        source_instance_id=1,
        source_card=db.get("trigger_char"),
        trigger=trigger,
        ability_id="characters_here_test",
        ability_key="trigger_char:trigger:0",
        ability_index=0,
        source_zones=("play",),
    )

    pending = PendingTriggeredEvent(
        id="evt_1",
        event="quest",
        player_id=0,
        subject_card_id=2,  # The neighbor character
    )

    result = trigger_matches_event(state, engine, candidate, pending)
    assert result is True


def test_object_on_filter_exclude_self_blocks_source():
    """excludeSelf must block the trigger source from matching itself."""
    from lorcana_bot.engine import GameEngine
    from lorcana_bot.cards import CardDatabase, CardDef, TriggerDef
    from lorcana_bot.state import GameState, CardInstance, PlayerState

    cards = [
        CardDef("trigger_char", "Trigger Char", "amber", 2, True, "character", 2, 2, 1),
    ]
    db = CardDatabase(cards)
    engine = GameEngine(db)

    state = GameState(players=[PlayerState(), PlayerState()], cards={})
    state.cards[1] = CardInstance(1, "trigger_char", owner=0, controller=0, zone="play")
    state.players[0].play = [1]

    # Object filter with excludeSelf: true
    trigger = TriggerDef(
        id="exclude_self_test",
        event="quest",
        on={"controller": "you", "excludeSelf": True},
    )
    candidate = TriggerCandidate(
        source_instance_id=1,
        source_card=db.get("trigger_char"),
        trigger=trigger,
        ability_id="exclude_self_test",
        ability_key="trigger_char:trigger:0",
        ability_index=0,
        source_zones=("play",),
    )

    pending = PendingTriggeredEvent(
        id="evt_1",
        event="quest",
        player_id=0,
        subject_card_id=1,  # Same as source - must be blocked
    )

    result = trigger_matches_event(state, engine, candidate, pending)
    assert result is False


def test_object_on_filter_controller_you_matches_controlled_subject():
    """controller: "you" must match when subject is controlled by trigger source controller."""
    from lorcana_bot.engine import GameEngine
    from lorcana_bot.cards import CardDatabase, CardDef, TriggerDef
    from lorcana_bot.state import GameState, CardInstance, PlayerState

    cards = [
        CardDef("trigger_char", "Trigger Char", "amber", 2, True, "character", 2, 2, 1),
        CardDef("my_char", "My Char", "amber", 2, True, "character", 2, 2, 1),
    ]
    db = CardDatabase(cards)
    engine = GameEngine(db)

    state = GameState(players=[PlayerState(), PlayerState()], cards={})
    state.cards[1] = CardInstance(1, "trigger_char", owner=0, controller=0, zone="play")
    state.cards[2] = CardInstance(2, "my_char", owner=0, controller=0, zone="play")
    state.players[0].play = [1, 2]

    trigger = TriggerDef(
        id="controller_you_test",
        event="quest",
        on={"controller": "you"},
    )
    candidate = TriggerCandidate(
        source_instance_id=1,
        source_card=db.get("trigger_char"),
        trigger=trigger,
        ability_id="controller_you_test",
        ability_key="trigger_char:trigger:0",
        ability_index=0,
        source_zones=("play",),
    )

    pending = PendingTriggeredEvent(
        id="evt_1",
        event="quest",
        player_id=0,
        subject_card_id=2,  # My char controlled by same player as trigger source
    )

    result = trigger_matches_event(state, engine, candidate, pending)
    assert result is True


def test_object_on_filter_controller_opponent_matches_opposing_subject():
    """controller: "opponent" must match when subject is controlled by opponent."""
    from lorcana_bot.engine import GameEngine
    from lorcana_bot.cards import CardDatabase, CardDef, TriggerDef
    from lorcana_bot.state import GameState, CardInstance, PlayerState

    cards = [
        CardDef("trigger_char", "Trigger Char", "amber", 2, True, "character", 2, 2, 1),
        CardDef("their_char", "Their Char", "amber", 2, True, "character", 2, 2, 1),
    ]
    db = CardDatabase(cards)
    engine = GameEngine(db)

    state = GameState(players=[PlayerState(), PlayerState()], cards={})
    state.cards[1] = CardInstance(1, "trigger_char", owner=0, controller=0, zone="play")
    state.cards[2] = CardInstance(2, "their_char", owner=1, controller=1, zone="play")
    state.players[0].play = [1]
    state.players[1].play = [2]

    trigger = TriggerDef(
        id="controller_opp_test",
        event="quest",
        on={"controller": "opponent"},
    )
    candidate = TriggerCandidate(
        source_instance_id=1,
        source_card=db.get("trigger_char"),
        trigger=trigger,
        ability_id="controller_opp_test",
        ability_key="trigger_char:trigger:0",
        ability_index=0,
        source_zones=("play",),
    )

    pending = PendingTriggeredEvent(
        id="evt_1",
        event="quest",
        player_id=1,  # Opponent performed the action
        subject_card_id=2,  # Their char controlled by opponent
    )

    result = trigger_matches_event(state, engine, candidate, pending)
    assert result is True


def test_object_on_filter_card_type_song_matches_song_action():
    """cardType: "song" must match action cards with action_subtype == "song"."""
    from lorcana_bot.engine import GameEngine
    from lorcana_bot.cards import CardDatabase, CardDef, TriggerDef, EffectDef
    from lorcana_bot.state import GameState, CardInstance, PlayerState

    cards = [
        CardDef("trigger_char", "Trigger Char", "amber", 2, True, "character", 2, 2, 1),
        CardDef(
            "my_song",
            "My Song",
            "amethyst",
            2,
            True,
            "action",
            effects=(EffectDef("draw", 1),),
            action_subtype="song",
        ),
    ]
    db = CardDatabase(cards)
    engine = GameEngine(db)

    state = GameState(players=[PlayerState(), PlayerState()], cards={})
    state.cards[1] = CardInstance(1, "trigger_char", owner=0, controller=0, zone="play")
    state.cards[2] = CardInstance(2, "my_song", owner=0, controller=0, zone="play")
    state.players[0].play = [1, 2]

    trigger = TriggerDef(
        id="song_type_test",
        event="quest",
        on={"cardType": "song"},
    )
    candidate = TriggerCandidate(
        source_instance_id=1,
        source_card=db.get("trigger_char"),
        trigger=trigger,
        ability_id="song_type_test",
        ability_key="trigger_char:trigger:0",
        ability_index=0,
        source_zones=("play",),
    )

    pending = PendingTriggeredEvent(
        id="evt_1",
        event="quest",
        player_id=0,
        subject_card_id=2,  # My song action
    )

    result = trigger_matches_event(state, engine, candidate, pending)
    assert result is True


def test_object_on_filter_classification_uses_subtypes():
    """classification filter must check CardDef.subtypes first."""
    from lorcana_bot.engine import GameEngine
    from lorcana_bot.cards import CardDatabase, CardDef, TriggerDef
    from lorcana_bot.state import GameState, CardInstance, PlayerState

    cards = [
        CardDef(
            "trigger_char",
            "Trigger Char",
            "amber",
            2,
            True,
            "character",
            2,
            2,
            1,
            subtypes=["Princess", "Folk"],
        ),
        CardDef(
            "princess_char",
            "Princess Char",
            "amber",
            2,
            True,
            "character",
            2,
            2,
            1,
            subtypes=["Princess"],
        ),
    ]
    db = CardDatabase(cards)
    engine = GameEngine(db)

    state = GameState(players=[PlayerState(), PlayerState()], cards={})
    state.cards[1] = CardInstance(1, "trigger_char", owner=0, controller=0, zone="play")
    state.cards[2] = CardInstance(2, "princess_char", owner=0, controller=0, zone="play")
    state.players[0].play = [1, 2]

    trigger = TriggerDef(
        id="classification_test",
        event="quest",
        on={"classification": "Princess"},
    )
    candidate = TriggerCandidate(
        source_instance_id=1,
        source_card=db.get("trigger_char"),
        trigger=trigger,
        ability_id="classification_test",
        ability_key="trigger_char:trigger:0",
        ability_index=0,
        source_zones=("play",),
    )

    pending = PendingTriggeredEvent(
        id="evt_1",
        event="quest",
        player_id=0,
        subject_card_id=2,  # Princess char
    )

    result = trigger_matches_event(state, engine, candidate, pending)
    assert result is True


def test_object_on_filter_ink_type_matches_subject_ink():
    """ink-type filter must match subject card's ink types."""
    from lorcana_bot.engine import GameEngine
    from lorcana_bot.cards import CardDatabase, CardDef, TriggerDef
    from lorcana_bot.state import GameState, CardInstance, PlayerState

    cards = [
        CardDef("trigger_char", "Trigger Char", "amber", 2, True, "character", 2, 2, 1),
        CardDef("steel_char", "Steel Char", "steel", 2, True, "character", 2, 2, 1),
    ]
    db = CardDatabase(cards)
    engine = GameEngine(db)

    state = GameState(players=[PlayerState(), PlayerState()], cards={})
    state.cards[1] = CardInstance(1, "trigger_char", owner=0, controller=0, zone="play")
    state.cards[2] = CardInstance(2, "steel_char", owner=0, controller=0, zone="play")
    state.players[0].play = [1, 2]

    trigger = TriggerDef(
        id="ink_type_test",
        event="quest",
        on={"filters": [{"type": "ink-type", "inkType": "steel"}]},
    )
    candidate = TriggerCandidate(
        source_instance_id=1,
        source_card=db.get("trigger_char"),
        trigger=trigger,
        ability_id="ink_type_test",
        ability_key="trigger_char:trigger:0",
        ability_index=0,
        source_zones=("play",),
    )

    pending = PendingTriggeredEvent(
        id="evt_1",
        event="quest",
        player_id=0,
        subject_card_id=2,  # Steel char
    )

    result = trigger_matches_event(state, engine, candidate, pending)
    assert result is True


def test_object_on_filter_damaged_exerted_ready_keywords():
    """damaged, exerted, and ready filters must work correctly."""
    from lorcana_bot.engine import GameEngine
    from lorcana_bot.cards import CardDatabase, CardDef, TriggerDef
    from lorcana_bot.state import GameState, CardInstance, PlayerState

    cards = [
        CardDef("trigger_char", "Trigger Char", "amber", 2, True, "character", 2, 2, 1),
        CardDef("damaged_char", "Damaged Char", "amber", 2, True, "character", 2, 2, 1),
        CardDef("exerted_char", "Exerted Char", "amber", 2, True, "character", 2, 2, 1),
        CardDef("ready_char", "Ready Char", "amber", 2, True, "character", 2, 2, 1),
    ]
    db = CardDatabase(cards)
    engine = GameEngine(db)

    state = GameState(players=[PlayerState(), PlayerState()], cards={})
    state.cards[1] = CardInstance(1, "trigger_char", owner=0, controller=0, zone="play")
    state.cards[2] = CardInstance(2, "damaged_char", owner=0, controller=0, zone="play", damage=2)
    # CardInstance uses exerted boolean field
    state.cards[3] = CardInstance(3, "exerted_char", owner=0, controller=0, zone="play", exerted=True)
    state.cards[4] = CardInstance(4, "ready_char", owner=0, controller=0, zone="play")
    state.players[0].play = [1, 2, 3, 4]

    trigger_damaged = TriggerDef(
        id="damaged_test",
        event="quest",
        on={"filters": [{"type": "damaged"}]},
    )
    candidate_damaged = TriggerCandidate(
        source_instance_id=1,
        source_card=db.get("trigger_char"),
        trigger=trigger_damaged,
        ability_id="damaged_test",
        ability_key="trigger_char:trigger:0",
        ability_index=0,
        source_zones=("play",),
    )
    pending_damaged = PendingTriggeredEvent(
        id="evt_1",
        event="quest",
        player_id=0,
        subject_card_id=2,  # Damaged char
    )
    assert trigger_matches_event(state, engine, candidate_damaged, pending_damaged) is True

    trigger_exerted = TriggerDef(
        id="exerted_test",
        event="quest",
        on={"filters": [{"type": "exerted"}]},
    )
    candidate_exerted = TriggerCandidate(
        source_instance_id=1,
        source_card=db.get("trigger_char"),
        trigger=trigger_exerted,
        ability_id="exerted_test",
        ability_key="trigger_char:trigger:1",
        ability_index=1,
        source_zones=("play",),
    )
    pending_exerted = PendingTriggeredEvent(
        id="evt_2",
        event="quest",
        player_id=0,
        subject_card_id=3,  # Exerted char
    )
    assert trigger_matches_event(state, engine, candidate_exerted, pending_exerted) is True

    trigger_ready = TriggerDef(
        id="ready_test",
        event="quest",
        on={"filters": [{"type": "ready"}]},
    )
    candidate_ready = TriggerCandidate(
        source_instance_id=1,
        source_card=db.get("trigger_char"),
        trigger=trigger_ready,
        ability_id="ready_test",
        ability_key="trigger_char:trigger:2",
        ability_index=2,
        source_zones=("play",),
    )
    pending_ready = PendingTriggeredEvent(
        id="evt_3",
        event="quest",
        player_id=0,
        subject_card_id=4,  # Ready char
    )
    assert trigger_matches_event(state, engine, candidate_ready, pending_ready) is True


def test_object_on_filter_at_location_source_matches():
    """at-location filter with location: "source" must match trigger source's location."""
    from lorcana_bot.engine import GameEngine
    from lorcana_bot.cards import CardDatabase, CardDef, TriggerDef
    from lorcana_bot.state import GameState, CardInstance, PlayerState

    cards = [
        CardDef("trigger_char", "Trigger Char", "amber", 2, True, "character", 2, 2, 1),
        CardDef("neighbor_char", "Neighbor Char", "amber", 2, True, "character", 2, 2, 1),
    ]
    db = CardDatabase(cards)
    engine = GameEngine(db)

    state = GameState(players=[PlayerState(), PlayerState()], cards={})
    state.cards[1] = CardInstance(1, "trigger_char", owner=0, controller=0, zone="play", location_instance_id=99)
    state.cards[2] = CardInstance(2, "neighbor_char", owner=0, controller=0, zone="play", location_instance_id=99)
    state.players[0].play = [1, 2]

    trigger = TriggerDef(
        id="at_location_test",
        event="quest",
        on={"filters": [{"type": "at-location", "location": "source"}]},
    )
    candidate = TriggerCandidate(
        source_instance_id=1,
        source_card=db.get("trigger_char"),
        trigger=trigger,
        ability_id="at_location_test",
        ability_key="trigger_char:trigger:0",
        ability_index=0,
        source_zones=("play",),
    )

    pending = PendingTriggeredEvent(
        id="evt_1",
        event="quest",
        player_id=0,
        subject_card_id=2,  # Neighbor at same location as source (99)
    )

    result = trigger_matches_event(state, engine, candidate, pending)
    assert result is True


def test_object_on_filter_unknown_filter_type_fails_closed():
    """Unknown filter types must return False (fail closed)."""
    from lorcana_bot.engine import GameEngine
    from lorcana_bot.cards import CardDatabase, CardDef, TriggerDef
    from lorcana_bot.state import GameState, CardInstance, PlayerState

    cards = [
        CardDef("trigger_char", "Trigger Char", "amber", 2, True, "character", 2, 2, 1),
        CardDef("target_char", "Target Char", "amber", 2, True, "character", 2, 2, 1),
    ]
    db = CardDatabase(cards)
    engine = GameEngine(db)

    state = GameState(players=[PlayerState(), PlayerState()], cards={})
    state.cards[1] = CardInstance(1, "trigger_char", owner=0, controller=0, zone="play")
    state.cards[2] = CardInstance(2, "target_char", owner=0, controller=0, zone="play")
    state.players[0].play = [1, 2]

    trigger = TriggerDef(
        id="unknown_filter_test",
        event="quest",
        on={"filters": [{"type": "unknown-filter-type", "value": "test"}]},
    )
    candidate = TriggerCandidate(
        source_instance_id=1,
        source_card=db.get("trigger_char"),
        trigger=trigger,
        ability_id="unknown_filter_test",
        ability_key="trigger_char:trigger:0",
        ability_index=0,
        source_zones=("play",),
    )

    pending = PendingTriggeredEvent(
        id="evt_1",
        event="quest",
        player_id=0,
        subject_card_id=2,
    )

    result = trigger_matches_event(state, engine, candidate, pending)
    assert result is False


def test_characters_here_does_not_match_character_elsewhere():
    """CHARACTERS_HERE must not match when subject is at different location."""
    from lorcana_bot.engine import GameEngine
    from lorcana_bot.cards import CardDatabase, CardDef, TriggerDef
    from lorcana_bot.state import GameState, CardInstance, PlayerState

    cards = [
        CardDef("trigger_char", "Trigger Char", "amber", 2, True, "character", 2, 2, 1),
        CardDef("distant_char", "Distant Char", "amber", 2, True, "character", 2, 2, 1),
    ]
    db = CardDatabase(cards)
    engine = GameEngine(db)

    state = GameState(players=[PlayerState(), PlayerState()], cards={})
    # Trigger source at location 1
    state.cards[1] = CardInstance(1, "trigger_char", owner=0, controller=0, zone="play", location_instance_id=1)
    # Subject character at different location (99)
    state.cards[2] = CardInstance(2, "distant_char", owner=0, controller=0, zone="play", location_instance_id=99)
    state.players[0].play = [1, 2]

    trigger = TriggerDef(id="characters_here_test", event="quest", on="CHARACTERS_HERE")
    candidate = TriggerCandidate(
        source_instance_id=1,
        source_card=db.get("trigger_char"),
        trigger=trigger,
        ability_id="characters_here_test",
        ability_key="trigger_char:trigger:0",
        ability_index=0,
        source_zones=("play",),
    )

    pending = PendingTriggeredEvent(
        id="evt_1",
        event="quest",
        player_id=0,
        subject_card_id=2,  # The distant character
    )

    result = trigger_matches_event(state, engine, candidate, pending)
    assert result is False


def test_your_items_matches_controlled_item_subject():
    """YOUR_ITEMS must match when subject is an item you control."""
    from lorcana_bot.engine import GameEngine
    from lorcana_bot.cards import CardDatabase, CardDef, TriggerDef
    from lorcana_bot.state import GameState, CardInstance, PlayerState

    cards = [
        CardDef("trigger_char", "Trigger Char", "amber", 2, True, "character", 2, 2, 1),
        CardDef("my_item", "My Item", "sapphire", 1, True, "item"),
    ]
    db = CardDatabase(cards)
    engine = GameEngine(db)

    state = GameState(players=[PlayerState(), PlayerState()], cards={})
    state.cards[1] = CardInstance(1, "trigger_char", owner=0, controller=0, zone="play")
    state.cards[2] = CardInstance(2, "my_item", owner=0, controller=0, zone="play")
    state.players[0].play = [1, 2]

    trigger = TriggerDef(id="your_items_test", event="quest", on="YOUR_ITEMS")
    candidate = TriggerCandidate(
        source_instance_id=1,
        source_card=db.get("trigger_char"),
        trigger=trigger,
        ability_id="your_items_test",
        ability_key="trigger_char:trigger:0",
        ability_index=0,
        source_zones=("play",),
    )

    pending = PendingTriggeredEvent(
        id="evt_1",
        event="quest",
        player_id=0,
        subject_card_id=2,  # My item
    )

    result = trigger_matches_event(state, engine, candidate, pending)
    assert result is True


def test_your_songs_matches_controlled_song_action_subject():
    """YOUR_SONGS must match when subject is a song action you control."""
    from lorcana_bot.engine import GameEngine
    from lorcana_bot.cards import CardDatabase, CardDef, EffectDef, TriggerDef
    from lorcana_bot.state import GameState, CardInstance, PlayerState

    cards = [
        CardDef("trigger_char", "Trigger Char", "amber", 2, True, "character", 2, 2, 1),
        CardDef(
            "my_song",
            "My Song",
            "amethyst",
            2,
            True,
            "action",
            effects=(EffectDef("draw", 1),),
            action_subtype="song",
            subtypes=("Song",),
        ),
    ]
    db = CardDatabase(cards)
    engine = GameEngine(db)

    state = GameState(players=[PlayerState(), PlayerState()], cards={})
    state.cards[1] = CardInstance(1, "trigger_char", owner=0, controller=0, zone="play")
    state.cards[2] = CardInstance(2, "my_song", owner=0, controller=0, zone="play")
    state.players[0].play = [1, 2]

    trigger = TriggerDef(id="your_songs_test", event="quest", on="YOUR_SONGS")
    candidate = TriggerCandidate(
        source_instance_id=1,
        source_card=db.get("trigger_char"),
        trigger=trigger,
        ability_id="your_songs_test",
        ability_key="trigger_char:trigger:0",
        ability_index=0,
        source_zones=("play",),
    )

    pending = PendingTriggeredEvent(
        id="evt_1",
        event="quest",
        player_id=0,
        subject_card_id=2,  # My song action
    )

    result = trigger_matches_event(state, engine, candidate, pending)
    assert result is True


def test_your_characters_or_locations_with_card_under_matches_stack_source():
    """YOUR_CHARACTERS_OR_LOCATIONS_WITH_CARD_UNDER must match controlled stack sources."""
    from lorcana_bot.engine import GameEngine
    from lorcana_bot.cards import CardDatabase, CardDef, TriggerDef
    from lorcana_bot.state import GameState, CardInstance, PlayerState

    cards = [
        CardDef("trigger_char", "Trigger Char", "amber", 2, True, "character", 2, 2, 1),
        CardDef("stack_char", "Stack Char", "amber", 2, True, "character", 2, 2, 1),
    ]
    db = CardDatabase(cards)
    engine = GameEngine(db)

    state = GameState(players=[PlayerState(), PlayerState()], cards={})
    state.cards[1] = CardInstance(1, "trigger_char", owner=0, controller=0, zone="play")
    # Stack char has cards under it
    state.cards[2] = CardInstance(2, "stack_char", owner=0, controller=0, zone="play", cards_under=[3])
    state.players[0].play = [1, 2]

    trigger = TriggerDef(id="stack_test", event="quest", on="YOUR_CHARACTERS_OR_LOCATIONS_WITH_CARD_UNDER")
    candidate = TriggerCandidate(
        source_instance_id=1,
        source_card=db.get("trigger_char"),
        trigger=trigger,
        ability_id="stack_test",
        ability_key="trigger_char:trigger:0",
        ability_index=0,
        source_zones=("play",),
    )

    pending = PendingTriggeredEvent(
        id="evt_1",
        event="quest",
        player_id=0,
        subject_card_id=2,  # Stack char with cards under
    )

    result = trigger_matches_event(state, engine, candidate, pending)
    assert result is True


def test_string_item_and_action_filters_require_matching_card_type():
    """YOUR_ITEMS and YOUR_ACTIONS must not match controlled non-matching card types."""
    from lorcana_bot.engine import GameEngine
    from lorcana_bot.cards import CardDatabase, CardDef, TriggerDef
    from lorcana_bot.state import GameState, CardInstance, PlayerState

    cards = [
        CardDef("trigger_char", "Trigger Char", "amber", 2, True, "character", 2, 2, 1),
        CardDef("item_card", "Item Card", "amber", 2, True, "item"),
        CardDef("action_card", "Action Card", "amber", 2, True, "action"),
    ]
    db = CardDatabase(cards)
    engine = GameEngine(db)

    state = GameState(players=[PlayerState(), PlayerState()], cards={})
    state.cards[1] = CardInstance(1, "trigger_char", owner=0, controller=0, zone="play")
    state.cards[2] = CardInstance(2, "item_card", owner=0, controller=0, zone="play")
    state.cards[3] = CardInstance(3, "action_card", owner=0, controller=0, zone="discard")
    state.players[0].play = [1, 2]
    state.players[0].discard = [3]

    item_trigger = TriggerDef(id="your_items", event="quest", on="YOUR_ITEMS")
    item_candidate = TriggerCandidate(
        source_instance_id=1,
        source_card=db.get("trigger_char"),
        trigger=item_trigger,
        ability_id="your_items",
        ability_key="trigger_char:trigger:0",
        ability_index=0,
        source_zones=("play",),
    )
    assert trigger_matches_event(
        state,
        engine,
        item_candidate,
        PendingTriggeredEvent(id="evt_item", event="quest", player_id=0, subject_card_id=2),
    ) is True
    assert trigger_matches_event(
        state,
        engine,
        item_candidate,
        PendingTriggeredEvent(id="evt_not_item", event="quest", player_id=0, subject_card_id=1),
    ) is False

    action_trigger = TriggerDef(id="your_actions", event="play", on="YOUR_ACTIONS")
    action_candidate = TriggerCandidate(
        source_instance_id=1,
        source_card=db.get("trigger_char"),
        trigger=action_trigger,
        ability_id="your_actions",
        ability_key="trigger_char:trigger:1",
        ability_index=1,
        source_zones=("play",),
    )
    assert trigger_matches_event(
        state,
        engine,
        action_candidate,
        PendingTriggeredEvent(id="evt_action", event="play", player_id=0, subject_card_id=3),
    ) is True
    assert trigger_matches_event(
        state,
        engine,
        action_candidate,
        PendingTriggeredEvent(id="evt_not_action", event="play", player_id=0, subject_card_id=2),
    ) is False


def test_object_on_filter_unknown_top_level_key_fails_closed():
    """Unknown object on-filter keys must fail closed rather than being ignored."""
    from lorcana_bot.engine import GameEngine
    from lorcana_bot.cards import CardDatabase, CardDef, TriggerDef
    from lorcana_bot.state import GameState, CardInstance, PlayerState

    cards = [
        CardDef("trigger_char", "Trigger Char", "amber", 2, True, "character", 2, 2, 1),
        CardDef("target_char", "Target Char", "amber", 2, True, "character", 2, 2, 1),
    ]
    db = CardDatabase(cards)
    engine = GameEngine(db)
    state = GameState(players=[PlayerState(), PlayerState()], cards={})
    state.cards[1] = CardInstance(1, "trigger_char", owner=0, controller=0, zone="play")
    state.cards[2] = CardInstance(2, "target_char", owner=0, controller=0, zone="play")
    state.players[0].play = [1, 2]

    trigger = TriggerDef(id="unknown_object_key", event="quest", on={"controller": "you", "unknownKey": True})
    candidate = TriggerCandidate(
        source_instance_id=1,
        source_card=db.get("trigger_char"),
        trigger=trigger,
        ability_id="unknown_object_key",
        ability_key="trigger_char:trigger:0",
        ability_index=0,
        source_zones=("play",),
    )

    assert trigger_matches_event(
        state,
        engine,
        candidate,
        PendingTriggeredEvent(id="evt_unknown_object_key", event="quest", player_id=0, subject_card_id=2),
    ) is False
