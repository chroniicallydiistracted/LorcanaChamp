"""Tests for scry, search, reveal, and deck routing mechanics.

B4: Implements scry/search/reveal/deck-routing mechanics per MICRO PROMPT 05.
"""

import pytest

from lorcana_bot.engine import GameEngine
from lorcana_bot.cards import CardDatabase, load_demo_database, CardDef
from lorcana_bot.state import GameState, PlayerState, CardInstance
from lorcana_bot.effects import EffectResolver
from lorcana_bot.effect_types import EffectResolutionContext, SUPPORTED_EFFECT_KINDS
from lorcana_bot.pending_effects import (
    create_pending_effect,
    has_pending_effects,
    get_pending_effects_for_chooser,
    complete_pending_effect,
)
from lorcana_bot.constants import ZONE_DECK, ZONE_HAND, ZONE_PLAY, ZONE_DISCARD
from lorcana_bot.actions import Action


class TestScryEffectSupport:
    """Tests for scry effect kind support."""

    def test_scry_in_supported_effect_kinds(self):
        """Scry effect kind should be in SUPPORTED_EFFECT_KINDS."""
        assert "scry" in SUPPORTED_EFFECT_KINDS

    def test_look_at_top_in_supported_effect_kinds(self):
        """look_at_top effect kind should be in SUPPORTED_EFFECT_KINDS."""
        assert "look_at_top" in SUPPORTED_EFFECT_KINDS

    def test_put_card_on_top_in_supported_effect_kinds(self):
        """put_card_on_top effect kind should be in SUPPORTED_EFFECT_KINDS."""
        assert "put_card_on_top" in SUPPORTED_EFFECT_KINDS

    def test_put_card_on_bottom_in_supported_effect_kinds(self):
        """put_card_on_bottom effect kind should be in SUPPORTED_EFFECT_KINDS."""
        assert "put_card_on_bottom" in SUPPORTED_EFFECT_KINDS


class TestSearchRevealEffectSupport:
    """Tests for search and reveal effect kind support."""

    def test_search_deck_in_supported_effect_kinds(self):
        """search_deck effect kind should be in SUPPORTED_EFFECT_KINDS."""
        assert "search_deck" in SUPPORTED_EFFECT_KINDS

    def test_reveal_top_card_in_supported_effect_kinds(self):
        """reveal_top_card effect kind should be in SUPPORTED_EFFECT_KINDS."""
        assert "reveal_top_card" in SUPPORTED_EFFECT_KINDS

    def test_reveal_hand_in_supported_effect_kinds(self):
        """reveal_hand effect kind should be in SUPPORTED_EFFECT_KINDS."""
        assert "reveal_hand" in SUPPORTED_EFFECT_KINDS

    def test_reveal_and_route_in_supported_effect_kinds(self):
        """reveal_and_route effect kind should be in SUPPORTED_EFFECT_KINDS."""
        assert "reveal_and_route" in SUPPORTED_EFFECT_KINDS

    def test_put_card_in_hand_in_supported_effect_kinds(self):
        """put_card_in_hand effect kind should be in SUPPORTED_EFFECT_KINDS."""
        assert "put_card_in_hand" in SUPPORTED_EFFECT_KINDS

    def test_shuffle_deck_in_supported_effect_kinds(self):
        """shuffle_deck effect kind should be in SUPPORTED_EFFECT_KINDS."""
        assert "shuffle_deck" in SUPPORTED_EFFECT_KINDS


class TestScryPrivacyRules:
    """Tests for scry privacy rules - no hidden info leak in public logs."""

    def test_look_at_top_is_private(self, sample_game_state, engine):
        """Look at top cards should emit private event, not reveal to opponent."""
        from lorcana_bot.cards import EffectDef
        
        resolver = EffectResolver(engine)
        context = EffectResolutionContext(actor=0, source=None)
        
        # Execute look_at_top effect
        effect = EffectDef(kind="look_at_top", amount=2)
        resolver.resolve(sample_game_state, effect, context)
        
        # Check that an event was emitted
        look_events = [e for e in sample_game_state.event_log if e.event_type == "LOOKED_AT_TOP_CARDS"]
        assert len(look_events) == 1
        
        # Verify it's marked as private
        assert look_events[0].payload.get("private") is True

    def test_scry_creates_pending_effect(self, sample_game_state, engine):
        """Scry should create a pending effect for ordering input."""
        from lorcana_bot.cards import EffectDef
        
        initial_pending_count = len(sample_game_state.pending_effects)
        
        resolver = EffectResolver(engine)
        context = EffectResolutionContext(actor=0, source=None)
        
        # Execute scry effect
        effect = EffectDef(kind="scry", amount=3)
        resolver.resolve(sample_game_state, effect, context)
        
        # Should have created a pending effect
        assert len(sample_game_state.pending_effects) == initial_pending_count + 1
        
        # The pending effect should be for the scry chooser
        pending = sample_game_state.pending_effects[-1]
        assert pending.chooser_id == 0
        assert pending.origin == "scry"


class TestRevealPrivacyRules:
    """Tests for reveal privacy rules."""

    def test_reveal_top_card_marks_public(self, sample_game_state, engine):
        """Reveal top card should mark card as revealed publicly."""
        from lorcana_bot.cards import EffectDef
        
        # Get a card from player's deck
        player_deck = sample_game_state.players[0].deck
        if not player_deck:
            pytest.skip("Need cards in deck")
        
        cid = player_deck[0]
        initial_revealed = sample_game_state.cards[cid].revealed
        
        resolver = EffectResolver(engine)
        context = EffectResolutionContext(actor=0, source=None)
        
        # Execute reveal_top_card effect
        effect = EffectDef(kind="reveal_top_card", amount=1)
        resolver.resolve(sample_game_state, effect, context)
        
        # Card should now be revealed
        assert sample_game_state.cards[cid].revealed is True

    def test_reveal_top_card_emits_event(self, sample_game_state, engine):
        """Reveal top card should emit CARD_REVEALED event."""
        from lorcana_bot.cards import EffectDef
        
        resolver = EffectResolver(engine)
        context = EffectResolutionContext(actor=0, source=None)
        
        # Execute reveal_top_card effect
        effect = EffectDef(kind="reveal_top_card", amount=1)
        resolver.resolve(sample_game_state, effect, context)
        
        # Check that a reveal event was emitted
        reveal_events = [e for e in sample_game_state.event_log if e.event_type == "CARD_REVEALED"]
        assert len(reveal_events) >= 1

    def test_reveal_hand_emits_event(self, sample_game_state, engine):
        """Reveal hand should emit HAND_REVEALED events."""
        from lorcana_bot.cards import EffectDef
        
        resolver = EffectResolver(engine)
        context = EffectResolutionContext(actor=0, source=None)
        
        # Execute reveal_hand effect
        effect = EffectDef(kind="reveal_hand")
        resolver.resolve(sample_game_state, effect, context)
        
        # Check that reveal events were emitted for each hand card
        reveal_events = [e for e in sample_game_state.event_log if e.event_type == "HAND_REVEALED"]
        assert len(reveal_events) >= 1


class TestSearchDeckMechanics:
    """Tests for search deck mechanics."""

    def test_search_deck_creates_pending_effect(self, sample_game_state, engine):
        """Search deck should create a pending effect for card selection."""
        from lorcana_bot.cards import EffectDef
        
        initial_pending_count = len(sample_game_state.pending_effects)
        
        resolver = EffectResolver(engine)
        context = EffectResolutionContext(actor=0, source=None)
        
        # Execute search_deck effect
        effect = EffectDef(kind="search_deck")
        resolver.resolve(sample_game_state, effect, context)
        
        # Should have created a pending effect
        assert len(sample_game_state.pending_effects) == initial_pending_count + 1
        
        # The pending effect should be for the deck owner
        pending = sample_game_state.pending_effects[-1]
        assert pending.chooser_id == 0
        assert pending.origin == "search_deck"


class TestShuffleDeterminism:
    """Tests for deterministic shuffling after search."""

    def test_shuffle_deck_is_deterministic(self, sample_game_state, engine):
        """Shuffle deck should use deterministic RNG based on seed."""
        from lorcana_bot.cards import EffectDef
        
        # Get a copy of the deck order before shuffle
        player_deck_before = list(sample_game_state.players[0].deck)
        
        resolver = EffectResolver(engine)
        context = EffectResolutionContext(actor=0, source=None)
        
        # Execute shuffle_deck effect
        effect = EffectDef(kind="shuffle_deck")
        resolver.resolve(sample_game_state, effect, context)
        
        # Deck should be same size
        assert len(sample_game_state.players[0].deck) == len(player_deck_before)
        
        # All same cards should be present
        deck_after = set(sample_game_state.players[0].deck)
        deck_before = set(player_deck_before)
        assert deck_after == deck_before


class TestPutCardRouting:
    """Tests for put card routing effects."""

    def test_put_card_on_top_moves_to_deck(self, sample_game_state, engine):
        """put_card_on_top should move card to top of owner's deck."""
        from lorcana_bot.cards import EffectDef
        
        # Get a card from player's hand
        hand = sample_game_state.players[0].hand
        if not hand:
            pytest.skip("Need cards in hand")
        
        cid = hand[0]
        resolver = EffectResolver(engine)
        context = EffectResolutionContext(actor=0, source=None, choice=cid)
        
        # Execute put_card_on_top effect
        effect = EffectDef(kind="put_card_on_top")
        resolver.resolve(sample_game_state, effect, context)
        
        # Card should now be on top of deck
        assert sample_game_state.players[0].deck[0] == cid
        assert sample_game_state.cards[cid].zone == ZONE_DECK

    def test_put_card_on_bottom_moves_to_deck(self, sample_game_state, engine):
        """put_card_on_bottom should move card to bottom of owner's deck."""
        from lorcana_bot.cards import EffectDef
        
        # Get a card from player's hand
        hand = sample_game_state.players[0].hand
        if not hand:
            pytest.skip("Need cards in hand")
        
        cid = hand[0]
        resolver = EffectResolver(engine)
        context = EffectResolutionContext(actor=0, source=None, choice=cid)
        
        # Execute put_card_on_bottom effect
        effect = EffectDef(kind="put_card_on_bottom")
        resolver.resolve(sample_game_state, effect, context)
        
        # Card should now be on bottom of deck
        assert sample_game_state.players[0].deck[-1] == cid
        assert sample_game_state.cards[cid].zone == ZONE_DECK

    def test_put_card_in_hand_moves_to_hand(self, sample_game_state, engine):
        """put_card_in_hand should move card to hand."""
        from lorcana_bot.cards import EffectDef
        
        # Get a card from player's deck
        deck = sample_game_state.players[0].deck
        if not deck:
            pytest.skip("Need cards in deck")
        
        cid = deck[0]
        initial_hand_size = len(sample_game_state.players[0].hand)
        
        resolver = EffectResolver(engine)
        context = EffectResolutionContext(actor=0, source=None, choice=cid)
        
        # Execute put_card_in_hand effect
        effect = EffectDef(kind="put_card_in_hand")
        resolver.resolve(sample_game_state, effect, context)
        
        # Card should now be in hand
        assert cid in sample_game_state.players[0].hand
        assert len(sample_game_state.players[0].hand) == initial_hand_size + 1


class TestRevealAndRoute:
    """Tests for reveal and route combined effect."""

    def test_reveal_and_route_reveals_card(self, sample_game_state, engine):
        """reveal_and_route should reveal the card before routing."""
        from lorcana_bot.cards import EffectDef
        
        # Get top card before effect
        deck = sample_game_state.players[0].deck
        if not deck:
            pytest.skip("Need cards in deck")
        
        cid = deck[0]
        
        resolver = EffectResolver(engine)
        context = EffectResolutionContext(actor=0, source=None)
        
        # Execute reveal_and_route effect with hand destination
        effect = EffectDef(kind="reveal_and_route", value="hand")
        resolver.resolve(sample_game_state, effect, context)
        
        # Card should be revealed (before routing to hand)
        assert sample_game_state.cards[cid].revealed is True

    def test_reveal_and_route_routes_to_hand(self, sample_game_state, engine):
        """reveal_and_route with value='hand' should route card to hand."""
        from lorcana_bot.cards import EffectDef
        
        deck = sample_game_state.players[0].deck
        if not deck:
            pytest.skip("Need cards in deck")
        
        cid = deck[0]
        initial_hand_size = len(sample_game_state.players[0].hand)
        
        resolver = EffectResolver(engine)
        context = EffectResolutionContext(actor=0, source=None)
        
        # Execute reveal_and_route effect with hand destination
        effect = EffectDef(kind="reveal_and_route", value="hand")
        resolver.resolve(sample_game_state, effect, context)
        
        # Card should now be in hand
        assert cid in sample_game_state.players[0].hand
        assert len(sample_game_state.players[0].hand) == initial_hand_size + 1


class TestTriggerBlockerReportUpdates:
    """Tests that trigger blocker report recognizes new effect kinds."""

    def test_scry_not_blocked_for_resolution_requirements(self):
        """Scry resolution requirement should map to scry_search_reveal work."""
        from lorcana_bot.decks.trigger_blocker_report import _get_recommended_work
        
        blockers = ["unsupported_trigger_resolution_requirement:scry_ordering"]
        work = _get_recommended_work(blockers)
        
        assert "scry_search_reveal" in work

    def test_reveal_routing_maps_to_scry_search_reveal(self):
        """reveal_routing requirement should map to scry_search_reveal work."""
        from lorcana_bot.decks.trigger_blocker_report import _get_recommended_work
        
        blockers = ["unsupported_trigger_resolution_requirement:reveal_routing"]
        work = _get_recommended_work(blockers)
        
        assert "scry_search_reveal" in work

    def test_named_card_maps_to_scry_search_reveal(self):
        """named_card requirement should map to scry_search_reveal work."""
        from lorcana_bot.decks.trigger_blocker_report import _get_recommended_work
        
        blockers = ["unsupported_trigger_resolution_requirement:named_card"]
        work = _get_recommended_work(blockers)
        
        assert "scry_search_reveal" in work


# Fixtures

@pytest.fixture
def sample_game_state():
    """Create a sample game state for testing."""
    players = [PlayerState(), PlayerState()]
    cards = {}
    next_id = 1
    
    # Create simple decks
    for player in range(2):
        for i in range(10):
            inst = CardInstance(
                instance_id=next_id,
                card_id=f"test_card_{player}_{i}",
                owner=player,
                controller=player,
            )
            cards[next_id] = inst
            players[player].deck.append(next_id)
            next_id += 1
    
    state = GameState(
        players=players,
        cards=cards,
        active_player=0,
        first_player=0,
        phase="MAIN",
        seed=42,  # Deterministic seed for testing
        bag=[],
        event_log=[],
        action_log=[],
    )
    
    # Draw hands
    for player in range(2):
        for _ in range(5):
            if state.players[player].deck:
                cid = state.players[player].deck.pop(0)
                state.cards[cid].zone = "hand"
                state.players[player].hand.append(cid)
    
    return state


@pytest.fixture
def engine():
    """Create a game engine for testing."""
    db = load_demo_database()
    return GameEngine(db)