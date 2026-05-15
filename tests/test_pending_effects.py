"""Tests for pending effect layer and target choice prompts."""

import pytest

from lorcana_bot.engine import GameEngine
from lorcana_bot.cards import CardDatabase
from lorcana_bot.pending_effects import (
    PendingEffect,
    TargetRequirement,
    create_pending_effect,
    get_current_pending_effect,
    get_pending_effects_for_chooser,
    get_valid_targets_for_requirement,
    resolve_pending_effect_optional,
    complete_pending_effect,
    has_pending_effects,
    get_pending_effect_by_id,
)
from lorcana_bot.constants import (
    ACTION_RESOLVE_PENDING_EFFECT,
    ZONE_PLAY,
)


class TestTargetRequirement:
    """Tests for TargetRequirement dataclass."""

    def test_basic_requirement(self):
        req = TargetRequirement(kind="chosen_character")
        assert req.kind == "chosen_character"
        assert req.min_targets == 1
        assert req.max_targets == 1
        assert req.optional is False

    def test_damaged_character_requirement(self):
        req = TargetRequirement(
            kind="chosen_damaged_character",
            must_be_damaged=True,
            card_type="character",
        )
        assert req.must_be_damaged is True
        assert req.card_type == "character"

    def test_opposing_character_requirement(self):
        req = TargetRequirement(
            kind="chosen_opposing_character",
            owner_filter="opponent",
        )
        assert req.owner_filter == "opponent"


class TestPendingEffect:
    """Tests for PendingEffect dataclass."""

    def test_current_effect_property(self):
        from lorcana_bot.cards import EffectDef
        effects = (
            EffectDef(kind="deal_damage", target="opposing_character", amount=2),
            EffectDef(kind="draw", amount=1),
        )
        pe = PendingEffect(
            id="pe_1",
            controller_id=0,
            chooser_id=0,
            source_id=None,
            source_card_id=None,
            effects=effects,
        )
        assert pe.current_effect == effects[0]
        assert pe.current_effect_index == 0

    def test_advance_effect(self):
        from lorcana_bot.cards import EffectDef
        effects = (
            EffectDef(kind="deal_damage", target="opposing_character", amount=2),
            EffectDef(kind="draw", amount=1),
        )
        pe = PendingEffect(
            id="pe_1",
            controller_id=0,
            chooser_id=0,
            source_id=None,
            source_card_id=None,
            effects=effects,
        )
        pe.current_effect_index += 1
        assert pe.current_effect == effects[1]

    def test_is_complete(self):
        from lorcana_bot.cards import EffectDef
        effects = (
            EffectDef(kind="deal_damage", target="opposing_character", amount=2),
            EffectDef(kind="draw", amount=1),
        )
        pe = PendingEffect(
            id="pe_1",
            controller_id=0,
            chooser_id=0,
            source_id=None,
            source_card_id=None,
            effects=effects,
        )
        assert pe.is_complete is False
        pe.current_effect_index = 2
        assert pe.is_complete is True

    def test_requires_target_input(self):
        from lorcana_bot.cards import EffectDef
        effects = (EffectDef(kind="deal_damage", target="chosen_character", amount=2),)
        requirements = (TargetRequirement(kind="chosen_character"),)
        pe = PendingEffect(
            id="pe_1",
            controller_id=0,
            chooser_id=0,
            source_id=None,
            source_card_id=None,
            effects=effects,
            required_targets=requirements,
        )
        assert pe.requires_target_input is True

    def test_does_not_require_target_for_non_chosen(self):
        from lorcana_bot.cards import EffectDef
        effects = (EffectDef(kind="draw", amount=2),)
        pe = PendingEffect(
            id="pe_1",
            controller_id=0,
            chooser_id=0,
            source_id=None,
            source_card_id=None,
            effects=effects,
        )
        assert pe.requires_target_input is False


class TestPendingEffectState:
    """Tests for pending effect state management."""

    def test_has_pending_effects(self, sample_game_state):
        from lorcana_bot.cards import EffectDef
        from lorcana_bot.state import GameState, PlayerState, CardInstance
        
        # Initially no pending effects
        assert has_pending_effects(sample_game_state) is False
        
        # Create a pending effect
        effects = (EffectDef(kind="draw", amount=1),)
        create_pending_effect(
            sample_game_state,
            controller_id=0,
            chooser_id=0,
            source_id=None,
            source_card_id=None,
            effects=effects,
        )
        
        assert has_pending_effects(sample_game_state) is True

    def test_get_pending_effects_for_chooser(self, sample_game_state):
        from lorcana_bot.cards import EffectDef
        
        create_pending_effect(
            sample_game_state,
            controller_id=0,
            chooser_id=1,
            source_id=None,
            source_card_id=None,
            effects=(EffectDef(kind="draw", amount=1),),
        )
        
        chooser_effects = get_pending_effects_for_chooser(sample_game_state, 1)
        assert len(chooser_effects) == 1
        assert chooser_effects[0].chooser_id == 1
        
        other_effects = get_pending_effects_for_chooser(sample_game_state, 0)
        assert len(other_effects) == 0

    def test_get_current_pending_effect(self, sample_game_state):
        from lorcana_bot.cards import EffectDef
        
        # Create pending effect with chooser=0
        pe = create_pending_effect(
            sample_game_state,
            controller_id=0,
            chooser_id=0,
            source_id=None,
            source_card_id=None,
            effects=(EffectDef(kind="draw", amount=1),),
        )
        
        current = get_current_pending_effect(sample_game_state, 0)
        assert current is not None
        assert current.id == pe.id

    def test_get_current_pending_effect_wrong_chooser(self, sample_game_state):
        from lorcana_bot.cards import EffectDef
        
        create_pending_effect(
            sample_game_state,
            controller_id=0,
            chooser_id=0,
            source_id=None,
            source_card_id=None,
            effects=(EffectDef(kind="draw", amount=1),),
        )
        
        current = get_current_pending_effect(sample_game_state, 1)
        assert current is None

    def test_complete_pending_effect(self, sample_game_state):
        from lorcana_bot.cards import EffectDef
        
        pe = create_pending_effect(
            sample_game_state,
            controller_id=0,
            chooser_id=0,
            source_id=None,
            source_card_id=None,
            effects=(EffectDef(kind="draw", amount=1),),
        )
        
        assert has_pending_effects(sample_game_state) is True
        
        completed = complete_pending_effect(sample_game_state, pe.id)
        
        assert completed is not None
        assert has_pending_effects(sample_game_state) is False

    def test_resolve_optional_decline(self, sample_game_state):
        from lorcana_bot.cards import EffectDef
        
        pe = create_pending_effect(
            sample_game_state,
            controller_id=0,
            chooser_id=0,
            source_id=None,
            source_card_id=None,
            effects=(EffectDef(kind="draw", amount=1),),
            optional=True,
        )
        
        resolve_pending_effect_optional(sample_game_state, pe.id, False)
        
        # After decline, pending effect should be marked as declined
        assert pe.accepted is False
        # The engine will complete the effect when it processes the decline action
        # is_complete stays False until the engine removes the effect


class TestValidTargets:
    """Tests for target validation."""

    def test_chosen_character_targets_empty_board(self, sample_game_state, engine):
        """Test when there are no characters in play."""
        requirement = TargetRequirement(
            kind="chosen_character",
            card_type="character",
        )
        
        targets = get_valid_targets_for_requirement(
            sample_game_state, requirement, chooser_id=0, engine=engine
        )
        
        # No characters in play, should return empty list
        assert len(targets) == 0

    def test_opposing_character_excludes_self(self, sample_game_state, engine):
        # Put a character in opponent's play area
        from lorcana_bot.constants import ZONE_PLAY
        
        char_id = 10  # Use an existing card
        sample_game_state.cards[char_id].zone = ZONE_PLAY
        sample_game_state.cards[char_id].controller = 1
        sample_game_state.players[1].play.append(char_id)
        
        requirement = TargetRequirement(
            kind="chosen_opposing_character",
            card_type="character",
            owner_filter="opponent",
        )
        
        targets = get_valid_targets_for_requirement(
            sample_game_state, requirement, chooser_id=0, engine=engine
        )
        
        # Should only include opponent's characters
        assert len(targets) >= 1  # At least the one we added

    def test_damaged_character_only(self, sample_game_state, engine):
        from lorcana_bot.constants import ZONE_PLAY
        
        # Add a character to play and damage it
        char_id = 1
        sample_game_state.cards[char_id].zone = ZONE_PLAY
        sample_game_state.cards[char_id].controller = 0
        sample_game_state.players[0].play.append(char_id)
        sample_game_state.cards[char_id].damage = 3
        
        requirement = TargetRequirement(
            kind="chosen_damaged_character",
            card_type="character",
            must_be_damaged=True,
        )
        
        targets = get_valid_targets_for_requirement(
            sample_game_state, requirement, chooser_id=0, engine=engine
        )
        
        # Only damaged character should be included
        assert len(targets) == 1
        assert targets[0] == char_id


class TestLegalActionsWithPendingEffects:
    """Tests for legal action generation with pending effects."""

    def test_pending_effect_blocks_normal_actions(self, sample_game_state, engine):
        from lorcana_bot.cards import EffectDef
        
        create_pending_effect(
            sample_game_state,
            controller_id=0,
            chooser_id=0,
            source_id=None,
            source_card_id=None,
            effects=(EffectDef(kind="draw", amount=1),),
        )
        
        # Player 0 has a pending effect
        legal = engine.legal_actions(sample_game_state, 0)
        
        # Should only have RESOLVE_PENDING_EFFECT and CONCEDE
        action_types = [a.kind for a in legal]
        assert ACTION_RESOLVE_PENDING_EFFECT in action_types
        assert "END_TURN" not in action_types
        assert "PLAY_CARD" not in action_types

    def test_non_chooser_can_only_concede(self, sample_game_state, engine):
        from lorcana_bot.cards import EffectDef
        
        create_pending_effect(
            sample_game_state,
            controller_id=0,
            chooser_id=0,
            source_id=None,
            source_card_id=None,
            effects=(EffectDef(kind="draw", amount=1),),
        )
        
        # Player 1 does not have the pending effect
        legal = engine.legal_actions(sample_game_state, 1)
        
        # Should only have CONCEDE
        assert len(legal) == 1
        assert legal[0].kind == "CONCEDE"

    def test_optional_pending_effect_has_accept_decline(self, sample_game_state, engine):
        from lorcana_bot.cards import EffectDef
        
        create_pending_effect(
            sample_game_state,
            controller_id=0,
            chooser_id=0,
            source_id=None,
            source_card_id=None,
            effects=(EffectDef(kind="draw", amount=1),),
            optional=True,
        )
        
        legal = engine.legal_actions(sample_game_state, 0)
        
        # Should have accept and decline options
        accept_action = None
        decline_action = None
        for action in legal:
            if action.choice and "accept" in action.choice:
                if action.choice["accept"] is True:
                    accept_action = action
                else:
                    decline_action = action
        
        assert accept_action is not None
        assert decline_action is not None


class TestResolvePendingEffectAction:
    """Tests for RESOLVE_PENDING_EFFECT action application."""

    def test_resolve_simple_pending_effect(self, sample_game_state, engine):
        from lorcana_bot.cards import EffectDef
        
        initial_hand_size = len(sample_game_state.players[0].hand)
        
        pe = create_pending_effect(
            sample_game_state,
            controller_id=0,
            chooser_id=0,
            source_id=None,
            source_card_id=None,
            effects=(EffectDef(kind="draw", amount=1),),
        )
        
        action = Action(
            ACTION_RESOLVE_PENDING_EFFECT,
            actor=0,
            source=None,
            choice={"pending_effect_id": pe.id},
        )
        
        state = engine.apply_action(sample_game_state, action)
        
        # Should have drawn a card
        assert len(state.players[0].hand) == initial_hand_size + 1
        # Pending effect should be removed
        assert has_pending_effects(state) is False

    def test_resolve_optional_accept(self, sample_game_state, engine):
        from lorcana_bot.cards import EffectDef
        
        initial_hand_size = len(sample_game_state.players[0].hand)
        
        pe = create_pending_effect(
            sample_game_state,
            controller_id=0,
            chooser_id=0,
            source_id=None,
            source_card_id=None,
            effects=(EffectDef(kind="draw", amount=1),),
            optional=True,
        )
        
        action = Action(
            ACTION_RESOLVE_PENDING_EFFECT,
            actor=0,
            source=None,
            choice={"pending_effect_id": pe.id, "accept": True},
        )
        
        state = engine.apply_action(sample_game_state, action)
        
        # Should have drawn a card
        assert len(state.players[0].hand) == initial_hand_size + 1

    def test_resolve_optional_decline(self, sample_game_state, engine):
        from lorcana_bot.cards import EffectDef
        
        initial_hand_size = len(sample_game_state.players[0].hand)
        
        pe = create_pending_effect(
            sample_game_state,
            controller_id=0,
            chooser_id=0,
            source_id=None,
            source_card_id=None,
            effects=(EffectDef(kind="draw", amount=1),),
            optional=True,
        )
        
        action = Action(
            ACTION_RESOLVE_PENDING_EFFECT,
            actor=0,
            source=None,
            choice={"pending_effect_id": pe.id, "accept": False},
        )
        
        state = engine.apply_action(sample_game_state, action)
        
        # Should NOT have drawn a card
        assert len(state.players[0].hand) == initial_hand_size
        # Pending effect should be removed
        assert has_pending_effects(state) is False

    def test_wrong_actor_cannot_resolve(self, sample_game_state, engine):
        from lorcana_bot.cards import EffectDef
        
        create_pending_effect(
            sample_game_state,
            controller_id=0,
            chooser_id=0,
            source_id=None,
            source_card_id=None,
            effects=(EffectDef(kind="draw", amount=1),),
        )
        
        # Player 1 tries to resolve player 0's pending effect
        action = Action(
            ACTION_RESOLVE_PENDING_EFFECT,
            actor=1,
            source=None,
            choice={"pending_effect_id": "pe_1"},
        )
        
        # Should raise error
        with pytest.raises(Exception):
            engine.apply_action(sample_game_state, action)


# Import Action for tests
from lorcana_bot.actions import Action


# Fixtures
@pytest.fixture
def sample_game_state():
    """Create a sample game state for testing."""
    from lorcana_bot.state import GameState, PlayerState, CardInstance
    
    players = [PlayerState(), PlayerState()]
    cards = {}
    next_id = 1
    
    # Create simple decks
    for player in range(2):
        for _ in range(10):
            inst = CardInstance(
                instance_id=next_id,
                card_id=f"test_card_{next_id}",
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
        bag=[],
        event_log=[],
        action_log=[],
    )
    
    # Draw hands
    for player in range(2):
        for _ in range(5):
            cid = state.players[player].deck.pop(0)
            state.cards[cid].zone = "hand"
            state.players[player].hand.append(cid)
    
    return state


@pytest.fixture
def engine():
    """Create a game engine for testing."""
    from lorcana_bot.cards import load_demo_database
    
    db = load_demo_database()
    return GameEngine(db)
