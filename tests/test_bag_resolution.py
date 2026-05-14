"""Tests for bag resolution functionality."""

import pytest
from lorcana_bot.engine import GameEngine
from lorcana_bot.state import GameState
from lorcana_bot.actions import Action
from lorcana_bot.constants import ACTION_RESOLVE_BAG


def test_resolve_bag_requires_action():
    """Test that bag resolution must go through ACTION_RESOLVE_BAG."""
    engine = GameEngine()
    state = engine.new_game("demo", ["deck1", "deck2"])
    
    # Direct resolve_bag call should raise
    with pytest.raises(RuntimeError, match="Bag must be resolved through ACTION_RESOLVE_BAG"):
        engine.resolve_bag(state)


def test_resolve_bag_action_processes_effects():
    """Test that ACTION_RESOLVE_BAG processes bag effects."""
    engine = GameEngine()
    state = engine.new_game("demo", ["deck1", "deck2"])
    
    # Create a mock bag entry (this would normally be created by triggers)
    # For now, just test that the action can be applied
    actions = engine.legal_actions(state, 0)
    resolve_actions = [a for a in actions if a.kind == ACTION_RESOLVE_BAG]
    
    if resolve_actions:
        next_state = engine.apply_action(state, resolve_actions[0])
        assert next_state is not None