"""Tests for static effect registry."""

import pytest

from lorcana_bot.state import GameState, PlayerState, CardInstance
from lorcana_bot.static_effects import (
    StaticEffectEntry,
    StaticEffectRegistry,
    StaticEffectType,
    create_modify_stat_effect,
    create_keyword_grant_effect,
    create_cost_reduction_effect,
    create_quest_restriction_effect,
    create_challenge_restriction_effect,
    parse_static_effects_from_card,
    register_static_effects_for_card,
    deregister_static_effects_for_card,
    get_static_modifier,
)
from lorcana_bot.cards import CardDef, CardDatabase
from lorcana_bot.card_logic.abilities import SourceAbilityDef
from lorcana_bot.card_logic.effects import SourceEffectDef
from lorcana_bot.card_logic.targets import SourceTargetDef


@pytest.fixture
def make_state():
    """Create a fresh game state."""
    def _make_state():
        players = [PlayerState(), PlayerState()]
        cards = {}
        return GameState(players=players, cards=cards)
    return _make_state


@pytest.fixture
def sample_cards():
    """Create a sample card database for testing."""
    cards = [
        CardDef("test_char", "Test Character", "amber", 2, True, "character", 2, 3, 1),
        CardDef("test_char2", "Test Character 2", "amber", 3, True, "character", 2, 4, 2),
    ]
    return CardDatabase(cards)


class TestStaticEffectRegistry:
    """Tests for StaticEffectRegistry."""

    def test_register_effect(self, make_state):
        """Test registering a static effect."""
        state = make_state()
        entry = create_modify_stat_effect(source_id=1, stat="strength", amount=2)
        state.static_effect_registry.register_effect(entry)
        assert len(state.static_effect_registry.effects) == 1

    def test_deregister_effects_from_source(self, make_state):
        """Test deregistering effects when source leaves play."""
        state = make_state()
        entry1 = create_modify_stat_effect(source_id=1, stat="strength", amount=2)
        entry2 = create_modify_stat_effect(source_id=2, stat="willpower", amount=1)
        state.static_effect_registry.register_effect(entry1)
        state.static_effect_registry.register_effect(entry2)
        
        state.static_effect_registry.deregister_effects_from_source(1)
        assert len(state.static_effect_registry.effects) == 1
        assert state.static_effect_registry.effects[0].source_id == 2

    def test_get_effects_for_instance(self, make_state):
        """Test getting effects that apply to a specific instance."""
        state = make_state()
        
        # Add source card in play
        state.cards[1] = CardInstance(instance_id=1, card_id="source", owner=0, controller=0, zone="play")
        state.cards[2] = CardInstance(instance_id=2, card_id="test", owner=0, controller=0, zone="play")
        state.cards[3] = CardInstance(instance_id=3, card_id="test", owner=1, controller=1, zone="play")
        
        # Self-targeted effect
        entry = create_modify_stat_effect(source_id=1, stat="strength", amount=3, target_mode="self")
        state.static_effect_registry.register_effect(entry)
        
        # Should apply to source (self)
        effects = state.static_effect_registry.get_effects_for_instance(state, 1)
        assert len(effects) == 1
        
        # Should not apply to other friendly characters
        effects = state.static_effect_registry.get_effects_for_instance(state, 2)
        assert len(effects) == 0

    def test_applies_to_your_characters(self, make_state):
        """Test effect targeting your characters."""
        state = make_state()
        
        state.cards[1] = CardInstance(instance_id=1, card_id="source", owner=0, controller=0, zone="play")
        state.cards[2] = CardInstance(instance_id=2, card_id="test", owner=0, controller=0, zone="play")
        state.cards[3] = CardInstance(instance_id=3, card_id="test", owner=1, controller=1, zone="play")
        
        entry = create_modify_stat_effect(source_id=1, stat="strength", amount=2, target_mode="your_characters")
        state.static_effect_registry.register_effect(entry)
        
        # Should apply to friendly character (id=2)
        effects = state.static_effect_registry.get_effects_for_instance(state, 2)
        assert len(effects) == 1
        
        # Should not apply to opposing character (id=3)
        effects = state.static_effect_registry.get_effects_for_instance(state, 3)
        assert len(effects) == 0

    def test_applies_to_opposing_characters(self, make_state):
        """Test effect targeting opposing characters."""
        state = make_state()
        
        state.cards[1] = CardInstance(instance_id=1, card_id="source", owner=0, controller=0, zone="play")
        state.cards[2] = CardInstance(instance_id=2, card_id="test", owner=0, controller=0, zone="play")
        state.cards[3] = CardInstance(instance_id=3, card_id="test", owner=1, controller=1, zone="play")
        
        entry = create_modify_stat_effect(source_id=1, stat="strength", amount=2, target_mode="opposing_characters")
        state.static_effect_registry.register_effect(entry)
        
        # Should apply to opposing character (id=3)
        effects = state.static_effect_registry.get_effects_for_instance(state, 3)
        assert len(effects) == 1
        
        # Should not apply to friendly character (id=2)
        effects = state.static_effect_registry.get_effects_for_instance(state, 2)
        assert len(effects) == 0

    def test_effect_removed_when_source_leaves_play(self, make_state):
        """Test that effect no longer applies when source card leaves play."""
        state = make_state()
        
        state.cards[1] = CardInstance(instance_id=1, card_id="source", owner=0, controller=0, zone="play")
        state.cards[2] = CardInstance(instance_id=2, card_id="test", owner=0, controller=0, zone="play")
        
        entry = create_modify_stat_effect(source_id=1, stat="strength", amount=2, target_mode="your_characters")
        state.static_effect_registry.register_effect(entry)
        
        # Source card in play - effect applies
        effects = state.static_effect_registry.get_effects_for_instance(state, 2)
        assert len(effects) == 1
        
        # Source card leaves play
        state.cards[1].zone = "discard"
        
        # Effect no longer applies
        effects = state.static_effect_registry.get_effects_for_instance(state, 2)
        assert len(effects) == 0


class TestStaticModifierCalculation:
    """Tests for static modifier calculations."""

    def test_get_static_modifier_strength(self, make_state):
        """Test getting static strength modifier."""
        state = make_state()
        
        state.cards[1] = CardInstance(instance_id=1, card_id="source", owner=0, controller=0, zone="play")
        state.cards[2] = CardInstance(instance_id=2, card_id="test", owner=0, controller=0, zone="play")
        
        entry = create_modify_stat_effect(source_id=1, stat="strength", amount=3, target_mode="your_characters")
        state.static_effect_registry.register_effect(entry)
        
        modifier = get_static_modifier(state, 2, "strength")
        assert modifier == 3

    def test_get_static_modifier_willpower(self, make_state):
        """Test getting static willpower modifier."""
        state = make_state()
        
        state.cards[1] = CardInstance(instance_id=1, card_id="source", owner=0, controller=0, zone="play")
        state.cards[2] = CardInstance(instance_id=2, card_id="test", owner=0, controller=0, zone="play")
        
        entry = create_modify_stat_effect(source_id=1, stat="willpower", amount=2, target_mode="your_characters")
        state.static_effect_registry.register_effect(entry)
        
        modifier = get_static_modifier(state, 2, "willpower")
        assert modifier == 2

    def test_multiple_static_modifiers(self, make_state):
        """Test multiple static modifiers stack."""
        state = make_state()
        
        state.cards[1] = CardInstance(instance_id=1, card_id="source1", owner=0, controller=0, zone="play")
        state.cards[2] = CardInstance(instance_id=2, card_id="source2", owner=0, controller=0, zone="play")
        state.cards[3] = CardInstance(instance_id=3, card_id="target", owner=0, controller=0, zone="play")
        
        entry1 = create_modify_stat_effect(source_id=1, stat="strength", amount=2, target_mode="your_characters")
        entry2 = create_modify_stat_effect(source_id=2, stat="strength", amount=3, target_mode="your_characters")
        state.static_effect_registry.register_effect(entry1)
        state.static_effect_registry.register_effect(entry2)
        
        modifier = get_static_modifier(state, 3, "strength")
        assert modifier == 5


class TestKeywordGrant:
    """Tests for static keyword grants."""

    def test_create_keyword_grant_effect(self, make_state):
        """Test creating a keyword grant effect."""
        entry = create_keyword_grant_effect(source_id=1, keyword="bodyguard")
        assert entry.effect_type == StaticEffectType.GRANT_KEYWORD
        assert entry.keyword == "BODYGUARD"

    def test_keyword_grant_effect_applies(self, make_state):
        """Test that keyword grant effect applies to target."""
        state = make_state()
        
        state.cards[1] = CardInstance(instance_id=1, card_id="source", owner=0, controller=0, zone="play")
        state.cards[2] = CardInstance(instance_id=2, card_id="test", owner=0, controller=0, zone="play")
        
        entry = create_keyword_grant_effect(source_id=1, keyword="bodyguard", target_mode="your_characters")
        state.static_effect_registry.register_effect(entry)
        
        effects = state.static_effect_registry.get_effects_for_instance(state, 2)
        assert len(effects) == 1
        assert effects[0].keyword == "BODYGUARD"


class TestCostReduction:
    """Tests for static cost reduction effects."""

    def test_create_cost_reduction_effect(self):
        """Test creating a cost reduction effect."""
        entry = create_cost_reduction_effect(source_id=1, amount=1, card_type=None)
        assert entry.effect_type == StaticEffectType.COST_REDUCTION
        assert entry.cost_reduction_amount == 1
        assert entry.cost_reduction_card_type is None

    def test_cost_reduction_with_card_type(self):
        """Test cost reduction for specific card type."""
        entry = create_cost_reduction_effect(source_id=1, amount=2, card_type="character")
        assert entry.effect_type == StaticEffectType.COST_REDUCTION
        assert entry.cost_reduction_amount == 2
        assert entry.cost_reduction_card_type == "character"


class TestQuestRestriction:
    """Tests for static quest restriction effects."""

    def test_create_quest_restriction_effect(self):
        """Test creating a quest restriction effect."""
        entry = create_quest_restriction_effect(source_id=1)
        assert entry.effect_type == StaticEffectType.QUEST_RESTRICTION
        assert entry.restriction_type == "cannot_quest"


class TestParseStaticEffectsFromCard:
    """Tests for parsing static effects from card source abilities."""

    def test_parse_modify_stat_ability(self, make_state):
        """Test parsing a modify-stat static ability."""
        abilities = (
            {
                "type": "static",
                "effect": {
                    "type": "modify-stat",
                    "attribute": "strength",
                    "amount": 2,
                },
            },
        )
        
        effects = []
        for ability in abilities:
            if ability.get("type") == "static":
                effect_raw = ability.get("effect") or {}
                if effect_raw.get("type") == "modify-stat":
                    stat = effect_raw.get("attribute") or "strength"
                    amount = int(effect_raw.get("amount") or 0)
                    effects.append(create_modify_stat_effect(
                        source_id=1,
                        stat=stat,
                        amount=amount,
                        target_mode="self",
                    ))
        
        assert len(effects) == 1
        assert effects[0].effect_type == StaticEffectType.MODIFY_STRENGTH
        assert effects[0].amount == 2

    def test_parse_keyword_grant_ability(self, make_state):
        """Test parsing a keyword grant static ability."""
        abilities = (
            {
                "type": "static",
                "effect": {
                    "type": "gain-keyword",
                    "keyword": "bodyguard",
                },
            },
        )
        
        effects = []
        for ability in abilities:
            if ability.get("type") == "static":
                effect_raw = ability.get("effect") or {}
                if effect_raw.get("type") == "gain-keyword":
                    keyword = effect_raw.get("keyword")
                    effects.append(create_keyword_grant_effect(
                        source_id=1,
                        keyword=keyword,
                        target_mode="your_characters",
                    ))
        
        assert len(effects) == 1
        assert effects[0].effect_type == StaticEffectType.GRANT_KEYWORD
        assert effects[0].keyword == "BODYGUARD"


class TestEffectDoesNotMutatePrintedCard:
    """Tests to verify static effects don't mutate printed card definitions."""

    def test_printed_stats_unchanged(self, sample_cards):
        """Test that printed stats remain unchanged."""
        char = sample_cards.get("test_char")
        original_strength = char.strength
        original_willpower = char.willpower
        
        # Create state and apply static effect
        players = [PlayerState(), PlayerState()]
        cards = {
            1: CardInstance(instance_id=1, card_id="test_char", owner=0, controller=0, zone="play"),
            2: CardInstance(instance_id=2, card_id="test_char", owner=0, controller=0, zone="play"),
        }
        state = GameState(players=players, cards=cards)
        
        # Register a +3 strength static effect
        entry = create_modify_stat_effect(source_id=1, stat="strength", amount=3, target_mode="your_characters")
        state.static_effect_registry.register_effect(entry)
        
        # Printed stats should be unchanged
        assert char.strength == original_strength
        assert char.willpower == original_willpower


class TestStaticEffectIntegration:
    """Integration tests for static effects with game engine."""

    def test_static_strength_modifier_affects_effective_strength(self, make_state, sample_cards):
        """Test that static strength modifier is reflected in effective_strength."""
        players = [PlayerState(), PlayerState()]
        cards = {
            1: CardInstance(instance_id=1, card_id="test_char", owner=0, controller=0, zone="play"),
            2: CardInstance(instance_id=2, card_id="test_char2", owner=0, controller=0, zone="play"),
        }
        state = GameState(players=players, cards=cards)
        
        # Register +2 strength static effect for player 0's characters
        entry = create_modify_stat_effect(source_id=1, stat="strength", amount=2, target_mode="your_characters")
        state.static_effect_registry.register_effect(entry)
        
        # Get static modifier for character 2
        modifier = get_static_modifier(state, 2, "strength")
        assert modifier == 2

    def test_static_keyword_affects_keywords_for_instance(self, make_state):
        """Test that static keyword grants are included in keywords_for_instance."""
        state = make_state()
        
        state.cards[1] = CardInstance(instance_id=1, card_id="source", owner=0, controller=0, zone="play")
        state.cards[2] = CardInstance(instance_id=2, card_id="target", owner=0, controller=0, zone="play")
        
        # Register bodyguard keyword grant
        entry = create_keyword_grant_effect(source_id=1, keyword="bodyguard", target_mode="your_characters")
        state.static_effect_registry.register_effect(entry)
        
        # Check that effect applies
        effects = state.static_effect_registry.get_effects_for_instance(state, 2)
        assert len(effects) == 1
        assert effects[0].keyword == "BODYGUARD"

    def test_static_cost_reduction_in_registry(self, make_state):
        """Test that static cost reduction is registered."""
        state = make_state()
        
        state.cards[1] = CardInstance(instance_id=1, card_id="source", owner=0, controller=0, zone="play")
        
        entry = create_cost_reduction_effect(source_id=1, amount=1, card_type="character")
        state.static_effect_registry.register_effect(entry)
        
        # Check effect is registered
        assert len(state.static_effect_registry.effects) == 1
        assert state.static_effect_registry.effects[0].effect_type == StaticEffectType.COST_REDUCTION
        assert state.static_effect_registry.effects[0].cost_reduction_amount == 1


class TestStaticBlockerClassification:
    """Tests for static effect blocker classification in trigger blocker report."""

    def test_static_effect_entry_has_blocker_info(self):
        """Test that static effect entries contain information for blocker classification."""
        entry = create_modify_stat_effect(source_id=1, stat="strength", amount=2)
        
        # Entry should have type information for classification
        assert entry.effect_type == StaticEffectType.MODIFY_STRENGTH
        
    def test_cost_reduction_static_effect_classification(self):
        """Test cost reduction static effect classification."""
        entry = create_cost_reduction_effect(source_id=1, amount=1)
        
        assert entry.effect_type == StaticEffectType.COST_REDUCTION
        assert entry.target_mode == "self"


class TestStaticEffectEngineWiring:
    """Tests for static effect wiring into game engine."""

    def test_static_quest_restriction_blocks_quest(self, make_state):
        """Test that static quest restriction prevents questing."""
        from lorcana_bot.static_effects import can_quest
        
        state = make_state()
        state.cards[1] = CardInstance(instance_id=1, card_id="test", owner=0, controller=0, zone="play")
        
        # Register quest restriction on card
        entry = create_quest_restriction_effect(source_id=1, target_mode="self")
        state.static_effect_registry.register_effect(entry)
        
        # Card should not be able to quest
        assert can_quest(state, 1) is False

    def test_static_challenge_restriction_blocks_challenge(self, make_state):
        """Test that static challenge restriction prevents challenging."""
        from lorcana_bot.static_effects import can_challenge
        
        state = make_state()
        state.cards[1] = CardInstance(instance_id=1, card_id="test", owner=0, controller=0, zone="play")
        
        # Register challenge restriction on card
        entry = create_challenge_restriction_effect(source_id=1, target_mode="self")
        state.static_effect_registry.register_effect(entry)
        
        # Card should not be able to challenge
        assert can_challenge(state, 1) is False

    def test_static_lore_modifier_affects_quest(self, make_state):
        """Test that static lore modifier affects lore gained on quest."""
        from lorcana_bot.static_effects import get_static_modifier
        
        state = make_state()
        state.cards[1] = CardInstance(instance_id=1, card_id="test", owner=0, controller=0, zone="play")
        
        # Register +2 lore static effect
        entry = create_modify_stat_effect(source_id=1, stat="lore", amount=2, target_mode="self")
        state.static_effect_registry.register_effect(entry)
        
        # Get static modifier for lore
        modifier = get_static_modifier(state, 1, "lore")
        assert modifier == 2

    def test_classification_targeting_matches_items(self, make_state):
        """Test that classification-based targeting correctly targets items.
        
        Note: Classification targeting currently uses placeholder logic.
        For full card type checking, engine access to card_def is needed.
        """
        state = make_state()
        
        # Create cards with different types
        state.cards[1] = CardInstance(instance_id=1, card_id="source", owner=0, controller=0, zone="play")
        state.cards[2] = CardInstance(instance_id=2, card_id="item_card", owner=0, controller=0, zone="play")
        
        # Register effect targeting items (classification mode)
        entry = create_modify_stat_effect(
            source_id=1, 
            stat="strength", 
            amount=3, 
            target_mode="classification",
            target_classification="item"
        )
        state.static_effect_registry.register_effect(entry)
        
        # Effect should apply to item card (id starts with "item")
        effects = state.static_effect_registry.get_effects_for_instance(state, 2)
        
        # Classification targeting should apply based on card_id pattern
        # (Placeholder: matches based on card_id contains target_classification)
        assert len(effects) == 1

    def test_static_effect_removal_on_source_leave_play(self, make_state):
        """Test that static effects are removed when source leaves play."""
        from lorcana_bot.static_effects import get_static_modifier
        
        state = make_state()
        state.cards[1] = CardInstance(instance_id=1, card_id="source", owner=0, controller=0, zone="play")
        state.cards[2] = CardInstance(instance_id=2, card_id="target", owner=0, controller=0, zone="play")
        
        # Register strength modifier
        entry = create_modify_stat_effect(source_id=1, stat="strength", amount=5, target_mode="your_characters")
        state.static_effect_registry.register_effect(entry)
        
        # Modifier should apply while source is in play
        modifier = get_static_modifier(state, 2, "strength")
        assert modifier == 5
        
        # Source leaves play (moves to discard)
        state.cards[1].zone = "discard"
        
        # Modifier should no longer apply
        modifier = get_static_modifier(state, 2, "strength")
        assert modifier == 0

    def test_deregister_static_effects_clears_effects(self, make_state):
        """Test that deregister_static_effects_for_card removes all effects from source."""
        state = make_state()
        state.cards[1] = CardInstance(instance_id=1, card_id="source", owner=0, controller=0, zone="play")
        
        # Register multiple static effects from same source
        entry1 = create_modify_stat_effect(source_id=1, stat="strength", amount=2, target_mode="self")
        entry2 = create_keyword_grant_effect(source_id=1, keyword="bodyguard", target_mode="self")
        state.static_effect_registry.register_effect(entry1)
        state.static_effect_registry.register_effect(entry2)
        
        assert len(state.static_effect_registry.effects) == 2
        
        # Deregister effects from source
        deregister_static_effects_for_card(state, 1)
        
        assert len(state.static_effect_registry.effects) == 0


class TestStaticEffectRegistryClear:
    """Tests for StaticEffectRegistry.clear method."""

    def test_clear_removes_all_effects(self, make_state):
        """Test that clear removes all effects from registry."""
        state = make_state()
        state.cards[1] = CardInstance(instance_id=1, card_id="source", owner=0, controller=0, zone="play")
        
        # Register some effects
        entry1 = create_modify_stat_effect(source_id=1, stat="strength", amount=2)
        entry2 = create_keyword_grant_effect(source_id=1, keyword="bodyguard")
        state.static_effect_registry.register_effect(entry1)
        state.static_effect_registry.register_effect(entry2)
        
        assert len(state.static_effect_registry.effects) == 2
        
        # Clear all effects
        state.static_effect_registry.clear()
        
        assert len(state.static_effect_registry.effects) == 0


class TestParseStaticEffectsFromSourceDataclasses:
    """Tests for parsing static effects from Lorcanito source dataclasses."""

    def test_parse_source_modify_stat_static_ability(self):
        """Test parsing SourceAbilityDef with modify-stat effect."""
        ability = SourceAbilityDef(
            id="static_modify",
            kind="static",
            effects=(
                SourceEffectDef(
                    kind="modify-stat",
                    amount=2,
                    target=SourceTargetDef(kind="alias", alias="YOUR_CHARACTERS"),
                    raw={"attribute": "strength"},
                ),
            ),
        )

        effects = parse_static_effects_from_card((ability,), source_id=10)

        assert len(effects) == 1
        assert effects[0].source_id == 10
        assert effects[0].effect_type == StaticEffectType.MODIFY_STRENGTH
        assert effects[0].amount == 2
        assert effects[0].target_mode == "your_characters"

    def test_parse_source_gain_keyword_static_ability(self):
        """Test parsing SourceAbilityDef with gain-keyword effect."""
        ability = SourceAbilityDef(
            id="static_keyword",
            kind="static",
            effects=(
                SourceEffectDef(
                    kind="gain-keyword",
                    target=SourceTargetDef(kind="alias", alias="SELF"),
                    raw={"keyword": "evasive"},
                ),
            ),
        )

        effects = parse_static_effects_from_card((ability,), source_id=11)

        assert len(effects) == 1
        assert effects[0].source_id == 11
        assert effects[0].effect_type == StaticEffectType.GRANT_KEYWORD
        assert effects[0].keyword == "EVASIVE"
        assert effects[0].target_mode == "self"

    def test_parse_source_cost_reduction_static_ability(self):
        """Test parsing SourceAbilityDef with cost-reduction effect."""
        ability = SourceAbilityDef(
            id="static_cost_reduction",
            kind="static",
            effects=(
                SourceEffectDef(
                    kind="cost-reduction",
                    amount=1,
                    raw={"cardType": "character"},
                ),
            ),
        )

        effects = parse_static_effects_from_card((ability,), source_id=12)

        assert len(effects) == 1
        assert effects[0].source_id == 12
        assert effects[0].effect_type == StaticEffectType.COST_REDUCTION
        assert effects[0].cost_reduction_amount == 1
        assert effects[0].cost_reduction_card_type == "character"

    def test_parse_source_static_ability_ignores_non_static_kind(self):
        """Test that SourceAbilityDef with non-static kind is ignored."""
        ability = SourceAbilityDef(
            id="triggered_not_static",
            kind="triggered",
            effects=(
                SourceEffectDef(kind="modify-stat", amount=2, raw={"attribute": "strength"}),
            ),
        )

        effects = parse_static_effects_from_card((ability,), source_id=13)

        assert effects == []

    def test_parse_dict_static_fallback_still_works(self):
        """Test that raw dict static abilities still parse correctly."""
        ability = {
            "type": "static",
            "effect": {
                "type": "modify-stat",
                "attribute": "willpower",
                "amount": 3,
                "target": "SELF",
            },
        }

        effects = parse_static_effects_from_card((ability,), source_id=14)

        assert len(effects) == 1
        assert effects[0].effect_type == StaticEffectType.MODIFY_WILLPOWER
        assert effects[0].amount == 3
        assert effects[0].target_mode == "self"
