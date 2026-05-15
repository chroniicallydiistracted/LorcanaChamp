"""Tests for replacement and prevention effects layer."""

import pytest

from lorcana_bot.state import GameState, CardInstance, PlayerState
from lorcana_bot.replacement_effects import (
    ReplacementEffectEntry,
    ReplacementEffectRegistry,
    ReplacementEffectType,
    DamageEvent,
    BanishEvent,
    deal_damage,
    banish_card,
    check_cannot_be_challenged,
    check_cannot_be_targeted,
    get_registry,
    register_replacement_effect,
    cleanup_replacement_effects_on_turn_end,
)
from lorcana_bot.constants import ZONE_PLAY, ZONE_DISCARD, ZONE_HAND


@pytest.fixture
def game_state():
    """Create a basic game state for testing."""
    state = GameState(
        players=[PlayerState(), PlayerState()],
        cards={},
    )
    return state


@pytest.fixture
def simple_state(game_state):
    """Add simple cards to the game state."""
    # Player 0's character
    game_state.cards[1] = CardInstance(
        instance_id=1,
        card_id="test_character",
        owner=0,
        controller=0,
        zone=ZONE_PLAY,
        damage=0,
    )
    # Player 1's character
    game_state.cards[2] = CardInstance(
        instance_id=2,
        card_id="test_character_2",
        owner=1,
        controller=1,
        zone=ZONE_PLAY,
        damage=0,
    )
    # Protector (player 0's)
    game_state.cards[3] = CardInstance(
        instance_id=3,
        card_id="protector",
        owner=0,
        controller=0,
        zone=ZONE_PLAY,
        damage=0,
    )
    return game_state


class TestReplacementEffectRegistry:
    """Test ReplacementEffectRegistry functionality."""

    def test_register_effect(self, simple_state):
        """Test adding an effect to the registry."""
        registry = get_registry(simple_state)
        effect = ReplacementEffectEntry(
            source_id=1,
            effect_type=ReplacementEffectType.PREVENT_DAMAGE,
            target_mode="self",
            amount=1,
        )
        registry.register_effect(effect)
        
        assert len(registry.effects) == 1
        assert registry.effects[0] == effect

    def test_deregister_effects_from_source(self, simple_state):
        """Test removing effects from a source card."""
        registry = get_registry(simple_state)
        effect1 = ReplacementEffectEntry(
            source_id=1,
            effect_type=ReplacementEffectType.PREVENT_DAMAGE,
            target_mode="self",
            amount=1,
        )
        effect2 = ReplacementEffectEntry(
            source_id=2,
            effect_type=ReplacementEffectType.PREVENT_DAMAGE,
            target_mode="self",
            amount=1,
        )
        registry.register_effect(effect1)
        registry.register_effect(effect2)
        
        registry.deregister_effects_from_source(1)
        
        assert len(registry.effects) == 1
        assert registry.effects[0].source_id == 2

    def test_get_effects_for_instance(self, simple_state):
        """Test filtering effects by target instance."""
        registry = get_registry(simple_state)
        # Effect on self
        effect_self = ReplacementEffectEntry(
            source_id=1,
            effect_type=ReplacementEffectType.PREVENT_DAMAGE,
            target_mode="self",
            amount=1,
        )
        # Effect on all characters
        effect_all = ReplacementEffectEntry(
            source_id=1,
            effect_type=ReplacementEffectType.PREVENT_DAMAGE,
            target_mode="all_characters",
            amount=1,
        )
        registry.register_effect(effect_self)
        registry.register_effect(effect_all)
        
        # Effects that apply to card 1 (source's self)
        effects_on_1 = registry.get_effects_for_instance(simple_state, 1)
        assert len(effects_on_1) == 2  # Both apply to self
        
        # Effects that apply to card 2 (opponent) - only "all_characters" applies
        effects_on_2 = registry.get_effects_for_instance(simple_state, 2)
        assert len(effects_on_2) == 1  # Only "all_characters" applies

    def test_check_and_use_once_per_turn(self, simple_state):
        """Test once-per-turn tracking."""
        registry = get_registry(simple_state)
        effect = ReplacementEffectEntry(
            source_id=1,
            effect_type=ReplacementEffectType.PREVENT_DAMAGE,
            target_mode="self",
            amount=1,
            once_per_turn=True,
            usage_key="prevent_1",
        )
        
        # First use should succeed
        assert registry.check_and_use_once_per_turn(simple_state, effect, 0) is True
        
        # Second use on same turn should fail
        assert registry.check_and_use_once_per_turn(simple_state, effect, 0) is False
        
        # But on a new turn it should work
        simple_state.turn_number = 2
        assert registry.check_and_use_once_per_turn(simple_state, effect, 0) is True

    def test_effects_without_once_per_turn_always_work(self, simple_state):
        """Test that non-once-per-turn effects always work."""
        registry = get_registry(simple_state)
        effect = ReplacementEffectEntry(
            source_id=1,
            effect_type=ReplacementEffectType.PREVENT_DAMAGE,
            target_mode="self",
            amount=1,
            once_per_turn=False,
        )
        
        # Multiple uses should all succeed
        assert registry.check_and_use_once_per_turn(simple_state, effect, 0) is True
        assert registry.check_and_use_once_per_turn(simple_state, effect, 0) is True
        assert registry.check_and_use_once_per_turn(simple_state, effect, 0) is True


class TestDealDamage:
    """Test deal_damage with replacement effects."""

    def test_deal_damage_no_effects(self, simple_state):
        """Test basic damage without replacement effects."""
        event = deal_damage(simple_state, 1, 2, 5)
        
        assert event.original_amount == 5
        assert event.current_amount == 5
        assert event.was_replaced is False
        assert simple_state.cards[1].damage == 5

    def test_deal_damage_prevented(self, simple_state):
        """Test damage prevention."""
        registry = get_registry(simple_state)
        effect = ReplacementEffectEntry(
            source_id=3,  # protector
            effect_type=ReplacementEffectType.PREVENT_DAMAGE,
            target_mode="your_characters",  # Protects player 0's characters
            amount=2,
            once_per_turn=False,
        )
        register_replacement_effect(simple_state, effect)
        
        event = deal_damage(simple_state, 1, 2, 5)  # Deal 5 to player 0's character
        
        assert event.was_replaced is True
        assert event.current_amount == 3  # 5 - 2 prevented
        assert simple_state.cards[1].damage == 3

    def test_deal_damage_prevent_all(self, simple_state):
        """Test full damage prevention."""
        registry = get_registry(simple_state)
        effect = ReplacementEffectEntry(
            source_id=3,
            effect_type=ReplacementEffectType.PREVENT_DAMAGE,
            target_mode="your_characters",
            amount=10,  # More than incoming damage
            once_per_turn=False,
        )
        register_replacement_effect(simple_state, effect)
        
        event = deal_damage(simple_state, 1, 2, 5)
        
        assert event.was_replaced is True
        assert event.current_amount == 0
        assert simple_state.cards[1].damage == 0

    def test_deal_damage_once_per_turn(self, simple_state):
        """Test once-per-turn damage prevention."""
        registry = get_registry(simple_state)
        effect = ReplacementEffectEntry(
            source_id=3,
            effect_type=ReplacementEffectType.PREVENT_DAMAGE,
            target_mode="your_characters",
            amount=2,
            once_per_turn=True,
            usage_key="protector_prevent",
        )
        register_replacement_effect(simple_state, effect)
        
        # First damage
        event1 = deal_damage(simple_state, 1, 2, 5)
        assert event1.was_replaced is True
        assert event1.current_amount == 3
        
        # Second damage same turn - effect exhausted
        event2 = deal_damage(simple_state, 1, 2, 5)
        assert event2.was_replaced is False
        assert event2.current_amount == 5

    def test_deal_damage_tracks_source(self, simple_state):
        """Test that damage event tracks source."""
        event = deal_damage(simple_state, 1, 2, 3, is_challenge=True)
        
        assert event.source_id == 2
        assert event.was_challenge is True
        assert simple_state.cards[1].last_damage_source == 2
        assert simple_state.cards[1].last_damage_was_challenge is True


class TestBanishCard:
    """Test banish_card with replacement effects."""

    def test_banish_card_no_effects(self, simple_state):
        """Test basic banish without replacement effects."""
        event = banish_card(simple_state, 1, 2)
        
        assert event.original_destination == "discard"
        assert event.actual_destination == "discard"
        assert event.was_replaced is False
        assert simple_state.cards[1].zone == ZONE_DISCARD

    def test_banish_replace_with_return_to_hand(self, simple_state):
        """Test banish replacement to hand."""
        registry = get_registry(simple_state)
        effect = ReplacementEffectEntry(
            source_id=3,
            effect_type=ReplacementEffectType.REPLACE_BANISH_RETURN_TO_HAND,
            target_mode="your_characters",
            once_per_turn=False,
        )
        register_replacement_effect(simple_state, effect)
        
        event = banish_card(simple_state, 1, 2)
        
        assert event.was_replaced is True
        assert event.actual_destination == "hand"
        assert simple_state.cards[1].zone == ZONE_HAND

    def test_banish_replace_with_discard(self, simple_state):
        """Test banish replacement to discard (instead of banish to inkwell).
        
        Note: The REPLACE_BANISH_DISCARD effect changes destination from the
        default "discard" to "discard", so was_replaced will be False since
        there's no actual change. This represents replacing banish-to-inkwell
        with banish-to-discard, which has no visible difference when default
        is already discard.
        """
        registry = get_registry(simple_state)
        effect = ReplacementEffectEntry(
            source_id=3,
            effect_type=ReplacementEffectType.REPLACE_BANISH_DISCARD,
            target_mode="your_characters",
            once_per_turn=False,
        )
        register_replacement_effect(simple_state, effect)
        
        event = banish_card(simple_state, 1, 2)
        
        # Card goes to discard as expected
        assert event.actual_destination == "discard"
        assert simple_state.cards[1].zone == ZONE_DISCARD
        # Note: was_replaced is False because discard == discard


class TestCannotBeChallenged:
    """Test cannot-be-challenged restrictions."""

    def test_no_restriction(self, simple_state):
        """Test normal challenge targeting."""
        assert check_cannot_be_challenged(simple_state, 1, 1) is False

    def test_cannot_be_challenged_self(self, simple_state):
        """Test cannot be challenged restriction."""
        registry = get_registry(simple_state)
        effect = ReplacementEffectEntry(
            source_id=1,
            effect_type=ReplacementEffectType.CANNOT_BE_CHALLENGED,
            target_mode="self",
        )
        register_replacement_effect(simple_state, effect)
        
        # Card 1 cannot be challenged
        assert check_cannot_be_challenged(simple_state, 1, 1) is True
        # Card 2 can still be challenged
        assert check_cannot_be_challenged(simple_state, 2, 0) is False

    def test_cannot_be_challenged_opponent(self, simple_state):
        """Test cannot be challenged restriction from opponent."""
        registry = get_registry(simple_state)
        # Card 3 (player 0) protects player 1's characters
        effect = ReplacementEffectEntry(
            source_id=3,
            effect_type=ReplacementEffectType.CANNOT_BE_CHALLENGED,
            target_mode="opposing_characters",
        )
        register_replacement_effect(simple_state, effect)
        
        # Card 2 (player 1) is protected from challenges
        assert check_cannot_be_challenged(simple_state, 2, 0) is True


class TestCannotBeTargeted:
    """Test cannot-be-targeted restrictions."""

    def test_no_restriction(self, simple_state):
        """Test normal targeting."""
        assert check_cannot_be_targeted(simple_state, 1, 1) is False

    def test_cannot_be_targeted_self(self, simple_state):
        """Test cannot be targeted restriction."""
        registry = get_registry(simple_state)
        effect = ReplacementEffectEntry(
            source_id=1,
            effect_type=ReplacementEffectType.CANNOT_BE_TARGETED,
            target_mode="self",
        )
        register_replacement_effect(simple_state, effect)
        
        # Card 1 cannot be targeted
        assert check_cannot_be_targeted(simple_state, 1, 1) is True


class TestOncePerTurnUsage:
    """Test once-per-turn usage tracking."""

    def test_cleanup_on_turn_end(self, simple_state):
        """Test cleanup of usage on turn end."""
        registry = get_registry(simple_state)
        effect = ReplacementEffectEntry(
            source_id=3,
            effect_type=ReplacementEffectType.PREVENT_DAMAGE,
            target_mode="your_characters",
            amount=1,
            once_per_turn=True,
            usage_key="prevent",
        )
        register_replacement_effect(simple_state, effect)
        
        # Use the effect
        registry.check_and_use_once_per_turn(simple_state, effect, 0)
        assert "prevent" in registry.usage_ledger
        
        # Move to next turn and cleanup
        simple_state.turn_number = 2
        cleanup_replacement_effects_on_turn_end(simple_state)
        
        # Old turn's usage should be cleared
        assert "prevent" not in registry.usage_ledger


class TestEffectAppliesTo:
    """Test targeting modes for replacement effects."""

    def test_self_mode(self, simple_state):
        """Test self targeting mode."""
        registry = get_registry(simple_state)
        effect = ReplacementEffectEntry(
            source_id=1,
            effect_type=ReplacementEffectType.PREVENT_DAMAGE,
            target_mode="self",
            amount=1,
        )
        register_replacement_effect(simple_state, effect)
        
        # Applies to source
        effects = registry.get_effects_for_instance(simple_state, 1)
        assert len(effects) == 1
        
        # Does not apply to others
        effects = registry.get_effects_for_instance(simple_state, 2)
        assert len(effects) == 0

    def test_all_characters_mode(self, simple_state):
        """Test all characters targeting mode."""
        registry = get_registry(simple_state)
        effect = ReplacementEffectEntry(
            source_id=1,
            effect_type=ReplacementEffectType.PREVENT_DAMAGE,
            target_mode="all_characters",
            amount=1,
        )
        register_replacement_effect(simple_state, effect)
        
        # Applies to all characters in play
        effects = registry.get_effects_for_instance(simple_state, 1)
        assert len(effects) == 1
        effects = registry.get_effects_for_instance(simple_state, 2)
        assert len(effects) == 1

    def test_source_not_in_play(self, simple_state):
        """Test that effects don't apply when source is not in play."""
        registry = get_registry(simple_state)
        effect = ReplacementEffectEntry(
            source_id=1,
            effect_type=ReplacementEffectType.PREVENT_DAMAGE,
            target_mode="self",
            amount=1,
        )
        register_replacement_effect(simple_state, effect)
        
        # Move source out of play
        simple_state.cards[1].zone = ZONE_DISCARD
        
        # Effect should not apply
        effects = registry.get_effects_for_instance(simple_state, 1)
        assert len(effects) == 0


class TestDamageEvent:
    """Test DamageEvent dataclass."""

    def test_damage_event_creation(self):
        """Test creating a damage event."""
        event = DamageEvent(
            target_id=1,
            source_id=2,
            original_amount=5,
            current_amount=3,
            was_challenge=True,
        )
        
        assert event.target_id == 1
        assert event.source_id == 2
        assert event.original_amount == 5
        assert event.current_amount == 3
        assert event.was_challenge is True
        assert event.was_replaced is False
        assert event.replacement_description is None

    def test_damage_event_with_replacement(self):
        """Test damage event with replacement."""
        event = DamageEvent(
            target_id=1,
            source_id=2,
            original_amount=5,
            current_amount=2,
            was_replaced=True,
            replacement_description="prevent 3 damage",
        )
        
        assert event.was_replaced is True
        assert event.replacement_description == "prevent 3 damage"


class TestBanishEvent:
    """Test BanishEvent dataclass."""

    def test_banish_event_creation(self):
        """Test creating a banish event."""
        event = BanishEvent(
            target_id=1,
            source_id=2,
        )
        
        assert event.target_id == 1
        assert event.source_id == 2
        assert event.original_destination == "discard"
        assert event.actual_destination == "discard"
        assert event.was_replaced is False

    def test_banish_event_with_replacement(self):
        """Test banish event with replacement."""
        event = BanishEvent(
            target_id=1,
            source_id=2,
            original_destination="discard",
            actual_destination="hand",
            was_replaced=True,
            replacement_description="return to hand instead of banish",
        )
        
        assert event.was_replaced is True
        assert event.actual_destination == "hand"
        assert event.replacement_description == "return to hand instead of banish"


class TestReplacementEffectEntry:
    """Test ReplacementEffectEntry dataclass."""

    def test_identifier_property(self):
        """Test the identifier property."""
        effect = ReplacementEffectEntry(
            source_id=5,
            effect_type=ReplacementEffectType.PREVENT_DAMAGE,
            target_mode="self",
        )
        
        assert effect.identifier == "PREVENT_DAMAGE:5"

    def test_frozen_dataclass(self):
        """Test that ReplacementEffectEntry is frozen."""
        effect = ReplacementEffectEntry(
            source_id=5,
            effect_type=ReplacementEffectType.PREVENT_DAMAGE,
            target_mode="self",
        )
        
        # Should not be able to modify
        with pytest.raises(Exception):  # frozen dataclass
            effect.amount = 10  # type: ignore


class TestIntegration:
    """Integration tests for replacement effects."""

    def test_multiple_prevention_effects(self, simple_state):
        """Test multiple prevention effects stacking."""
        registry = get_registry(simple_state)
        
        # Both effects target card 1
        effect1 = ReplacementEffectEntry(
            source_id=1,
            effect_type=ReplacementEffectType.PREVENT_DAMAGE,
            target_mode="self",
            amount=2,
            once_per_turn=False,
        )
        effect2 = ReplacementEffectEntry(
            source_id=1,  # Same source as effect1
            effect_type=ReplacementEffectType.PREVENT_DAMAGE,
            target_mode="all_characters",  # Applies to all characters
            amount=1,
            once_per_turn=False,
        )
        register_replacement_effect(simple_state, effect1)
        register_replacement_effect(simple_state, effect2)
        
        event = deal_damage(simple_state, 1, 2, 5)
        
        # Both effects should apply
        assert event.was_replaced is True
        # Total prevention = 2 + 1 = 3, damage dealt = 5 - 3 = 2
        assert event.current_amount == 2
        assert simple_state.cards[1].damage == 2

    def test_replace_banish_once_per_turn(self, simple_state):
        """Test once-per-turn banish replacement."""
        registry = get_registry(simple_state)
        effect = ReplacementEffectEntry(
            source_id=3,
            effect_type=ReplacementEffectType.REPLACE_BANISH_RETURN_TO_HAND,
            target_mode="your_characters",
            once_per_turn=True,
            usage_key="save_card",
        )
        register_replacement_effect(simple_state, effect)
        
        # First banish
        event1 = banish_card(simple_state, 1, 2)
        assert event1.was_replaced is True
        assert simple_state.cards[1].zone == ZONE_HAND
        
        # Reset to play for second test
        simple_state.cards[1].zone = ZONE_PLAY
        
        # Second banish same turn - effect exhausted, goes to discard
        event2 = banish_card(simple_state, 1, 2)
        assert event2.was_replaced is False
        assert simple_state.cards[1].zone == ZONE_DISCARD

    def test_mixed_effect_types(self, simple_state):
        """Test multiple effect types on same target."""
        registry = get_registry(simple_state)
        
        # Prevent damage effect
        effect1 = ReplacementEffectEntry(
            source_id=3,
            effect_type=ReplacementEffectType.PREVENT_DAMAGE,
            target_mode="your_characters",
            amount=2,
            once_per_turn=False,
        )
        # Banish replacement effect
        effect2 = ReplacementEffectEntry(
            source_id=3,
            effect_type=ReplacementEffectType.REPLACE_BANISH_RETURN_TO_HAND,
            target_mode="your_characters",
            once_per_turn=False,
        )
        register_replacement_effect(simple_state, effect1)
        register_replacement_effect(simple_state, effect2)
        
        # Damage should be prevented
        event = deal_damage(simple_state, 1, 2, 5)
        assert event.was_replaced is True
        assert simple_state.cards[1].damage == 3
        
        # Banish should be replaced
        banish_event = banish_card(simple_state, 1, 2)
        assert banish_event.was_replaced is True
        assert simple_state.cards[1].zone == ZONE_HAND


class TestEdgeCases:
    """Edge case tests."""

    def test_deal_damage_to_nonexistent_card(self, game_state):
        """Test dealing damage to a card that doesn't exist."""
        event = deal_damage(game_state, 999, 1, 5)
        
        # Should not crash, event returned with no modification
        assert event.current_amount == 5

    def test_banish_nonexistent_card(self, game_state):
        """Test banishing a card that doesn't exist."""
        event = banish_card(game_state, 999, 1)
        
        # Should not crash, event returned with no modification
        assert event.actual_destination == "discard"

    def test_empty_registry(self, simple_state):
        """Test operations with empty registry."""
        event = deal_damage(simple_state, 1, 2, 5)
        
        # No replacement, damage applied directly
        assert event.was_replaced is False
        assert simple_state.cards[1].damage == 5

    def test_prevention_on_opponent_card(self, simple_state):
        """Test prevention effect doesn't apply to opponent's cards."""
        registry = get_registry(simple_state)
        effect = ReplacementEffectEntry(
            source_id=1,  # Player 0's card
            effect_type=ReplacementEffectType.PREVENT_DAMAGE,
            target_mode="your_characters",  # Only protects player 0's characters
            amount=5,
            once_per_turn=False,
        )
        register_replacement_effect(simple_state, effect)
        
        # Deal damage to player 1's character
        event = deal_damage(simple_state, 2, 1, 5)
        
        # Effect doesn't apply (opponent's character)
        assert event.was_replaced is False
        assert simple_state.cards[2].damage == 5