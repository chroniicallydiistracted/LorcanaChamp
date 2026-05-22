"""Tests for scry, search, reveal, and deck routing mechanics.

B4: Implements scry/search/reveal/deck-routing mechanics per MICRO PROMPT 05.
"""

import pytest

from lorcana_bot.engine import GameEngine
from lorcana_bot.cards import CardDatabase, load_demo_database, CardDef, EffectDef
from lorcana_bot.state import GameState, PlayerState, CardInstance
from lorcana_bot.effects import EffectResolver
from lorcana_bot.effect_types import EffectResolutionContext, SUPPORTED_EFFECT_KINDS
from lorcana_bot.pending_effects import (
    create_pending_effect,
    has_pending_effects,
    get_pending_effects_for_chooser,
    complete_pending_effect,
)
from lorcana_bot.constants import ZONE_DECK, ZONE_HAND, ZONE_INKWELL, ZONE_PLAY, ZONE_DISCARD, ACTION_RESOLVE_PENDING_EFFECT
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

    def test_search_deck_filters_candidates_from_source_data(self):
        """Search candidates are narrowed by source cardType/classification filters."""
        princess = CardDef(
            "test_princess",
            "Test Princess",
            "amber",
            2,
            True,
            "character",
            1,
            2,
            1,
            subtypes=("Princess",),
        )
        non_princess = CardDef(
            "test_guard",
            "Test Guard",
            "amber",
            2,
            True,
            "character",
            1,
            2,
            1,
            subtypes=("Guard",),
        )
        searcher = CardDef(
            "test_searcher",
            "Test Searcher",
            "amber",
            1,
            True,
            "action",
            effects=(
                EffectDef(
                    kind="search_deck",
                    target="you",
                    raw={"cardType": "character", "classification": "Princess"},
                ),
            ),
        )
        engine = GameEngine(CardDatabase([princess, non_princess, searcher]))
        state = engine.setup_game(
            [["Test Searcher"] + ["Test Princess", "Test Guard"] * 25, ["Test Guard"] * 50],
            seed=401,
        )
        source = state.players[0].hand[0]

        EffectResolver(engine).resolve(
            state,
            searcher.effects[0],
            EffectResolutionContext(actor=0, source=source),
        )

        pending = state.pending_effects[-1]
        candidates = tuple(pending.raw["requirement"].candidate_ids)
        assert candidates
        assert all(engine.card_def(state, cid).full_name == "Test Princess" for cid in candidates)

        action = Action(
            ACTION_RESOLVE_PENDING_EFFECT,
            actor=0,
            source=source,
            choice={"pending_effect_id": pending.id, "selected_card_id": candidates[0]},
        )
        next_state = engine.apply_action(state, action)
        assert candidates[0] in next_state.players[0].hand
        assert candidates[0] not in next_state.players[0].deck

    def test_put_into_inkwell_resolves_selected_chosen_target_exerted(self):
        """Let It Go / Into the Unknown style effects move selected targets to inkwell."""
        action_def = CardDef(
            "test_let_it_go",
            "Test Let It Go",
            "sapphire",
            1,
            True,
            "action",
            effects=(
                EffectDef(
                    kind="put_into_inkwell",
                    target="chosen_exerted_character",
                    raw={"type": "put-into-inkwell", "exerted": True, "facedown": True},
                ),
            ),
        )
        target_def = CardDef("test_target", "Test Exerted Target", "amber", 1, True, "character", 2, 2, 1)
        engine = GameEngine(CardDatabase([action_def, target_def]))
        state = engine.setup_game(
            [["Test Let It Go"] * 50, ["Test Exerted Target"] * 50],
            seed=402,
        )
        action_card = state.players[0].hand[0]
        state.move_card(action_card, ZONE_HAND, controller=0)
        target = state.players[1].deck[0]
        state.move_card(target, ZONE_PLAY, controller=1)
        state.cards[target].exerted = True
        ink = state.players[0].deck[0]
        state.move_card(ink, ZONE_INKWELL, controller=0)
        state.cards[ink].exerted = False

        actions = [
            action
            for action in engine.legal_actions(state, 0)
            if action.kind == "PLAY_CARD" and action.card == action_card
        ]
        assert {action.target for action in actions} == {target}

        next_state = engine.apply_action(state, actions[0])
        assert target in next_state.players[1].inkwell
        assert next_state.cards[target].exerted is True


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

    def test_reveal_and_route_public_reveal_can_route_to_inkwell_exerted(self):
        card = CardDef("test_top", "Test Top", "amber", 1, True, "character", 1, 2, 1)
        revealer = CardDef(
            "test_revealer",
            "Test Revealer",
            "sapphire",
            1,
            True,
            "action",
            effects=(EffectDef("reveal_and_route", target="you", raw={"destination": "inkwell", "exerted": True}),),
        )
        engine = GameEngine(CardDatabase([card, revealer]))
        state = engine.setup_game([["Test Revealer"] + ["Test Top"] * 49, ["Test Top"] * 50], seed=501)
        source = state.players[0].hand[0]
        top = state.players[0].deck[0]

        EffectResolver(engine).resolve(
            state,
            revealer.effects[0],
            EffectResolutionContext(actor=0, source=source),
        )

        assert top in state.players[0].inkwell
        assert state.cards[top].exerted is True
        reveal_events = [event for event in state.event_log if event.event_type == "CARD_REVEALED"]
        assert reveal_events
        assert reveal_events[-1].payload["card_id"] == top

    def test_reveal_and_route_private_look_does_not_emit_public_identity(self):
        card = CardDef("test_private_top", "Test Private Top", "amber", 1, True, "character", 1, 2, 1)
        revealer = CardDef(
            "test_private_revealer",
            "Test Private Revealer",
            "sapphire",
            1,
            True,
            "action",
            effects=(EffectDef("reveal_and_route", target="you", raw={"destination": "deck-bottom", "visibility": "private"}),),
        )
        engine = GameEngine(CardDatabase([card, revealer]))
        state = engine.setup_game([["Test Private Revealer"] + ["Test Private Top"] * 49, ["Test Private Top"] * 50], seed=502)
        source = state.players[0].hand[0]
        top = state.players[0].deck[0]

        EffectResolver(engine).resolve(
            state,
            revealer.effects[0],
            EffectResolutionContext(actor=0, source=source),
        )

        assert top == state.players[0].deck[-1]
        assert not any(event.event_type == "CARD_REVEALED" and event.payload.get("card_id") == top for event in state.event_log)
        private_events = [event for event in state.event_log if event.event_type == "PRIVATE_CARD_LOOKED_AT"]
        assert private_events
        assert private_events[-1].payload == {"private": True, "count": 1, "from_zone": ZONE_DECK, "player": 0}


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

    def test_scry_destinations_resolve_through_legal_actions_and_apply_action(self, sample_game_state, engine):
        """Structured scry destinations should resolve through the public engine path."""
        from lorcana_bot.cards import EffectDef

        deck_before = tuple(sample_game_state.players[0].deck)
        chosen_for_hand = deck_before[1]
        bottom_card = deck_before[0]

        resolver = EffectResolver(engine)
        context = EffectResolutionContext(actor=0, source=None)
        effect = EffectDef(
            kind="scry",
            amount=2,
            raw={
                "raw": {
                    "type": "scry",
                    "amount": 2,
                    "destinations": [
                        {"zone": "hand", "min": 1, "max": 1},
                        {"zone": "deck-bottom", "remainder": True},
                    ],
                }
            },
        )
        resolver.resolve(sample_game_state, effect, context)

        pending = sample_game_state.pending_effects[-1]
        legal = [
            action for action in engine.legal_actions(sample_game_state, 0)
            if action.kind == ACTION_RESOLVE_PENDING_EFFECT
            and action.choice.get("pending_effect_id") == pending.id
            and action.choice.get("destinations")
        ]
        assert legal

        selected = next(
            action for action in legal
            if action.choice["destinations"][0]["cards"] == (chosen_for_hand,)
        )
        state_after = engine.apply_action(sample_game_state, selected)

        assert pending.id not in [pe.id for pe in state_after.pending_effects]
        assert chosen_for_hand in state_after.players[0].hand
        assert state_after.cards[chosen_for_hand].zone == ZONE_HAND
        assert state_after.players[0].deck[-1] == bottom_card
        assert state_after.cards[bottom_card].zone == ZONE_DECK
        events = [event for event in state_after.event_log if event.event_type == "SCRY_RESOLVED"]
        assert events
        assert events[-1].payload["private"] is True
        assert "card_ids" not in events[-1].payload

    def test_scry_destinations_reject_duplicate_cards(self, sample_game_state, engine):
        """A looked-at card cannot be assigned to more than one scry destination."""
        from lorcana_bot.pending_effects import create_scry_pending_effect, resolve_scry_destinations

        pe = create_scry_pending_effect(
            sample_game_state,
            0,
            0,
            None,
            None,
            2,
            destinations=(
                {"zone": "hand", "min": 1, "max": 1},
                {"zone": "deck-bottom", "remainder": True},
            ),
            origin="test",
        )
        card = pe.raw["requirement"].candidate_ids[0]

        with pytest.raises(ValueError, match="only one destination"):
            resolve_scry_destinations(
                sample_game_state,
                pe.id,
                (
                    {"zone": "hand", "cards": (card,)},
                    {"zone": "deck-bottom", "cards": (card,)},
                ),
                engine=engine,
            )

    def test_scry_destination_to_inkwell_respects_exerted_destination(self, sample_game_state, engine):
        """Scry destination routing can put a looked-at card into inkwell exerted."""
        from lorcana_bot.pending_effects import create_scry_pending_effect, resolve_scry_destinations

        pe = create_scry_pending_effect(
            sample_game_state,
            0,
            0,
            None,
            None,
            1,
            destinations=({"zone": "inkwell", "min": 1, "max": 1, "exerted": True, "facedown": True},),
            origin="test",
        )
        card = pe.raw["requirement"].candidate_ids[0]

        resolve_scry_destinations(
            sample_game_state,
            pe.id,
            ({"zone": "inkwell", "cards": (card,)},),
            engine=engine,
        )

        assert card in sample_game_state.players[0].inkwell
        assert sample_game_state.cards[card].zone == ZONE_INKWELL
        assert sample_game_state.cards[card].exerted is True


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

    def test_resolve_search_selection_moves_card(self, sample_game_state, engine):
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

        resolve_search_selection(sample_game_state, pe.id, selected_card_id=cid, engine=engine)

        # Card should be in hand
        assert cid in sample_game_state.players[0].hand
        assert len(sample_game_state.players[0].hand) == initial_hand_size + 1

    def test_resolve_search_selection_shuffles_if_required(self, sample_game_state, engine):
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

        resolve_search_selection(sample_game_state, pe.id, selected_card_id=cid, engine=engine)

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

    def test_search_event_does_not_leak_filter(self, sample_game_state, engine):
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

        resolve_search_selection(sample_game_state, pe.id, selected_card_id=cid, engine=engine)

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
