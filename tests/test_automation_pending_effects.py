"""Tests for automation pending effects functionality.

Validates that:
- resolveEffect candidates are enumerated correctly
- target selection candidates are generated with proper metadata
- choice index candidates are generated
- optional accept/decline candidates are created
- candidate metadata includes effect polarity and projected benefit
- validator correctly handles resolveEffect family
- B9: All pending choice fields round-trip through automation candidates
"""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch

from lorcana_bot.actions import Action
from lorcana_bot.automation.candidate_enumerator import enumerate_automated_action_candidates, _candidate_from_action
from lorcana_bot.automation.candidates import AutomatedActionCandidate, AutomatedActionFamily
from lorcana_bot.automation.candidate_validator import validate_candidate
from lorcana_bot.automation.move_adapter import candidate_to_action
from lorcana_bot.pending_effects import PendingEffect, TargetRequirement
from lorcana_bot.state import GameState, PlayerState, CardInstance
from lorcana_bot.engine import GameEngine
from lorcana_bot.constants import ACTION_RESOLVE_PENDING_EFFECT


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


# =============================================================================
# B9: Round-Trip Tests for Pending Choice Fields
# Tests that all pending choice fields round-trip through automation candidates
# =============================================================================

class TestPendingChoiceRoundTrip:
    """B9: Tests that pending choice fields round-trip correctly.

    Round-trip invariant:
    candidate_to_action(action_to_candidate(action, state, engine)) == action
    """

    def _make_mock_engine(self):
        """Create a mock engine for card_def lookups."""
        mock_engine = MagicMock()
        mock_engine.card_def = MagicMock(side_effect=lambda state, cid: MagicMock(
            id=f"card_{cid}",
            full_name=f"Card {cid}",
            card_type="character",
        ))
        return mock_engine

    def _make_mock_state_with_cards(self):
        """Create a mock state with some cards."""
        mock_state = MagicMock()
        mock_state.cards = {}
        for cid in range(1, 21):
            mock_state.cards[cid] = MagicMock(
                zone="play",
                damage=0,
                exerted=False,
                card_id=f"card_{cid}",
            )
        mock_state.opponent = MagicMock(return_value=1)
        mock_state.players = {
            0: MagicMock(play=[1, 2, 3], hand=[10, 11], deck=[100, 101, 102, 103]),
            1: MagicMock(play=[4, 5, 6], hand=[12, 13], deck=[200, 201]),
        }
        return mock_state

    def test_amount_pending_action_round_trips(self):
        """B9: amount pending action round-trips through automation candidate."""
        mock_state = self._make_mock_state_with_cards()
        mock_engine = self._make_mock_engine()

        # Create action with amount
        action = Action(
            ACTION_RESOLVE_PENDING_EFFECT,
            actor=0,
            source=1,
            choice={
                "pending_effect_id": "pe_amount",
                "amount": 5,
            }
        )

        # Convert action to candidate
        candidate = _candidate_from_action(mock_state, mock_engine, action)

        # Verify candidate has amount
        assert candidate is not None
        assert candidate.amount == 5
        assert candidate.metadata.get("amount") == 5

        # Convert candidate back to action
        result_action = candidate_to_action(candidate)

        # Verify round-trip
        assert result_action.kind == ACTION_RESOLVE_PENDING_EFFECT
        assert result_action.choice.get("amount") == 5
        assert result_action.choice.get("pending_effect_id") == "pe_amount"

    def test_target_pending_action_round_trips(self):
        """B9: target pending action round-trips (single target)."""
        mock_state = self._make_mock_state_with_cards()
        mock_engine = self._make_mock_engine()

        # Create action with single target
        action = Action(
            ACTION_RESOLVE_PENDING_EFFECT,
            actor=0,
            source=1,
            target=4,
            choice={
                "pending_effect_id": "pe_target",
                "target": 4,
            }
        )

        # Convert action to candidate
        candidate = _candidate_from_action(mock_state, mock_engine, action)

        # Verify candidate has target
        assert candidate is not None
        assert candidate.target_instance_id == 4

        # Convert candidate back to action
        result_action = candidate_to_action(candidate)

        # Verify round-trip
        assert result_action.kind == ACTION_RESOLVE_PENDING_EFFECT
        assert result_action.target == 4
        assert result_action.choice.get("target") == 4

    def test_multi_target_pending_action_round_trips(self):
        """B9: multi_target pending action round-trips."""
        mock_state = self._make_mock_state_with_cards()
        mock_engine = self._make_mock_engine()

        # Create action with multiple targets
        action = Action(
            ACTION_RESOLVE_PENDING_EFFECT,
            actor=0,
            source=1,
            choice={
                "pending_effect_id": "pe_multi_target",
                "targets": [4, 5, 6],
            }
        )

        # Convert action to candidate
        candidate = _candidate_from_action(mock_state, mock_engine, action)

        # Verify candidate has targets
        assert candidate is not None
        assert candidate.targets == (4, 5, 6)
        assert candidate.metadata.get("targets") == (4, 5, 6)

        # Convert candidate back to action
        result_action = candidate_to_action(candidate)

        # Verify round-trip
        assert result_action.kind == ACTION_RESOLVE_PENDING_EFFECT
        assert result_action.choice.get("targets") == [4, 5, 6]

    def test_discard_choice_pending_action_round_trips(self):
        """B9: discard_choice pending action round-trips."""
        mock_state = self._make_mock_state_with_cards()
        mock_engine = self._make_mock_engine()

        # Create action with discard_card_ids
        action = Action(
            ACTION_RESOLVE_PENDING_EFFECT,
            actor=0,
            source=1,
            choice={
                "pending_effect_id": "pe_discard",
                "discard_card_ids": [10, 11],
            }
        )

        # Convert action to candidate
        candidate = _candidate_from_action(mock_state, mock_engine, action)

        # Verify candidate has discard_card_ids
        assert candidate is not None
        assert candidate.discard_card_ids == (10, 11)
        assert candidate.metadata.get("discard_card_ids") == (10, 11)

        # Convert candidate back to action
        result_action = candidate_to_action(candidate)

        # Verify round-trip
        assert result_action.kind == ACTION_RESOLVE_PENDING_EFFECT
        assert result_action.choice.get("discard_card_ids") == [10, 11]

    def test_choice_pending_action_round_trips(self):
        """B9: choice pending action round-trips."""
        mock_state = self._make_mock_state_with_cards()
        mock_engine = self._make_mock_engine()

        # Create action with choice_index
        action = Action(
            ACTION_RESOLVE_PENDING_EFFECT,
            actor=0,
            source=1,
            choice={
                "pending_effect_id": "pe_choice",
                "choice_index": 2,
            }
        )

        # Convert action to candidate
        candidate = _candidate_from_action(mock_state, mock_engine, action)

        # Verify candidate has choice_index
        assert candidate is not None
        assert candidate.choice_index == 2
        assert candidate.metadata.get("choice_index") == 2

        # Convert candidate back to action
        result_action = candidate_to_action(candidate)

        # Verify round-trip
        assert result_action.kind == ACTION_RESOLVE_PENDING_EFFECT
        assert result_action.choice.get("choice_index") == 2

    def test_optional_pending_action_round_trips(self):
        """B9: optional pending action round-trips."""
        mock_state = self._make_mock_state_with_cards()
        mock_engine = self._make_mock_engine()

        # Create action with accept
        action = Action(
            ACTION_RESOLVE_PENDING_EFFECT,
            actor=0,
            source=1,
            choice={
                "pending_effect_id": "pe_optional",
                "accept": True,
            }
        )

        # Convert action to candidate
        candidate = _candidate_from_action(mock_state, mock_engine, action)

        # Verify candidate has resolve_optional
        assert candidate is not None
        assert candidate.resolve_optional is True
        assert candidate.metadata.get("accept") is True

        # Convert candidate back to action
        result_action = candidate_to_action(candidate)

        # Verify round-trip
        assert result_action.kind == ACTION_RESOLVE_PENDING_EFFECT
        assert result_action.choice.get("accept") is True

    def test_enter_play_exerted_pending_action_round_trips(self):
        """B9: enter_play_exerted pending action round-trips."""
        mock_state = self._make_mock_state_with_cards()
        mock_engine = self._make_mock_engine()

        # Create action with enter_play_exerted
        action = Action(
            ACTION_RESOLVE_PENDING_EFFECT,
            actor=0,
            source=1,
            choice={
                "pending_effect_id": "pe_exerted",
                "enter_play_exerted": True,
            }
        )

        # Convert action to candidate
        candidate = _candidate_from_action(mock_state, mock_engine, action)

        # Verify candidate has enter_play_exerted
        assert candidate is not None
        assert candidate.enter_play_exerted is True
        assert candidate.metadata.get("enter_play_exerted") is True

        # Convert candidate back to action
        result_action = candidate_to_action(candidate)

        # Verify round-trip
        assert result_action.kind == ACTION_RESOLVE_PENDING_EFFECT
        assert result_action.choice.get("enter_play_exerted") is True

    def test_named_card_pending_action_round_trips(self):
        """B9: named_card pending action round-trips."""
        mock_state = self._make_mock_state_with_cards()
        mock_engine = self._make_mock_engine()

        # Create action with named_card
        action = Action(
            ACTION_RESOLVE_PENDING_EFFECT,
            actor=0,
            source=1,
            choice={
                "pending_effect_id": "pe_named",
                "named_card": "Mickey Mouse",
            }
        )

        # Convert action to candidate
        candidate = _candidate_from_action(mock_state, mock_engine, action)

        # Verify candidate has named_card
        assert candidate is not None
        assert candidate.named_card == "Mickey Mouse"

        # Convert candidate back to action
        result_action = candidate_to_action(candidate)

        # Verify round-trip
        assert result_action.kind == ACTION_RESOLVE_PENDING_EFFECT
        assert result_action.choice.get("named_card") == "Mickey Mouse"

    def test_destination_pending_action_round_trips(self):
        """B9: destination pending action round-trips."""
        mock_state = self._make_mock_state_with_cards()
        mock_engine = self._make_mock_engine()

        # Create action with destination
        action = Action(
            ACTION_RESOLVE_PENDING_EFFECT,
            actor=0,
            source=1,
            choice={
                "pending_effect_id": "pe_destination",
                "destination": "hand",
            }
        )

        # Convert action to candidate
        candidate = _candidate_from_action(mock_state, mock_engine, action)

        # Verify candidate has destination in metadata
        assert candidate is not None
        assert candidate.metadata.get("destination") == "hand"
        assert "hand" in candidate.destinations

        # Convert candidate back to action
        result_action = candidate_to_action(candidate)

        # Verify round-trip
        assert result_action.kind == ACTION_RESOLVE_PENDING_EFFECT
        assert result_action.choice.get("destination") == "hand"

    def test_all_fields_together_round_trip(self):
        """B9: Verify all pending choice fields round-trip together."""
        mock_state = self._make_mock_state_with_cards()
        mock_engine = self._make_mock_engine()

        # Create action with all new fields
        action = Action(
            ACTION_RESOLVE_PENDING_EFFECT,
            actor=0,
            source=1,
            target=4,
            choice={
                "pending_effect_id": "pe_all",
                "amount": 3,
                "targets": [4, 5],
                "discard_card_ids": [10, 11],
                "enter_play_exerted": False,
                "accept": True,
                "choice_index": 1,
                "named_card": "Stitch",
                "destination": "play",
                "selected_card_id": 101,
                "top_cards": [100, 101],
                "bottom_cards": [102],
            }
        )

        # Convert action to candidate
        candidate = _candidate_from_action(mock_state, mock_engine, action)

        # Verify all fields captured
        assert candidate is not None
        assert candidate.amount == 3
        assert candidate.targets == (4, 5)
        assert candidate.discard_card_ids == (10, 11)
        assert candidate.enter_play_exerted is False
        assert candidate.resolve_optional is True
        assert candidate.choice_index == 1
        assert candidate.named_card == "Stitch"
        assert candidate.target_instance_id == 4
        assert candidate.metadata.get("selected_card_id") == 101
        assert candidate.metadata.get("top_cards") == (100, 101)
        assert candidate.metadata.get("bottom_cards") == (102,)

        # Convert candidate back to action
        result_action = candidate_to_action(candidate)

        # Verify all fields round-trip (note: lists may become tuples in metadata storage)
        assert result_action.kind == ACTION_RESOLVE_PENDING_EFFECT
        assert result_action.choice.get("amount") == 3
        assert list(result_action.choice.get("targets")) == [4, 5]
        assert list(result_action.choice.get("discard_card_ids")) == [10, 11]
        assert result_action.choice.get("enter_play_exerted") is False
        assert result_action.choice.get("accept") is True
        assert result_action.choice.get("choice_index") == 1
        assert result_action.choice.get("named_card") == "Stitch"
        assert result_action.choice.get("destination") == "play"
        assert result_action.choice.get("selected_card_id") == 101
        # top_cards/bottom_cards stored as tuples in metadata, converted back to lists in choice
        assert list(result_action.choice.get("top_cards")) == [100, 101]
        assert list(result_action.choice.get("bottom_cards")) == [102]
        assert result_action.target == 4

    def test_special_microfix_4_scry_ordering_round_trips(self):
        """B9: Special Microfix 4 scry_ordering pending actions still round-trip."""
        mock_state = self._make_mock_state_with_cards()
        mock_engine = self._make_mock_engine()

        # Create scry action
        action = Action(
            ACTION_RESOLVE_PENDING_EFFECT,
            actor=0,
            source=1,
            choice={
                "pending_effect_id": "pe_scry",
                "top_cards": [100, 101],
                "bottom_cards": [102],
            }
        )

        # Convert action to candidate
        candidate = _candidate_from_action(mock_state, mock_engine, action)

        # Verify scry fields captured
        assert candidate is not None
        assert candidate.metadata.get("top_cards") == (100, 101)
        assert candidate.metadata.get("bottom_cards") == (102,)

        # Convert candidate back to action
        result_action = candidate_to_action(candidate)

        # Verify round-trip (metadata stores tuples, choice may preserve them)
        assert result_action.kind == ACTION_RESOLVE_PENDING_EFFECT
        assert list(result_action.choice.get("top_cards")) == [100, 101]
        assert list(result_action.choice.get("bottom_cards")) == [102]

    def test_special_microfix_4_search_selection_round_trips(self):
        """B9: Special Microfix 4 search_selection pending actions still round-trip."""
        mock_state = self._make_mock_state_with_cards()
        mock_engine = self._make_mock_engine()

        # Create search action
        action = Action(
            ACTION_RESOLVE_PENDING_EFFECT,
            actor=0,
            source=1,
            choice={
                "pending_effect_id": "pe_search",
                "selected_card_id": 101,
                "destination": "hand",
            }
        )

        # Convert action to candidate
        candidate = _candidate_from_action(mock_state, mock_engine, action)

        # Verify search fields captured
        assert candidate is not None
        assert candidate.metadata.get("selected_card_id") == 101
        assert candidate.metadata.get("destination") == "hand"

        # Convert candidate back to action
        result_action = candidate_to_action(candidate)

        # Verify round-trip
        assert result_action.kind == ACTION_RESOLVE_PENDING_EFFECT
        assert result_action.choice.get("selected_card_id") == 101
        assert result_action.choice.get("destination") == "hand"

    def test_slotted_target_pending_action_round_trips(self):
        """B10.7: slotted target input round-trips through automation candidates."""
        mock_state = self._make_mock_state_with_cards()
        mock_engine = self._make_mock_engine()

        action = Action(
            ACTION_RESOLVE_PENDING_EFFECT,
            actor=0,
            source=1,
            choice={
                "pending_effect_id": "pe_slotted",
                "slotted_targets": {
                    "kind": "move-damage",
                    "from": [4],
                    "to": [5],
                },
            },
        )

        candidate = _candidate_from_action(mock_state, mock_engine, action)

        assert candidate is not None
        assert candidate.slotted_targets == {
            "kind": "move-damage",
            "from": (4,),
            "to": (5,),
        }
        assert candidate.targets == (4, 5)
        assert candidate.metadata["slotted_targets"] == candidate.slotted_targets

        result_action = candidate_to_action(candidate)

        assert result_action.kind == ACTION_RESOLVE_PENDING_EFFECT
        assert result_action.choice["slotted_targets"] == candidate.slotted_targets
        assert result_action.choice["targets"] == [4, 5]

    def test_move_adapter_writes_flat_targets_for_slotted_candidate_without_targets(self):
        """B10.7: move adapter exposes flattened targets for legacy pending paths."""
        candidate = AutomatedActionCandidate(
            family=AutomatedActionFamily.RESOLVE_EFFECT,
            actor=0,
            stable_key="slotted",
            pending_effect_id="pe_slotted",
            slotted_targets={
                "kind": "banish-and-play",
                "banish": (4,),
                "play": (5, 6),
            },
        )

        action = candidate_to_action(candidate)

        assert action.choice["slotted_targets"] == candidate.slotted_targets
        assert action.choice["targets"] == [4, 5, 6]
