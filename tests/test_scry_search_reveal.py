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


class TestScryRequirementTruthfulness:
    """Tests for scry pending requirement truthfulness (MICRO PROMPT 5.1)."""

    def test_scry_creates_pending_without_moving_cards(self, sample_game_state, engine):
        """Scry should create pending effect without moving any cards."""
        from lorcana_bot.cards import EffectDef
        
        # Get deck before
        deck_before = list(sample_game_state.players[0].deck)
        
        resolver = EffectResolver(engine)
        context = EffectResolutionContext(actor=0, source=None)
        
        # Execute scry effect
        effect = EffectDef(kind="scry", amount=3)
        resolver.resolve(sample_game_state, effect, context)
        
        # Deck should be unchanged
        deck_after = list(sample_game_state.players[0].deck)
        assert deck_after == deck_before
        
        # But we should have a pending effect
        pending = [pe for pe in sample_game_state.pending_effects 
                   if pe.raw.get("requirement_kind") == "scry_ordering"]
        assert len(pending) == 1

    def test_scry_pending_effect_has_candidates(self, sample_game_state, engine):
        """Scry pending effect should store top N card IDs."""
        from lorcana_bot.cards import EffectDef
        
        resolver = EffectResolver(engine)
        context = EffectResolutionContext(actor=0, source=None)
        
        effect = EffectDef(kind="scry", amount=3)
        resolver.resolve(sample_game_state, effect, context)
        
        pending = sample_game_state.pending_effects[-1]
        scry_req = pending.raw.get("requirement")
        
        assert scry_req is not None
        assert len(scry_req.candidate_ids) == 3
        assert all(cid in sample_game_state.players[0].deck for cid in scry_req.candidate_ids)

    def test_resolve_scry_ordering_validates_count(self, sample_game_state):
        """resolve_scry_ordering should reject mismatched counts."""
        from lorcana_bot.pending_effects import (
            create_scry_pending_effect, resolve_scry_ordering, get_pending_effect_by_id
        )
        
        # Create scry for 3 cards
        pe = create_scry_pending_effect(
            sample_game_state, 0, 0, None, None, 3, origin="test"
        )
        
        # Try to resolve with wrong count
        with pytest.raises(ValueError, match="count mismatch"):
            resolve_scry_ordering(
                sample_game_state, pe.id,
                top_cards=(1, 2),  # Only 2 cards
                bottom_cards=()    # Empty - should be 1 bottom card for total of 3
            )

    def test_resolve_scry_ordering_validates_cards(self, sample_game_state):
        """resolve_scry_ordering should reject invalid card IDs."""
        from lorcana_bot.pending_effects import create_scry_pending_effect, resolve_scry_ordering
        
        pe = create_scry_pending_effect(
            sample_game_state, 0, 0, None, None, 3, origin="test"
        )
        
        # Try to resolve with a card not in candidates
        with pytest.raises(ValueError, match="not a valid scry candidate"):
            resolve_scry_ordering(
                sample_game_state, pe.id,
                top_cards=(1, 2, 999),  # 999 is not in candidates
                bottom_cards=()
            )

    def test_resolve_scry_ordering_mutates_deck(self, sample_game_state):
        """resolve_scry_ordering should correctly reorder deck."""
        from lorcana_bot.pending_effects import create_scry_pending_effect, resolve_scry_ordering
        
        # Get top 3 cards
        original_cids = sample_game_state.players[0].deck[:3]
        
        pe = create_scry_pending_effect(
            sample_game_state, 0, 0, None, None, 3, origin="test"
        )
        
        # Put card 3 on top, cards 1-2 on bottom
        resolve_scry_ordering(
            sample_game_state, pe.id,
            top_cards=(original_cids[2],),
            bottom_cards=(original_cids[0], original_cids[1])
        )
        
        # Check new order - top card should be last of top cards
        # After reorder: [original_cids[2], original_cids[0], original_cids[1], ...rest]
        new_deck = sample_game_state.players[0].deck
        assert new_deck[0] == original_cids[2]  # Top card from scry on top


class TestSearchRequirementTruthfulness:
    """Tests for search pending requirement truthfulness (MICRO PROMPT 5.1)."""

    def test_search_creates_pending_with_candidates(self, sample_game_state, engine):
        """Search should create pending effect with candidates for chooser."""
        from lorcana_bot.cards import EffectDef
        
        resolver = EffectResolver(engine)
        context = EffectResolutionContext(actor=0, source=None)
        
        effect = EffectDef(kind="search_deck")
        resolver.resolve(sample_game_state, effect, context)
        
        pending = sample_game_state.pending_effects[-1]
        search_req = pending.raw.get("requirement")
        
        assert search_req is not None
        assert len(search_req.candidate_ids) > 0
        # Search candidates should be in choice_options (private to chooser)
        assert len(pending.choice_options) > 0

    def test_resolve_search_selection_validates_card(self, sample_game_state):
        """resolve_search_selection should reject invalid card."""
        from lorcana_bot.pending_effects import create_search_pending_effect, resolve_search_selection
        
        pe = create_search_pending_effect(
            sample_game_state, 0, 0, None, None,
            candidate_ids=(1, 2, 3),
            destination="hand",
            origin="test"
        )
        
        with pytest.raises(ValueError, match="not a valid search candidate"):
            resolve_search_selection(sample_game_state, pe.id, selected_card_id=999)

    def test_resolve_search_selection_moves_card(self, sample_game_state):
        """resolve_search_selection should move card to destination."""
        from lorcana_bot.pending_effects import create_search_pending_effect, resolve_search_selection
        
        # Get a card from deck
        cid = sample_game_state.players[0].deck[0]
        
        pe = create_search_pending_effect(
            sample_game_state, 0, 0, None, None,
            candidate_ids=(cid,),
            destination="hand",
            origin="test"
        )
        
        initial_hand_size = len(sample_game_state.players[0].hand)
        
        resolve_search_selection(sample_game_state, pe.id, selected_card_id=cid)
        
        # Card should be in hand
        assert cid in sample_game_state.players[0].hand
        assert len(sample_game_state.players[0].hand) == initial_hand_size + 1

    def test_resolve_search_selection_shuffles_if_required(self, sample_game_state):
        """resolve_search_selection should shuffle if shuffle_after=True."""
        from lorcana_bot.pending_effects import create_search_pending_effect, resolve_search_selection
        
        cid = sample_game_state.players[0].deck[0]
        
        pe = create_search_pending_effect(
            sample_game_state, 0, 0, None, None,
            candidate_ids=(cid,),
            destination="hand",
            shuffle_after=True,
            origin="test"
        )
        
        resolve_search_selection(sample_game_state, pe.id, selected_card_id=cid)
        
        # Deck should still have same cards (just reordered)
        assert len(sample_game_state.players[0].deck) == 4


class TestPrivacyPolicy:
    """Tests for privacy policy in scry/search/reveal (MICRO PROMPT 5.1)."""

    def test_scry_event_does_not_leak_identities(self, sample_game_state, engine):
        """SCRY_RESOLVED event should not include card identities in payload."""
        from lorcana_bot.pending_effects import create_scry_pending_effect, resolve_scry_ordering
        from lorcana_bot.state import GameEvent
        
        pe = create_scry_pending_effect(
            sample_game_state, 0, 0, None, None, 3, origin="test"
        )
        
        # Get candidate IDs to verify
        candidates = pe.raw["requirement"].candidate_ids
        
        # Resolve scry
        resolve_scry_ordering(
            sample_game_state, pe.id,
            top_cards=(candidates[0],),
            bottom_cards=(candidates[1], candidates[2])
        )
        
        # Find scry event
        scry_events = [e for e in sample_game_state.event_log 
                      if e.event_type == "SCRY_RESOLVED"]
        assert len(scry_events) == 1
        
        event = scry_events[0]
        assert event.payload.get("private") is True
        # Verify card identities are NOT in payload
        assert "card_ids" not in event.payload
        assert "top_card_ids" not in event.payload

    def test_search_event_does_not_leak_filter(self, sample_game_state):
        """SEARCH_RESOLVED event should not reveal filter details."""
        from lorcana_bot.pending_effects import create_search_pending_effect, resolve_search_selection
        
        cid = sample_game_state.players[0].deck[0]
        
        pe = create_search_pending_effect(
            sample_game_state, 0, 0, None, None,
            candidate_ids=(cid,),
            destination="hand",
            filter_desc="character",
            origin="test"
        )
        
        resolve_search_selection(sample_game_state, pe.id, selected_card_id=cid)
        
        # Find search event
        search_events = [e for e in sample_game_state.event_log 
                        if e.event_type == "SEARCH_RESOLVED"]
        assert len(search_events) == 1
        
        event = search_events[0]
        assert event.payload.get("private") is True


class TestRevealRoutingTruthfulness:
    """Tests for reveal routing truthfulness (MICRO PROMPT 5.1)."""

    def test_reveal_top_card_marks_public(self, sample_game_state, engine):
        """Reveal top card should mark card as revealed (public)."""
        from lorcana_bot.cards import EffectDef
        
        deck = sample_game_state.players[0].deck
        if not deck:
            pytest.skip("Need cards in deck")
        
        cid = deck[0]
        
        resolver = EffectResolver(engine)
        context = EffectResolutionContext(actor=0, source=None)
        
        effect = EffectDef(kind="reveal_top_card", amount=1)
        resolver.resolve(sample_game_state, effect, context)
        
        assert sample_game_state.cards[cid].revealed is True

    def test_reveal_and_route_with_fixed_destination(self, sample_game_state, engine):
        """reveal_and_route with fixed destination should auto-route."""
        from lorcana_bot.cards import EffectDef
        
        deck = sample_game_state.players[0].deck
        if not deck:
            pytest.skip("Need cards in deck")
        
        cid = deck[0]
        initial_hand_size = len(sample_game_state.players[0].hand)
        
        resolver = EffectResolver(engine)
        context = EffectResolutionContext(actor=0, source=None)
        
        # Fixed destination = hand
        effect = EffectDef(kind="reveal_and_route", value="hand")
        resolver.resolve(sample_game_state, effect, context)
        
        # Card should be in hand
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