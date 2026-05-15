"""Tests for bag resolution functionality."""

import pytest
from lorcana_bot.engine import GameEngine
from lorcana_bot.cards import CardDatabase, CardDef, EffectDef, TriggerDef
from lorcana_bot.state import GameState, BagEffectEntry, PendingTriggeredEvent, GameEvent
from lorcana_bot.actions import Action
from lorcana_bot.constants import ACTION_RESOLVE_BAG
from lorcana_bot.effect_types import EffectResolutionContext


@pytest.fixture
def engine():
    """Create a GameEngine with a minimal card database."""
    cards = [
        CardDef("test_char", "Test Char", "amber", 2, True, "character", 2, 2, 1),
        CardDef("test_char2", "Test Char 2", "amber", 3, True, "character", 3, 3, 1),
        CardDef("lore_char", "Lore Char", "amber", 2, True, "character", 2, 2, 2),
    ]
    db = CardDatabase(cards)
    return GameEngine(db)


def test_resolve_bag_requires_action(engine):
    """Test that bag resolution must go through ACTION_RESOLVE_BAG."""
    state = engine.setup_game([["test_char"], ["test_char"]], seed=42)
    
    # Direct resolve_bag call should raise
    with pytest.raises(RuntimeError, match="Bag must be resolved through ACTION_RESOLVE_BAG"):
        engine.resolve_bag(state)


def test_resolve_bag_action_processes_effects(engine):
    """Test that ACTION_RESOLVE_BAG processes bag effects."""
    state = engine.setup_game([["test_char"], ["test_char"]], seed=42)
    
    # Create a mock bag entry (this would normally be created by triggers)
    # For now, just test that the action can be applied
    actions = engine.legal_actions(state, 0)
    resolve_actions = [a for a in actions if a.kind == ACTION_RESOLVE_BAG]
    
    if resolve_actions:
        next_state = engine.apply_action(state, resolve_actions[0])
        assert next_state is not None


class TestTriggerContextInBagResolution:
    """Tests for trigger context being passed to effect resolution."""

    def test_trigger_subject_available_in_resolution(self, engine):
        """Test that trigger_subject is passed to effect resolution context."""
        state = engine.setup_game([["test_char"] * 30, ["test_char"] * 30], seed=42)
        
        # Manually create card instances in play using CardInstance
        from lorcana_bot.state import CardInstance
        from lorcana_bot.constants import ZONE_PLAY
        
        # Get next available instance ID
        next_id = max(state.cards.keys()) + 1 if state.cards else 1
        test_char = next_id
        lore_char = next_id + 1
        
        # Create instances
        state.cards[test_char] = CardInstance(instance_id=test_char, card_id="test_char", owner=0, controller=0, zone=ZONE_PLAY)
        state.cards[lore_char] = CardInstance(instance_id=lore_char, card_id="lore_char", owner=0, controller=0, zone=ZONE_PLAY)
        state.players[0].play.extend([test_char, lore_char])
        
        # Create a bag entry with trigger context
        pending_event = PendingTriggeredEvent(
            id="test_event_1",
            event="challenge",
            player_id=0,
            subject_card_id=lore_char,
            trigger_source_card_id=test_char,
            source_card_type="character",
            payload={},
        )
        
        bag_entry = BagEffectEntry(
            id="bag_1",
            kind="triggered_ability",
            ability_id="test_ability",
            ability_index=0,
            ability_key="test:0",
            ability_name="Test Ability",
            auto_resolve=True,
            controller_id=0,
            chooser_id=0,
            source_id=test_char,
            source_card_id="test_char",
            trigger={"event": "challenge", "on": None},
            condition=None,
            effects=(EffectDef("deal_damage", 1, "trigger_subject"),),
            occurrence_index=1,
            event=pending_event,
            raw={},
        )
        
        # Add to bag
        state.bag.append(bag_entry)
        
        # Find resolve bag action
        actions = engine.legal_actions(state, 0)
        resolve_actions = [a for a in actions if a.kind == ACTION_RESOLVE_BAG]
        assert len(resolve_actions) > 0
        
        # Apply the resolve action
        next_state = engine.apply_action(state, resolve_actions[0])
        
        # The trigger_subject (lore_char) should have taken damage
        assert next_state.cards[lore_char].damage == 1

    def test_event_target_in_payload(self, engine):
        """Test that event_target from payload is used."""
        state = engine.setup_game([["test_char"] * 30, ["test_char"] * 30], seed=42)
        
        # Manually create card instances in play for both players
        from lorcana_bot.state import CardInstance
        from lorcana_bot.constants import ZONE_PLAY
        
        next_id = max(state.cards.keys()) + 1 if state.cards else 1
        test_char = next_id
        lore_char = next_id + 1
        
        state.cards[test_char] = CardInstance(instance_id=test_char, card_id="test_char", owner=0, controller=0, zone=ZONE_PLAY)
        state.cards[lore_char] = CardInstance(instance_id=lore_char, card_id="lore_char", owner=1, controller=1, zone=ZONE_PLAY)
        state.players[0].play.append(test_char)
        state.players[1].play.append(lore_char)
        
        # Create a bag entry with event_target in payload
        pending_event = PendingTriggeredEvent(
            id="test_event_2",
            event="challenge",
            player_id=0,
            subject_card_id=test_char,
            trigger_source_card_id=test_char,
            source_card_type="character",
            payload={"event_target_id": lore_char},
        )
        
        bag_entry = BagEffectEntry(
            id="bag_2",
            kind="triggered_ability",
            ability_id="test_ability",
            ability_index=0,
            ability_key="test:0",
            ability_name="Test Ability",
            auto_resolve=True,
            controller_id=0,
            chooser_id=0,
            source_id=test_char,
            source_card_id="test_char",
            trigger={"event": "challenge", "on": None},
            condition=None,
            effects=(EffectDef("deal_damage", 2, "event_target"),),
            occurrence_index=1,
            event=pending_event,
            raw={},
        )
        
        # Add to bag
        state.bag.append(bag_entry)
        
        # Find resolve bag action
        actions = engine.legal_actions(state, 0)
        resolve_actions = [a for a in actions if a.kind == ACTION_RESOLVE_BAG]
        assert len(resolve_actions) > 0
        
        # Apply the resolve action
        next_state = engine.apply_action(state, resolve_actions[0])
        
        # The event_target (lore_char) should have taken damage
        # Note: lore_char has willpower=2, so 2 damage banishes it (moves to discard)
        # Check the card state - it should have been banished (zone = discard)
        assert next_state.cards[lore_char].zone == "discard" or next_state.cards[lore_char].damage >= 2

    def test_controller_target_in_bag_effect(self, engine):
        """Test that controller target resolves to controller in bag effect."""
        state = engine.setup_game([["lore_char"] * 30, ["test_char"] * 30], seed=42)
        
        # Manually create card instance in play
        from lorcana_bot.state import CardInstance
        from lorcana_bot.constants import ZONE_PLAY
        
        next_id = max(state.cards.keys()) + 1 if state.cards else 1
        lore_char = next_id
        
        state.cards[lore_char] = CardInstance(instance_id=lore_char, card_id="lore_char", owner=0, controller=0, zone=ZONE_PLAY)
        state.players[0].play.append(lore_char)
        
        initial_lore = state.players[0].lore
        
        # Create a bag entry with controller target
        pending_event = PendingTriggeredEvent(
            id="test_event_3",
            event="quest",
            player_id=0,
            subject_card_id=lore_char,
            trigger_source_card_id=lore_char,
            source_card_type="character",
            payload={},
        )
        
        bag_entry = BagEffectEntry(
            id="bag_3",
            kind="triggered_ability",
            ability_id="test_ability",
            ability_index=0,
            ability_key="test:0",
            ability_name="Test Ability",
            auto_resolve=True,
            controller_id=0,
            chooser_id=0,
            source_id=lore_char,
            source_card_id="lore_char",
            trigger={"event": "quest", "on": None},
            condition=None,
            effects=(EffectDef("gain_lore", 1, "controller"),),
            occurrence_index=1,
            event=pending_event,
            raw={},
        )
        
        # Add to bag
        state.bag.append(bag_entry)
        
        # Find resolve bag action
        actions = engine.legal_actions(state, 0)
        resolve_actions = [a for a in actions if a.kind == ACTION_RESOLVE_BAG]
        assert len(resolve_actions) > 0
        
        # Apply the resolve action
        next_state = engine.apply_action(state, resolve_actions[0])
        
        # Controller should have gained lore
        assert next_state.players[0].lore == initial_lore + 1


class TestYourOtherCharactersExcludesSource:
    """Tests for your_other_characters correctly excluding source."""

    def test_your_other_characters_excludes_trigger_source(self, engine):
        """your_other_characters should exclude trigger_source."""
        state = engine.setup_game([["test_char"] * 30, ["lore_char"] * 30], seed=42)
        
        # Manually create two card instances in play
        from lorcana_bot.state import CardInstance
        from lorcana_bot.constants import ZONE_PLAY
        
        next_id = max(state.cards.keys()) + 1 if state.cards else 1
        char1 = next_id
        char2 = next_id + 1
        
        state.cards[char1] = CardInstance(instance_id=char1, card_id="test_char", owner=0, controller=0, zone=ZONE_PLAY)
        state.cards[char2] = CardInstance(instance_id=char2, card_id="lore_char", owner=0, controller=0, zone=ZONE_PLAY)
        state.players[0].play.extend([char1, char2])
        
        # Create bag entry targeting your_other_characters
        pending_event = PendingTriggeredEvent(
            id="test_event_4",
            event="challenge",
            player_id=0,
            subject_card_id=char1,
            trigger_source_card_id=char1,
            source_card_type="character",
            payload={},
        )
        
        bag_entry = BagEffectEntry(
            id="bag_4",
            kind="triggered_ability",
            ability_id="test_ability",
            ability_index=0,
            ability_key="test:0",
            ability_name="Test Ability",
            auto_resolve=True,
            controller_id=0,
            chooser_id=0,
            source_id=char1,
            source_card_id="test_char",
            trigger={"event": "challenge", "on": None},
            condition=None,
            effects=(EffectDef("for_each", value="your_other_characters", effects=(EffectDef("deal_damage", 1, "target"),)),),
            occurrence_index=1,
            event=pending_event,
            raw={},
        )
        
        # Add to bag
        state.bag.append(bag_entry)
        
        # Find resolve bag action
        actions = engine.legal_actions(state, 0)
        resolve_actions = [a for a in actions if a.kind == ACTION_RESOLVE_BAG]
        assert len(resolve_actions) > 0
        
        # Apply the resolve action
        next_state = engine.apply_action(state, resolve_actions[0])
        
        # char2 (other character) should have damage, char1 (source) should not
        assert next_state.cards[char2].damage == 1
        assert next_state.cards[char1].damage == 0
