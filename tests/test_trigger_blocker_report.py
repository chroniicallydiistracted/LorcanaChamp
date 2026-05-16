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


def test_trigger_summary_per_event_unique_deck_counts():
    """Test that by_trigger_event has per-event unique cards and deck counts."""
    rows = [
        {"projection_status": "not_projected", "trigger_event": "play", "card_id": "card1", "deck_id": "deck1", "copy_weight": 1},
        {"projection_status": "not_projected", "trigger_event": "play", "card_id": "card2", "deck_id": "deck1", "copy_weight": 1},
        {"projection_status": "not_projected", "trigger_event": "quest", "card_id": "card3", "deck_id": "deck2", "copy_weight": 1},
    ]

    summary = build_trigger_summary(rows)

    # Find play event stats
    play_event = next((item for item in summary["by_trigger_event"] if item["trigger_event"] == "play"), None)
    assert play_event is not None
    assert play_event["unique_cards"] == 2  # card1 and card2
    assert play_event["deck_presence"] == 1  # deck1 only

    # Find quest event stats
    quest_event = next((item for item in summary["by_trigger_event"] if item["trigger_event"] == "quest"), None)
    assert quest_event is not None
    assert quest_event["unique_cards"] == 1  # card3 only
    assert quest_event["deck_presence"] == 1  # deck2 only


def test_trigger_summary_projected_excluded_from_blocker_counts():
    """Test that projected rows are excluded from all blocker aggregation."""
    rows = [
        {"projection_status": "projected", "primary_blocker": "unknown", "card_id": "card1", "deck_id": "deck1", "copy_weight": 5, "trigger_on": "SELF", "effect_kinds": ["draw"], "target_kinds": ["SELF"], "condition_kinds": ["none"], "resolution_requirements": []},
        {"projection_status": "not_projected", "primary_blocker": "blocker1", "card_id": "card2", "deck_id": "deck1", "copy_weight": 2, "trigger_on": "SELF", "effect_kinds": ["draw"], "target_kinds": ["SELF"], "condition_kinds": ["none"], "resolution_requirements": []},
    ]

    summary = build_trigger_summary(rows)

    # Projected row should not contribute to blocker counts
    assert summary["summary"]["blocked_trigger_copies"] == 2  # Only non-projected
    assert "unknown" not in [item["blocker"] for item in summary["by_primary_blocker_copies"]]

    # Check that by_trigger_on, by_effect_kind, etc. are populated (not empty)
    assert summary["by_trigger_on"]  # Should not be empty
    assert summary["by_effect_kind"]  # Should not be empty


def test_unknown_effect_maps_to_other_source_execution():
    """Test that unknown effect kinds map to other_source_execution, not scry_search_reveal."""
    from lorcana_bot.decks.trigger_blocker_report import _get_recommended_work

    # Unknown effect kind should map to other_source_execution
    blockers = ["unsupported_trigger_effect:totally_unknown_effect"]
    work = _get_recommended_work(blockers)

    assert "other_source_execution" in work
    assert "scry_search_reveal" not in work


def test_trigger_summary_all_dimensions_populated():
    """Test that all dimension aggregations are populated (not empty)."""
    rows = [
        {"projection_status": "not_projected", "trigger_event": "play", "trigger_on": "SELF",
         "effect_kinds": ["draw"], "target_kinds": ["SELF"], "condition_kinds": ["none"],
         "resolution_requirements": ["optional"], "card_id": "card1", "deck_id": "deck1", "copy_weight": 1},
    ]

    summary = build_trigger_summary(rows)

    # All dimensions should be populated
    assert summary["by_trigger_event"]  # Not empty
    assert summary["by_trigger_on"]  # Not empty
    assert summary["by_effect_kind"]  # Not empty
    assert summary["by_target_kind"]  # Not empty
    assert summary["by_condition_kind"]  # Not empty
    assert summary["by_resolution_requirement"]  # Not empty
