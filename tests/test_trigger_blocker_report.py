"""Tests for trigger blocker report functionality."""

import pytest
from lorcana_bot.decks.trigger_blocker_report import (
    _analyze_trigger_on_filter,
    _extract_resolution_requirements,
    analyze_source_trigger_projection,
    build_trigger_summary,
)


def test_analyze_trigger_on_filter_supported():
    """Test that supported trigger on filters return None."""
    # Simple supported keys
    assert _analyze_trigger_on_filter({"cardType": "character"}) is None
    assert _analyze_trigger_on_filter({"controller": "you"}) is None
    assert _analyze_trigger_on_filter({"cardType": "character", "controller": "you"}) is None


def test_analyze_trigger_on_filter_unsupported():
    """Test that unsupported trigger on filters return blocker strings."""
    assert _analyze_trigger_on_filter({"unsupported_key": "value"}) == "unsupported_trigger_on:complex_filter:unsupported_key"
    assert _analyze_trigger_on_filter({"cardType": "character", "bad_key": "value"}) == "unsupported_trigger_on:complex_filter:bad_key"


def test_extract_resolution_requirements_recursive():
    """Test that resolution requirements are extracted recursively."""
    # Mock ability with nested effects
    class MockEffect:
        def __init__(self, kind, effects=None, branches=None, raw=None):
            self.kind = kind
            self.effects = effects or []
            self.branches = branches or []
            self.raw = raw or {}
    
    class MockAbility:
        def __init__(self, effects, auto_resolve=True):
            self.effects = effects
            self.auto_resolve = auto_resolve
    
    # Test nested scry
    nested_scry = MockEffect("sequence", effects=[MockEffect("scry")])
    ability = MockAbility([nested_scry])
    
    requirements = _extract_resolution_requirements(ability)
    assert "scry_ordering" in requirements


def test_build_trigger_summary_excludes_projected():
    """Test that projected rows are excluded from blocker aggregation."""
    rows = [
        {"projection_status": "projected", "primary_blocker": "unknown", "card_id": "card1", "copy_weight": 1},
        {"projection_status": "executable", "primary_blocker": "some_blocker", "card_id": "card2", "copy_weight": 2},
    ]
    
    summary = build_trigger_summary(rows)
    
    # Projected row should not contribute to blocker counts
    assert summary["summary"]["blocked_trigger_copies"] == 2  # Only the executable row
    assert "unknown" not in [item["blocker"] for item in summary["by_primary_blocker_copies"]]


def test_trigger_summary_aggregation_math():
    """Test that aggregation uses correct per-blocker sets."""
    rows = [
        {"projection_status": "executable", "primary_blocker": "blocker1", "card_id": "card1", "deck_id": "deck1", "copy_weight": 1},
        {"projection_status": "executable", "primary_blocker": "blocker1", "card_id": "card1", "deck_id": "deck1", "copy_weight": 1},  # Duplicate
        {"projection_status": "executable", "primary_blocker": "blocker2", "card_id": "card2", "deck_id": "deck2", "copy_weight": 1},
    ]
    
    summary = build_trigger_summary(rows)
    
    blocker1_stats = next(item for item in summary["by_primary_blocker_copies"] if item["blocker"] == "blocker1")
    assert blocker1_stats["copies"] == 2  # Sum of weights
    assert blocker1_stats["unique_cards"] == 1  # Unique card_ids
    assert blocker1_stats["deck_presence"] == 1  # Unique deck_ids