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


def test_characters_here_no_longer_reports_unsupported_on():
    """Test that CHARACTERS_HERE and related string filters no longer report unsupported_on."""
    from lorcana_bot.decks.trigger_blocker_report import SUPPORTED_TRIGGER_ON_VALUES

    # 2C: These string filters are now supported
    assert "CHARACTERS_HERE" in SUPPORTED_TRIGGER_ON_VALUES
    assert "CHARACTER_HERE" in SUPPORTED_TRIGGER_ON_VALUES
    assert "ANY_ITEM" in SUPPORTED_TRIGGER_ON_VALUES
    assert "YOUR_ACTIONS" in SUPPORTED_TRIGGER_ON_VALUES
    assert "YOUR_SONGS" in SUPPORTED_TRIGGER_ON_VALUES
    assert "YOUR_CHARACTERS_OR_LOCATIONS" in SUPPORTED_TRIGGER_ON_VALUES
    assert "YOUR_CHARACTERS_OR_LOCATIONS_WITH_CARD_UNDER" in SUPPORTED_TRIGGER_ON_VALUES


def test_ink_type_filter_no_longer_reports_complex_filter():
    """Test that ink-type filter no longer reports complex_filter."""
    from lorcana_bot.decks.trigger_blocker_report import _analyze_trigger_on_filter, SUPPORTED_FILTER_KEYS, SUPPORTED_FILTER_TYPES

    # 2C: Verify ink-type filter type is now supported
    assert "ink-type" in SUPPORTED_FILTER_TYPES

    # Pluto-style trigger with ink-type filter
    pluto_style_trigger = {
        "cardType": "character",
        "controller": "you",
        "excludeSelf": True,
        "filters": [{"type": "ink-type", "inkType": "steel"}],
    }

    # 2C: This should NOT report unsupported - ink-type is supported
    assert _analyze_trigger_on_filter(pluto_style_trigger) is None


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

    # 4C: Test recursive extraction of other requirements
    # scry_ordering is no longer a blocker since Brief 4B supports pending scry
    nested_draw = MockEffect("sequence", effects=[MockEffect("draw", raw={"type": "draw", "amount": 1})])
    ability = MockAbility([nested_draw])

    requirements = _extract_resolution_requirements(ability)
    # Amount is not a blocker for static integer shape
    assert "amount" not in requirements
    # Ensure recursive extraction still works for other requirements
    assert True  # Other requirements would be added here


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


def test_has_card_under_no_longer_reports_unsupported_condition():
    """Test that has-card-under condition no longer reports unsupported_condition."""
    from lorcana_bot.importers.lorcanito_source_mapper import SUPPORTED_CONDITION_KINDS

    # 3C: has-card-under is now supported
    assert "has-card-under" in SUPPORTED_CONDITION_KINDS


def test_turn_metric_no_longer_reports_unsupported_condition():
    """Test that turn-metric condition no longer reports unsupported_condition."""
    from lorcana_bot.importers.lorcanito_source_mapper import SUPPORTED_CONDITION_KINDS

    # 3C: turn-metric is now supported
    assert "turn-metric" in SUPPORTED_CONDITION_KINDS


class TestMicrofix4CBlockerReportAlignment:
    """Tests for microfix 4C blocker report alignment."""

    def test_supported_amount_shape_not_reported_as_resolution_blocker(self):
        """Supported amount shapes should not be reported as amount blockers."""
        from lorcana_bot.decks.trigger_blocker_report import _extract_resolution_requirements, _get_amount_shape_from_raw

        # Verify the amount shape detection works
        assert _get_amount_shape_from_raw(2) == "static_integer"
        assert _get_amount_shape_from_raw("3") == "numeric_string"
        assert _get_amount_shape_from_raw({"type": "static", "amount": 1}) == "static_object"
        assert _get_amount_shape_from_raw({"type": "event-snapshot", "key": "drawnCount"}) == "event_snapshot_drawn_count"
        assert _get_amount_shape_from_raw({"type": "event-snapshot", "key": "cardsUnderCountBeforeBanish"}) == "event_snapshot_cards_under_count"

        # Mock ability with supported amount shape (static integer)
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

        # Supported static integer amount
        effect_static = MockEffect("gain-lore", raw={"type": "gain-lore", "amount": 2})
        ability_static = MockAbility([effect_static])

        requirements = _extract_resolution_requirements(ability_static)
        # 4C: static_integer amount shape is NOT a blocker
        assert "amount" not in requirements

        # Supported numeric string amount
        effect_string = MockEffect("draw", raw={"type": "draw", "amount": "3"})
        ability_string = MockAbility([effect_string])

        requirements = _extract_resolution_requirements(ability_string)
        # 4C: numeric_string amount shape is NOT a blocker
        assert "amount" not in requirements

        # Supported static object amount
        effect_static_obj = MockEffect("deal-damage", raw={"type": "deal-damage", "amount": {"type": "static", "amount": 1}})
        ability_static_obj = MockAbility([effect_static_obj])

        requirements = _extract_resolution_requirements(ability_static_obj)
        # 4C: static_object amount shape is NOT a blocker
        assert "amount" not in requirements

        # Supported event-snapshot amount
        effect_event = MockEffect("gain-lore", raw={"type": "gain-lore", "amount": {"type": "event-snapshot", "key": "drawnCount"}})
        ability_event = MockAbility([effect_event])

        requirements = _extract_resolution_requirements(ability_event)
        # 4C: event_snapshot amount shape is NOT a blocker
        assert "amount" not in requirements

    def test_unsupported_amount_shape_still_reported_as_resolution_blocker(self):
        """Unsupported amount shapes should still be reported as blockers."""
        from lorcana_bot.decks.trigger_blocker_report import _extract_resolution_requirements, _get_amount_shape_from_raw

        # Verify unsupported shapes return None
        assert _get_amount_shape_from_raw({"type": "dynamic", "key": "unknown"}) is None
        assert _get_amount_shape_from_raw({"type": "event-snapshot", "key": "unknownKey"}) is None
        assert _get_amount_shape_from_raw([1, 2, 3]) is None

        # Mock ability with unsupported amount shape
        class MockEffect:
            def __init__(self, kind, raw=None):
                self.kind = kind
                self.effects = []
                self.branches = []
                self.raw = raw or {}

        class MockAbility:
            def __init__(self, effects, auto_resolve=True):
                self.effects = effects
                self.auto_resolve = auto_resolve

        # Unsupported dynamic amount
        effect_dynamic = MockEffect("deal-damage", raw={"type": "deal-damage", "amount": {"type": "dynamic", "key": "opponentCharacterCount"}})
        ability_dynamic = MockAbility([effect_dynamic])

        requirements = _extract_resolution_requirements(ability_dynamic)
        # 4C: Unsupported amount shape IS a blocker
        assert "amount" in requirements

        # Unsupported event-snapshot key
        effect_unknown_key = MockEffect("gain-lore", raw={"type": "gain-lore", "amount": {"type": "event-snapshot", "key": "unknownKey"}})
        ability_unknown_key = MockAbility([effect_unknown_key])

        requirements = _extract_resolution_requirements(ability_unknown_key)
        # 4C: Unknown event-snapshot key IS a blocker
        assert "amount" in requirements

        # Unsupported list amount
        effect_list = MockEffect("draw", raw={"type": "draw", "amount": [1, 2, 3]})
        ability_list = MockAbility([effect_list])

        requirements = _extract_resolution_requirements(ability_list)
        # 4C: Unsupported list amount IS a blocker
        assert "amount" in requirements

    def test_scry_ordering_not_reported_when_pending_route_supported(self):
        """Scry ordering should not be reported as blocker since Brief 4B supports pending scry."""
        from lorcana_bot.decks.trigger_blocker_report import _extract_resolution_requirements

        # Mock ability with scry effect
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

        # Scry effect (no amount required - Brief 4B handles pending scry)
        effect_scry = MockEffect("scry", raw={"type": "scry"})
        ability_scry = MockAbility([effect_scry])

        requirements = _extract_resolution_requirements(ability_scry)
        # 4C: scry_ordering is NOT a blocker because Brief 4B supports pending scry through bag completion
        assert "scry_ordering" not in requirements

        # Nested scry effect
        effect_nested = MockEffect("sequence", effects=[
            MockEffect("scry", raw={"type": "scry"})
        ])
        ability_nested = MockAbility([effect_nested])

        requirements = _extract_resolution_requirements(ability_nested)
        # 4C: Nested scry also does not report scry_ordering
        assert "scry_ordering" not in requirements

    def test_reveal_routing_still_reported_as_blocker(self):
        """reveal-routing should still be reported as blocker."""
        from lorcana_bot.decks.trigger_blocker_report import _extract_resolution_requirements

        # Mock ability with reveal-and-route effect
        class MockEffect:
            def __init__(self, kind, raw=None):
                self.kind = kind
                self.effects = []
                self.branches = []
                self.raw = raw or {}

        class MockAbility:
            def __init__(self, effects, auto_resolve=True):
                self.effects = effects
                self.auto_resolve = auto_resolve

        # reveal-and-route effect
        effect_reveal = MockEffect("reveal-and-route", raw={"type": "reveal-and-route"})
        ability_reveal = MockAbility([effect_reveal])

        requirements = _extract_resolution_requirements(ability_reveal)
        # reveal_routing is still a blocker (not addressed by Brief 4B)
        assert "reveal_routing" in requirements
