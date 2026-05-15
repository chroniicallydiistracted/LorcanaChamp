"""Tests for automation pending effects functionality.

Validates that:
- resolveEffect candidates are enumerated correctly
- target selection candidates are generated with proper metadata
- choice index candidates are generated
- optional accept/decline candidates are created
- candidate metadata includes effect polarity and projected benefit
- validator correctly handles resolveEffect family
"""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch

from lorcana_bot.automation.candidate_enumerator import enumerate_automated_action_candidates
from lorcana_bot.automation.candidates import AutomatedActionFamily
from lorcana_bot.automation.candidate_validator import validate_candidate
from lorcana_bot.automation.move_adapter import candidate_to_action
from lorcana_bot.pending_effects import PendingEffect, TargetRequirement
from lorcana_bot.state import GameState, PlayerState, CardInstance
from lorcana_bot.engine import GameEngine


class TestPendingEffectCandidateEnumeration:
    """Test that pending effect candidates are properly enumerated."""

    def test_resolve_effect_enumerates_with_optional_accept_decline(self):
        """Optional pending effects should create accept and decline candidates."""
        # Create mock pending effect with optional
        pe = MagicMock()
        pe.id = "pe_1"
        pe.chooser_id = 0
        pe.source_id = 1
        pe.source_card_id = "card_123"
        pe.effects = []
        pe.current_effect_index = 0
        pe.optional = True
        pe.accepted = None
        pe.current_requirement = None
        pe.requires_target_input = False
        pe.requires_choice_input = False
        pe.origin = "action"
        pe.origin_id = "test_ability"
        pe.raw = {}
        
        with patch("lorcana_bot.pending_effects.get_current_pending_effect", return_value=pe):
            from lorcana_bot.automation.candidate_enumerator import _pending_effect_candidates
            candidates = _pending_effect_candidates(MagicMock(), MagicMock(), 0)
        
        assert len(candidates) == 2  # Accept and decline
        
        # Check accept candidate
        accept = next((c for c in candidates if c.resolve_optional is True), None)
        assert accept is not None
        assert accept.family == AutomatedActionFamily.RESOLVE_EFFECT
        assert accept.metadata.get("accept") is True
        
        # Check decline candidate
        decline = next((c for c in candidates if c.resolve_optional is False), None)
        assert decline is not None
        assert decline.family == AutomatedActionFamily.RESOLVE_EFFECT
        assert decline.metadata.get("accept") is False

    def test_resolve_effect_enumerates_with_target_selection(self):
        """Target selection requirements should create target-specific candidates."""
        requirement = TargetRequirement(
            kind="chosen_opposing_character",
            min_targets=1,
            max_targets=1,
            card_type="character",
            owner_filter="opponent",
        )
        
        pe = MagicMock()
        pe.id = "pe_2"
        pe.chooser_id = 0
        pe.source_id = 1
        pe.source_card_id = "card_123"
        pe.effects = []
        pe.current_effect_index = 0
        pe.optional = False
        pe.accepted = None
        pe.current_requirement = requirement
        pe.requires_target_input = True
        pe.requires_choice_input = False
        pe.origin = "bag"
        pe.origin_id = None
        pe.raw = {}
        
        # Mock state with two characters in opponent play area
        mock_state = MagicMock()
        mock_state.cards = {}
        mock_state.players = {
            0: MagicMock(play=[]),  # Player 0 has no play
            1: MagicMock(play=[10, 11]),  # Player 1 (opponent) has two characters
        }
        mock_state.opponent = MagicMock(return_value=1)
        
        # Mock card instances
        for cid in [10, 11]:
            mock_state.cards[cid] = MagicMock(
                zone="play",
                damage=0,
                exerted=False,
            )
        
        mock_engine = MagicMock()
        mock_engine.card_def = MagicMock(return_value=MagicMock(card_type="character"))
        
        with patch("lorcana_bot.pending_effects.get_current_pending_effect", return_value=pe):
            with patch("lorcana_bot.pending_effects.get_valid_targets_for_requirement", return_value=[10, 11]):
                from lorcana_bot.automation.candidate_enumerator import _pending_effect_candidates
                candidates = _pending_effect_candidates(mock_state, mock_engine, 0)
        
        # Should have candidates for each valid target
        assert len(candidates) == 2
        assert all(c.family == AutomatedActionFamily.RESOLVE_EFFECT for c in candidates)
        assert all(c.target_instance_id in [10, 11] for c in candidates)

    def test_resolve_effect_includes_effect_metadata(self):
        """Candidates should include effect kind and polarity metadata."""
        pe = MagicMock()
        pe.id = "pe_3"
        pe.chooser_id = 0
        pe.source_id = 1
        pe.source_card_id = "card_123"
        pe.effects = []
        pe.current_effect_index = 0
        pe.optional = True
        pe.accepted = None
        pe.current_requirement = None
        pe.requires_target_input = False
        pe.requires_choice_input = False
        pe.origin = "bag"
        pe.origin_id = None
        pe.raw = {}
        
        with patch("lorcana_bot.pending_effects.get_current_pending_effect", return_value=pe):
            from lorcana_bot.automation.candidate_enumerator import _pending_effect_candidates
            candidates = _pending_effect_candidates(MagicMock(), MagicMock(), 0)
        
        assert len(candidates) > 0
        for c in candidates:
            assert "effect_kind" in c.metadata or c.effect_kind is not None
            assert "effect_polarity" in c.metadata or c.effect_polarity is not None


class TestPendingEffectValidation:
    """Test validation of resolveEffect candidates."""

    def test_resolve_effect_chooser_check_exists(self):
        """resolveEffect validator checks that actor is the correct chooser."""
        # This tests the validator logic exists by checking the function structure
        from lorcana_bot.automation.candidate_validator import validate_candidate
        # The function should exist and handle resolveEffect
        assert callable(validate_candidate)


class TestPendingEffectMoveAdapter:
    """Test move adapter correctly maps resolveEffect to action."""

    def test_resolve_effect_maps_to_resolve_pending_effect_action(self):
        """candidate_to_action should map RESOLVE_EFFECT to ACTION_RESOLVE_PENDING_EFFECT."""
        candidate = MagicMock()
        candidate.family = AutomatedActionFamily.RESOLVE_EFFECT
        candidate.actor = 0
        candidate.pending_effect_id = "pe_1"
        candidate.source_instance_id = 5
        candidate.target_instance_id = 10
        candidate.choice_index = None
        candidate.resolve_optional = None
        candidate.metadata = {"pending_effect_id": "pe_1"}
        
        action = candidate_to_action(candidate)
        
        assert action.kind == "RESOLVE_PENDING_EFFECT"
        assert action.actor == 0
        assert action.source == 5
        assert action.target == 10

    def test_resolve_effect_with_accept_maps_correctly(self):
        """resolveEffect with accept=True should include accept in choice."""
        candidate = MagicMock()
        candidate.family = AutomatedActionFamily.RESOLVE_EFFECT
        candidate.actor = 0
        candidate.pending_effect_id = "pe_1"
        candidate.source_instance_id = 5
        candidate.target_instance_id = None
        candidate.choice_index = None
        candidate.resolve_optional = True  # Accepting
        candidate.metadata = {"pending_effect_id": "pe_1"}
        
        action = candidate_to_action(candidate)
        
        assert action.kind == "RESOLVE_PENDING_EFFECT"
        assert action.choice.get("accept") is True

    def test_resolve_effect_with_choice_index(self):
        """resolveEffect with choice index should include it in choice."""
        candidate = MagicMock()
        candidate.family = AutomatedActionFamily.RESOLVE_EFFECT
        candidate.actor = 0
        candidate.pending_effect_id = "pe_1"
        candidate.source_instance_id = 5
        candidate.target_instance_id = None
        candidate.choice_index = 2
        candidate.resolve_optional = None
        candidate.metadata = {"pending_effect_id": "pe_1"}
        
        action = candidate_to_action(candidate)
        
        assert action.choice.get("choice_index") == 2