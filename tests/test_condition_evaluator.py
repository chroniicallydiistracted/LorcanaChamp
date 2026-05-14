"""B2 tests for condition evaluator."""

import pytest

from lorcana_bot.condition_evaluator import (
    UnsupportedConditionError,
    evaluate_condition,
)
from lorcana_bot.state import GameState, PendingTriggeredEvent


@pytest.fixture
def state_with_cards():
    """Create a game state with cards in play."""
    from lorcana_bot.state import CardInstance, PlayerState
    
    state = GameState(
        players=[PlayerState(), PlayerState()],
        cards={},
    )
    # Add characters in play
    card1 = CardInstance(instance_id=1, card_id="test_char", owner=0, controller=0, zone="play")
    card2 = CardInstance(instance_id=2, card_id="test_char2", owner=1, controller=1, zone="play")
    state.cards[1] = card1
    state.cards[2] = card2
    state.players[0].play = [1]
    state.players[1].play = [2]
    return state


@pytest.fixture
def mock_engine():
    """Create a mock engine for condition tests."""
    from lorcana_bot.cards import CardDef
    
    class MockEngine:
        def card_def(self, state, instance_id):
            return CardDef("test_char", "Test Char", "amber", 2, True, "character", 2, 2, 1)
    
    return MockEngine()


def test_none_condition_is_true(state_with_cards, mock_engine):
    """Test that None condition returns True."""
    assert evaluate_condition(None, state_with_cards, None, 1, mock_engine) is True


def test_always_condition_is_true(state_with_cards, mock_engine):
    """Test that 'always' condition returns True."""
    condition = {"type": "always"}
    assert evaluate_condition(condition, state_with_cards, None, 1, mock_engine) is True


def test_your_turn_condition(state_with_cards, mock_engine):
    """Test your-turn condition."""
    state_with_cards.active_player = 0
    
    condition = {"type": "your-turn"}
    assert evaluate_condition(condition, state_with_cards, None, 1, mock_engine) is True
    
    # When it's opponent's turn
    state_with_cards.active_player = 1
    assert evaluate_condition(condition, state_with_cards, None, 1, mock_engine) is False


def test_opponent_turn_condition(state_with_cards, mock_engine):
    """Test opponent-turn condition."""
    state_with_cards.active_player = 1
    
    condition = {"type": "opponent-turn"}
    assert evaluate_condition(condition, state_with_cards, None, 1, mock_engine) is True
    
    # When it's your turn
    state_with_cards.active_player = 0
    assert evaluate_condition(condition, state_with_cards, None, 1, mock_engine) is False


def test_has_character_count_condition(state_with_cards, mock_engine):
    """Test has-character-count condition."""
    condition = {"type": "has-character-count", "comparison": ">=", "value": 1}
    assert evaluate_condition(condition, state_with_cards, None, 1, mock_engine) is True
    
    condition = {"type": "has-character-count", "comparison": ">=", "value": 5}
    assert evaluate_condition(condition, state_with_cards, None, 1, mock_engine) is False


def test_inkwell_count_condition(state_with_cards, mock_engine):
    """Test inkwell-count condition."""
    # No ink in inkwell
    condition = {"type": "inkwell-count", "comparison": ">=", "value": 1}
    assert evaluate_condition(condition, state_with_cards, None, 1, mock_engine) is False
    
    # Add ink
    state_with_cards.players[0].inkwell = [1]
    condition = {"type": "inkwell-count", "comparison": ">=", "value": 1}
    assert evaluate_condition(condition, state_with_cards, None, 1, mock_engine) is True


def test_and_condition(state_with_cards, mock_engine):
    """Test 'and' logical condition."""
    condition = {
        "type": "and",
        "conditions": [
            {"type": "always"},
            {"type": "always"},
        ]
    }
    assert evaluate_condition(condition, state_with_cards, None, 1, mock_engine) is True
    
    # And with one false
    condition = {
        "type": "and",
        "conditions": [
            {"type": "always"},
            {"type": "opponent-turn"},  # Will be false when player 0 is active
        ]
    }
    state_with_cards.active_player = 0
    assert evaluate_condition(condition, state_with_cards, None, 1, mock_engine) is False


def test_or_condition(state_with_cards, mock_engine):
    """Test 'or' logical condition."""
    condition = {
        "type": "or",
        "conditions": [
            {"type": "opponent-turn"},  # False when player 0 is active
            {"type": "always"},  # True
        ]
    }
    state_with_cards.active_player = 0
    assert evaluate_condition(condition, state_with_cards, None, 1, mock_engine) is True


def test_not_condition(state_with_cards, mock_engine):
    """Test 'not' logical condition."""
    condition = {
        "type": "not",
        "condition": {"type": "opponent-turn"},
    }
    state_with_cards.active_player = 0
    assert evaluate_condition(condition, state_with_cards, None, 1, mock_engine) is True


def test_unsupported_condition_raises(state_with_cards, mock_engine):
    """Test that unsupported condition raises UnsupportedConditionError."""
    condition = {"type": "unsupported-weird-condition"}
    with pytest.raises(UnsupportedConditionError):
        evaluate_condition(condition, state_with_cards, None, 1, mock_engine)


def test_during_turn_condition(state_with_cards, mock_engine):
    """Test during-turn condition."""
    state_with_cards.active_player = 0
    
    condition = {"type": "during-turn"}
    assert evaluate_condition(condition, state_with_cards, None, 1, mock_engine) is True
    
    state_with_cards.active_player = 1
    assert evaluate_condition(condition, state_with_cards, None, 1, mock_engine) is False


def test_comparison_operators(state_with_cards, mock_engine):
    """Test different comparison operators."""
    from lorcana_bot.state import CardInstance
    state_with_cards.cards[1] = CardInstance(instance_id=1, card_id="test_char", owner=0, controller=0, zone="play")
    state_with_cards.players[0].inkwell = [1]
    
    # Test >= 
    condition = {"type": "inkwell-count", "comparison": ">=", "value": 1}
    assert evaluate_condition(condition, state_with_cards, None, 1, mock_engine) is True
    
    # Test >
    condition = {"type": "inkwell-count", "comparison": ">", "value": 0}
    assert evaluate_condition(condition, state_with_cards, None, 1, mock_engine) is True
    
    # Test <=
    condition = {"type": "inkwell-count", "comparison": "<=", "value": 1}
    assert evaluate_condition(condition, state_with_cards, None, 1, mock_engine) is True
    
    # Test <
    condition = {"type": "inkwell-count", "comparison": "<", "value": 2}
    assert evaluate_condition(condition, state_with_cards, None, 1, mock_engine) is True
    
    # Test ==
    condition = {"type": "inkwell-count", "comparison": "==", "value": 1}
    assert evaluate_condition(condition, state_with_cards, None, 1, mock_engine) is True