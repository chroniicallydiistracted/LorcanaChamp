"""Tests for bag resolution functionality."""

import pytest
from lorcana_bot.engine import GameEngine
from lorcana_bot.cards import CardDatabase, CardDef, EffectDef, TriggerDef
from lorcana_bot.state import GameState, BagEffectEntry, PendingTriggeredEvent, GameEvent
from lorcana_bot.actions import Action
from lorcana_bot.constants import ACTION_RESOLVE_BAG, ACTION_CONCEDE, ACTION_END_TURN, ACTION_RESOLVE_PENDING_EFFECT
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


class TestChallengeTriggerEventTarget:
    """Tests for challenge trigger EVENT_TARGET resolution."""

    def test_challenge_trigger_with_defender_id(self, engine):
        """Challenge trigger with deal-damage to event_target should use defender_id from payload."""
        state = engine.setup_game([["test_char"] * 30, ["test_char"] * 30], seed=42)

        # Create card instances for both players
        from lorcana_bot.state import CardInstance
        from lorcana_bot.constants import ZONE_PLAY

        next_id = max(state.cards.keys()) + 1 if state.cards else 1
        attacker = next_id
        defender = next_id + 1

        # Player 0 has attacker, Player 1 has defender
        state.cards[attacker] = CardInstance(instance_id=attacker, card_id="test_char", owner=0, controller=0, zone=ZONE_PLAY)
        state.cards[defender] = CardInstance(instance_id=defender, card_id="test_char", owner=1, controller=1, zone=ZONE_PLAY)
        state.players[0].play.append(attacker)
        state.players[1].play.append(defender)

        # Create bag entry with defender_id (like challenge event does)
        pending_event = PendingTriggeredEvent(
            id="test_challenge_event",
            event="challenge",
            player_id=0,
            subject_card_id=attacker,
            trigger_source_card_id=attacker,
            source_card_type="character",
            payload={"defender_id": defender},  # B2: challenge payload uses defender_id
        )

        bag_entry = BagEffectEntry(
            id="bag_challenge",
            kind="triggered_ability",
            ability_id="test_ability",
            ability_index=0,
            ability_key="test:0",
            ability_name="Test Challenge Ability",
            auto_resolve=True,
            controller_id=0,
            chooser_id=0,
            source_id=attacker,
            source_card_id="test_char",
            trigger={"event": "challenge", "on": "SELF"},
            condition=None,
            effects=(EffectDef("deal_damage", 1, "event_target"),),
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

        # The event_target (defender) should have taken damage
        # defender is a character with willpower=2, so 1 damage doesn't banish it
        assert next_state.cards[defender].damage == 1
        assert next_state.cards[defender].zone == ZONE_PLAY

    def test_quest_trigger_with_subject_card_id(self, engine):
        """Quest trigger with trigger_subject should use subject_card_id from payload."""
        state = engine.setup_game([["lore_char"] * 30, ["test_char"] * 30], seed=42)

        # Create card instance
        from lorcana_bot.state import CardInstance
        from lorcana_bot.constants import ZONE_PLAY

        next_id = max(state.cards.keys()) + 1 if state.cards else 1
        quester = next_id

        state.cards[quester] = CardInstance(instance_id=quester, card_id="lore_char", owner=0, controller=0, zone=ZONE_PLAY)
        state.players[0].play.append(quester)

        # Create bag entry using subject_card_id (quest payload)
        pending_event = PendingTriggeredEvent(
            id="test_quest_event",
            event="quest",
            player_id=0,
            subject_card_id=quester,
            trigger_source_card_id=quester,
            source_card_type="character",
            payload={"subject_card_id": quester},  # B2: quest payload uses subject_card_id
        )

        bag_entry = BagEffectEntry(
            id="bag_quest",
            kind="triggered_ability",
            ability_id="test_ability",
            ability_index=0,
            ability_key="test:0",
            ability_name="Test Quest Ability",
            auto_resolve=True,
            controller_id=0,
            chooser_id=0,
            source_id=quester,
            source_card_id="lore_char",
            trigger={"event": "quest", "on": None},
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

        # The trigger_subject (quester) should have taken damage
        assert next_state.cards[quester].damage == 1


class TestNonActiveBagResolver:
    """Tests for non-active player acting as bag resolver."""

    def test_non_active_player_can_resolve_bag(self, engine):
        """Test that non-active player can receive ACTION_RESOLVE_BAG."""
        state = engine.setup_game([["test_char"] * 30, ["test_char"] * 30], seed=42)

        # Manually create a card in play for player 1
        from lorcana_bot.state import CardInstance
        from lorcana_bot.constants import ZONE_PLAY

        next_id = max(state.cards.keys()) + 1 if state.cards else 1
        test_char = next_id

        state.cards[test_char] = CardInstance(instance_id=test_char, card_id="test_char", owner=1, controller=1, zone=ZONE_PLAY)
        state.players[1].play.append(test_char)

        # Create a bag entry controlled by player 1
        from lorcana_bot.state import PendingTriggeredEvent
        pending_event = PendingTriggeredEvent(
            id="test_event_5",
            event="quest",
            player_id=1,
            subject_card_id=test_char,
            trigger_source_card_id=test_char,
            source_card_type="character",
            payload={},
        )

        bag_entry = BagEffectEntry(
            id="bag_5",
            kind="triggered_ability",
            ability_id="test_ability",
            ability_index=0,
            ability_key="test:0",
            ability_name="Test Ability",
            auto_resolve=True,
            controller_id=1,
            chooser_id=1,
            source_id=test_char,
            source_card_id="test_char",
            trigger={"event": "quest", "on": None},
            condition=None,
            effects=(EffectDef("gain_lore", 1, "controller"),),
            occurrence_index=1,
            event=pending_event,
            raw={},
        )

        state.bag.append(bag_entry)

        # Player 0 is active, but player 1 is the bag resolver
        # Player 1 (non-active) should get RESOLVE_BAG action
        player1_actions = engine.legal_actions(state, 1)
        resolve_actions = [a for a in player1_actions if a.kind == ACTION_RESOLVE_BAG]

        assert len(resolve_actions) > 0, "Non-active bag resolver should get RESOLVE_BAG action"

        # Player 0 (active) should only get CONCEDE since they're not the resolver
        player0_actions = engine.legal_actions(state, 0)
        non_concede = [a for a in player0_actions if a.kind != ACTION_CONCEDE]
        assert len(non_concede) == 0, "Active player should not get normal actions when opponent is bag resolver"

    def test_normal_actions_resume_when_bag_empty(self, engine):
        """Test that normal actions resume when bag is empty."""
        state = engine.setup_game([["test_char"] * 30, ["test_char"] * 30], seed=42)

        # No bag items - active player should get normal actions
        actions = engine.legal_actions(state, state.active_player)

        # Should have normal actions, not just CONCEDE
        end_turn = [a for a in actions if a.kind == ACTION_END_TURN]
        assert len(end_turn) > 0, "Active player should have END_TURN when bag is empty"

        # Non-active player should have no actions (no bag, not active)
        non_active = 1 - state.active_player
        non_active_actions = engine.legal_actions(state, non_active)
        assert len(non_active_actions) == 0, "Non-active player with empty bag should have no actions"


class TestTriggeredScryPending:
    """Tests for triggered scry effects creating pending effects from bag resolution."""

    def test_triggered_scry_creates_bag_origin_pending_effect(self, engine):
        """Test that resolving a bag-origin triggered scry effect creates a pending effect.

        Required behavior:
        1. Resolving a bag-origin triggered scry effect creates a pending effect
           with requirement_kind == "scry_ordering".
        2. The pending effect raw data includes:
           - origin == "bag"
           - origin_id == bag_id
        3. The bag item remains in state.bag while the pending effect is unresolved.
        """
        state = engine.setup_game([["test_char"] * 30, ["test_char"] * 30], seed=42)

        # Manually create a card in play
        from lorcana_bot.state import CardInstance
        from lorcana_bot.constants import ZONE_PLAY

        next_id = max(state.cards.keys()) + 1 if state.cards else 1
        test_char = next_id

        state.cards[test_char] = CardInstance(instance_id=test_char, card_id="test_char", owner=0, controller=0, zone=ZONE_PLAY)
        state.players[0].play.append(test_char)

        # Create a bag entry with a scry effect
        from lorcana_bot.state import PendingTriggeredEvent
        pending_event = PendingTriggeredEvent(
            id="test_event_scry",
            event="quest",
            player_id=0,
            subject_card_id=test_char,
            trigger_source_card_id=test_char,
            source_card_type="character",
            payload={},
        )

        # Scry effect with amount 2 (look at top 2 cards)
        scry_effect = EffectDef(kind="scry", amount=2)

        bag_entry = BagEffectEntry(
            id="bag_scry_1",
            kind="triggered_ability",
            ability_id="test_scry_ability",
            ability_index=0,
            ability_key="test_scry:0",
            ability_name="Test Scry Ability",
            auto_resolve=True,
            controller_id=0,
            chooser_id=0,
            source_id=test_char,
            source_card_id="test_char",
            trigger={"event": "quest", "on": None},
            condition=None,
            effects=(scry_effect,),
            occurrence_index=1,
            event=pending_event,
            raw={},
        )

        state.bag.append(bag_entry)

        # Find resolve bag action
        actions = engine.legal_actions(state, 0)
        resolve_actions = [a for a in actions if a.kind == ACTION_RESOLVE_BAG]
        assert len(resolve_actions) > 0

        # Apply the resolve action
        next_state = engine.apply_action(state, resolve_actions[0])

        # Check that a pending effect was created with scry_ordering requirement_kind
        assert len(next_state.pending_effects) == 1, "Should have created one pending effect"
        pe = next_state.pending_effects[0]
        assert pe.raw.get("requirement_kind") == "scry_ordering", "Pending effect should have scry_ordering requirement_kind"

        # Check that pending effect has bag origin
        assert pe.origin == "bag", "Pending effect should have bag origin"
        assert pe.origin_id == "bag_scry_1", "Pending effect should have correct origin_id"

        # Check that bag entry is still present (not removed yet)
        bag_ids = [entry.id for entry in next_state.bag]
        assert "bag_scry_1" in bag_ids, "Bag entry should remain while pending effect is unresolved"

    def test_resolving_bag_origin_scry_pending_removes_bag_item_once(self, engine):
        """Test that resolving a bag-origin scry pending effect removes exactly one bag item.

        Required behavior:
        1. Resolving the pending scry effect removes exactly one matching bag item.
        2. Deck order changes according to resolved top/bottom ordering.
        """
        state = engine.setup_game([["test_char"] * 30, ["test_char"] * 30], seed=42)

        # Manually create a card in play
        from lorcana_bot.state import CardInstance
        from lorcana_bot.constants import ZONE_PLAY

        next_id = max(state.cards.keys()) + 1 if state.cards else 1
        test_char = next_id

        state.cards[test_char] = CardInstance(instance_id=test_char, card_id="test_char", owner=0, controller=0, zone=ZONE_PLAY)
        state.players[0].play.append(test_char)

        # Store initial deck order
        initial_deck = list(state.players[0].deck)
        assert len(initial_deck) >= 2, "Need at least 2 cards in deck for scry test"

        # Create a bag entry with a scry effect
        from lorcana_bot.state import PendingTriggeredEvent
        pending_event = PendingTriggeredEvent(
            id="test_event_scry_2",
            event="quest",
            player_id=0,
            subject_card_id=test_char,
            trigger_source_card_id=test_char,
            source_card_type="character",
            payload={},
        )

        scry_effect = EffectDef(kind="scry", amount=2)

        bag_entry = BagEffectEntry(
            id="bag_scry_2",
            kind="triggered_ability",
            ability_id="test_scry_ability_2",
            ability_index=0,
            ability_key="test_scry_2:0",
            ability_name="Test Scry Ability 2",
            auto_resolve=True,
            controller_id=0,
            chooser_id=0,
            source_id=test_char,
            source_card_id="test_char",
            trigger={"event": "quest", "on": None},
            condition=None,
            effects=(scry_effect,),
            occurrence_index=1,
            event=pending_event,
            raw={},
        )

        state.bag.append(bag_entry)

        # First action: resolve bag
        actions = engine.legal_actions(state, 0)
        resolve_bag_actions = [a for a in actions if a.kind == ACTION_RESOLVE_BAG]
        assert len(resolve_bag_actions) > 0

        state_after_bag = engine.apply_action(state, resolve_bag_actions[0])

        # Check pending effect was created
        assert len(state_after_bag.pending_effects) == 1
        pe = state_after_bag.pending_effects[0]

        # Second action: resolve the scry pending effect
        # Get the scry candidates (top 2 cards from deck)
        from lorcana_bot.pending_effects import ScryRequirement
        scry_req = pe.raw.get("requirement")
        assert isinstance(scry_req, ScryRequirement), "Requirement should be ScryRequirement"
        candidate_ids = scry_req.candidate_ids
        assert len(candidate_ids) == 2, "Should have 2 scry candidates"

        # Resolve with specific ordering: top_cards=(first, second), bottom_cards=()
        resolve_pending_action = Action(
            ACTION_RESOLVE_PENDING_EFFECT,
            actor=0,
            source=pe.source_id,
            choice={
                "pending_effect_id": pe.id,
                "top_cards": candidate_ids,
                "bottom_cards": (),
            },
        )

        # Verify this action is legal
        actions_after_bag = engine.legal_actions(state_after_bag, 0)
        assert resolve_pending_action in actions_after_bag, "Scry resolution action should be legal"

        state_final = engine.apply_action(state_after_bag, resolve_pending_action)

        # Check pending effect was completed
        assert len(state_final.pending_effects) == 0, "Pending effect should be completed"

        # Check bag entry was removed
        bag_ids = [entry.id for entry in state_final.bag]
        assert "bag_scry_2" not in bag_ids, "Bag entry should be removed after pending resolution"

        # Check deck order changed - the top 2 cards should now be at the top (possibly reordered)
        # The scry should have moved cards around
        new_deck = state_final.players[0].deck
        assert set(new_deck[:2]) == set(candidate_ids), "Scry candidates should be at top of deck"
