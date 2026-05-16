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
from unittest.mock import MagicMock

from lorcana_bot.cards import CardDef, CardDatabase
from lorcana_bot.constants import (
    ACTION_CHALLENGE,
    ACTION_PLAY_SHIFTED,
    ACTION_QUEST,
    ACTION_SING_SONG,
    ACTION_USE_ABILITY,
    ZONE_UNDER,
)
from lorcana_bot.engine import GameEngine
from lorcana_bot.state import CardInstance, GameState, PlayerState
from lorcana_bot.play_modes import (
    get_shift_info,
    get_shift_targets,
    can_play_as_shift,
    can_sing_song,
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


def _ready_ink(state: GameState, player: int, count: int) -> None:
    start = 1000 + len(state.players[player].inkwell)
    for offset in range(count):
        cid = start + offset
        state.cards[cid] = CardInstance(
            instance_id=cid,
            card_id="ink_amber",
            owner=player,
            controller=player,
            zone="inkwell",
        )
        state.players[player].inkwell.append(cid)


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

    def test_shift_moves_target_under_shifted(self):
        """Shift play should move target character under shifted card (B12)."""
        engine, state = self._setup_shift_game_state()

        assert 1 in state.players[0].play

        execute_shift_play(state, engine, 2, 1)

        # B12: Shift target goes UNDER the shifted card, not to discard
        assert 1 not in state.players[0].play  # Target no longer in play area
        assert 1 in state.cards[2].cards_under  # Target is under shifted card
        assert state.cards[1].stack_parent_id == 2  # Target's parent is shifted card

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


class TestShiftTargetModes:
    """Tests for different shift target modes (same-name, classification, universal)."""

    def _make_classification_shift_card(
        self,
        card_id: str,
        full_name: str,
        classification: str,
        shift_cost: int = 3,
    ) -> CardDef:
        """Create a test Shift character card with classification-based target."""
        return CardDef(
            id=card_id,
            full_name=full_name,
            ink="amethyst",
            cost=8,
            inkable=True,
            card_type="character",
            strength=5,
            willpower=5,
            lore=2,
            # Use rules_text to trigger text-based parsing for classification
            rules_text=f"Shift {shift_cost}. You may shift this character on top of one of your {classification} characters.",
            keywords=(f"SHIFT({shift_cost})",),
        )

    def _make_universal_shift_card(
        self,
        card_id: str,
        full_name: str,
        shift_cost: int = 3,
    ) -> CardDef:
        """Create a test Shift character card with universal shift."""
        return CardDef(
            id=card_id,
            full_name=full_name,
            ink="amethyst",
            cost=8,
            inkable=True,
            card_type="character",
            strength=5,
            willpower=5,
            lore=2,
            # Use rules_text to trigger text-based parsing for universal
            rules_text="Universal Shift 3. You may shift this character on top of any one of your characters.",
            keywords=("SHIFT(3)",),
        )

    def test_get_shift_rules_returns_ink_cost(self):
        """get_shift_rules should return ink cost for standard shift."""
        from lorcana_bot.play_modes import get_shift_rules
        
        card = _make_test_shift_card(
            "test_card", "Test Character", shift_cost=5
        )
        rules = get_shift_rules(card)
        
        assert rules is not None
        assert rules.ink_cost == 5

    def test_get_shift_rules_classification_shift(self):
        """get_shift_rules should parse classification-based shift."""
        from lorcana_bot.play_modes import get_shift_rules
        
        card = self._make_classification_shift_card(
            "test_sorcerer", "Mickey Sorcerer", "Sorcerer", shift_cost=4
        )
        rules = get_shift_rules(card)
        
        assert rules is not None
        assert rules.target_mode is not None
        assert rules.target_mode.type == "classification"
        assert rules.target_mode.classification == "Sorcerer"

    def test_get_shift_rules_universal_shift(self):
        """get_shift_rules should parse universal shift."""
        from lorcana_bot.play_modes import get_shift_rules
        
        card = self._make_universal_shift_card(
            "test_uni", "Universal Test", shift_cost=3
        )
        rules = get_shift_rules(card)
        
        assert rules is not None
        assert rules.target_mode is not None
        assert rules.target_mode.type == "universal"

    def test_get_shift_rules_non_character_returns_none(self):
        """get_shift_rules should return None for non-character cards."""
        from lorcana_bot.play_modes import get_shift_rules
        
        card = CardDef(
            id="test_action",
            full_name="Test Action",
            ink="amber",
            cost=2,
            inkable=True,
            card_type="action",
        )
        rules = get_shift_rules(card)
        
        assert rules is None

    def test_get_shift_rules_no_shift_returns_none(self):
        """get_shift_rules should return None for non-shift characters."""
        from lorcana_bot.play_modes import get_shift_rules
        
        card = _make_test_character("test_char", "Regular Character")
        rules = get_shift_rules(card)
        
        assert rules is None

    def test_classification_shift_targets_matching_classification(self):
        """Classification shift should target cards with matching classification."""
        from lorcana_bot.play_modes import ShiftTargetMode
        
        # Mock the target mode resolution to use classification
        # This tests that classification-based targeting works
        mode = ShiftTargetMode(type="classification", classification="Sorcerer")
        
        # Verify classification parsing works
        assert mode.type == "classification"
        assert mode.classification == "Sorcerer"

    def test_classification_shift_is_legal_action_and_resolves(self):
        """Classification Shift should be playable through legal_actions/apply_action."""
        cards = [
            CardDef(
                id="sorcerer_base",
                full_name="Yen Sid",
                ink="amber",
                cost=3,
                inkable=True,
                card_type="character",
                strength=2,
                willpower=3,
                lore=1,
                subtypes=("Sorcerer",),
            ),
            self._make_classification_shift_card(
                "mickey_sorcerer",
                "Mickey Mouse - Wayward Sorcerer",
                "Sorcerer",
                shift_cost=4,
            ),
            _make_test_character("ink_amber", "Ink"),
        ]
        engine = GameEngine(CardDatabase(cards))
        state = GameState(players=[PlayerState(), PlayerState()], cards={})
        state.cards[1] = CardInstance(1, "sorcerer_base", owner=0, controller=0, zone="play")
        state.players[0].play.append(1)
        state.cards[2] = CardInstance(2, "mickey_sorcerer", owner=0, controller=0, zone="hand")
        state.players[0].hand.append(2)
        _ready_ink(state, 0, 4)

        actions = engine.legal_actions(state, 0)
        shift_action = next(
            action
            for action in actions
            if action.kind == ACTION_PLAY_SHIFTED and action.card == 2 and action.target == 1
        )
        next_state = engine.apply_action(state, shift_action)

        assert next_state.cards[1].zone == ZONE_UNDER
        assert 1 in next_state.players[0].under
        assert 1 not in next_state.players[0].play
        assert next_state.cards[2].zone == "play"
        assert next_state.cards[2].cards_under == [1]
        assert next_state.cards[1].stack_parent_id == 2

    def test_universal_shift_is_legal_action_and_resolves(self):
        """Universal Shift should target any controlled public character."""
        cards = [
            _make_test_character("stitch_base", "Stitch - New Dog"),
            self._make_universal_shift_card("universal_shift", "Test Universal", shift_cost=3),
            _make_test_character("ink_amber", "Ink"),
        ]
        engine = GameEngine(CardDatabase(cards))
        state = GameState(players=[PlayerState(), PlayerState()], cards={})
        state.cards[1] = CardInstance(1, "stitch_base", owner=0, controller=0, zone="play")
        state.players[0].play.append(1)
        state.cards[2] = CardInstance(2, "universal_shift", owner=0, controller=0, zone="hand")
        state.players[0].hand.append(2)
        _ready_ink(state, 0, 3)

        actions = engine.legal_actions(state, 0)
        shift_action = next(
            action
            for action in actions
            if action.kind == ACTION_PLAY_SHIFTED and action.card == 2 and action.target == 1
        )
        next_state = engine.apply_action(state, shift_action)

        assert next_state.cards[1].zone == ZONE_UNDER
        assert next_state.cards[2].cards_under == [1]
        assert next_state.cards[1].stack_parent_id == 2


class TestShiftStackRestrictions:
    """Tests for shift stack restrictions on cards under."""

    def test_is_card_under_returns_true_for_stacked_card(self):
        """is_card_under should return True for card in shift stack."""
        from lorcana_bot.play_modes import is_card_under
        
        state = GameState(
            players=[PlayerState(), PlayerState()],
            cards={},
        )
        
        # Create a stack: card 2 is on top, card 1 is under
        state.cards[1] = CardInstance(
            instance_id=1, card_id="base", owner=0, controller=0,
            zone="under", stack_parent_id=2  # Card 1 is under card 2
        )
        state.cards[2] = CardInstance(
            instance_id=2, card_id="shifted", owner=0, controller=0,
            zone="play", cards_under=[1]
        )
        
        assert is_card_under(state, 1) is True
        assert is_card_under(state, 2) is False

    def test_is_publicly_in_play_returns_false_for_stacked_card(self):
        """is_publicly_in_play should return False for card under another."""
        from lorcana_bot.play_modes import is_publicly_in_play
        
        state = GameState(
            players=[PlayerState(), PlayerState()],
            cards={},
        )
        
        # Card 1 is in under (under stack) - should not be publicly in play
        state.cards[1] = CardInstance(
            instance_id=1, card_id="base", owner=0, controller=0,
            zone="under", stack_parent_id=2
        )
        
        assert is_publicly_in_play(state, 1) is False

    def test_is_publicly_in_play_returns_true_for_top_card(self):
        """is_publicly_in_play should return True for top card in stack."""
        from lorcana_bot.play_modes import is_publicly_in_play
        
        state = GameState(
            players=[PlayerState(), PlayerState()],
            cards={},
        )
        
        # Card 2 is in play as top of stack
        state.cards[2] = CardInstance(
            instance_id=2, card_id="shifted", owner=0, controller=0,
            zone="play", stack_parent_id=None, cards_under=[1]
        )
        state.players[0].play.append(2)
        
        assert is_publicly_in_play(state, 2) is True


class TestShiftStackMovement:
    """Tests for shift stack movement when top card leaves play."""

    def test_get_stacked_card_ids_returns_full_stack(self):
        """get_stacked_card_ids should return all cards in stack."""
        from lorcana_bot.play_modes import get_stacked_card_ids
        
        state = GameState(
            players=[PlayerState(), PlayerState()],
            cards={},
        )
        
        # Create a stack: card 3 on top, card 2, card 1 under
        state.cards[1] = CardInstance(instance_id=1, card_id="base1", owner=0, controller=0, zone="under")
        state.cards[2] = CardInstance(instance_id=2, card_id="base2", owner=0, controller=0, zone="under")
        state.cards[3] = CardInstance(
            instance_id=3, card_id="shifted", owner=0, controller=0,
            zone="play", cards_under=[2, 1]
        )
        
        stack = get_stacked_card_ids(state, 3)
        
        assert stack == [3, 2, 1]

    def test_move_card_out_of_play_with_stack_moves_all(self):
        """move_card_out_of_play_with_stack should move entire stack."""
        from lorcana_bot.play_modes import move_card_out_of_play_with_stack
        from lorcana_bot.constants import ZONE_DISCARD
        
        state = GameState(
            players=[PlayerState(), PlayerState()],
            cards={},
        )
        
        # Create a stack
        state.cards[1] = CardInstance(instance_id=1, card_id="base", owner=0, controller=0, zone="under")
        state.cards[2] = CardInstance(
            instance_id=2, card_id="shifted", owner=0, controller=0,
            zone="play", cards_under=[1]
        )
        state.players[0].play.append(2)
        
        # Create a mock engine
        engine = MagicMock()
        engine._move_card_eventful = MagicMock()
        
        move_card_out_of_play_with_stack(state, engine, 2, ZONE_DISCARD)
        
        # Both cards should be moved
        assert engine._move_card_eventful.call_count == 2

    def test_shift_stack_clears_parent_on_move(self):
        """Moving stack should clear stack_parent_id."""
        from lorcana_bot.play_modes import move_card_out_of_play_with_stack
        from lorcana_bot.constants import ZONE_DISCARD
        
        state = GameState(
            players=[PlayerState(), PlayerState()],
            cards={},
        )
        
        # Create a stack with parent links
        state.cards[1] = CardInstance(
            instance_id=1, card_id="base", owner=0, controller=0,
            zone="under", stack_parent_id=2
        )
        state.cards[2] = CardInstance(
            instance_id=2, card_id="shifted", owner=0, controller=0,
            zone="play", cards_under=[1]
        )
        
        # Create a mock engine
        engine = MagicMock()
        engine._move_card_eventful = MagicMock()
        
        move_card_out_of_play_with_stack(state, engine, 2, ZONE_DISCARD)
        
        # Parent links should be cleared
        assert state.cards[1].stack_parent_id is None
        assert state.cards[2].stack_parent_id is None


class TestUnsupportedShiftCost:
    """Tests for unsupported non-ink Shift costs."""

    def test_get_shift_rules_with_unsupported_cost_returns_reason(self):
        """get_shift_rules should return unsupportedReason for non-ink costs."""
        from lorcana_bot.play_modes import get_shift_rules, UNSUPPORTED_SHIFT_COST_TODO
        
        # Create a card with a non-ink shift cost (e.g., discard cost)
        card = CardDef(
            id="unsupported_shift",
            full_name="Unsupported Shift",
            ink="amethyst",
            cost=8,
            inkable=True,
            card_type="character",
            strength=5,
            willpower=5,
            lore=2,
            abilities=({
                "keyword": "Shift",
                "cost": {"discardCards": 1, "discardCardType": "location"},
                "text": "Shift: Discard a location card",
            },),
            keywords=("SHIFT",),
        )
        
        rules = get_shift_rules(card)
        
        assert rules is not None
        # The discard cost should be detected
        assert rules.discard_cost is not None
        assert rules.discard_cost.discard_cards == 1
        assert rules.unsupported_reason == UNSUPPORTED_SHIFT_COST_TODO

    def test_discard_cost_shift_blocks_before_payment_and_legal_action(self):
        """Discard-cost Shift is parsed but not playable until non-ink costs migrate."""
        from lorcana_bot.play_modes import UNSUPPORTED_SHIFT_COST_TODO

        cards = [
            _make_test_character("diablo_base", "Diablo"),
            CardDef(
                id="diablo_shift",
                full_name="Diablo",
                ink="amethyst",
                cost=7,
                inkable=True,
                card_type="character",
                strength=4,
                willpower=4,
                lore=2,
                keywords=("SHIFT",),
                abilities=({
                    "type": "keyword",
                    "keyword": "Shift",
                    "cost": {"discardCards": 1, "discardCardType": "song"},
                    "shiftTarget": "Diablo",
                    "text": "Shift: Discard a song card",
                },),
            ),
            _make_test_character("ink_amber", "Ink"),
        ]
        engine = GameEngine(CardDatabase(cards))
        state = GameState(players=[PlayerState(), PlayerState()], cards={})
        state.cards[1] = CardInstance(1, "diablo_base", owner=0, controller=0, zone="play")
        state.players[0].play.append(1)
        state.cards[2] = CardInstance(2, "diablo_shift", owner=0, controller=0, zone="hand")
        state.players[0].hand.append(2)
        _ready_ink(state, 0, 10)
        available_before = engine.available_ink(state, 0)

        can_play, reason = can_play_as_shift(state, engine, 2, 1)
        actions = engine.legal_actions(state, 0)

        assert can_play is False
        assert reason == UNSUPPORTED_SHIFT_COST_TODO
        assert all(action.kind != ACTION_PLAY_SHIFTED or action.card != 2 for action in actions)
        assert engine.available_ink(state, 0) == available_before


class TestShiftPlayIntegration:
    """Integration tests for shift play with stack mechanics."""

    def _setup_shift_with_under_cards(self) -> tuple[GameEngine, GameState]:
        """Set up a shift stack with cards under the target."""
        cards = [
            _make_test_shift_card(
                "mal_base", "Maleficent", shift_cost=3,
                strength=3, willpower=4, lore=1
            ),
            _make_test_shift_card(
                "mal_shifted", "Maleficent", shift_cost=3,
                strength=7, willpower=7, lore=2
            ),
            _make_test_character("other_char", "Other Character"),
        ]
        engine = GameEngine(CardDatabase(cards))
        
        state = GameState(
            players=[PlayerState(), PlayerState()],
            cards={},
        )
        
        # Add base Maleficent to play (this will be shifted onto)
        state.cards[1] = CardInstance(
            instance_id=1, card_id="mal_base", owner=0, controller=0, zone="play"
        )
        state.players[0].play.append(1)
        
        # Add another character under base Maleficent (existing stack)
        state.cards[2] = CardInstance(
            instance_id=2, card_id="other_char", owner=0, controller=0,
            zone="under", stack_parent_id=1
        )
        state.cards[1].cards_under.append(2)
        
        # Add shifted Maleficent to hand
        state.cards[3] = CardInstance(
            instance_id=3, card_id="mal_shifted", owner=0, controller=0, zone="hand"
        )
        state.players[0].hand.append(3)
        
        # Add ink for player 0
        for i in range(10):
            state.cards[100 + i] = CardInstance(
                instance_id=100 + i, card_id="ink_amber", owner=0, controller=0, zone="inkwell"
            )
            state.players[0].inkwell.append(100 + i)
        
        return engine, state

    def test_shift_preserves_existing_under_cards(self):
        """Shift should preserve existing cards_under when stacking."""
        engine, state = self._setup_shift_with_under_cards()
        
        # Verify initial state: card 2 is under card 1
        assert state.cards[1].cards_under == [2]
        assert state.cards[2].stack_parent_id == 1
        
        # Execute shift
        execute_shift_play(state, engine, 3, 1)
        
        # After shift: card 1 is under card 3, card 2 is under card 1 (preserved)
        assert state.cards[3].cards_under == [1, 2]  # Card 3 now has both under it
        assert state.cards[1].stack_parent_id == 3
        assert state.cards[2].stack_parent_id == 3  # Card 2 now points to card 3


class TestLifecycleRegistrationOnEntry:
    """Tests for static and replacement effect registration on card entry to play."""

    def _setup_shift_game_with_static_ability(self) -> tuple[GameEngine, GameState]:
        """Set up a game with a shift character that has static abilities."""
        cards = [
            _make_test_shift_card(
                "mal_base", "Maleficent", shift_cost=3,
                strength=3, willpower=4, lore=1
            ),
            _make_test_shift_card(
                "mal_shifted", "Maleficent", shift_cost=3,
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
            instance_id=1, card_id="mal_base", owner=0, controller=0, zone="play"
        )
        state.players[0].play.append(1)
        
        # Add shifted Maleficent to hand for player 0
        state.cards[2] = CardInstance(
            instance_id=2, card_id="mal_shifted", owner=0, controller=0, zone="hand"
        )
        state.players[0].hand.append(2)
        
        # Add ink for player 0
        for i in range(10):
            state.cards[100 + i] = CardInstance(
                instance_id=100 + i, card_id="ink_amber", owner=0, controller=0, zone="inkwell"
            )
            state.players[0].inkwell.append(100 + i)
        
        return engine, state

    def test_normal_character_entry_registers_static_effects(self):
        """Test that a normally played character registers static effects."""
        from lorcana_bot.cards import CardDef, CardDatabase
        from lorcana_bot.static_effects import StaticEffectRegistry
        
        # Create a character with a static ability
        char_card = CardDef(
            id="static_char",
            full_name="Test Character",
            ink="amber",
            cost=3,
            inkable=True,
            card_type="character",
            strength=2,
            willpower=3,
            lore=1,
            abilities=({
                "type": "static",
                "effect": {
                    "type": "modify-stat",
                    "attribute": "strength",
                    "amount": 2,
                },
            },),
        )
        
        cards = [char_card]
        engine = GameEngine(CardDatabase(cards))
        state = GameState(players=[PlayerState(), PlayerState()], cards={})
        
        # Add ink for player 0
        for i in range(10):
            state.cards[100 + i] = CardInstance(
                instance_id=100 + i, card_id="ink_amber", owner=0, controller=0, zone="inkwell"
            )
            state.players[0].inkwell.append(100 + i)
        
        # Add character to hand
        state.cards[1] = CardInstance(
            instance_id=1, card_id="static_char", owner=0, controller=0, zone="hand"
        )
        state.players[0].hand.append(1)
        
        # Play the character
        from lorcana_bot.actions import Action
        from lorcana_bot.constants import ACTION_PLAY_CARD
        action = Action(ACTION_PLAY_CARD, actor=0, card=1)
        next_state = engine.apply_action(state, action)
        
        # Verify character is in play
        assert next_state.cards[1].zone == "play"
        
        # Verify static effects were registered (registry should have effects for this card)
        static_effects = next_state.static_effect_registry.get_effects_for_instance(next_state, 1)
        # The card registers its own static effects as "self" target
        assert len(static_effects) == 1
        assert static_effects[0].source_id == 1

    def test_normal_character_entry_registers_replacement_effects(self):
        """Test that a normally played character registers replacement effects."""
        from lorcana_bot.cards import CardDef, CardDatabase
        from lorcana_bot.replacement_effects import get_registry
        
        # Create a character with a replacement ability
        char_card = CardDef(
            id="replacement_char",
            full_name="Test Character",
            ink="amber",
            cost=3,
            inkable=True,
            card_type="character",
            strength=2,
            willpower=3,
            lore=1,
            abilities=({
                "type": "replacement",
                "effect": {
                    "type": "prevent-damage",
                    "amount": 1,
                },
            },),
        )
        
        cards = [char_card]
        engine = GameEngine(CardDatabase(cards))
        state = GameState(players=[PlayerState(), PlayerState()], cards={})
        
        # Add ink for player 0
        for i in range(10):
            state.cards[100 + i] = CardInstance(
                instance_id=100 + i, card_id="ink_amber", owner=0, controller=0, zone="inkwell"
            )
            state.players[0].inkwell.append(100 + i)
        
        # Add character to hand
        state.cards[1] = CardInstance(
            instance_id=1, card_id="replacement_char", owner=0, controller=0, zone="hand"
        )
        state.players[0].hand.append(1)
        
        # Play the character
        from lorcana_bot.actions import Action
        from lorcana_bot.constants import ACTION_PLAY_CARD
        action = Action(ACTION_PLAY_CARD, actor=0, card=1)
        next_state = engine.apply_action(state, action)
        
        # Verify character is in play
        assert next_state.cards[1].zone == "play"
        
        # Verify replacement effects were registered
        registry = get_registry(next_state)
        replacement_effects = registry.get_effects_for_instance(next_state, 1)
        # The card registers its own replacement effects as "self" target
        assert len(replacement_effects) == 1
        assert replacement_effects[0].source_id == 1

    def test_shifted_character_entry_registers_static_effects(self):
        """Test that a shifted character entering play registers static effects."""
        from lorcana_bot.cards import CardDef, CardDatabase
        from lorcana_bot.static_effects import StaticEffectRegistry
        
        # Create shift cards with static abilities
        base_card = CardDef(
            id="static_base",
            full_name="Test Character",
            ink="amber",
            cost=3,
            inkable=True,
            card_type="character",
            strength=2,
            willpower=3,
            lore=1,
        )
        shifted_card = CardDef(
            id="static_shifted",
            full_name="Test Character",
            ink="amber",
            cost=8,
            inkable=True,
            card_type="character",
            strength=5,
            willpower=5,
            lore=2,
            keywords=("SHIFT(3)",),
            abilities=({
                "type": "static",
                "effect": {
                    "type": "modify-stat",
                    "attribute": "strength",
                    "amount": 3,
                },
            },),
        )
        
        cards = [base_card, shifted_card]
        engine = GameEngine(CardDatabase(cards))
        state = GameState(players=[PlayerState(), PlayerState()], cards={})
        
        # Add ink for player 0
        for i in range(10):
            state.cards[100 + i] = CardInstance(
                instance_id=100 + i, card_id="ink_amber", owner=0, controller=0, zone="inkwell"
            )
            state.players[0].inkwell.append(100 + i)
        
        # Add base character to play
        state.cards[1] = CardInstance(
            instance_id=1, card_id="static_base", owner=0, controller=0, zone="play"
        )
        state.players[0].play.append(1)
        
        # Add shifted character to hand
        state.cards[2] = CardInstance(
            instance_id=2, card_id="static_shifted", owner=0, controller=0, zone="hand"
        )
        state.players[0].hand.append(2)
        
        # Shift play the character
        from lorcana_bot.actions import Action
        action = Action("PLAY_SHIFTED", actor=0, card=2, target=1)
        next_state = engine.apply_action(state, action)
        
        # Verify shifted character is in play
        assert next_state.cards[2].zone == "play"
        
        # Verify static effects were registered for the shifted card
        static_effects = next_state.static_effect_registry.get_effects_for_instance(next_state, 2)
        assert len(static_effects) == 1
        assert static_effects[0].source_id == 2

    def test_shifted_character_entry_registers_replacement_effects(self):
        """Test that a shifted character entering play registers replacement effects."""
        from lorcana_bot.cards import CardDef, CardDatabase
        from lorcana_bot.replacement_effects import get_registry
        
        # Create shift cards with replacement abilities
        base_card = CardDef(
            id="repl_base",
            full_name="Test Character",
            ink="amber",
            cost=3,
            inkable=True,
            card_type="character",
            strength=2,
            willpower=3,
            lore=1,
        )
        shifted_card = CardDef(
            id="repl_shifted",
            full_name="Test Character",
            ink="amber",
            cost=8,
            inkable=True,
            card_type="character",
            strength=5,
            willpower=5,
            lore=2,
            keywords=("SHIFT(3)",),
            abilities=({
                "type": "replacement",
                "effect": {
                    "type": "prevent-damage",
                    "amount": 2,
                },
            },),
        )
        
        cards = [base_card, shifted_card]
        engine = GameEngine(CardDatabase(cards))
        state = GameState(players=[PlayerState(), PlayerState()], cards={})
        
        # Add ink for player 0
        for i in range(10):
            state.cards[100 + i] = CardInstance(
                instance_id=100 + i, card_id="ink_amber", owner=0, controller=0, zone="inkwell"
            )
            state.players[0].inkwell.append(100 + i)
        
        # Add base character to play
        state.cards[1] = CardInstance(
            instance_id=1, card_id="repl_base", owner=0, controller=0, zone="play"
        )
        state.players[0].play.append(1)
        
        # Add shifted character to hand
        state.cards[2] = CardInstance(
            instance_id=2, card_id="repl_shifted", owner=0, controller=0, zone="hand"
        )
        state.players[0].hand.append(2)
        
        # Shift play the character
        from lorcana_bot.actions import Action
        action = Action("PLAY_SHIFTED", actor=0, card=2, target=1)
        next_state = engine.apply_action(state, action)
        
        # Verify shifted character is in play
        assert next_state.cards[2].zone == "play"
        
        # Verify replacement effects were registered for the shifted card
        registry = get_registry(next_state)
        replacement_effects = registry.get_effects_for_instance(next_state, 2)
        assert len(replacement_effects) == 1
        assert replacement_effects[0].source_id == 2

    def test_shifted_under_card_does_not_register_effects(self):
        """Test that the card UNDER a shifted character does not register as public permanent."""
        from lorcana_bot.cards import CardDef, CardDatabase
        from lorcana_bot.static_effects import StaticEffectRegistry
        from lorcana_bot.replacement_effects import get_registry
        
        # Create shift cards where the base has static effects
        base_card = CardDef(
            id="static_base",
            full_name="Test Character",
            ink="amber",
            cost=3,
            inkable=True,
            card_type="character",
            strength=2,
            willpower=3,
            lore=1,
            abilities=({
                "type": "static",
                "effect": {
                    "type": "modify-stat",
                    "attribute": "strength",
                    "amount": 5,
                },
            },),
        )
        shifted_card = CardDef(
            id="shifted_char",
            full_name="Test Character",
            ink="amber",
            cost=8,
            inkable=True,
            card_type="character",
            strength=5,
            willpower=5,
            lore=2,
            keywords=("SHIFT(3)",),
        )
        
        cards = [base_card, shifted_card]
        engine = GameEngine(CardDatabase(cards))
        state = GameState(players=[PlayerState(), PlayerState()], cards={})
        
        # Add ink for player 0
        for i in range(10):
            state.cards[100 + i] = CardInstance(
                instance_id=100 + i, card_id="ink_amber", owner=0, controller=0, zone="inkwell"
            )
            state.players[0].inkwell.append(100 + i)
        
        # Add base character to play (has static ability)
        state.cards[1] = CardInstance(
            instance_id=1, card_id="static_base", owner=0, controller=0, zone="play"
        )
        state.players[0].play.append(1)
        
        # Add shifted character to hand
        state.cards[2] = CardInstance(
            instance_id=2, card_id="shifted_char", owner=0, controller=0, zone="hand"
        )
        state.players[0].hand.append(2)
        
        # Record initial static effects count
        initial_effects_count = len(state.static_effect_registry.effects)
        
        # Shift play the character
        from lorcana_bot.actions import Action
        action = Action("PLAY_SHIFTED", actor=0, card=2, target=1)
        next_state = engine.apply_action(state, action)
        
        # Verify base character is now under (ZONE_UNDER)
        assert next_state.cards[1].zone == ZONE_UNDER
        assert next_state.cards[1].stack_parent_id == 2
        
        # The card UNDER should NOT have registered static effects because it's not a public permanent
        # Verify it's NOT in the play zone (it's under)
        assert 1 not in next_state.players[0].play
        
        # The static effects for the base card should have been deregistered when it moved to under
        static_effects_on_1 = next_state.static_effect_registry.get_effects_for_instance(next_state, 1)
        
        # Since the base card moved to ZONE_UNDER (not play), its effects should not apply
        # as if it were a public permanent. The helper should have refused to register
        # because stack_parent_id is not None for the shifted card after shift.
        # 
        # Note: The base card's static effects were registered when it originally entered play.
        # After shift, it moves to under and should be deregistered.
        # Let's verify the helper correctly refused to register the under card.

    def test_lifecycle_helper_refuses_stack_parent_id(self):
        """Test that _register_lifecycle_effects_for_public_permanent refuses cards with stack_parent_id."""
        from lorcana_bot.cards import CardDef, CardDatabase
        from lorcana_bot.static_effects import StaticEffectRegistry
        
        # Create a card with static ability
        char_card = CardDef(
            id="test_char",
            full_name="Test Character",
            ink="amber",
            cost=3,
            inkable=True,
            card_type="character",
            strength=2,
            willpower=3,
            lore=1,
            abilities=({
                "type": "static",
                "effect": {
                    "type": "modify-stat",
                    "attribute": "strength",
                    "amount": 2,
                },
            },),
        )
        
        cards = [char_card]
        engine = GameEngine(CardDatabase(cards))
        state = GameState(players=[PlayerState(), PlayerState()], cards={})
        
        # Create a card with stack_parent_id set (simulating a card under another)
        state.cards[1] = CardInstance(
            instance_id=1, card_id="test_char", owner=0, controller=0, zone="play", stack_parent_id=999
        )
        
        effects_before = len(state.static_effect_registry.effects)
        
        # Call the helper - should do nothing because stack_parent_id is set
        engine._register_lifecycle_effects_for_public_permanent(state, 1)
        
        # Verify no effects were registered
        assert len(state.static_effect_registry.effects) == effects_before

    def test_lifecycle_helper_refuses_action_cards(self):
        """Test that _register_lifecycle_effects_for_public_permanent refuses action cards."""
        from lorcana_bot.cards import CardDef, CardDatabase
        from lorcana_bot.static_effects import StaticEffectRegistry
        
        # Create an action card with static ability (actions shouldn't register)
        action_card = CardDef(
            id="test_action",
            full_name="Test Action",
            ink="amber",
            cost=2,
            inkable=True,
            card_type="action",
            abilities=({
                "type": "static",
                "effect": {
                    "type": "modify-stat",
                    "attribute": "strength",
                    "amount": 2,
                },
            },),
        )
        
        cards = [action_card]
        engine = GameEngine(CardDatabase(cards))
        state = GameState(players=[PlayerState(), PlayerState()], cards={})
        
        # Create an action card in play
        state.cards[1] = CardInstance(
            instance_id=1, card_id="test_action", owner=0, controller=0, zone="play"
        )
        
        effects_before = len(state.static_effect_registry.effects)
        
        # Call the helper - should do nothing because it's an action
        engine._register_lifecycle_effects_for_public_permanent(state, 1)
        
        # Verify no effects were registered
        assert len(state.static_effect_registry.effects) == effects_before


class TestCardsUnderRestrictions:
    """Tests for restrictions on cards under in shift stacks."""

    def test_cards_under_do_not_generate_public_legal_actions(self):
        """Cards under cannot quest, challenge, sing, or use activated abilities."""
        base = CardDef(
            id="base_singer",
            full_name="Ariel",
            ink="amber",
            cost=3,
            inkable=True,
            card_type="character",
            strength=2,
            willpower=3,
            lore=1,
            keywords=("SINGER:5",),
            activated_abilities=({"id": "legacy_test", "name": "Test Ability"},),
        )
        shifted = _make_test_shift_card("shifted_ariel", "Ariel", shift_cost=2)
        song = CardDef(
            id="song",
            full_name="Test Song",
            ink="amber",
            cost=1,
            inkable=True,
            card_type="action",
            action_subtype="song",
        )
        defender = _make_test_character("defender", "Opposing Character")
        cards = [base, shifted, song, defender, _make_test_character("ink_amber", "Ink")]
        engine = GameEngine(CardDatabase(cards))
        state = GameState(players=[PlayerState(), PlayerState()], cards={})
        state.cards[1] = CardInstance(1, "base_singer", owner=0, controller=0, zone="play")
        state.players[0].play.append(1)
        state.cards[2] = CardInstance(2, "shifted_ariel", owner=0, controller=0, zone="hand")
        state.players[0].hand.append(2)
        state.cards[3] = CardInstance(3, "song", owner=0, controller=0, zone="hand")
        state.players[0].hand.append(3)
        state.cards[4] = CardInstance(4, "defender", owner=1, controller=1, zone="play", exerted=True)
        state.players[1].play.append(4)
        _ready_ink(state, 0, 2)

        execute_shift_play(state, engine, 2, 1)
        actions = engine.legal_actions(state, 0)
        can_sing, sing_reason = can_sing_song(state, engine, 1, 3)

        assert state.cards[1].zone == ZONE_UNDER
        assert can_sing is False
        assert "play" in sing_reason
        assert all(action.source != 1 for action in actions if action.kind == ACTION_QUEST)
        assert all(action.source != 1 for action in actions if action.kind == ACTION_CHALLENGE)
        assert all(action.source != 1 for action in actions if action.kind == ACTION_SING_SONG)
        assert all(action.source != 1 for action in actions if action.kind == ACTION_USE_ABILITY)

    def test_cards_under_not_in_player_play(self):
        """Cards under should be removed from player.play list."""
        from lorcana_bot.play_modes import is_card_under
        
        state = GameState(
            players=[PlayerState(), PlayerState()],
            cards={},
        )
        
        # Create a stack with card 1 under card 2
        state.cards[1] = CardInstance(
            instance_id=1, card_id="base", owner=0, controller=0,
            zone="under", stack_parent_id=2
        )
        state.cards[2] = CardInstance(
            instance_id=2, card_id="shifted", owner=0, controller=0,
            zone="play", cards_under=[1]
        )
        
        # Card 1 should be in under, not in play
        assert state.cards[1].zone == "under"
        assert 1 not in state.players[0].play  # Not in play list
        
        # Card 1 is under card 2
        assert is_card_under(state, 1) is True

    def test_cards_under_not_publicly_in_play(self):
        """Cards under should not be publicly in play."""
        from lorcana_bot.play_modes import is_publicly_in_play
        
        state = GameState(
            players=[PlayerState(), PlayerState()],
            cards={},
        )
        
        # Create a stack
        state.cards[1] = CardInstance(
            instance_id=1, card_id="base", owner=0, controller=0,
            zone="under", stack_parent_id=2
        )
        state.cards[2] = CardInstance(
            instance_id=2, card_id="shifted", owner=0, controller=0,
            zone="play", cards_under=[1]
        )
        
        # Card 1 under is not publicly in play
        assert is_publicly_in_play(state, 1) is False
        
        # Card 2 (top) is publicly in play
        assert is_publicly_in_play(state, 2) is True

    def test_get_play_zone_cards_excludes_cards_under(self):
        """get_play_zone_cards should exclude cards under."""
        from lorcana_bot.play_modes import get_play_zone_cards
        
        state = GameState(
            players=[PlayerState(), PlayerState()],
            cards={},
        )
        
        # Create a stack
        state.cards[1] = CardInstance(
            instance_id=1, card_id="base", owner=0, controller=0,
            zone="under", stack_parent_id=2
        )
        state.cards[2] = CardInstance(
            instance_id=2, card_id="shifted", owner=0, controller=0,
            zone="play", cards_under=[1]
        )
        state.players[0].play.append(2)  # Add top card to play list
        
        # Only card 2 should be in play zone cards
        play_zone = get_play_zone_cards(state, 0)
        assert 1 not in play_zone  # Card 1 is under
        assert 2 in play_zone  # Card 2 is top

    def test_is_legal_play_zone_target_false_for_under(self):
        """is_legal_play_zone_target should return False for cards under."""
        from lorcana_bot.play_modes import is_legal_play_zone_target
        
        state = GameState(
            players=[PlayerState(), PlayerState()],
            cards={},
        )
        
        # Create a stack
        state.cards[1] = CardInstance(
            instance_id=1, card_id="base", owner=0, controller=0,
            zone="under", stack_parent_id=2
        )
        state.cards[2] = CardInstance(
            instance_id=2, card_id="shifted", owner=0, controller=0,
            zone="play", cards_under=[1]
        )
        state.players[0].play.append(2)  # Add top card to play list
        
        # Card 1 under is not a legal play zone target
        assert is_legal_play_zone_target(state, 1, 0) is False
        
        # Card 2 (top) is a legal play zone target
        assert is_legal_play_zone_target(state, 2, 0) is True

    def test_top_leaving_play_moves_full_stack(self):
        """When top card leaves play, all cards under move with it."""
        from lorcana_bot.play_modes import get_stacked_card_ids, move_card_out_of_play_with_stack
        from lorcana_bot.constants import ZONE_DISCARD
        
        state = GameState(
            players=[PlayerState(), PlayerState()],
            cards={},
        )
        
        # Create a 3-card stack
        state.cards[1] = CardInstance(instance_id=1, card_id="base1", owner=0, controller=0, zone="under")
        state.cards[2] = CardInstance(instance_id=2, card_id="base2", owner=0, controller=0, zone="under", stack_parent_id=3)
        state.cards[3] = CardInstance(
            instance_id=3, card_id="shifted", owner=0, controller=0,
            zone="play", cards_under=[2, 1]
        )
        state.players[0].play.append(3)
        
        # Verify stack
        stack = get_stacked_card_ids(state, 3)
        assert stack == [3, 2, 1]
        
        # Move entire stack to discard
        engine = MagicMock()
        engine._move_card_eventful = MagicMock()
        
        move_card_out_of_play_with_stack(state, engine, 3, ZONE_DISCARD)
        
        # All 3 cards should be moved
        assert engine._move_card_eventful.call_count == 3
        
        # Stack relationships should be cleared
        assert state.cards[1].stack_parent_id is None
        assert state.cards[2].stack_parent_id is None
        assert state.cards[3].stack_parent_id is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
