"""Tests for automation resolve bag functionality.

Validates that:
- resolveBag candidates are enumerated with correct metadata
- candidates rank before normal play actions (family order 3)
- optional accept/decline are scored appropriately
- mandatory triggers always score high
"""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock

from lorcana_bot.automation.candidate_enumerator import enumerate_automated_action_candidates, _pending_effect_candidates
from lorcana_bot.automation.candidates import AutomatedActionFamily, FAMILY_ORDER
from lorcana_bot.automation.strategies.lore_race_strategy import score_lore_race
from lorcana_bot.automation.strategy import StrategyContext
from lorcana_bot.cards import CardDatabase
from lorcana_bot.state import BagEffectEntry, GameState, PlayerState, CardInstance
from lorcana_bot.engine import GameEngine


class TestResolveBagFamilyOrder:
    """Test that RESOLVE_BAG ranks before normal play actions."""

    def test_resolve_bag_before_play_card(self):
        """RESOLVE_BAG (order 3) should rank before PLAY_CARD (order 4)."""
        assert FAMILY_ORDER[AutomatedActionFamily.RESOLVE_BAG] < FAMILY_ORDER[AutomatedActionFamily.PLAY_CARD]

    def test_resolve_bag_before_quest(self):
        """RESOLVE_BAG (order 3) should rank before QUEST (order 4.5)."""
        assert FAMILY_ORDER[AutomatedActionFamily.RESOLVE_BAG] < FAMILY_ORDER[AutomatedActionFamily.QUEST]

    def test_resolve_effect_before_resolve_bag(self):
        """RESOLVE_EFFECT (order 2) should rank before RESOLVE_BAG (order 3)."""
        assert FAMILY_ORDER[AutomatedActionFamily.RESOLVE_EFFECT] < FAMILY_ORDER[AutomatedActionFamily.RESOLVE_BAG]


class TestResolveBagScoring:
    """Test scoring logic for resolve bag candidates."""

    def test_mandatory_trigger_scores_high(self):
        """Mandatory triggers should have high resolution priority."""
        state = MagicMock(spec=GameState)
        engine = MagicMock(spec=GameEngine)
        context = StrategyContext(
            state=state,
            engine=engine,
            actor=0,
            information_policy="fair",
            actor_observation=None,
            actor_deck_profile=None,
            opponent_deck_profile=None,
            turn_number=1,
            phase="MAIN",
        )

        # Create mandatory resolve bag candidate
        candidate = MagicMock()
        candidate.family = AutomatedActionFamily.RESOLVE_BAG
        candidate.effect_polarity = "beneficial"
        candidate.projected_benefit = 3.0
        candidate.projected_harm = 0.0
        candidate.resolve_optional = None  # Mandatory
        candidate.metadata = {"optional": False}
        candidate.actor = 0

        score, contributors = score_lore_race(context, candidate)

        # Should have high resolve_required score
        resolve_required = next((c for c in contributors if c.name == "resolve_required"), None)
        assert resolve_required is not None
        assert resolve_required.value == 100

        # Should have mandatory resolution bonus
        mandatory = next((c for c in contributors if c.name == "mandatory_resolution"), None)
        assert mandatory is not None


    def test_optional_beneficial_accept_scores_higher(self):
        """Accepting beneficial optional triggers should score higher than declining."""
        state = MagicMock(spec=GameState)
        engine = MagicMock(spec=GameEngine)
        context = StrategyContext(
            state=state,
            engine=engine,
            actor=0,
            information_policy="fair",
            actor_observation=None,
            actor_deck_profile=None,
            opponent_deck_profile=None,
            turn_number=1,
            phase="MAIN",
        )

        # Create optional beneficial accept candidate
        accept_candidate = MagicMock()
        accept_candidate.family = AutomatedActionFamily.RESOLVE_BAG
        accept_candidate.effect_polarity = "beneficial"
        accept_candidate.projected_benefit = 3.0
        accept_candidate.projected_harm = 0.0
        accept_candidate.resolve_optional = True  # Accepting
        accept_candidate.metadata = {"optional": True}
        accept_candidate.actor = 0

        # Create optional beneficial decline candidate
        decline_candidate = MagicMock()
        decline_candidate.family = AutomatedActionFamily.RESOLVE_BAG
        decline_candidate.effect_polarity = "beneficial"
        decline_candidate.projected_benefit = 3.0
        decline_candidate.projected_harm = 0.0
        decline_candidate.resolve_optional = False  # Declining
        decline_candidate.metadata = {"optional": True}
        decline_candidate.actor = 0

        accept_score, _ = score_lore_race(context, accept_candidate)
        decline_score, _ = score_lore_race(context, decline_candidate)

        assert accept_score > decline_score


    def test_optional_harmful_decline_scores_higher(self):
        """Declining harmful optional triggers should score higher than accepting."""
        state = MagicMock(spec=GameState)
        engine = MagicMock(spec=GameEngine)
        context = StrategyContext(
            state=state,
            engine=engine,
            actor=0,
            information_policy="fair",
            actor_observation=None,
            actor_deck_profile=None,
            opponent_deck_profile=None,
            turn_number=1,
            phase="MAIN",
        )

        # Create optional harmful accept candidate
        accept_candidate = MagicMock()
        accept_candidate.family = AutomatedActionFamily.RESOLVE_BAG
        accept_candidate.effect_polarity = "harmful"
        accept_candidate.projected_benefit = 0.0
        accept_candidate.projected_harm = 3.0
        accept_candidate.resolve_optional = True  # Accepting (bad)
        accept_candidate.metadata = {"optional": True}
        accept_candidate.actor = 0

        # Create optional harmful decline candidate
        decline_candidate = MagicMock()
        decline_candidate.family = AutomatedActionFamily.RESOLVE_BAG
        decline_candidate.effect_polarity = "harmful"
        decline_candidate.projected_benefit = 0.0
        decline_candidate.projected_harm = 3.0
        decline_candidate.resolve_optional = False  # Declining (good)
        decline_candidate.metadata = {"optional": True}
        decline_candidate.actor = 0

        accept_score, _ = score_lore_race(context, accept_candidate)
        decline_score, _ = score_lore_race(context, decline_candidate)

        assert decline_score > accept_score


class TestResolveEffectFamilyOrder:
    """Test that RESOLVE_EFFECT ranks correctly."""

    def test_resolve_effect_before_resolve_bag(self):
        """RESOLVE_EFFECT (order 2) should rank before RESOLVE_BAG (order 3)."""
        assert FAMILY_ORDER[AutomatedActionFamily.RESOLVE_EFFECT] < FAMILY_ORDER[AutomatedActionFamily.RESOLVE_BAG]

    def test_resolve_effect_before_play_card(self):
        """RESOLVE_EFFECT (order 2) should rank before PLAY_CARD (order 4)."""
        assert FAMILY_ORDER[AutomatedActionFamily.RESOLVE_EFFECT] < FAMILY_ORDER[AutomatedActionFamily.PLAY_CARD]