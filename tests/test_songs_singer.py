"""Tests for Songs and Singer mechanics.

This module tests:
- Singer keyword parsing and threshold application
- Song card identification and singing constraints
- Singer exerts character when singing
- Sing events emit sung=True in payload
- Non-song cards cannot be sung
- Characters without Singer cannot sing
"""

import pytest
from lorcana_bot.cards import CardDef, CardDatabase
from lorcana_bot.engine import GameEngine
from lorcana_bot.state import CardInstance, GameState, PlayerState
from lorcana_bot.play_modes import (
    get_singer_info,
    can_sing_song,
    execute_sing_song,
    is_song_card,
    SingerInfo,
)


def _make_test_card(
    card_id: str,
    full_name: str,
    card_type: str,
    cost: int,
    keywords: tuple[str, ...] = (),
    action_subtype: str | None = None,
    strength: int | None = None,
    willpower: int | None = None,
    lore: int | None = None,
) -> CardDef:
    """Create a test card definition."""
    return CardDef(
        id=card_id,
        full_name=full_name,
        ink="amber",
        cost=cost,
        inkable=True,
        card_type=card_type,
        strength=strength,
        willpower=willpower,
        lore=lore,
        keywords=keywords,
        action_subtype=action_subtype,
    )


class TestSingerKeywordParsing:
    """Tests for Singer keyword parsing."""

    def test_singer_with_value(self):
        """Singer(5) should parse to threshold 5."""
        from lorcana_bot.play_modes import _parse_singer_threshold
        
        keywords = ("SINGER(5)",)
        threshold = _parse_singer_threshold(keywords)
        assert threshold == 5

    def test_singer_with_colon(self):
        """SINGER:3 should parse to threshold 3."""
        from lorcana_bot.play_modes import _parse_singer_threshold
        
        keywords = ("SINGER:3",)
        threshold = _parse_singer_threshold(keywords)
        assert threshold == 3

    def test_singer_no_value_defaults_to_1(self):
        """SINGER alone should default to threshold 1."""
        from lorcana_bot.play_modes import _parse_singer_threshold
        
        keywords = ("SINGER",)
        threshold = _parse_singer_threshold(keywords)
        assert threshold == 1

    def test_singer_case_insensitive(self):
        """Singer parsing should be case insensitive."""
        from lorcana_bot.play_modes import _parse_singer_threshold
        
        keywords = ("singer(4)",)
        threshold = _parse_singer_threshold(keywords)
        assert threshold == 4

    def test_no_singer_returns_none(self):
        """No Singer keyword should return None."""
        from lorcana_bot.play_modes import _parse_singer_threshold
        
        keywords = ("EVASIVE", "RUSH")
        threshold = _parse_singer_threshold(keywords)
        assert threshold is None


class TestSingerInfoRetrieval:
    """Tests for getting Singer info from a character in play."""

    def _setup_engine_with_singer(self, singer_threshold: int = 5) -> tuple[GameEngine, GameState]:
        """Set up engine with a singer character in play."""
        # Use only registered card IDs in the database
        cards = [
            _make_test_card(
                "test_singer", "Ariel Singer", "character",
                cost=5, keywords=(f"SINGER({singer_threshold})",),
                strength=2, willpower=3, lore=2
            ),
            _make_test_card(
                "test_non_singer", "Regular Character", "character",
                cost=3, keywords=(),
                strength=1, willpower=1, lore=1
            ),
        ]
        engine = GameEngine(CardDatabase(cards))
        
        state = GameState(
            players=[PlayerState(), PlayerState()],
            cards={},
        )
        
        # Add singer to play for player 0
        singer_inst = CardInstance(
            instance_id=1, card_id="test_singer", owner=0, controller=0, zone="play"
        )
        state.cards[1] = singer_inst
        state.players[0].play.append(1)
        
        # Add ink for player 0
        for i in range(10):
            ink_inst = CardInstance(
                instance_id=100 + i, card_id="ink_amber", owner=0, controller=0, zone="inkwell"
            )
            state.cards[100 + i] = ink_inst
            state.players[0].inkwell.append(100 + i)
        
        return engine, state

    def test_get_singer_info_returns_singerinfo(self):
        """get_singer_info should return SingerInfo for singer character."""
        engine, state = self._setup_engine_with_singer(5)
        
        info = get_singer_info(state, engine, 1)
        assert info is not None
        assert isinstance(info, SingerInfo)
        assert info.threshold == 5
        assert info.sing_together is False

    def test_get_singer_info_none_for_non_singer(self):
        """get_singer_info should return None for non-singer character."""
        engine, state = self._setup_engine_with_singer(5)
        
        # Add non-singer card (using registered card_id)
        state.cards[2] = CardInstance(
            instance_id=2, card_id="test_non_singer", owner=0, controller=0, zone="play"
        )
        state.players[0].play.append(2)
        
        info = get_singer_info(state, engine, 2)
        assert info is None


class TestSongCardIdentification:
    """Tests for identifying song cards."""

    def _setup_engine_with_song(
        self, song_cost: int = 3, action_subtype: str = "song"
    ) -> tuple[GameEngine, GameState]:
        """Set up engine with a song card in hand."""
        cards = [
            _make_test_card(
                "test_song", "The Mob Song", "action",
                cost=song_cost, action_subtype=action_subtype
            ),
            _make_test_card(
                "test_action", "Normal Action", "action",
                cost=2, action_subtype=None
            ),
        ]
        engine = GameEngine(CardDatabase(cards))
        
        state = GameState(
            players=[PlayerState(), PlayerState()],
            cards={},
        )
        
        # Add song to hand for player 0
        song_inst = CardInstance(
            instance_id=1, card_id="test_song", owner=0, controller=0, zone="hand"
        )
        state.cards[1] = song_inst
        state.players[0].hand.append(1)
        
        # Add ink for player 0
        for i in range(10):
            ink_inst = CardInstance(
                instance_id=100 + i, card_id="ink_amber", owner=0, controller=0, zone="inkwell"
            )
            state.cards[100 + i] = ink_inst
            state.players[0].inkwell.append(100 + i)
        
        return engine, state

    def test_is_song_card_with_song_subtype(self):
        """is_song_card should return True for song action."""
        engine, state = self._setup_engine_with_song()
        
        assert is_song_card(engine, "test_song") is True

    def test_is_song_card_with_non_song(self):
        """is_song_card should return False for non-song action."""
        engine, state = self._setup_engine_with_song()
        
        assert is_song_card(engine, "test_action") is False


class TestCanSingSong:
    """Tests for can_sing_song validation."""

    def _setup_full_game_state(self) -> tuple[GameEngine, GameState]:
        """Set up complete game state with singer and song."""
        cards = [
            _make_test_card(
                "test_singer", "Ariel Singer", "character",
                cost=5, keywords=("SINGER(5)",),
                strength=2, willpower=3, lore=2
            ),
            _make_test_card(
                "test_song", "The Mob Song", "action",
                cost=3, action_subtype="song"
            ),
            _make_test_card(
                "test_non_singer", "Regular Character", "character",
                cost=3, keywords=(),
                strength=1, willpower=1, lore=1
            ),
            _make_test_card(
                "test_action", "Normal Action", "action",
                cost=2, action_subtype=None
            ),
        ]
        engine = GameEngine(CardDatabase(cards))
        
        state = GameState(
            players=[PlayerState(), PlayerState()],
            cards={},
        )
        
        # Add singer to play for player 0
        state.cards[1] = CardInstance(
            instance_id=1, card_id="test_singer", owner=0, controller=0, zone="play"
        )
        state.players[0].play.append(1)
        
        # Add song to hand for player 0
        state.cards[2] = CardInstance(
            instance_id=2, card_id="test_song", owner=0, controller=0, zone="hand"
        )
        state.players[0].hand.append(2)
        
        # Add ink for player 0
        for i in range(10):
            state.cards[100 + i] = CardInstance(
                instance_id=100 + i, card_id="ink_amber", owner=0, controller=0, zone="inkwell"
            )
            state.players[0].inkwell.append(100 + i)
        
        return engine, state

    def test_singer_can_sing_within_threshold(self):
        """Singer should be able to sing song within threshold."""
        engine, state = self._setup_full_game_state()
        
        can_sing, reason = can_sing_song(state, engine, 1, 2)
        assert can_sing is True
        assert reason == ""

    def test_exerted_singer_cannot_sing(self):
        """Exerted singer should not be able to sing."""
        engine, state = self._setup_full_game_state()
        
        # Make singer exerted
        state.cards[1].exerted = True
        
        can_sing, reason = can_sing_song(state, engine, 1, 2)
        assert can_sing is False
        assert "exerted" in reason

    def test_non_singer_cannot_sing(self):
        """Non-singer character should not be able to sing."""
        engine, state = self._setup_full_game_state()
        
        # Add a non-singer character (using registered card_id)
        state.cards[3] = CardInstance(
            instance_id=3, card_id="test_non_singer", owner=0, controller=0, zone="play"
        )
        state.players[0].play.append(3)
        
        # Try to use non-singer (test_non_singer doesn't have Singer keyword)
        # Note: test_singer is the only singer, so using non-singer should fail
        can_sing, reason = can_sing_song(state, engine, 3, 2)
        assert can_sing is False
        assert "Singer" in reason

    def test_song_not_in_hand_fails(self):
        """Song not in hand should fail."""
        engine, state = self._setup_full_game_state()
        
        # Move song to play
        state.cards[2].zone = "play"
        state.players[0].hand.remove(2)
        state.players[0].play.append(2)
        
        can_sing, reason = can_sing_song(state, engine, 1, 2)
        assert can_sing is False
        assert "hand" in reason

    def test_non_song_action_fails(self):
        """Non-song action should fail."""
        engine, state = self._setup_full_game_state()
        
        # Add a non-song action (using registered card_id)
        state.cards[4] = CardInstance(
            instance_id=4, card_id="test_action", owner=0, controller=0, zone="hand"
        )
        state.players[0].hand.append(4)
        
        can_sing, reason = can_sing_song(state, engine, 1, 4)
        assert can_sing is False
        assert "song" in reason

    def test_insufficient_ink_fails(self):
        """Insufficient ink should fail."""
        engine, state = self._setup_full_game_state()
        
        # Exhaust all ink
        for cid in list(state.players[0].inkwell):
            state.cards[cid].exerted = True
        
        can_sing, reason = can_sing_song(state, engine, 1, 2)
        assert can_sing is False
        assert "ink" in reason


class TestExecuteSingSong:
    """Tests for execute_sing_song execution."""

    def _setup_full_game_state(self) -> tuple[GameEngine, GameState]:
        """Set up complete game state with singer and song."""
        cards = [
            _make_test_card(
                "test_singer", "Ariel Singer", "character",
                cost=5, keywords=("SINGER(5)",),
                strength=2, willpower=3, lore=2
            ),
            _make_test_card(
                "test_song", "The Mob Song", "action",
                cost=3, action_subtype="song"
            ),
        ]
        engine = GameEngine(CardDatabase(cards))
        
        state = GameState(
            players=[PlayerState(), PlayerState()],
            cards={},
        )
        
        # Add singer to play for player 0
        state.cards[1] = CardInstance(
            instance_id=1, card_id="test_singer", owner=0, controller=0, zone="play"
        )
        state.players[0].play.append(1)
        
        # Add song to hand for player 0
        state.cards[2] = CardInstance(
            instance_id=2, card_id="test_song", owner=0, controller=0, zone="hand"
        )
        state.players[0].hand.append(2)
        
        # Add ink for player 0
        for i in range(10):
            state.cards[100 + i] = CardInstance(
                instance_id=100 + i, card_id="ink_amber", owner=0, controller=0, zone="inkwell"
            )
            state.players[0].inkwell.append(100 + i)
        
        # Add opponent character
        state.cards[50] = CardInstance(
            instance_id=50, card_id="opponent_char", owner=1, controller=1, zone="play"
        )
        state.players[1].play.append(50)
        
        return engine, state

    def test_singing_exerts_singer(self):
        """Singing should exert the singer character."""
        engine, state = self._setup_full_game_state()
        
        assert state.cards[1].exerted is False
        
        execute_sing_song(state, engine, 1, 2)
        
        assert state.cards[1].exerted is True

    def test_singing_moves_song_to_discard(self):
        """Singing should move song to discard."""
        engine, state = self._setup_full_game_state()
        
        assert 2 in state.players[0].hand
        assert 2 not in state.players[0].discard
        
        execute_sing_song(state, engine, 1, 2)
        
        assert 2 not in state.players[0].hand
        assert 2 in state.players[0].discard

    def test_singing_pays_ink(self):
        """Singing should pay ink cost."""
        engine, state = self._setup_full_game_state()
        
        available_before = engine.available_ink(state, 0)
        assert available_before >= 3
        
        execute_sing_song(state, engine, 1, 2)
        
        available_after = engine.available_ink(state, 0)
        assert available_after == available_before - 3

    def test_singing_emits_sung_event(self):
        """Singing should emit event with sung=True payload."""
        engine, state = self._setup_full_game_state()
        
        initial_events = len(state.event_log)
        
        execute_sing_song(state, engine, 1, 2)
        
        # Find the CARD_PLAYED event with sung=True
        sung_events = [
            e for e in state.event_log[initial_events:]
            if e.event_type == "CARD_PLAYED" and e.payload.get("sung") is True
        ]
        assert len(sung_events) == 1
        assert sung_events[0].payload.get("singer_id") == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])