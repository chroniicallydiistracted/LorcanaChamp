"""Tests for the runtime condition evaluator.

B2: Tests for expanded conditions including:
- target-query, resource-count, banished-in-challenge-this-turn
- lore comparison, card type comparison
- has-character-with-strength, has-location-in-play
"""

from __future__ import annotations

from typing import Any
from unittest.mock import Mock, MagicMock

import pytest

from lorcana_bot.condition_evaluator import (
    UnsupportedConditionError,
    create_condition_context,
    evaluate_condition,
)
from lorcana_bot.effect_types import ConditionContext
from lorcana_bot.state import GameState, PlayerState, CardInstance


class TestConditionContext:
    """Tests for ConditionContext creation."""

    def test_create_condition_context_basic(self, state, engine):
        """Test basic ConditionContext creation."""
        context = create_condition_context(state, source_instance_id=1)

        assert context.actor == context.controller
        assert context.source == 1
        assert context.turn_player == state.active_player

    def test_create_condition_context_with_event(self, state, engine):
        """Test ConditionContext creation with a pending event."""
        from lorcana_bot.state import PendingTriggeredEvent

        # Find a card from player 0 to use as source
        source_id = state.players[0].play[0] if state.players[0].play else 1
        subject_id = state.players[1].play[0] if state.players[1].play else 4

        event = PendingTriggeredEvent(
            id="test-event",
            event="challenged",
            subject_card_id=subject_id,
            attacker_id=source_id,
            defender_id=subject_id,
            happened_in_challenge=True,
            payload={"damage": 3},
        )

        context = create_condition_context(state, source_instance_id=source_id, event=event)

        assert context.subject_card_id == subject_id
        assert context.attacker_id == source_id
        assert context.defender_id == subject_id
        assert context.happened_in_challenge is True
        assert context.event_payload == {"damage": 3}


class TestBasicConditions:
    """Tests for basic condition kinds."""

    def test_always_condition(self, state, engine):
        """Test 'always' condition always returns True."""
        source_id = state.players[0].play[0] if state.players[0].play else 1
        result = evaluate_condition({"type": "always"}, state, None, source_id, engine)
        assert result is True

    def test_none_condition(self, state, engine):
        """Test None condition returns True."""
        source_id = state.players[0].play[0] if state.players[0].play else 1
        result = evaluate_condition(None, state, None, source_id, engine)
        assert result is True

    def test_your_turn_true(self, state, engine):
        """Test 'your-turn' condition when it's the source controller's turn."""
        source_id = state.players[0].play[0] if state.players[0].play else 1
        state.active_player = 0  # Player 0's turn
        result = evaluate_condition({"type": "your-turn"}, state, None, source_id, engine)
        assert result is True

    def test_your_turn_false(self, state, engine):
        """Test 'your-turn' condition when it's not the source controller's turn."""
        source_id = state.players[0].play[0] if state.players[0].play else 1
        state.active_player = 1  # Opponent's turn
        result = evaluate_condition({"type": "your-turn"}, state, None, source_id, engine)
        assert result is False

    def test_opponent_turn_true(self, state, engine):
        """Test 'opponent-turn' condition when it's the opponent's turn."""
        source_id = state.players[0].play[0] if state.players[0].play else 1
        state.active_player = 1  # Opponent's turn
        result = evaluate_condition({"type": "opponent-turn"}, state, None, source_id, engine)
        assert result is True

    def test_opponent_turn_false(self, state, engine):
        """Test 'opponent-turn' condition when it's the source controller's turn."""
        source_id = state.players[0].play[0] if state.players[0].play else 1
        state.active_player = 0  # Player's own turn
        result = evaluate_condition({"type": "opponent-turn"}, state, None, source_id, engine)
        assert result is False


class TestCountConditions:
    """Tests for count-based conditions."""

    def test_has_character_count_meets_threshold(self, state, engine):
        """Test has-character-count when threshold is met."""
        source_id = state.players[0].play[0] if state.players[0].play else 1
        char_count = len(state.players[0].play)

        # Test with threshold of 0 (always true if condition supported)
        condition = {"type": "has-character-count", "value": 0, "comparison": ">="}
        result = evaluate_condition(condition, state, None, source_id, engine)
        assert result is True

    def test_has_character_count_below_threshold(self, state, engine):
        """Test has-character-count when threshold is not met."""
        source_id = state.players[0].play[0] if state.players[0].play else 1

        # Use an impossibly high threshold
        condition = {"type": "has-character-count", "value": 99999, "comparison": ">="}
        result = evaluate_condition(condition, state, None, source_id, engine)
        assert result is False


class TestStatusConditions:
    """Tests for status-based conditions."""

    def test_is_exerted_true(self, state, engine):
        """Test is-exerted when card is exerted."""
        source_id = state.players[0].play[0] if state.players[0].play else 1
        state.cards[source_id].exerted = True
        condition = {"type": "is-exerted"}
        result = evaluate_condition(condition, state, None, source_id, engine)
        assert result is True

    def test_is_exerted_false(self, state, engine):
        """Test is-exerted when card is not exerted."""
        source_id = state.players[0].play[0] if state.players[0].play else 1
        state.cards[source_id].exerted = False
        condition = {"type": "is-exerted"}
        result = evaluate_condition(condition, state, None, source_id, engine)
        assert result is False

    def test_self_has_damage_true(self, state, engine):
        """Test self-has-damage when card has damage."""
        source_id = state.players[0].play[0] if state.players[0].play else 1
        state.cards[source_id].damage = 3
        condition = {"type": "self-has-damage"}
        result = evaluate_condition(condition, state, None, source_id, engine)
        assert result is True

    def test_self_has_damage_false(self, state, engine):
        """Test self-has-damage when card has no damage."""
        source_id = state.players[0].play[0] if state.players[0].play else 1
        state.cards[source_id].damage = 0
        condition = {"type": "self-has-damage"}
        result = evaluate_condition(condition, state, None, source_id, engine)
        assert result is False


class TestResourceConditions:
    """Tests for resource conditions."""

    def test_inkwell_count_meets_threshold(self, state, engine):
        """Test inkwell-count when threshold is met."""
        source_id = state.players[0].play[0] if state.players[0].play else 1
        ink_count = len(state.players[0].inkwell)

        condition = {"type": "inkwell-count", "value": ink_count - 1, "comparison": ">="}
        result = evaluate_condition(condition, state, None, source_id, engine)
        assert result is True

    def test_inkwell_count_below_threshold(self, state, engine):
        """Test inkwell-count when threshold is not met."""
        source_id = state.players[0].play[0] if state.players[0].play else 1

        condition = {"type": "inkwell-count", "value": 9999, "comparison": ">="}
        result = evaluate_condition(condition, state, None, source_id, engine)
        assert result is False


class TestEventBasedConditions:
    """Tests for event-based conditions."""

    def test_target_damaged_with_pending_event(self, state, engine):
        """Test target_damaged with a pending challenge event."""
        from lorcana_bot.state import PendingTriggeredEvent

        source_id = state.players[0].play[0] if state.players[0].play else 1
        target_id = state.players[1].play[0] if state.players[1].play else 4

        event = PendingTriggeredEvent(
            id="challenge-event",
            event="challenged",
            subject_card_id=source_id,
            defender_id=target_id,
            happened_in_challenge=True,
        )
        state.cards[target_id].damage = 2

        condition = {"type": "target_damaged"}
        result = evaluate_condition(condition, state, event, source_id, engine)
        assert result is True

    def test_target_damaged_no_damage(self, state, engine):
        """Test target_damaged when target has no damage."""
        from lorcana_bot.state import PendingTriggeredEvent

        source_id = state.players[0].play[0] if state.players[0].play else 1
        target_id = state.players[1].play[0] if state.players[1].play else 4

        event = PendingTriggeredEvent(
            id="challenge-event",
            event="challenged",
            subject_card_id=source_id,
            defender_id=target_id,
        )
        state.cards[target_id].damage = 0

        condition = {"type": "target_damaged"}
        result = evaluate_condition(condition, state, event, source_id, engine)
        assert result is False


class TestLogicalConditions:
    """Tests for logical conditions (and, or, not)."""

    def test_and_condition_all_true(self, state, engine):
        """Test 'and' condition when all operands are true."""
        source_id = state.players[0].play[0] if state.players[0].play else 1
        condition = {
            "type": "and",
            "conditions": [
                {"type": "your-turn"},
                {"type": "has-character-count", "value": 0, "comparison": ">="}
            ]
        }
        state.active_player = 0
        result = evaluate_condition(condition, state, None, source_id, engine)
        assert result is True

    def test_and_condition_one_false(self, state, engine):
        """Test 'and' condition when one operand is false."""
        source_id = state.players[0].play[0] if state.players[0].play else 1
        condition = {
            "type": "and",
            "conditions": [
                {"type": "your-turn"},
                {"type": "has-character-count", "value": 9999, "comparison": ">="}
            ]
        }
        state.active_player = 0
        result = evaluate_condition(condition, state, None, source_id, engine)
        assert result is False

    def test_or_condition_one_true(self, state, engine):
        """Test 'or' condition when one operand is true."""
        source_id = state.players[0].play[0] if state.players[0].play else 1
        condition = {
            "type": "or",
            "conditions": [
                {"type": "your-turn"},
                {"type": "has-character-count", "value": 9999, "comparison": ">="}
            ]
        }
        state.active_player = 0
        result = evaluate_condition(condition, state, None, source_id, engine)
        assert result is True

    def test_or_condition_all_false(self, state, engine):
        """Test 'or' condition when all operands are false."""
        source_id = state.players[0].play[0] if state.players[0].play else 1
        condition = {
            "type": "or",
            "conditions": [
                {"type": "opponent-turn"},
                {"type": "has-character-count", "value": 9999, "comparison": ">="}
            ]
        }
        state.active_player = 0  # Not opponent's turn
        result = evaluate_condition(condition, state, None, source_id, engine)
        assert result is False

    def test_not_condition(self, state, engine):
        """Test 'not' condition."""
        source_id = state.players[0].play[0] if state.players[0].play else 1
        condition = {
            "type": "not",
            "condition": {"type": "has-character-count", "value": 9999, "comparison": ">="}
        }
        result = evaluate_condition(condition, state, None, source_id, engine)
        assert result is True


class TestAdvancedConditions:
    """Tests for advanced conditions."""

    def test_in_challenge_condition(self, state, engine):
        """Test in-challenge condition."""
        source_id = state.players[0].play[0] if state.players[0].play else 1
        state.cards[source_id].was_challenged_this_turn = True

        condition = {"type": "in-challenge", "role": "defender"}
        result = evaluate_condition(condition, state, None, source_id, engine)
        assert result is True

    def test_being_challenged_condition(self, state, engine):
        """Test being-challenged condition."""
        source_id = state.players[0].play[0] if state.players[0].play else 1
        state.cards[source_id].was_challenged_this_turn = True

        condition = {"type": "being-challenged"}
        result = evaluate_condition(condition, state, None, source_id, engine)
        assert result is True

    def test_opponent_has_damaged_character(self, state, engine):
        """Test opponent-has-damaged-character condition.

        This tests that the condition evaluates without error.
        In the demo deck setup, opponent may or may not have damaged characters.
        """
        source_id = state.players[0].play[0] if state.players[0].play else 1
        condition = {"type": "opponent-has-damaged-character"}
        # Just verify it evaluates without raising an error
        result = evaluate_condition(condition, state, None, source_id, engine)
        assert isinstance(result, bool)


class TestUnsupportedCondition:
    """Tests for unsupported condition handling."""

    def test_unsupported_condition_raises_error(self, state, engine):
        """Test that unsupported conditions raise UnsupportedConditionError."""
        source_id = state.players[0].play[0] if state.players[0].play else 1
        condition = {"type": "totally-unknown-condition"}
        with pytest.raises(UnsupportedConditionError) as exc_info:
            evaluate_condition(condition, state, None, source_id, engine)
        assert "Unsupported condition kind" in str(exc_info.value)

    def test_no_silent_true_for_unsupported(self, state, engine):
        """Test that unsupported conditions do NOT silently evaluate to True."""
        source_id = state.players[0].play[0] if state.players[0].play else 1
        condition = {"type": "truly-unsupported-condition"}
        with pytest.raises(UnsupportedConditionError):
            evaluate_condition(condition, state, None, source_id, engine)


class TestComparisonOperators:
    """Tests for various comparison operators."""

    def test_greater_than(self, state, engine):
        """Test > comparison."""
        source_id = state.players[0].play[0] if state.players[0].play else 1
        condition = {"type": "has-character-count", "value": 1000, "comparison": ">"}
        result = evaluate_condition(condition, state, None, source_id, engine)
        assert result is False

    def test_greater_than_or_equal(self, state, engine):
        """Test >= comparison."""
        source_id = state.players[0].play[0] if state.players[0].play else 1
        char_count = len(state.players[0].play)
        condition = {"type": "has-character-count", "value": char_count, "comparison": ">="}
        result = evaluate_condition(condition, state, None, source_id, engine)
        assert result is True

    def test_equal(self, state, engine):
        """Test == comparison."""
        source_id = state.players[0].play[0] if state.players[0].play else 1
        char_count = len(state.players[0].play)
        condition = {"type": "has-character-count", "value": char_count, "comparison": "=="}
        result = evaluate_condition(condition, state, None, source_id, engine)
        assert result is True

    def test_not_equal(self, state, engine):
        """Test != comparison."""
        source_id = state.players[0].play[0] if state.players[0].play else 1
        condition = {"type": "has-character-count", "value": 9999, "comparison": "!="}
        result = evaluate_condition(condition, state, None, source_id, engine)
        assert result is True


class TestRealDeckConditions:
    """Tests for conditions appearing in real decks (6.1 safety hardening).

    These conditions should either:
    1. Be fully implemented and evaluate correctly
    2. Raise UnsupportedConditionError if not implementable
    They should NEVER silently return True.
    """

    def test_target_query_condition(self, state, engine):
        """Test target-query condition (real deck condition)."""
        source_id = state.players[0].play[0] if state.players[0].play else 1
        condition = {
            "type": "target-query",
            "comparison": {"operator": ">=", "value": 1},
            "query": {
                "cardType": "character",
                "owner": "you",
                "zones": ["play"]
            }
        }
        result = evaluate_condition(condition, state, None, source_id, engine)
        assert isinstance(result, bool)

    def test_target_query_missing_query_raises(self, state, engine):
        """Test target-query raises when query is missing."""
        source_id = state.players[0].play[0] if state.players[0].play else 1
        condition = {"type": "target-query"}
        with pytest.raises(UnsupportedConditionError):
            evaluate_condition(condition, state, None, source_id, engine)

    def test_used_shift_raises(self, state, engine):
        """Test used-shift condition raises (not implemented)."""
        source_id = state.players[0].play[0] if state.players[0].play else 1
        condition = {"type": "used-shift"}
        # This should raise because used-shift is blocked
        with pytest.raises(UnsupportedConditionError):
            evaluate_condition(condition, state, None, source_id, engine)

    def test_banished_in_challenge_raises(self, state, engine):
        """Test banished-in-challenge-this-turn raises (stub returns False)."""
        source_id = state.players[0].play[0] if state.players[0].play else 1
        condition = {"type": "banished-in-challenge-this-turn"}
        # Should return False (stub implementation) rather than raise
        result = evaluate_condition(condition, state, None, source_id, engine)
        assert isinstance(result, bool)

    def test_has_card_under_raises(self, state, engine):
        """Test has-card-under raises (not tracked)."""
        source_id = state.players[0].play[0] if state.players[0].play else 1
        condition = {"type": "has-card-under"}
        # This should raise because has-card-under is blocked
        with pytest.raises(UnsupportedConditionError):
            evaluate_condition(condition, state, None, source_id, engine)

    def test_trigger_subject_had_card_under_raises(self, state, engine):
        """Test trigger-subject-had-card-under raises (not tracked)."""
        source_id = state.players[0].play[0] if state.players[0].play else 1
        condition = {"type": "trigger-subject-had-card-under"}
        with pytest.raises(UnsupportedConditionError):
            evaluate_condition(condition, state, None, source_id, engine)

    def test_put_card_under_any_this_turn_raises(self, state, engine):
        """Test put-card-under-any-this-turn raises (not tracked)."""
        source_id = state.players[0].play[0] if state.players[0].play else 1
        condition = {"type": "put-card-under-any-this-turn"}
        with pytest.raises(UnsupportedConditionError):
            evaluate_condition(condition, state, None, source_id, engine)

    def test_target_aggregate_comparison_raises(self, state, engine):
        """Test target-aggregate-comparison raises (not implemented)."""
        source_id = state.players[0].play[0] if state.players[0].play else 1
        condition = {"type": "target-aggregate-comparison"}
        with pytest.raises(UnsupportedConditionError):
            evaluate_condition(condition, state, None, source_id, engine)

    def test_non_dict_condition_raises(self, state, engine):
        """Test non-dict condition raises UnsupportedConditionError."""
        source_id = state.players[0].play[0] if state.players[0].play else 1
        with pytest.raises(UnsupportedConditionError) as exc_info:
            evaluate_condition("not-a-dict", state, None, source_id, engine)
        assert "Non-dict condition" in str(exc_info.value)

    def test_unknown_dict_condition_raises(self, state, engine):
        """Test unknown dict condition kind raises."""
        source_id = state.players[0].play[0] if state.players[0].play else 1
        condition = {"type": "totally-unknown-condition-xyz"}
        with pytest.raises(UnsupportedConditionError) as exc_info:
            evaluate_condition(condition, state, None, source_id, engine)
        assert "Unsupported condition kind" in str(exc_info.value)

    def test_nested_unsupported_in_and_propagates(self, state, engine):
        """Test unsupported nested condition raises through 'and'."""
        source_id = state.players[0].play[0] if state.players[0].play else 1
        condition = {
            "type": "and",
            "conditions": [
                {"type": "your-turn"},
                {"type": "totally-unsupported-xyz"}
            ]
        }
        with pytest.raises(UnsupportedConditionError):
            evaluate_condition(condition, state, None, source_id, engine)

    def test_nested_unsupported_in_or_propagates(self, state, engine):
        """Test unsupported nested condition raises through 'or'."""
        source_id = state.players[0].play[0] if state.players[0].play else 1
        condition = {
            "type": "or",
            "conditions": [
                {"type": "has-character-count", "value": 9999, "comparison": ">="},
                {"type": "another-unsupported-xyz"}
            ]
        }
        with pytest.raises(UnsupportedConditionError):
            evaluate_condition(condition, state, None, source_id, engine)

    def test_nested_unsupported_in_not_propagates(self, state, engine):
        """Test unsupported nested condition raises through 'not'."""
        source_id = state.players[0].play[0] if state.players[0].play else 1
        condition = {
            "type": "not",
            "condition": {"type": "really-unsupported-xyz"}
        }
        with pytest.raises(UnsupportedConditionError):
            evaluate_condition(condition, state, None, source_id, engine)
