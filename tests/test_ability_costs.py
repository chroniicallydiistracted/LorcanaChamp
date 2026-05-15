"""Tests for ability cost validation and payment."""

import pytest
from unittest.mock import MagicMock

from lorcana_bot.state import GameState, PlayerState, CardInstance
from lorcana_bot.cards import CardDef
from lorcana_bot.engine import GameEngine
from lorcana_bot.cards import CardDatabase
from lorcana_bot.constants import ZONE_PLAY, ZONE_INKWELL, ZONE_HAND, ZONE_DISCARD

from lorcana_bot.card_logic import SourceAbilityDef, SourceTriggerDef, SourceCostDef, SourceEffectDef
from lorcana_bot.abilities import (
    get_activated_abilities_for_card,
    can_use_ability_this_turn,
    validate_ability_costs,
    AbilityCostError,
    ActivatedAbility,
)
from lorcana_bot.costs import (
    validate_cost_payable,
    pay_cost,
)


def _make_card_def(card_id: str, abilities: list[SourceAbilityDef] | None = None) -> MagicMock:
    """Create a mock card def with source abilities."""
    mock = MagicMock(spec=CardDef)
    mock.id = card_id
    mock.full_name = f"Test Card {card_id}"
    mock.card_type = "character"
    mock.source_abilities = abilities or []
    return mock


def _make_source_cost(kind: str, amount: int = 1) -> SourceCostDef:
    """Create a mock source cost."""
    return SourceCostDef(
        kind=kind,
        amount=amount,
        raw={},
    )


def _make_source_effect(kind: str) -> SourceEffectDef:
    """Create a mock source effect."""
    return SourceEffectDef(
        kind=kind,
        target=None,
        raw={},
    )


def _make_source_ability(
    ability_id: str,
    costs: list[SourceCostDef] | None = None,
    effects: list[SourceEffectDef] | None = None,
) -> SourceAbilityDef:
    """Create a mock source ability."""
    return SourceAbilityDef(
        id=ability_id,
        name=f"Test Ability {ability_id}",
        kind="activated",
        trigger=None,
        costs=tuple(costs or []),
        effects=tuple(effects or []),
        condition=None,
        source_zones=None,
        auto_resolve=True,
        raw={},
    )


class TestExertSourceCost:
    """Test exert source cost validation and payment."""
    
    def test_exert_cost_payable_when_source_not_exerted(self):
        """Exert cost should be payable when source is not exerted."""
        state = GameState(
            players=[PlayerState(), PlayerState()],
            cards={1: CardInstance(instance_id=1, card_id="test", owner=0, controller=0)},
        )
        state.cards[1].zone = ZONE_PLAY
        state.cards[1].exerted = False
        
        engine = MagicMock(spec=GameEngine)
        card_def = _make_card_def("test", [
            _make_source_ability("exert_ability", costs=[_make_source_cost("exert_source")])
        ])
        
        ability = ActivatedAbility(
            source_instance_id=1,
            source_card_id="test",
            ability_id="exert_ability",
            ability_index=0,
            name="Exert Ability",
            costs=(_make_source_cost("exert_source"),),
            effects=(),
            condition=None,
        )
        
        can_pay, reason = validate_cost_payable(state, engine, ability, ability.costs[0])
        assert can_pay is True
        assert "not exerted" in reason.lower() or reason == ""
    
    def test_exert_cost_not_payable_when_source_exerted(self):
        """Exert cost should NOT be payable when source is already exerted."""
        state = GameState(
            players=[PlayerState(), PlayerState()],
            cards={1: CardInstance(instance_id=1, card_id="test", owner=0, controller=0)},
        )
        state.cards[1].zone = ZONE_PLAY
        state.cards[1].exerted = True
        
        engine = MagicMock(spec=GameEngine)
        
        ability = ActivatedAbility(
            source_instance_id=1,
            source_card_id="test",
            ability_id="exert_ability",
            ability_index=0,
            name="Exert Ability",
            costs=(_make_source_cost("exert_source"),),
            effects=(),
            condition=None,
        )
        
        can_pay, reason = validate_cost_payable(state, engine, ability, ability.costs[0])
        assert can_pay is False
        assert "exerted" in reason.lower()
    
    def test_exert_cost_payment_exerts_source(self):
        """Paying exert cost should exert the source card."""
        state = GameState(
            players=[PlayerState(), PlayerState()],
            cards={1: CardInstance(instance_id=1, card_id="test", owner=0, controller=0)},
        )
        state.cards[1].zone = ZONE_PLAY
        state.cards[1].exerted = False
        
        engine = MagicMock(spec=GameEngine)
        
        ability = ActivatedAbility(
            source_instance_id=1,
            source_card_id="test",
            ability_id="exert_ability",
            ability_index=0,
            name="Exert Ability",
            costs=(_make_source_cost("exert_source"),),
            effects=(),
            condition=None,
        )
        
        pay_cost(state, engine, ability, ability.costs[0])
        
        assert state.cards[1].exerted is True


class TestInkCost:
    """Test ink cost (exert inkwell) validation and payment."""
    
    def test_ink_cost_payable_with_available_ink(self):
        """Ink cost should be payable when player has ready ink."""
        state = GameState(
            players=[PlayerState(), PlayerState()],
            cards={
                1: CardInstance(instance_id=1, card_id="ink1", owner=0, controller=0),
                2: CardInstance(instance_id=2, card_id="ink2", owner=0, controller=0),
            },
        )
        state.players[0].inkwell = [1, 2]
        state.cards[1].zone = ZONE_INKWELL
        state.cards[1].exerted = False
        state.cards[2].zone = ZONE_INKWELL
        state.cards[2].exerted = False
        
        engine = MagicMock(spec=GameEngine)
        engine.available_ink.return_value = 2
        
        ability = ActivatedAbility(
            source_instance_id=3,
            source_card_id="test",
            ability_id="ink_ability",
            ability_index=0,
            name="Ink Ability",
            costs=(_make_source_cost("ink", 1),),
            effects=(),
            condition=None,
        )
        
        can_pay, reason = validate_cost_payable(state, engine, ability, ability.costs[0])
        assert can_pay is True
    
    def test_ink_cost_not_payable_with_insufficient_ink(self):
        """Ink cost should NOT be payable when player lacks ready ink."""
        state = GameState(
            players=[PlayerState(), PlayerState()],
            cards={},
        )
        engine = MagicMock(spec=GameEngine)
        engine.available_ink.return_value = 0
        
        ability = ActivatedAbility(
            source_instance_id=3,
            source_card_id="test",
            ability_id="ink_ability",
            ability_index=0,
            name="Ink Ability",
            costs=(_make_source_cost("ink", 2),),
            effects=(),
            condition=None,
        )
        
        can_pay, reason = validate_cost_payable(state, engine, ability, ability.costs[0])
        assert can_pay is False
    
    def test_ink_cost_payment_exerts_ink(self):
        """Paying ink cost should exert the specified amount of ink cards."""
        state = GameState(
            players=[PlayerState(), PlayerState()],
            cards={
                1: CardInstance(instance_id=1, card_id="ink1", owner=0, controller=0),
                2: CardInstance(instance_id=2, card_id="ink2", owner=0, controller=0),
            },
        )
        state.players[0].inkwell = [1, 2]
        state.cards[1].zone = ZONE_INKWELL
        state.cards[1].exerted = False
        state.cards[2].zone = ZONE_INKWELL
        state.cards[2].exerted = False
        
        engine = MagicMock(spec=GameEngine)
        engine.available_ink.return_value = 2
        
        ability = ActivatedAbility(
            source_instance_id=3,
            source_card_id="test",
            ability_id="ink_ability",
            ability_index=0,
            name="Ink Ability",
            costs=(_make_source_cost("ink", 2),),
            effects=(),
            condition=None,
        )
        
        pay_cost(state, engine, ability, ability.costs[0])
        
        assert state.cards[1].exerted is True
        assert state.cards[2].exerted is True


class TestBanishSelfCost:
    """Test banish self cost validation and payment."""
    
    def test_banish_self_cost_payable_in_play(self):
        """Banish self cost should be payable when source is in play."""
        state = GameState(
            players=[PlayerState(), PlayerState()],
            cards={1: CardInstance(instance_id=1, card_id="test", owner=0, controller=0)},
        )
        state.cards[1].zone = ZONE_PLAY
        
        engine = MagicMock(spec=GameEngine)
        
        ability = ActivatedAbility(
            source_instance_id=1,
            source_card_id="test",
            ability_id="banish_ability",
            ability_index=0,
            name="Banish Self",
            costs=(_make_source_cost("banish_self"),),
            effects=(),
            condition=None,
        )
        
        can_pay, reason = validate_cost_payable(state, engine, ability, ability.costs[0])
        assert can_pay is True
    
    def test_banish_self_cost_not_payable_not_in_play(self):
        """Banish self cost should NOT be payable when source is not in play."""
        state = GameState(
            players=[PlayerState(), PlayerState()],
            cards={1: CardInstance(instance_id=1, card_id="test", owner=0, controller=0)},
        )
        state.cards[1].zone = ZONE_HAND
        
        engine = MagicMock(spec=GameEngine)
        
        ability = ActivatedAbility(
            source_instance_id=1,
            source_card_id="test",
            ability_id="banish_ability",
            ability_index=0,
            name="Banish Self",
            costs=(_make_source_cost("banish_self"),),
            effects=(),
            condition=None,
        )
        
        can_pay, reason = validate_cost_payable(state, engine, ability, ability.costs[0])
        assert can_pay is False
    
    def test_banish_self_cost_moves_to_discard(self):
        """Paying banish self cost should move source to discard."""
        state = GameState(
            players=[PlayerState(), PlayerState()],
            cards={1: CardInstance(instance_id=1, card_id="test", owner=0, controller=0)},
        )
        state.cards[1].zone = ZONE_PLAY
        state.players[0].play = [1]
        
        engine = MagicMock(spec=GameEngine)
        
        ability = ActivatedAbility(
            source_instance_id=1,
            source_card_id="test",
            ability_id="banish_ability",
            ability_index=0,
            name="Banish Self",
            costs=(_make_source_cost("banish_self"),),
            effects=(),
            condition=None,
        )
        
        pay_cost(state, engine, ability, ability.costs[0])
        
        assert state.cards[1].zone == ZONE_DISCARD
        assert 1 not in state.players[0].play


class TestDiscardCost:
    """Test discard N cards cost validation and payment."""
    
    def test_discard_cost_payable_with_sufficient_cards(self):
        """Discard cost should be payable when player has enough cards."""
        state = GameState(
            players=[PlayerState(), PlayerState()],
            cards={
                1: CardInstance(instance_id=1, card_id="hand1", owner=0, controller=0),
                2: CardInstance(instance_id=2, card_id="hand2", owner=0, controller=0),
            },
        )
        state.players[0].hand = [1, 2]
        state.cards[1].zone = ZONE_HAND
        state.cards[2].zone = ZONE_HAND
        
        engine = MagicMock(spec=GameEngine)
        
        ability = ActivatedAbility(
            source_instance_id=3,
            source_card_id="test",
            ability_id="discard_ability",
            ability_index=0,
            name="Discard",
            costs=(_make_source_cost("discard", 1),),
            effects=(),
            condition=None,
        )
        
        can_pay, reason = validate_cost_payable(state, engine, ability, ability.costs[0])
        assert can_pay is True
    
    def test_discard_cost_not_payable_with_insufficient_cards(self):
        """Discard cost should NOT be payable when player lacks cards."""
        state = GameState(
            players=[PlayerState(), PlayerState()],
            cards={},
        )
        state.players[0].hand = []
        
        engine = MagicMock(spec=GameEngine)
        
        ability = ActivatedAbility(
            source_instance_id=3,
            source_card_id="test",
            ability_id="discard_ability",
            ability_index=0,
            name="Discard",
            costs=(_make_source_cost("discard", 2),),
            effects=(),
            condition=None,
        )
        
        can_pay, reason = validate_cost_payable(state, engine, ability, ability.costs[0])
        assert can_pay is False


class TestOncePerTurn:
    """Test once per turn per source restriction."""
    
    def test_can_use_ability_first_time_this_turn(self):
        """Ability should be usable first time this turn."""
        state = GameState(
            players=[PlayerState(), PlayerState()],
            cards={1: CardInstance(instance_id=1, card_id="test", owner=0, controller=0)},
        )
        state.cards[1].zone = ZONE_PLAY
        state.cards[1].used_abilities_this_turn = []
        
        ability = ActivatedAbility(
            source_instance_id=1,
            source_card_id="test",
            ability_id="once_ability",
            ability_index=0,
            name="Once",
            costs=(),
            effects=(),
            condition=None,
        )
        
        assert can_use_ability_this_turn(state, ability) is True
    
    def test_cannot_use_ability_second_time_this_turn(self):
        """Ability should NOT be usable after being used this turn."""
        state = GameState(
            players=[PlayerState(), PlayerState()],
            cards={1: CardInstance(instance_id=1, card_id="test", owner=0, controller=0)},
        )
        state.cards[1].zone = ZONE_PLAY
        state.cards[1].used_abilities_this_turn = ["1:once_ability"]
        
        ability = ActivatedAbility(
            source_instance_id=1,
            source_card_id="test",
            ability_id="once_ability",
            ability_index=0,
            name="Once",
            costs=(),
            effects=(),
            condition=None,
        )
        
        assert can_use_ability_this_turn(state, ability) is False
    
    def test_can_use_different_ability_same_source(self):
        """Different abilities on same source should be independently usable."""
        state = GameState(
            players=[PlayerState(), PlayerState()],
            cards={1: CardInstance(instance_id=1, card_id="test", owner=0, controller=0)},
        )
        state.cards[1].zone = ZONE_PLAY
        state.cards[1].used_abilities_this_turn = ["1:ability_1"]
        
        ability_2 = ActivatedAbility(
            source_instance_id=1,
            source_card_id="test",
            ability_id="ability_2",
            ability_index=1,
            name="Ability 2",
            costs=(),
            effects=(),
            condition=None,
        )
        
        assert can_use_ability_this_turn(state, ability_2) is True


class TestCombinedCosts:
    """Test abilities with multiple costs."""
    
    def test_combined_exert_and_ink_cost(self):
        """Ability with exert + ink costs should require both."""
        state = GameState(
            players=[PlayerState(), PlayerState()],
            cards={
                1: CardInstance(instance_id=1, card_id="source", owner=0, controller=0),
                2: CardInstance(instance_id=2, card_id="ink", owner=0, controller=0),
            },
        )
        state.cards[1].zone = ZONE_PLAY
        state.cards[1].exerted = False
        state.cards[2].zone = ZONE_INKWELL
        state.cards[2].exerted = False
        state.players[0].inkwell = [2]
        
        engine = MagicMock(spec=GameEngine)
        engine.available_ink.return_value = 1
        
        costs = (
            _make_source_cost("exert_source"),
            _make_source_cost("ink", 1),
        )
        
        ability = ActivatedAbility(
            source_instance_id=1,
            source_card_id="test",
            ability_id="combined",
            ability_index=0,
            name="Combined",
            costs=costs,
            effects=(),
            condition=None,
        )
        
        can_pay, payable = validate_ability_costs(state, engine, ability)
        assert can_pay is True
        assert "exert_source" in payable
        assert "ink" in payable
    
    def test_combined_cost_fails_if_one_unpayable(self):
        """Combined cost should fail if any single cost is unpayable."""
        state = GameState(
            players=[PlayerState(), PlayerState()],
            cards={
                1: CardInstance(instance_id=1, card_id="source", owner=0, controller=0),
            },
        )
        state.cards[1].zone = ZONE_PLAY
        state.cards[1].exerted = True  # Source already exerted
        
        engine = MagicMock(spec=GameEngine)
        
        costs = (
            _make_source_cost("exert_source"),  # Can't pay - source exerted
            _make_source_cost("ink", 1),
        )
        
        ability = ActivatedAbility(
            source_instance_id=1,
            source_card_id="test",
            ability_id="combined",
            ability_index=0,
            name="Combined",
            costs=costs,
            effects=(),
            condition=None,
        )
        
        can_pay, payable = validate_ability_costs(state, engine, ability)
        assert can_pay is False
        assert len(payable) == 0  # No costs paid on failure