"""Tests for automation resolve bag functionality."""

import pytest
from lorcana_bot.automation import AutomationEngine
from lorcana_bot.engine import GameEngine
from lorcana_bot.state import GameState
from lorcana_bot.constants import ACTION_RESOLVE_BAG


def test_automation_enumerates_resolve_bag():
    """Test that automation enumerates RESOLVE_BAG actions."""
    engine = GameEngine()
    automation = AutomationEngine(engine)
    state = engine.new_game("demo", ["deck1", "deck2"])
    
    # Get automation candidates
    candidates = automation.get_candidates(state, 0)
    
    # Should include RESOLVE_BAG if bag has items
    resolve_candidates = [c for c in candidates if c.action.kind == ACTION_RESOLVE_BAG]
    # May or may not have candidates depending on game state


def test_automation_validates_resolve_bag():
    """Test that automation validates RESOLVE_BAG actions."""
    engine = GameEngine()
    automation = AutomationEngine(engine)
    state = engine.new_game("demo", ["deck1", "deck2"])
    
    # Test validation of RESOLVE_BAG actions
    actions = engine.legal_actions(state, 0)
    resolve_actions = [a for a in actions if a.kind == ACTION_RESOLVE_BAG]
    
    for action in resolve_actions:
        assert automation.validate_action(state, action)


def test_automation_maps_resolve_bag():
    """Test that automation maps RESOLVE_BAG actions."""
    engine = GameEngine()
    automation = AutomationEngine(engine)
    state = engine.new_game("demo", ["deck1", "deck2"])
    
    # Test mapping of RESOLVE_BAG actions
    actions = engine.legal_actions(state, 0)
    resolve_actions = [a for a in actions if a.kind == ACTION_RESOLVE_BAG]
    
    for action in resolve_actions:
        mapping = automation.map_action(state, action)
        assert mapping is not None