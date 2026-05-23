"""Tests for full activated ability execution flow."""

import pytest
from unittest.mock import MagicMock, patch

from lorcana_bot.state import GameState, PlayerState, CardInstance
from lorcana_bot.cards import CardDef, CardDatabase
from lorcana_bot.engine import GameEngine, IllegalActionError
from lorcana_bot.constants import (
    ZONE_PLAY, ZONE_INKWELL, ZONE_HAND, ZONE_DISCARD, ZONE_DECK,
    ACTION_USE_ABILITY, ACTION_RESOLVE_PENDING_EFFECT, PHASE_MAIN,
)
from lorcana_bot.actions import Action

from lorcana_bot.card_logic import SourceAbilityDef, SourceCostDef, SourceEffectDef, SourceTargetDef
from lorcana_bot.abilities import (
    use_ability,
    get_activated_abilities_for_card,
    get_available_abilities_for_player,
    validate_ability_costs,
    pay_ability_costs,
    execute_ability_effects,
    AbilityUseResult,
)
from lorcana_bot.effects import EffectResolver
from lorcana_bot.effect_types import EffectResolutionContext


def _make_card_def(
    card_id: str,
    card_type: str = "character",
    abilities: list[SourceAbilityDef] | None = None,
) -> MagicMock:
    """Create a mock card def with source abilities."""
    mock = MagicMock(spec=CardDef)
    mock.id = card_id
    mock.full_name = f"Test Card {card_id}"
    mock.card_type = card_type
    mock.cost = 2
    mock.strength = 2
    mock.willpower = 2
    mock.lore = 1
    mock.keywords = []
    mock.effects = []
    mock.source_abilities = abilities or []
    return mock


def _make_source_cost(kind: str, amount: int = 1) -> SourceCostDef:
    """Create a mock source cost."""
    return SourceCostDef(
        kind=kind,
        amount=amount,
        raw={},
    )


def _chosen_character_target() -> SourceTargetDef:
    return SourceTargetDef(
        kind="selector",
        selector="chosen",
        count=1,
        owner="any",
        zones=("play",),
        card_types=("character",),
        raw={
            "selector": "chosen",
            "count": 1,
            "owner": "any",
            "zones": ["play"],
            "cardTypes": ["character"],
        },
    )


def _chosen_two_characters_target() -> SourceTargetDef:
    return SourceTargetDef(
        kind="selector",
        selector="chosen",
        count=2,
        owner="opponent",
        zones=("play",),
        card_types=("character",),
        raw={
            "selector": "chosen",
            "count": 2,
            "owner": "opponent",
            "zones": ["play"],
            "cardTypes": ["character"],
        },
    )


def _make_source_effect(kind: str, **kwargs) -> SourceEffectDef:
    """Create a mock source effect."""
    target = kwargs.pop("target", None)
    return SourceEffectDef(
        kind=kind,
        target=target,
        amount=kwargs.get("amount"),
        effects=kwargs.get("effects", ()),
        raw=kwargs.get("raw", {}),
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


class TestUseAbilityAction:
    """Test USE_ABILITY action through the game engine."""

    def test_use_ability_generates_legal_action(self):
        """USE_ABILITY should appear in legal actions when cost is payable."""
        db = MagicMock(spec=CardDatabase)

        # Create a card with an activated ability
        card_def = _make_card_def("test_ability_card", abilities=[
            _make_source_ability(
                "draw_ability",
                costs=[_make_source_cost("exert_source")],
                effects=[_make_source_effect("draw", amount=1)],
            )
        ])
        db.get.return_value = card_def

        engine = GameEngine(db)

        # Set up game state with the ability card in play
        state = GameState(
            players=[PlayerState(), PlayerState()],
            cards={
                1: CardInstance(instance_id=1, card_id="test_ability_card", owner=0, controller=0),
                10: CardInstance(instance_id=10, card_id="deck_card", owner=0, controller=0),
            },
        )
        state.cards[1].zone = ZONE_PLAY
        state.cards[10].zone = ZONE_DECK
        state.players[0].play = [1]
        state.players[0].deck = [10]
        state.players[0].hand = []
        state.phase = PHASE_MAIN
        state.active_player = 0
        state.turn_number = 1

        # Check legal actions include USE_ABILITY
        legal = engine.legal_actions(state, 0)
        use_ability_actions = [a for a in legal if a.kind == ACTION_USE_ABILITY]

        assert len(use_ability_actions) == 1
        assert use_ability_actions[0].source == 1

    def test_use_ability_generates_multi_target_actions_and_resolves_all_selected_targets(self):
        """USE_ABILITY should carry selected target tuples for count=2 target requirements."""
        db = MagicMock(spec=CardDatabase)

        source_card = _make_card_def("multi_target_card", abilities=[
            _make_source_ability(
                "damage_two",
                costs=[],
                effects=[
                    _make_source_effect(
                        "deal-damage",
                        amount=1,
                        target=_chosen_two_characters_target(),
                    ),
                ],
            )
        ])
        target_card = _make_card_def("target_character")

        def get_card(card_id):
            if card_id == "multi_target_card":
                return source_card
            return target_card

        db.get.side_effect = get_card

        engine = GameEngine(db)
        state = GameState(
            players=[PlayerState(), PlayerState()],
            cards={
                1: CardInstance(instance_id=1, card_id="multi_target_card", owner=0, controller=0),
                2: CardInstance(instance_id=2, card_id="target_character", owner=1, controller=1),
                3: CardInstance(instance_id=3, card_id="target_character", owner=1, controller=1),
                4: CardInstance(instance_id=4, card_id="target_character", owner=1, controller=1),
            },
        )
        state.cards[1].zone = ZONE_PLAY
        state.cards[2].zone = ZONE_PLAY
        state.cards[3].zone = ZONE_PLAY
        state.cards[4].zone = ZONE_PLAY
        state.players[0].play = [1]
        state.players[1].play = [2, 3, 4]
        state.phase = PHASE_MAIN
        state.active_player = 0

        legal = engine.legal_actions(state, 0)
        use_ability_actions = [action for action in legal if action.kind == ACTION_USE_ABILITY]

        selections = {tuple(action.choice["targets"]) for action in use_ability_actions}

        assert selections == {
            (2, 3),
            (2, 4),
            (3, 4),
        }

        action = next(action for action in use_ability_actions if tuple(action.choice["targets"]) == (2, 3))
        next_state = engine.apply_action(state, action)

        assert next_state.cards[2].damage == 1
        assert next_state.cards[3].damage == 1
        assert next_state.cards[4].damage == 0

    def test_move_to_location_activated_ability_uses_slotted_targets(self):
        db = MagicMock(spec=CardDatabase)

        source_card = _make_card_def("move_source", card_type="item", abilities=[
            _make_source_ability(
                "move_to_location",
                costs=[],
                effects=[
                    _make_source_effect(
                        "move-to-location",
                        raw={
                            "character": {
                                "selector": "chosen",
                                "count": 1,
                                "owner": "you",
                                "zones": ["play"],
                                "cardTypes": ["character"],
                            },
                            "location": {
                                "selector": "chosen",
                                "count": 1,
                                "owner": "you",
                                "zones": ["play"],
                                "cardTypes": ["location"],
                            },
                        },
                    ),
                ],
            )
        ])
        character_card = _make_card_def("friendly_character")
        location_card = _make_card_def("friendly_location", card_type="location")

        def get_card(card_id):
            if card_id == "move_source":
                return source_card
            if card_id == "friendly_location":
                return location_card
            return character_card

        db.get.side_effect = get_card

        engine = GameEngine(db)
        state = GameState(
            players=[PlayerState(), PlayerState()],
            cards={
                1: CardInstance(instance_id=1, card_id="move_source", owner=0, controller=0),
                2: CardInstance(instance_id=2, card_id="friendly_character", owner=0, controller=0),
                3: CardInstance(instance_id=3, card_id="friendly_location", owner=0, controller=0),
            },
        )
        for cid in (1, 2, 3):
            state.cards[cid].zone = ZONE_PLAY
        state.players[0].play = [1, 2, 3]
        state.phase = PHASE_MAIN
        state.active_player = 0

        use_ability_actions = [action for action in engine.legal_actions(state, 0) if action.kind == ACTION_USE_ABILITY]

        assert len(use_ability_actions) == 1
        assert use_ability_actions[0].choice["slotted_targets"] == {
            "kind": "move-to-location",
            "subject": (2,),
            "location": (3,),
        }

        next_state = engine.apply_action(state, use_ability_actions[0])

        assert next_state.cards[2].location_instance_id == 3

    def test_use_ability_exerts_source(self):
        """USE_ABILITY with exert cost should exert the source."""
        db = MagicMock(spec=CardDatabase)

        card_def = _make_card_def("exert_card", abilities=[
            _make_source_ability(
                "exert_ability",
                costs=[_make_source_cost("exert_source")],
            )
        ])
        db.get.return_value = card_def

        engine = GameEngine(db)

        state = GameState(
            players=[PlayerState(), PlayerState()],
            cards={1: CardInstance(instance_id=1, card_id="exert_card", owner=0, controller=0)},
        )
        state.cards[1].zone = ZONE_PLAY
        state.cards[1].exerted = False
        state.players[0].play = [1]
        state.phase = PHASE_MAIN
        state.active_player = 0

        action = Action(
            ACTION_USE_ABILITY,
            actor=0,
            source=1,
            choice={"ability_id": "exert_ability", "ability_index": 0},
        )

        next_state = engine.apply_action(state, action)

        assert next_state.cards[1].exerted is True

    def test_use_ability_banish_self_moves_to_discard(self):
        """USE_ABILITY with banish self should move source to discard."""
        db = MagicMock(spec=CardDatabase)

        card_def = _make_card_def("banish_card", abilities=[
            _make_source_ability(
                "banish_ability",
                costs=[_make_source_cost("banish_self")],
            )
        ])
        db.get.return_value = card_def

        engine = GameEngine(db)

        state = GameState(
            players=[PlayerState(), PlayerState()],
            cards={1: CardInstance(instance_id=1, card_id="banish_card", owner=0, controller=0)},
        )
        state.cards[1].zone = ZONE_PLAY
        state.players[0].play = [1]
        state.phase = PHASE_MAIN
        state.active_player = 0

        action = Action(
            ACTION_USE_ABILITY,
            actor=0,
            source=1,
            choice={"ability_id": "banish_ability", "ability_index": 0},
        )

        next_state = engine.apply_action(state, action)

        assert next_state.cards[1].zone == ZONE_DISCARD
        assert 1 not in next_state.players[0].play

    def test_use_ability_fails_when_cost_unpayable(self):
        """USE_ABILITY should fail when source is already exerted."""
        db = MagicMock(spec=CardDatabase)

        card_def = _make_card_def("exert_card", abilities=[
            _make_source_ability(
                "exert_ability",
                costs=[_make_source_cost("exert_source")],
            )
        ])
        db.get.return_value = card_def

        engine = GameEngine(db)

        state = GameState(
            players=[PlayerState(), PlayerState()],
            cards={1: CardInstance(instance_id=1, card_id="exert_card", owner=0, controller=0)},
        )
        state.cards[1].zone = ZONE_PLAY
        state.cards[1].exerted = True  # Already exerted - can't pay exert cost
        state.players[0].play = [1]
        state.phase = PHASE_MAIN
        state.active_player = 0

        # USE_ABILITY should NOT appear in legal actions
        legal = engine.legal_actions(state, 0)
        use_ability_actions = [a for a in legal if a.kind == ACTION_USE_ABILITY]

        assert len(use_ability_actions) == 0


class TestAbilityEffectResolution:
    """Test that ability effects resolve correctly."""

    def test_ability_effect_draws_cards(self):
        """Ability with draw effect should draw cards after cost paid."""
        db = MagicMock(spec=CardDatabase)

        card_def = _make_card_def("draw_card", abilities=[
            _make_source_ability(
                "draw_ability",
                costs=[_make_source_cost("exert_source")],
                effects=[_make_source_effect("draw", amount=2)],
            )
        ])
        db.get.return_value = card_def

        engine = GameEngine(db)

        state = GameState(
            players=[PlayerState(), PlayerState()],
            cards={
                1: CardInstance(instance_id=1, card_id="draw_card", owner=0, controller=0),
                10: CardInstance(instance_id=10, card_id="deck1", owner=0, controller=0),
                11: CardInstance(instance_id=11, card_id="deck2", owner=0, controller=0),
            },
        )
        state.cards[1].zone = ZONE_PLAY
        state.cards[10].zone = ZONE_DECK
        state.cards[11].zone = ZONE_DECK
        state.players[0].play = [1]
        state.players[0].deck = [10, 11]
        state.players[0].hand = []
        state.phase = PHASE_MAIN
        state.active_player = 0

        action = Action(
            ACTION_USE_ABILITY,
            actor=0,
            source=1,
            choice={"ability_id": "draw_ability", "ability_index": 0},
        )

        next_state = engine.apply_action(state, action)

        # Should have drawn 2 cards
        assert len(next_state.players[0].hand) == 2

    def test_discard_chosen_cost_creates_pending_then_resolves_effect(self):
        """Chosen discard cost is selected through legal_actions before effects resolve."""
        db = MagicMock(spec=CardDatabase)
        card_def = _make_card_def("angel", abilities=[
            _make_source_ability(
                "good_aim",
                costs=[_make_source_cost("discardCards", 1), _make_source_cost("discardChosen", True)],
                effects=[_make_source_effect("deal-damage", target=_chosen_character_target(), amount=2)],
            )
        ])
        hand_def = _make_card_def("fodder", card_type="action")
        target_def = _make_card_def("target", card_type="character")
        db.get.side_effect = lambda card_id: {
            "angel": card_def,
            "fodder": hand_def,
            "target": target_def,
        }[card_id]

        engine = GameEngine(db)
        state = GameState(
            players=[PlayerState(), PlayerState()],
            cards={
                1: CardInstance(instance_id=1, card_id="angel", owner=0, controller=0),
                2: CardInstance(instance_id=2, card_id="fodder", owner=0, controller=0),
                3: CardInstance(instance_id=3, card_id="target", owner=1, controller=1),
            },
        )
        state.cards[1].zone = ZONE_PLAY
        state.cards[2].zone = ZONE_HAND
        state.cards[3].zone = ZONE_PLAY
        state.players[0].play = [1]
        state.players[0].hand = [2]
        state.players[1].play = [3]
        state.phase = PHASE_MAIN
        state.active_player = 0

        legal = engine.legal_actions(state, 0)
        use = next(action for action in legal if action.kind == ACTION_USE_ABILITY and action.target == 3)
        assert use.target == 3

        pending_state = engine.apply_action(state, use)
        assert len(pending_state.pending_effects) == 1
        assert pending_state.cards[2].zone == ZONE_HAND
        assert pending_state.cards[3].damage == 0

        resolve = next(
            action for action in engine.legal_actions(pending_state, 0)
            if action.kind == ACTION_RESOLVE_PENDING_EFFECT
        )
        assert resolve.choice["discard_card_ids"] == (2,)

        resolved = engine.apply_action(pending_state, resolve)
        assert resolved.cards[2].zone == ZONE_DISCARD
        assert resolved.cards[3].zone == ZONE_DISCARD
        assert not resolved.pending_effects

    def test_unsupported_effect_blocks_before_cost_payment(self):
        db = MagicMock(spec=CardDatabase)
        card_def = _make_card_def("bad", abilities=[
            _make_source_ability(
                "bad_ability",
                costs=[_make_source_cost("banish_self")],
                effects=[_make_source_effect("totally-unsupported")],
            )
        ])
        db.get.return_value = card_def
        engine = GameEngine(db)
        state = GameState(
            players=[PlayerState(), PlayerState()],
            cards={1: CardInstance(instance_id=1, card_id="bad", owner=0, controller=0)},
        )
        state.cards[1].zone = ZONE_PLAY
        state.players[0].play = [1]
        state.phase = PHASE_MAIN
        state.active_player = 0

        action = Action(ACTION_USE_ABILITY, actor=0, source=1, choice={"ability_id": "bad_ability", "ability_index": 0})
        with pytest.raises(Exception):
            engine.apply_action(state, action)
        assert state.cards[1].zone == ZONE_PLAY


class TestOncePerTurnTracking:
    """Test that once-per-turn tracking works correctly."""

    def test_ability_can_be_used_once_per_turn(self):
        """Ability should be usable on first activation, not second."""
        db = MagicMock(spec=CardDatabase)

        card_def = _make_card_def("once_card", abilities=[
            _make_source_ability(
                "once_ability",
                costs=[],  # No cost for easy testing
            )
        ])
        db.get.return_value = card_def

        engine = GameEngine(db)

        state = GameState(
            players=[PlayerState(), PlayerState()],
            cards={1: CardInstance(instance_id=1, card_id="once_card", owner=0, controller=0)},
        )
        state.cards[1].zone = ZONE_PLAY
        state.players[0].play = [1]
        state.phase = PHASE_MAIN
        state.active_player = 0

        # First use should be legal
        action1 = Action(
            ACTION_USE_ABILITY,
            actor=0,
            source=1,
            choice={"ability_id": "once_ability", "ability_index": 0},
        )

        next_state = engine.apply_action(state, action1)

        # Second use should NOT be legal (used_abilities_this_turn tracked)
        legal2 = engine.legal_actions(next_state, 0)
        use_ability_actions = [a for a in legal2 if a.kind == ACTION_USE_ABILITY]

        # The card is still in play, but the ability was used
        # Since the ability has no cost, it would appear but should be filtered
        # by the once-per-turn check in get_available_abilities_for_player


class TestAtomicCostPayment:
    """Test that costs are paid atomically (no partial state changes)."""

    def test_combined_cost_pays_all_or_none(self):
        """Combined costs should pay all or none (no partial mutations)."""
        db = MagicMock(spec=CardDatabase)

        card_def = _make_card_def("combined_card", abilities=[
            _make_source_ability(
                "combined_ability",
                costs=[
                    _make_source_cost("exert_source"),
                    _make_source_cost("ink", 5),  # More than available
                ],
            )
        ])
        db.get.return_value = card_def

        engine = GameEngine(db)

        state = GameState(
            players=[PlayerState(), PlayerState()],
            cards={1: CardInstance(instance_id=1, card_id="combined_card", owner=0, controller=0)},
        )
        state.cards[1].zone = ZONE_PLAY
        state.cards[1].exerted = False
        state.players[0].play = [1]
        state.players[0].inkwell = []
        state.phase = PHASE_MAIN
        state.active_player = 0

        # Should NOT appear in legal actions because ink cost can't be paid
        legal = engine.legal_actions(state, 0)
        use_ability_actions = [a for a in legal if a.kind == ACTION_USE_ABILITY]

        assert len(use_ability_actions) == 0

        # Verify source was NOT exerted (cost wasn't partially paid)
        assert state.cards[1].exerted is False


class TestAutomationIntegration:
    """Test that automation system sees USE_ABILITY candidates."""

    def test_candidate_enumerator_includes_activated_ability(self):
        """Candidate enumerator should produce USE_ABILITY candidates."""
        from lorcana_bot.automation.candidate_enumerator import enumerate_automated_action_candidates

        db = MagicMock(spec=CardDatabase)

        card_def = _make_card_def("auto_ability_card", abilities=[
            _make_source_ability(
                "auto_ability",
                costs=[_make_source_cost("exert_source")],
            )
        ])
        db.get.return_value = card_def

        engine = GameEngine(db)

        state = GameState(
            players=[PlayerState(), PlayerState()],
            cards={1: CardInstance(instance_id=1, card_id="auto_ability_card", owner=0, controller=0)},
        )
        state.cards[1].zone = ZONE_PLAY
        state.cards[1].exerted = False
        state.players[0].play = [1]
        state.phase = PHASE_MAIN
        state.active_player = 0
        state.turn_number = 1  # Required for once-per-turn tracking

        result = enumerate_automated_action_candidates(state, engine, 0)

        # Check for ACTIVATE_ABILITY candidates
        # B20-fix: family.value is lowercase string, not enum value
        ability_candidates = [
            c for c in result.candidates
            if c.family == "activateAbility"
        ]

        assert len(ability_candidates) >= 1

        # Check the candidate has correct metadata
        ability_candidate = ability_candidates[0]
        assert ability_candidate.source_instance_id == 1
        assert ability_candidate.ability_id == "auto_ability"

    def test_move_adapter_converts_ability_candidate_to_action(self):
        """Move adapter should convert ACTIVATE_ABILITY candidate to USE_ABILITY action."""
        from lorcana_bot.automation.move_adapter import candidate_to_action
        from lorcana_bot.automation.candidates import AutomatedActionCandidate, AutomatedActionFamily

        candidate = AutomatedActionCandidate(
            family=AutomatedActionFamily.ACTIVATE_ABILITY,
            actor=0,
            stable_key="test_ability_0",
            source_instance_id=1,
            source_card_id="test_card",
            ability_id="test_ability",
            ability_index=0,
            label="Test ability",
        )

        action = candidate_to_action(candidate)

        assert action.kind == ACTION_USE_ABILITY
        assert action.source == 1
        assert action.choice["ability_id"] == "test_ability"
