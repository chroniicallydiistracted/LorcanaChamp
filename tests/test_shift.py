"""Tests for Shift mechanics.

This module tests:
- Shift keyword parsing and cost extraction
- Shift target matching by character name
- Shift requires matching character in play
- Shift pays shift cost instead of normal cost
- Shift emits play event with used_shift=True
- Shift conservatively transfers state (no damage, no exerted, etc.)
"""

import pytest
from lorcana_bot.cards import CardDef, CardDatabase
from lorcana_bot.engine import GameEngine
from lorcana_bot.state import CardInstance, GameState, PlayerState
from lorcana_bot.play_modes import (
    get_shift_info,
    get_shift_targets,
    can_play_as_shift,
    execute_shift_play,
    ShiftTarget,
)


def _make_test_shift_card(
    card_id: str,
    full_name: str,
    shift_cost: int,
    strength: int = 2,
    willpower: int = 3,
    lore: int = 1,
) -> CardDef:
    """Create a test Shift character card definition."""
    return CardDef(
        id=card_id,
        full_name=full_name,
        ink="amethyst",
        cost=8,  # Normal cost is 8
        inkable=True,
        card_type="character",
        strength=strength,
        willpower=willpower,
        lore=lore,
        keywords=(f"SHIFT({shift_cost})",) if shift_cost else ("SHIFT",),
    )


def _make_test_character(
    card_id: str,
    full_name: str,
    strength: int = 2,
    willpower: int = 3,
    lore: int = 1,
) -> CardDef:
    """Create a test non-shift character card definition."""
    return CardDef(
        id=card_id,
        full_name=full_name,
        ink="amber",
        cost=3,
        inkable=True,
        card_type="character",
        strength=strength,
        willpower=willpower,
        lore=lore,
        keywords=(),
    )


class TestShiftKeywordParsing:
    """Tests for Shift keyword parsing."""

    def test_shift_with_value(self):
        """SHIFT(5) should parse to cost 5."""
        keywords = ("SHIFT(5)",)
        cost = _parse_shift_cost(keywords)
        assert cost == 5

    def test_shift_with_colon(self):
        """SHIFT:3 should parse to cost 3."""
        keywords = ("SHIFT:3",)
        cost = _parse_shift_cost(keywords)
        assert cost == 3

    def test_shift_no_value_defaults_to_1(self):
        """SHIFT alone should default to cost 1."""
        keywords = ("SHIFT",)
        cost = _parse_shift_cost(keywords)
        assert cost == 1

    def test_shift_case_insensitive(self):
        """Shift parsing should be case insensitive."""
        keywords = ("shift(4)",)
        cost = _parse_shift_cost(keywords)
        assert cost == 4

    def test_no_shift_returns_none(self):
        """No Shift keyword should return None."""
        keywords = ("EVASIVE", "RUSH")
        cost = _parse_shift_cost(keywords)
        assert cost is None


def _parse_shift_cost(keywords: tuple[str, ...]) -> int | None:
    """Parse Shift X cost from keywords (same logic as play_modes)."""
    for keyword in keywords:
        upper = keyword.upper()
        if upper.startswith("SHIFT"):
            parts = upper.replace("(", ":").replace(")", ":").split(":")
            if len(parts) >= 2 and parts[1].isdigit():
                return int(parts[1])
            return 1
    return None


class TestShiftInfoRetrieval:
    """Tests for getting Shift info from a character."""

    def _setup_engine_with_shift(self, shift_cost: int = 3) -> tuple[GameEngine, GameState]:
        """Set up engine with a Shift character."""
        cards = [
            _make_test_shift_card(
                "test_shift_mal", "Maleficent", shift_cost,
                strength=7, willpower=7, lore=2
            ),
            _make_test_character(
                "test_regular", "Regular Character",
                strength=2, willpower=2, lore=1
            ),
        ]
        engine = GameEngine(CardDatabase(cards))
        
        state = GameState(
            players=[PlayerState(), PlayerState()],
            cards={},
        )
        
        # Add ink for player 0
        for i in range(10):
            state.cards[100 + i] = CardInstance(
                instance_id=100 + i, card_id="ink_amber", owner=0, controller=0, zone="inkwell"
            )
            state.players[0].inkwell.append(100 + i)
        
        return engine, state

    def test_get_shift_info_returns_cost(self):
        """get_shift_info should return shift cost for shift character."""
        engine, state = self._setup_engine_with_shift(3)
        
        cost = get_shift_info(state, engine, 1)  # Card not in play yet
        assert cost is None  # Card not in any zone
        
        # Add card to hand
        state.cards[1] = CardInstance(
            instance_id=1, card_id="test_shift_mal", owner=0, controller=0, zone="hand"
        )
        state.players[0].hand.append(1)
        
        cost = get_shift_info(state, engine, 1)
        assert cost == 3

    def test_get_shift_info_none_for_non_shift(self):
        """get_shift_info should return None for non-shift character."""
        engine, state = self._setup_engine_with_shift(3)
        
        # Create non-shift card (using registered card_id)
        state.cards[2] = CardInstance(
            instance_id=2, card_id="test_regular", owner=0, controller=0, zone="play"
        )
        state.players[0].play.append(2)
        
        cost = get_shift_info(state, engine, 2)
        assert cost is None


class TestShiftTargetMatching:
    """Tests for finding valid shift targets."""

    def _setup_shift_game_state(self) -> tuple[GameEngine, GameState]:
        """Set up complete game state with base character and shifted version."""
        cards = [
            _make_test_shift_card(
                "test_mal_base", "Maleficent", shift_cost=3,
                strength=3, willpower=4, lore=1
            ),
            _make_test_shift_card(
                "test_mal_shift", "Maleficent", shift_cost=3,
                strength=7, willpower=7, lore=2
            ),
        ]
        engine = GameEngine(CardDatabase(cards))
        
        state = GameState(
            players=[PlayerState(), PlayerState()],
            cards={},
        )
        
        # Add base Maleficent to play for player 0
        state.cards[1] = CardInstance(
            instance_id=1, card_id="test_mal_base", owner=0, controller=0, zone="play"
        )
        state.players[0].play.append(1)
        
        # Add shifted Maleficent to hand for player 0
        state.cards[2] = CardInstance(
            instance_id=2, card_id="test_mal_shift", owner=0, controller=0, zone="hand"
        )
        state.players[0].hand.append(2)
        
        # Add ink for player 0
        for i in range(10):
            state.cards[100 + i] = CardInstance(
                instance_id=100 + i, card_id="ink_amber", owner=0, controller=0, zone="inkwell"
            )
            state.players[0].inkwell.append(100 + i)
        
        return engine, state

    def test_get_shift_targets_finds_matching_character(self):
        """get_shift_targets should find character with matching name."""
        engine, state = self._setup_shift_game_state()
        
        targets = get_shift_targets(state, engine, 2)  # Shifted card in hand
        
        assert len(targets) == 1
        assert targets[0].instance_id == 1
        assert targets[0].card_name == "Maleficent"
        assert targets[0].shift_cost == 3

    def test_get_shift_targets_requires_hand(self):
        """get_shift_targets should only work for shifted card in hand."""
        engine, state = self._setup_shift_game_state()
        
        # Move shifted card to play (not in hand)
        state.cards[2].zone = "play"
        state.players[0].hand.remove(2)
        state.players[0].play.append(2)
        
        targets = get_shift_targets(state, engine, 2)
        assert len(targets) == 0


class TestCanPlayAsShift:
    """Tests for can_play_as_shift validation."""

    def _setup_shift_game_state(self) -> tuple[GameEngine, GameState]:
        """Set up complete game state."""
        cards = [
            _make_test_shift_card(
                "test_mal_base", "Maleficent", shift_cost=3,
                strength=3, willpower=4, lore=1
            ),
            _make_test_shift_card(
                "test_mal_shift", "Maleficent", shift_cost=3,
                strength=7, willpower=7, lore=2
            ),
        ]
        engine = GameEngine(CardDatabase(cards))
        
        state = GameState(
            players=[PlayerState(), PlayerState()],
            cards={},
        )
        
        # Add base Maleficent to play for player 0
        state.cards[1] = CardInstance(
            instance_id=1, card_id="test_mal_base", owner=0, controller=0, zone="play"
        )
        state.players[0].play.append(1)
        
        # Add shifted Maleficent to hand for player 0
        state.cards[2] = CardInstance(
            instance_id=2, card_id="test_mal_shift", owner=0, controller=0, zone="hand"
        )
        state.players[0].hand.append(2)
        
        # Add ink for player 0
        for i in range(10):
            state.cards[100 + i] = CardInstance(
                instance_id=100 + i, card_id="ink_amber", owner=0, controller=0, zone="inkwell"
            )
            state.players[0].inkwell.append(100 + i)
        
        return engine, state

    def test_valid_shift_play(self):
        """Valid shift play should succeed."""
        engine, state = self._setup_shift_game_state()
        
        can_play, reason = can_play_as_shift(state, engine, 2, 1)
        assert can_play is True
        assert reason == ""

    def test_shift_card_not_in_hand_fails(self):
        """Shift card not in hand should fail."""
        engine, state = self._setup_shift_game_state()
        
        # Move shifted card to play
        state.cards[2].zone = "play"
        state.players[0].hand.remove(2)
        state.players[0].play.append(2)
        
        can_play, reason = can_play_as_shift(state, engine, 2, 1)
        assert can_play is False
        assert "hand" in reason

    def test_target_not_in_play_fails(self):
        """Target character not in play should fail."""
        engine, state = self._setup_shift_game_state()
        
        # Move target to hand
        state.cards[1].zone = "hand"
        state.players[0].play.remove(1)
        state.players[0].hand.append(1)
        
        can_play, reason = can_play_as_shift(state, engine, 2, 1)
        assert can_play is False
        assert "play" in reason

    def test_insufficient_ink_fails(self):
        """Insufficient ink for shift cost should fail."""
        engine, state = self._setup_shift_game_state()
        
        # Exhaust all ink
        for cid in list(state.players[0].inkwell):
            state.cards[cid].exerted = True
        
        can_play, reason = can_play_as_shift(state, engine, 2, 1)
        assert can_play is False
        assert "ink" in reason


class TestExecuteShiftPlay:
    """Tests for execute_shift_play execution."""

    def _setup_shift_game_state(self) -> tuple[GameEngine, GameState]:
        """Set up complete game state."""
        cards = [
            _make_test_shift_card(
                "test_mal_base", "Maleficent", shift_cost=3,
                strength=3, willpower=4, lore=1
            ),
            _make_test_shift_card(
                "test_mal_shift", "Maleficent", shift_cost=3,
                strength=7, willpower=7, lore=2
            ),
        ]
        engine = GameEngine(CardDatabase(cards))
        
        state = GameState(
            players=[PlayerState(), PlayerState()],
            cards={},
        )
        
        # Add base Maleficent to play for player 0 (with damage)
        state.cards[1] = CardInstance(
            instance_id=1, card_id="test_mal_base", owner=0, controller=0, zone="play"
        )
        state.cards[1].damage = 2  # Target has damage
        state.players[0].play.append(1)
        
        # Add shifted Maleficent to hand for player 0
        state.cards[2] = CardInstance(
            instance_id=2, card_id="test_mal_shift", owner=0, controller=0, zone="hand"
        )
        state.players[0].hand.append(2)
        
        # Add ink for player 0
        for i in range(10):
            state.cards[100 + i] = CardInstance(
                instance_id=100 + i, card_id="ink_amber", owner=0, controller=0, zone="inkwell"
            )
            state.players[0].inkwell.append(100 + i)
        
        return engine, state

    def test_shift_pays_shift_cost(self):
        """Shift play should pay shift cost (not normal cost)."""
        engine, state = self._setup_shift_game_state()
        
        available_before = engine.available_ink(state, 0)
        assert available_before >= 3
        
        execute_shift_play(state, engine, 2, 1)
        
        available_after = engine.available_ink(state, 0)
        assert available_after == available_before - 3

    def test_shift_moves_shifted_to_play(self):
        """Shift play should move shifted card to play."""
        engine, state = self._setup_shift_game_state()
        
        assert 2 in state.players[0].hand
        assert 2 not in state.players[0].play
        
        execute_shift_play(state, engine, 2, 1)
        
        assert 2 not in state.players[0].hand
        assert 2 in state.players[0].play

    def test_shift_moves_target_to_discard(self):
        """Shift play should move target character to discard."""
        engine, state = self._setup_shift_game_state()
        
        assert 1 in state.players[0].play
        assert 1 not in state.players[0].discard
        
        execute_shift_play(state, engine, 2, 1)
        
        assert 1 not in state.players[0].play
        assert 1 in state.players[0].discard

    def test_shifted_character_not_damaged(self):
        """Shifted character should start with no damage."""
        engine, state = self._setup_shift_game_state()
        
        assert state.cards[1].damage == 2  # Target has damage
        
        execute_shift_play(state, engine, 2, 1)
        
        # Shifted character (now at instance_id 2) should have 0 damage
        assert state.cards[2].damage == 0

    def test_shifted_character_not_exerted(self):
        """Shifted character should start not exerted."""
        engine, state = self._setup_shift_game_state()
        
        execute_shift_play(state, engine, 2, 1)
        
        assert state.cards[2].exerted is False

    def test_shifted_character_not_drying(self):
        """Shifted character should start not drying."""
        engine, state = self._setup_shift_game_state()
        
        execute_shift_play(state, engine, 2, 1)
        
        assert state.cards[2].drying is False

    def test_shifted_character_just_played(self):
        """Shifted character should start with just_played=True."""
        engine, state = self._setup_shift_game_state()
        
        execute_shift_play(state, engine, 2, 1)
        
        assert state.cards[2].just_played is True

    def test_shift_emits_used_shift_event(self):
        """Shift play should emit event with used_shift=True."""
        engine, state = self._setup_shift_game_state()
        
        initial_events = len(state.event_log)
        
        execute_shift_play(state, engine, 2, 1)
        
        # Find the CARD_PLAYED event with used_shift=True
        shift_events = [
            e for e in state.event_log[initial_events:]
            if e.event_type == "CARD_PLAYED" and e.payload.get("used_shift") is True
        ]
        assert len(shift_events) == 1
        assert shift_events[0].payload.get("shift_cost") == 3
        assert shift_events[0].payload.get("shift_target_name") == "Maleficent"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])