"""Tests for ability cost validation and payment."""

import pytest
from unittest.mock import MagicMock

from lorcana_bot.state import GameState, PlayerState, CardInstance
from lorcana_bot.cards import CardDef
from lorcana_bot.engine import GameEngine
from lorcana_bot.cards import CardDatabase
from lorcana_bot.constants import (
    EVENT_CARD_DISCARDED,
    EVENT_CARD_EXERTED,
    EVENT_CHARACTER_BANISHED,
    ZONE_PLAY,
    ZONE_INKWELL,
    ZONE_HAND,
    ZONE_DISCARD,
)

from lorcana_bot.card_logic import SourceAbilityDef, SourceTriggerDef, SourceCostDef, SourceEffectDef
from lorcana_bot.abilities import (
    get_activated_abilities_for_card,
    can_use_ability_this_turn,
    validate_ability_costs,
    pay_ability_costs,
    use_ability,
    AbilityCostError,
    ActivatedAbility,
)
from lorcana_bot.costs import (
    validate_cost_payable,
    pay_cost,
    pay_all_costs,
    CostPaymentError,
)


def _make_card_def(card_id: str, abilities: list[SourceAbilityDef] | None = None) -> MagicMock:
    """Create a mock card def with source abilities."""
    mock = MagicMock(spec=CardDef)
    mock.id = card_id
    mock.full_name = f"Test Card {card_id}"
    mock.card_type = "character"
    mock.source_abilities = abilities or []
    return mock


def _eventful_cost_engine() -> GameEngine:
    return GameEngine(
        CardDatabase(
            [
                CardDef("test", "Test Card test", "amber", 1, True, "character", 1, 1, 1),
                CardDef("hand1", "Hand One", "amber", 1, True, "action"),
                CardDef("hand2", "Hand Two", "amber", 1, True, "action"),
            ]
        )
    )


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

        engine = _eventful_cost_engine()

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
        event = next(event for event in reversed(state.event_log) if event.event_type == EVENT_CARD_EXERTED)
        assert event.payload["subject_card_id"] == 1
        assert event.payload["reason"] == "ability_cost"


class TestInkCost:
    """Test ink cost (exert inkwell) validation and payment."""

    def test_ink_cost_payable_with_available_ink(self):
        """Ink cost should be payable when player has ready ink."""
        state = GameState(
            players=[PlayerState(), PlayerState()],
            cards={
                1: CardInstance(instance_id=1, card_id="ink1", owner=0, controller=0),
                2: CardInstance(instance_id=2, card_id="ink2", owner=0, controller=0),
                # B15-fix: source_instance_id=3 must exist in state.cards for _pay_ink_cost
                3: CardInstance(instance_id=3, card_id="test", owner=0, controller=0),
            },
        )
        state.players[0].inkwell = [1, 2]
        state.cards[1].zone = ZONE_INKWELL
        state.cards[1].exerted = False
        state.cards[2].zone = ZONE_INKWELL
        state.cards[2].exerted = False
        state.cards[3].zone = ZONE_PLAY

        engine = MagicMock(spec=GameEngine)
        engine.available_ink.return_value = 2
        engine._exert_eventful.side_effect = (
            lambda state_arg, card_id, **kwargs: setattr(state_arg.cards[card_id], "exerted", True)
        )

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
            cards={
                3: CardInstance(instance_id=3, card_id="test", owner=0, controller=0),
            },
        )
        state.cards[3].zone = ZONE_PLAY
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
                3: CardInstance(instance_id=3, card_id="test", owner=0, controller=0),
            },
        )
        state.players[0].inkwell = [1, 2]
        state.cards[1].zone = ZONE_INKWELL
        state.cards[1].exerted = False
        state.cards[2].zone = ZONE_INKWELL
        state.cards[2].exerted = False
        state.cards[3].zone = ZONE_PLAY

        engine = MagicMock(spec=GameEngine)
        engine.available_ink.return_value = 2
        engine._exert_eventful.side_effect = (
            lambda state_arg, card_id, **kwargs: setattr(state_arg.cards[card_id], "exerted", True)
        )

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

        engine = _eventful_cost_engine()

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
        event = next(event for event in reversed(state.event_log) if event.event_type == EVENT_CHARACTER_BANISHED)
        assert event.payload["subject_card_id"] == 1
        assert event.payload["from_zone"] == ZONE_PLAY
        assert event.payload["to_zone"] == ZONE_DISCARD
        assert event.payload["reason"] == "ability_cost"


class TestDiscardCost:
    """Test discard N cards cost validation and payment."""

    def test_discard_cost_requires_choice_prompt(self):
        """Discard cost is payable only through the pending choice path."""
        state = GameState(
            players=[PlayerState(), PlayerState()],
            cards={
                1: CardInstance(instance_id=1, card_id="hand1", owner=0, controller=0),
                2: CardInstance(instance_id=2, card_id="hand2", owner=0, controller=0),
                3: CardInstance(instance_id=3, card_id="test", owner=0, controller=0),
            },
        )
        state.players[0].hand = [1, 2]
        state.cards[1].zone = ZONE_HAND
        state.cards[2].zone = ZONE_HAND
        state.cards[3].zone = ZONE_PLAY

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
        assert reason == ""

    def test_random_discard_cost_payable_with_sufficient_cards(self):
        """Random discard cost is payable when player has enough cards."""
        state = GameState(
            players=[PlayerState(), PlayerState()],
            cards={
                1: CardInstance(instance_id=1, card_id="hand1", owner=0, controller=0),
                2: CardInstance(instance_id=2, card_id="hand2", owner=0, controller=0),
                3: CardInstance(instance_id=3, card_id="test", owner=0, controller=0),
            },
        )
        state.players[0].hand = [1, 2]
        state.cards[1].zone = ZONE_HAND
        state.cards[2].zone = ZONE_HAND
        state.cards[3].zone = ZONE_PLAY

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
            raw={"random_discard": True},  # B15: Marked as explicitly random
        )

        can_pay, reason = validate_cost_payable(state, engine, ability, ability.costs[0])
        assert can_pay is True

    def test_random_discard_cost_payment_emits_discard_event(self, monkeypatch):
        """Random discard cost should discard through the engine event helper."""
        state = GameState(
            players=[PlayerState(), PlayerState()],
            cards={
                1: CardInstance(instance_id=1, card_id="hand1", owner=0, controller=0),
                2: CardInstance(instance_id=2, card_id="hand2", owner=0, controller=0),
                3: CardInstance(instance_id=3, card_id="test", owner=0, controller=0),
            },
        )
        state.players[0].hand = [1, 2]
        state.cards[1].zone = ZONE_HAND
        state.cards[2].zone = ZONE_HAND
        state.cards[3].zone = ZONE_PLAY
        state.players[0].play = [3]

        engine = _eventful_cost_engine()
        ability = ActivatedAbility(
            source_instance_id=3,
            source_card_id="test",
            ability_id="discard_ability",
            ability_index=0,
            name="Discard",
            costs=(_make_source_cost("discard", 1),),
            effects=(),
            condition=None,
            raw={"random_discard": True},
        )

        monkeypatch.setattr("lorcana_bot.costs.random.randrange", lambda _: 0)
        pay_cost(state, engine, ability, ability.costs[0])

        assert 1 in state.players[0].discard
        event = next(event for event in reversed(state.event_log) if event.event_type == EVENT_CARD_DISCARDED)
        assert event.payload["subject_card_id"] == 1
        assert event.payload["source_card_id"] == 3
        assert event.payload["reason"] == "ability_cost"
    def test_non_random_discard_direct_pay_cost_requires_pending_choice(self):
        """Direct pay_cost must not randomly discard non-random discard costs."""
        state = GameState(
            players=[PlayerState(), PlayerState()],
            cards={
                1: CardInstance(instance_id=1, card_id="hand1", owner=0, controller=0),
                2: CardInstance(instance_id=2, card_id="hand2", owner=0, controller=0),
                3: CardInstance(instance_id=3, card_id="test", owner=0, controller=0),
            },
        )
        state.players[0].hand = [1, 2]
        state.cards[1].zone = ZONE_HAND
        state.cards[2].zone = ZONE_HAND
        state.cards[3].zone = ZONE_PLAY

        engine = _eventful_cost_engine()
        ability = ActivatedAbility(
            source_instance_id=3,
            source_card_id="test",
            ability_id="discard_ability",
            ability_index=0,
            name="Discard",
            costs=(_make_source_cost("discard", 1),),
            effects=(),
            condition=None,
            raw={},  # non-random discard
        )

        with pytest.raises(CostPaymentError, match="pending discard choice"):
            pay_cost(state, engine, ability, ability.costs[0])

        assert state.players[0].hand == [1, 2]
        assert state.cards[1].zone == ZONE_HAND
        assert state.cards[2].zone == ZONE_HAND
        assert not any(event.event_type == EVENT_CARD_DISCARDED for event in state.event_log)

    def test_non_random_discard_pay_all_costs_fails_before_partial_payment(self):
        """pay_all_costs must fail before paying earlier costs when discard needs choice."""
        state = GameState(
            players=[PlayerState(), PlayerState()],
            cards={
                1: CardInstance(instance_id=1, card_id="hand1", owner=0, controller=0),
                2: CardInstance(instance_id=2, card_id="test", owner=0, controller=0),
            },
        )
        state.players[0].hand = [1]
        state.cards[1].zone = ZONE_HAND
        state.cards[2].zone = ZONE_PLAY
        state.cards[2].exerted = False

        engine = _eventful_cost_engine()
        ability = ActivatedAbility(
            source_instance_id=2,
            source_card_id="test",
            ability_id="combined_discard",
            ability_index=0,
            name="Combined Discard",
            costs=(
                _make_source_cost("exert_source"),
                _make_source_cost("discard", 1),
            ),
            effects=(),
            condition=None,
            raw={},  # non-random discard
        )

        with pytest.raises(CostPaymentError, match="pending discard choice"):
            pay_all_costs(state, engine, ability)

        assert state.cards[2].exerted is False
        assert state.players[0].hand == [1]
        assert state.cards[1].zone == ZONE_HAND

    def test_non_random_discard_pay_ability_costs_fails_before_partial_payment(self):
        """pay_ability_costs must fail before any direct payment for non-random discard."""
        state = GameState(
            players=[PlayerState(), PlayerState()],
            cards={
                1: CardInstance(instance_id=1, card_id="hand1", owner=0, controller=0),
                2: CardInstance(instance_id=2, card_id="test", owner=0, controller=0),
            },
        )
        state.players[0].hand = [1]
        state.cards[1].zone = ZONE_HAND
        state.cards[2].zone = ZONE_PLAY
        state.cards[2].exerted = False

        engine = _eventful_cost_engine()
        ability = ActivatedAbility(
            source_instance_id=2,
            source_card_id="test",
            ability_id="ability_costs_discard",
            ability_index=0,
            name="Ability Costs Discard",
            costs=(
                _make_source_cost("exert_source"),
                _make_source_cost("discard", 1),
            ),
            effects=(),
            condition=None,
            raw={},  # non-random discard
        )

        with pytest.raises(AbilityCostError, match="pending discard choice"):
            pay_ability_costs(state, engine, ability)

        assert state.cards[2].exerted is False
        assert state.players[0].hand == [1]
        assert state.cards[1].zone == ZONE_HAND
        assert ability.unique_use_key not in state.cards[2].used_abilities_this_turn

    def test_non_random_discard_use_ability_returns_failure_without_payment(self):
        """Direct use_ability must fail cleanly and not mutate state for non-random discard."""
        state = GameState(
            players=[PlayerState(), PlayerState()],
            cards={
                1: CardInstance(instance_id=1, card_id="hand1", owner=0, controller=0),
                2: CardInstance(instance_id=2, card_id="test", owner=0, controller=0),
            },
        )
        state.players[0].hand = [1]
        state.cards[1].zone = ZONE_HAND
        state.cards[2].zone = ZONE_PLAY
        state.cards[2].exerted = False

        engine = _eventful_cost_engine()
        ability = ActivatedAbility(
            source_instance_id=2,
            source_card_id="test",
            ability_id="use_ability_discard",
            ability_index=0,
            name="Use Ability Discard",
            costs=(
                _make_source_cost("exert_source"),
                _make_source_cost("discard", 1),
            ),
            effects=(),
            condition=None,
            raw={},  # non-random discard
        )

        result = use_ability(state, engine, ability)

        assert result.success is False
        assert result.error_message is not None
        assert "pending discard choice" in result.error_message
        assert state.cards[2].exerted is False
        assert state.players[0].hand == [1]
        assert state.cards[1].zone == ZONE_HAND
        assert ability.unique_use_key not in state.cards[2].used_abilities_this_turn

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
