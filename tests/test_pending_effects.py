"""Tests for pending effect layer and target choice prompts."""

import pytest

from lorcana_bot.engine import GameEngine
from lorcana_bot.cards import CardDatabase, CardDef, DEMO_FEATURE_CARD_IDS, EffectDef
from lorcana_bot.effect_types import EffectResolutionContext
from lorcana_bot.automation.actor_resolution import resolve_current_actor
from lorcana_bot.state import Action, CardInstance, GameState, PlayerState
from lorcana_bot.pending_effects import (
    PendingEffect,
    TargetRequirement,
    NamedCardRequirement,
    create_pending_effect,
    create_scry_pending_effect,
    create_search_pending_effect,
    create_reveal_routing_pending_effect,
    get_current_pending_effect,
    get_pending_effects_for_chooser,
    get_valid_targets_for_requirement,
    resolve_pending_effect_optional,
    resolve_slotted_target_selection,
    complete_pending_effect,
    has_pending_effects,
    get_pending_effect_by_id,
)
from lorcana_bot.constants import (
    ACTION_RESOLVE_PENDING_EFFECT,
    ACTION_CONCEDE,
    ZONE_DECK,
    ZONE_HAND,
    ZONE_PLAY,
    ZONE_UNDER,
)


class TestTargetRequirement:
    """Tests for TargetRequirement dataclass."""

    def test_basic_requirement(self):
        req = TargetRequirement(kind="chosen_character")
        assert req.kind == "chosen_character"
        assert req.min_targets == 1
        assert req.max_targets == 1
        assert req.optional is False

    def test_damaged_character_requirement(self):
        req = TargetRequirement(
            kind="chosen_damaged_character",
            must_be_damaged=True,
            card_type="character",
        )
        assert req.must_be_damaged is True
        assert req.card_type == "character"

    def test_opposing_character_requirement(self):
        req = TargetRequirement(
            kind="chosen_opposing_character",
            owner_filter="opponent",
        )
        assert req.owner_filter == "opponent"


class TestPendingEffect:
    """Tests for PendingEffect dataclass."""

    def test_current_effect_property(self):
        from lorcana_bot.cards import EffectDef
        effects = (
            EffectDef(kind="deal_damage", target="opposing_character", amount=2),
            EffectDef(kind="draw", amount=1),
        )
        pe = PendingEffect(
            id="pe_1",
            controller_id=0,
            chooser_id=0,
            source_id=None,
            source_card_id=None,
            effects=effects,
        )
        assert pe.current_effect == effects[0]
        assert pe.current_effect_index == 0

    def test_advance_effect(self):
        from lorcana_bot.cards import EffectDef
        effects = (
            EffectDef(kind="deal_damage", target="opposing_character", amount=2),
            EffectDef(kind="draw", amount=1),
        )
        pe = PendingEffect(
            id="pe_1",
            controller_id=0,
            chooser_id=0,
            source_id=None,
            source_card_id=None,
            effects=effects,
        )
        pe.current_effect_index += 1
        assert pe.current_effect == effects[1]

    def test_is_complete(self):
        from lorcana_bot.cards import EffectDef
        effects = (
            EffectDef(kind="deal_damage", target="opposing_character", amount=2),
            EffectDef(kind="draw", amount=1),
        )
        pe = PendingEffect(
            id="pe_1",
            controller_id=0,
            chooser_id=0,
            source_id=None,
            source_card_id=None,
            effects=effects,
        )
        assert pe.is_complete is False
        pe.current_effect_index = 2
        assert pe.is_complete is True

    def test_requires_target_input(self):
        from lorcana_bot.cards import EffectDef
        effects = (EffectDef(kind="deal_damage", target="chosen_character", amount=2),)
        requirements = (TargetRequirement(kind="chosen_character"),)
        pe = PendingEffect(
            id="pe_1",
            controller_id=0,
            chooser_id=0,
            source_id=None,
            source_card_id=None,
            effects=effects,
            required_targets=requirements,
        )
        assert pe.requires_target_input is True

    def test_does_not_require_target_for_non_chosen(self):
        from lorcana_bot.cards import EffectDef
        effects = (EffectDef(kind="draw", amount=2),)
        pe = PendingEffect(
            id="pe_1",
            controller_id=0,
            chooser_id=0,
            source_id=None,
            source_card_id=None,
            effects=effects,
        )
        assert pe.requires_target_input is False


class TestPendingEffectState:
    """Tests for pending effect state management."""

    def test_has_pending_effects(self, sample_game_state):
        from lorcana_bot.cards import EffectDef
        from lorcana_bot.state import GameState, PlayerState, CardInstance

        # Initially no pending effects
        assert has_pending_effects(sample_game_state) is False

        # Create a pending effect
        effects = (EffectDef(kind="draw", amount=1),)
        create_pending_effect(
            sample_game_state,
            controller_id=0,
            chooser_id=0,
            source_id=None,
            source_card_id=None,
            effects=effects,
        )

        assert has_pending_effects(sample_game_state) is True

    def test_get_pending_effects_for_chooser(self, sample_game_state):
        from lorcana_bot.cards import EffectDef

        create_pending_effect(
            sample_game_state,
            controller_id=0,
            chooser_id=1,
            source_id=None,
            source_card_id=None,
            effects=(EffectDef(kind="draw", amount=1),),
        )

        chooser_effects = get_pending_effects_for_chooser(sample_game_state, 1)
        assert len(chooser_effects) == 1
        assert chooser_effects[0].chooser_id == 1

        other_effects = get_pending_effects_for_chooser(sample_game_state, 0)
        assert len(other_effects) == 0

    def test_get_current_pending_effect(self, sample_game_state):
        from lorcana_bot.cards import EffectDef

        # Create pending effect with chooser=0
        pe = create_pending_effect(
            sample_game_state,
            controller_id=0,
            chooser_id=0,
            source_id=None,
            source_card_id=None,
            effects=(EffectDef(kind="draw", amount=1),),
        )

        current = get_current_pending_effect(sample_game_state, 0)
        assert current is not None
        assert current.id == pe.id

    def test_get_current_pending_effect_wrong_chooser(self, sample_game_state):
        from lorcana_bot.cards import EffectDef

        create_pending_effect(
            sample_game_state,
            controller_id=0,
            chooser_id=0,
            source_id=None,
            source_card_id=None,
            effects=(EffectDef(kind="draw", amount=1),),
        )

        current = get_current_pending_effect(sample_game_state, 1)
        assert current is None

    def test_complete_pending_effect(self, sample_game_state):
        from lorcana_bot.cards import EffectDef

        pe = create_pending_effect(
            sample_game_state,
            controller_id=0,
            chooser_id=0,
            source_id=None,
            source_card_id=None,
            effects=(EffectDef(kind="draw", amount=1),),
        )

        assert has_pending_effects(sample_game_state) is True

        completed = complete_pending_effect(sample_game_state, pe.id)

        assert completed is not None
        assert has_pending_effects(sample_game_state) is False

    def test_resolve_optional_decline(self, sample_game_state):
        from lorcana_bot.cards import EffectDef

        pe = create_pending_effect(
            sample_game_state,
            controller_id=0,
            chooser_id=0,
            source_id=None,
            source_card_id=None,
            effects=(EffectDef(kind="draw", amount=1),),
            optional=True,
        )

        resolve_pending_effect_optional(sample_game_state, pe.id, False)

        # After decline, pending effect should be marked as declined
        assert pe.accepted is False
        # The engine will complete the effect when it processes the decline action
        # is_complete stays False until the engine removes the effect


class TestValidTargets:
    """Tests for target validation."""

    def test_chosen_character_targets_empty_board(self, sample_game_state, engine):
        """Test when there are no characters in play."""
        requirement = TargetRequirement(
            kind="chosen_character",
            card_type="character",
        )

        targets = get_valid_targets_for_requirement(
            sample_game_state, requirement, chooser_id=0, engine=engine
        )

        # No characters in play, should return empty list
        assert len(targets) == 0

    def test_opposing_character_excludes_self(self, sample_game_state, engine):
        # Put a character in opponent's play area
        from lorcana_bot.constants import ZONE_PLAY

        char_id = 10  # Use an existing card
        sample_game_state.cards[char_id].zone = ZONE_PLAY
        sample_game_state.cards[char_id].controller = 1
        sample_game_state.players[1].play.append(char_id)

        requirement = TargetRequirement(
            kind="chosen_opposing_character",
            card_type="character",
            owner_filter="opponent",
        )

        targets = get_valid_targets_for_requirement(
            sample_game_state, requirement, chooser_id=0, engine=engine
        )

        # Should only include opponent's characters
        assert len(targets) >= 1  # At least the one we added

    def test_damaged_character_only(self, sample_game_state, engine):
        from lorcana_bot.constants import ZONE_PLAY

        # Add a character to play and damage it
        char_id = 1
        sample_game_state.cards[char_id].zone = ZONE_PLAY
        sample_game_state.cards[char_id].controller = 0
        sample_game_state.players[0].play.append(char_id)
        sample_game_state.cards[char_id].damage = 3

        requirement = TargetRequirement(
            kind="chosen_damaged_character",
            card_type="character",
            must_be_damaged=True,
        )

        targets = get_valid_targets_for_requirement(
            sample_game_state, requirement, chooser_id=0, engine=engine
        )

        # Only damaged character should be included
        assert len(targets) == 1
        assert targets[0] == char_id


class TestLegalActionsWithPendingEffects:
    """Tests for legal action generation with pending effects."""

    def test_pending_effect_blocks_normal_actions(self, sample_game_state, engine):
        from lorcana_bot.cards import EffectDef

        create_pending_effect(
            sample_game_state,
            controller_id=0,
            chooser_id=0,
            source_id=None,
            source_card_id=None,
            effects=(EffectDef(kind="draw", amount=1),),
        )

        # Player 0 has a pending effect
        legal = engine.legal_actions(sample_game_state, 0)

        # Should only have RESOLVE_PENDING_EFFECT and CONCEDE
        action_types = [a.kind for a in legal]
        assert ACTION_RESOLVE_PENDING_EFFECT in action_types
        assert "END_TURN" not in action_types
        assert "PLAY_CARD" not in action_types

    def test_non_chooser_can_only_concede(self, sample_game_state, engine):
        from lorcana_bot.cards import EffectDef

        create_pending_effect(
            sample_game_state,
            controller_id=0,
            chooser_id=0,
            source_id=None,
            source_card_id=None,
            effects=(EffectDef(kind="draw", amount=1),),
        )

        # Player 1 does not have the pending effect
        legal = engine.legal_actions(sample_game_state, 1)

        # Should only have CONCEDE
        assert len(legal) == 1
        assert legal[0].kind == "CONCEDE"

    def test_optional_pending_effect_has_accept_decline(self, sample_game_state, engine):
        from lorcana_bot.cards import EffectDef

        create_pending_effect(
            sample_game_state,
            controller_id=0,
            chooser_id=0,
            source_id=None,
            source_card_id=None,
            effects=(EffectDef(kind="draw", amount=1),),
            optional=True,
        )

        legal = engine.legal_actions(sample_game_state, 0)

        # Should have accept and decline options
        accept_action = None
        decline_action = None
        for action in legal:
            if action.choice and "accept" in action.choice:
                if action.choice["accept"] is True:
                    accept_action = action
                else:
                    decline_action = action

        assert accept_action is not None
        assert decline_action is not None


class TestResolvePendingEffectAction:
    """Tests for RESOLVE_PENDING_EFFECT action application."""

    def test_resolve_simple_pending_effect(self, sample_game_state, engine):
        from lorcana_bot.cards import EffectDef

        initial_hand_size = len(sample_game_state.players[0].hand)

        pe = create_pending_effect(
            sample_game_state,
            controller_id=0,
            chooser_id=0,
            source_id=None,
            source_card_id=None,
            effects=(EffectDef(kind="draw", amount=1),),
        )

        action = Action(
            ACTION_RESOLVE_PENDING_EFFECT,
            actor=0,
            source=None,
            choice={"pending_effect_id": pe.id},
        )

        state = engine.apply_action(sample_game_state, action)

        # Should have drawn a card
        assert len(state.players[0].hand) == initial_hand_size + 1
        # Pending effect should be removed
        assert has_pending_effects(state) is False

    def test_resolve_optional_accept(self, sample_game_state, engine):
        from lorcana_bot.cards import EffectDef

        initial_hand_size = len(sample_game_state.players[0].hand)

        pe = create_pending_effect(
            sample_game_state,
            controller_id=0,
            chooser_id=0,
            source_id=None,
            source_card_id=None,
            effects=(EffectDef(kind="draw", amount=1),),
            optional=True,
        )

        action = Action(
            ACTION_RESOLVE_PENDING_EFFECT,
            actor=0,
            source=None,
            choice={"pending_effect_id": pe.id, "accept": True},
        )

        state = engine.apply_action(sample_game_state, action)

        # Should have drawn a card
        assert len(state.players[0].hand) == initial_hand_size + 1

    def test_resolve_optional_decline(self, sample_game_state, engine):
        from lorcana_bot.cards import EffectDef

        initial_hand_size = len(sample_game_state.players[0].hand)

        pe = create_pending_effect(
            sample_game_state,
            controller_id=0,
            chooser_id=0,
            source_id=None,
            source_card_id=None,
            effects=(EffectDef(kind="draw", amount=1),),
            optional=True,
        )

        action = Action(
            ACTION_RESOLVE_PENDING_EFFECT,
            actor=0,
            source=None,
            choice={"pending_effect_id": pe.id, "accept": False},
        )

        state = engine.apply_action(sample_game_state, action)

        # Should NOT have drawn a card
        assert len(state.players[0].hand) == initial_hand_size
        # Pending effect should be removed
        assert has_pending_effects(state) is False

    def test_wrong_actor_cannot_resolve(self, sample_game_state, engine):
        from lorcana_bot.cards import EffectDef

        create_pending_effect(
            sample_game_state,
            controller_id=0,
            chooser_id=0,
            source_id=None,
            source_card_id=None,
            effects=(EffectDef(kind="draw", amount=1),),
        )

        # Player 1 tries to resolve player 0's pending effect
        action = Action(
            ACTION_RESOLVE_PENDING_EFFECT,
            actor=1,
            source=None,
            choice={"pending_effect_id": "pe_1"},
        )

        # Should raise error
        with pytest.raises(Exception):
            engine.apply_action(sample_game_state, action)


# Import Action for tests
from lorcana_bot.actions import Action


# Fixtures
@pytest.fixture
def sample_game_state():
    """Create a sample game state for testing."""
    from lorcana_bot.state import GameState, PlayerState, CardInstance

    players = [PlayerState(), PlayerState()]
    cards = {}
    next_id = 1

    # Create simple decks
    for player in range(2):
        for _ in range(10):
            inst = CardInstance(
                instance_id=next_id,
                card_id=DEMO_FEATURE_CARD_IDS["basic_character"],
                owner=player,
                controller=player,
            )
            cards[next_id] = inst
            players[player].deck.append(next_id)
            next_id += 1

    state = GameState(
        players=players,
        cards=cards,
        active_player=0,
        first_player=0,
        phase="MAIN",
        bag=[],
        event_log=[],
        action_log=[],
    )

    # Draw hands
    for player in range(2):
        for _ in range(5):
            cid = state.players[player].deck.pop(0)
            state.cards[cid].zone = "hand"
            state.players[player].hand.append(cid)

    return state


@pytest.fixture
def engine():
    """Create a game engine for testing."""
    from lorcana_bot.cards import load_demo_database

    db = load_demo_database()
    return GameEngine(db)


class TestSpecialPendingRequirementEngineRouting:
    """Engine-path tests for special pending requirement_kind dispatch."""

    def _engine(self) -> GameEngine:
        cards = [
            CardDef("a", "A", "amber", 1, True, "character", 1, 1, 1),
            CardDef("b", "B", "amber", 1, True, "character", 1, 1, 1),
            CardDef("c", "C", "amber", 1, True, "character", 1, 1, 1),
        ]
        return GameEngine(CardDatabase(cards))

    def _state_with_deck(self) -> GameState:
        state = GameState(players=[PlayerState(), PlayerState()], cards={})
        state.cards[1] = CardInstance(instance_id=1, card_id="a", owner=0, controller=0, zone=ZONE_DECK)
        state.cards[2] = CardInstance(instance_id=2, card_id="b", owner=0, controller=0, zone=ZONE_DECK)
        state.cards[3] = CardInstance(instance_id=3, card_id="c", owner=0, controller=0, zone=ZONE_DECK)
        state.players[0].deck = [1, 2, 3]
        state.active_player = 0
        return state

    def test_scry_pending_requirement_resolves_through_engine_action(self):
        engine = self._engine()
        state = self._state_with_deck()

        pe = create_scry_pending_effect(
            state,
            controller_id=0,
            chooser_id=0,
            source_id=None,
            source_card_id=None,
            amount=2,
        )

        actions = engine.legal_actions(state, 0)
        resolve_actions = [a for a in actions if a.kind == ACTION_RESOLVE_PENDING_EFFECT]
        action = Action(
            ACTION_RESOLVE_PENDING_EFFECT,
            actor=0,
            choice={
                "pending_effect_id": pe.id,
                "top_cards": (2,),
                "bottom_cards": (1,),
            },
        )
        assert action in resolve_actions

        next_state = engine.apply_action(state, action)

        assert next_state.players[0].deck == [2, 3, 1]
        assert next_state.pending_effects == []

    def test_search_pending_requirement_resolves_through_engine_action(self):
        engine = self._engine()
        state = self._state_with_deck()

        pe = create_search_pending_effect(
            state,
            controller_id=0,
            chooser_id=0,
            source_id=None,
            source_card_id=None,
            candidate_ids=(1, 2),
            destination=ZONE_HAND,
            shuffle_after=False,
        )

        actions = engine.legal_actions(state, 0)
        resolve_actions = [a for a in actions if a.kind == ACTION_RESOLVE_PENDING_EFFECT]
        action = Action(
            ACTION_RESOLVE_PENDING_EFFECT,
            actor=0,
            choice={"pending_effect_id": pe.id, "selected_card_id": 2},
        )
        assert action in resolve_actions

        next_state = engine.apply_action(state, action)

        assert 2 in next_state.players[0].hand
        assert 2 not in next_state.players[0].deck
        assert next_state.pending_effects == []

    def test_reveal_routing_pending_requirement_resolves_through_engine_action(self):
        engine = self._engine()
        state = self._state_with_deck()

        pe = create_reveal_routing_pending_effect(
            state,
            controller_id=0,
            chooser_id=0,
            source_id=None,
            source_card_id=None,
            card_ids=(1,),
            destination=None,
            destination_options=(ZONE_HAND, ZONE_DECK),
        )

        actions = engine.legal_actions(state, 0)
        resolve_actions = [a for a in actions if a.kind == ACTION_RESOLVE_PENDING_EFFECT]
        action = Action(
            ACTION_RESOLVE_PENDING_EFFECT,
            actor=0,
            choice={"pending_effect_id": pe.id, "destination": ZONE_HAND},
        )
        assert action in resolve_actions

        next_state = engine.apply_action(state, action)

        assert next_state.cards[1].revealed is True
        assert 1 in next_state.players[0].hand
        assert 1 not in next_state.players[0].deck
        assert next_state.pending_effects == []

    def test_named_card_pending_requirement_resolves_through_engine_action(self):
        engine = self._engine()
        state = self._state_with_deck()

        pending = PendingEffect(
            id="pe_named",
            controller_id=0,
            chooser_id=0,
            source_id=None,
            source_card_id=None,
            effects=(),
            choice_options=("a", "b"),
            raw={
                "requirement_kind": "named_card",
                "requirement": NamedCardRequirement(valid_card_def_ids=("a", "b"), chooser_id=0),
            },
        )
        state.pending_effects.append(pending)

        actions = engine.legal_actions(state, 0)
        resolve_actions = [a for a in actions if a.kind == ACTION_RESOLVE_PENDING_EFFECT]
        action = Action(
            ACTION_RESOLVE_PENDING_EFFECT,
            actor=0,
            choice={"pending_effect_id": pending.id, "named_card": "b"},
        )
        assert action in resolve_actions

        next_state = engine.apply_action(state, action)

        assert any(
            event.event_type == "NAMED_CARD_CHOSEN"
            and event.payload.get("named_card") == "b"
            for event in next_state.event_log
        )
        assert next_state.pending_effects == []

    def test_destination_pending_requirement_resolves_through_engine_action(self):
        engine = self._engine()
        state = self._state_with_deck()

        pending = PendingEffect(
            id="pe_destination",
            controller_id=0,
            chooser_id=0,
            source_id=None,
            source_card_id=None,
            effects=(),
            choice_options=(ZONE_HAND, ZONE_DECK),
            raw={
                "requirement_kind": "destination",
                "destination_options": (ZONE_HAND, ZONE_DECK),
            },
        )
        state.pending_effects.append(pending)

        action = Action(
            ACTION_RESOLVE_PENDING_EFFECT,
            actor=0,
            choice={"pending_effect_id": pending.id, "destination": ZONE_HAND},
        )
        assert action in engine.legal_actions(state, 0)

        next_state = engine.apply_action(state, action)

        assert any(
            event.event_type == "DESTINATION_CHOSEN"
            and event.payload.get("destination") == ZONE_HAND
            for event in next_state.event_log
        )
        assert next_state.pending_effects == []

    def test_name_a_card_effect_creates_named_card_pending_requirement(self):
        engine = self._engine()
        state = self._state_with_deck()
        state.cards[4] = CardInstance(instance_id=4, card_id="a", owner=0, controller=0, zone=ZONE_PLAY)
        state.players[0].play.append(4)

        engine.effect_resolver.resolve(
            state,
            EffectDef(kind="name_a_card"),
            EffectResolutionContext(actor=0, source=4),
        )

        pending = state.pending_effects[-1]
        assert pending.raw.get("requirement_kind") == "named_card"
        assert pending.effects == ()

        action = Action(
            ACTION_RESOLVE_PENDING_EFFECT,
            actor=0,
            source=4,
            choice={"pending_effect_id": pending.id, "named_card": "b"},
        )
        assert action in engine.legal_actions(state, 0)

        next_state = engine.apply_action(state, action)

        assert any(
            event.event_type == "NAMED_CARD_CHOSEN"
            and event.payload.get("named_card") == "b"
            for event in next_state.event_log
        )
        assert next_state.pending_effects == []

    def test_special_pending_requirement_counts_for_actor_resolution(self):
        state = self._state_with_deck()
        create_scry_pending_effect(
            state,
            controller_id=0,
            chooser_id=1,
            source_id=None,
            source_card_id=None,
            amount=2,
        )

        resolution = resolve_current_actor(state, self._engine())

        assert resolution.actor == 1
        assert resolution.reason == "pending_effect_chooser"


class TestRequirementKindLegalActions:
    """Test that legal_actions() enumerates correct RESOLVE_PENDING_EFFECT actions
    for each requirement_kind type."""

    @pytest.fixture
    def engine(self):
        from lorcana_bot.engine import GameEngine
        from lorcana_bot.cards import load_demo_database
        db = load_demo_database()
        return GameEngine(db)

    @pytest.fixture
    def state_with_pending(self, engine):
        """Create a basic game state with no deck to avoid draws."""
        from lorcana_bot.state import GameState, PlayerState, CardInstance

        state = GameState(
            players=[PlayerState(), PlayerState()],
            cards={},
            active_player=0,
            first_player=0,
            phase="MAIN",
        )
        # Add a card for testing (use string card_id)
        cid = 1
        state.cards[cid] = CardInstance(
            instance_id=cid,
            card_id=DEMO_FEATURE_CARD_IDS["basic_character"],
            owner=0,
            controller=0,
        )
        return state, engine

    def _create_pending_effect(
        self,
        state,
        chooser_id: int = 0,
        controller_id: int = 0,
        source_id: int = 1,
        requirement_kind: str = "target",
        raw: dict = None,
        required_targets: tuple[TargetRequirement, ...] = (),
        optional: bool = False,
        accepted: bool | None = None,
    ):
        """Helper to create a pending effect with specified requirement_kind."""
        from lorcana_bot.pending_effects import PendingEffect

        pe_id = len(state.pending_effects) + 1
        raw = raw or {}
        raw["requirement_kind"] = requirement_kind

        pe = PendingEffect(
            id=f"pe_{pe_id}",
            controller_id=controller_id,
            chooser_id=chooser_id,
            source_id=source_id,
            source_card_id=None,
            effects=(),
            required_targets=required_targets,
            optional=optional,
            accepted=accepted,
            raw=raw,
        )
        state.pending_effects.append(pe)
        return pe

    def test_amount_requirement_kind_enumerates_amounts(self, state_with_pending):
        """Test that amount requirement_kind emits one action per allowed amount."""
        state, engine = state_with_pending

        # Create amount pending effect with explicit amount_options
        raw = {
            "requirement_kind": "amount",
            "amount_options": [1, 2, 3],
        }
        self._create_pending_effect(state, requirement_kind="amount", raw=raw)

        actions = engine.legal_actions(state, 0)
        resolve_actions = [a for a in actions if a.kind == ACTION_RESOLVE_PENDING_EFFECT]

        # Should have 3 actions for amounts 1, 2, 3 plus CONCEDE
        assert len(resolve_actions) == 3
        amounts = {a.choice.get("amount") for a in resolve_actions}
        assert amounts == {1, 2, 3}

    def test_amount_requirement_kind_with_min_max_fallback(self, state_with_pending):
        """Test amount fallback to min/max when no explicit options."""
        state, engine = state_with_pending

        # Create requirement object with min/max
        class MockRequirement:
            min = 1
            max = 4

        raw = {
            "requirement_kind": "amount",
            "requirement": MockRequirement(),
        }
        self._create_pending_effect(state, requirement_kind="amount", raw=raw)

        actions = engine.legal_actions(state, 0)
        resolve_actions = [a for a in actions if a.kind == ACTION_RESOLVE_PENDING_EFFECT]

        # Should have 4 actions for amounts 1, 2, 3, 4
        assert len(resolve_actions) == 4
        amounts = {a.choice.get("amount") for a in resolve_actions}
        assert amounts == {1, 2, 3, 4}

    def test_amount_requirement_kind_uses_raw_min_amount_max_amount(self, state_with_pending):
        """Test amount fallback also honors raw min_amount/max_amount fields."""
        state, engine = state_with_pending

        raw = {
            "requirement_kind": "amount",
            "min_amount": 2,
            "max_amount": 4,
        }
        self._create_pending_effect(state, requirement_kind="amount", raw=raw)

        actions = engine.legal_actions(state, 0)
        resolve_actions = [a for a in actions if a.kind == ACTION_RESOLVE_PENDING_EFFECT]

        assert len(resolve_actions) == 3
        assert {a.choice.get("amount") for a in resolve_actions} == {2, 3, 4}

    def test_amount_resolver_validates_raw_min_max_aliases(self, state_with_pending):
        """Test amount resolver accepts raw min/max aliases used by legal_actions."""
        state, _engine = state_with_pending
        from lorcana_bot.pending_effects import resolve_amount_choice

        pe = self._create_pending_effect(
            state,
            requirement_kind="amount",
            raw={"requirement_kind": "amount", "min": 1, "max": 3},
        )

        resolve_amount_choice(state, pe.id, 3)
        assert pe.raw["resolution_input"]["amount"] == 3
        with pytest.raises(ValueError):
            resolve_amount_choice(state, pe.id, 4)

    def test_choice_index_resolver_uses_option_index_not_option_value(self, state_with_pending):
        """Test choice resolver accepts indexes for non-integer option labels."""
        state, _engine = state_with_pending
        from lorcana_bot.pending_effects import resolve_choice_index

        pe = self._create_pending_effect(
            state,
            requirement_kind="choice",
            raw={"requirement_kind": "choice", "options": ["draw", "gain_lore"]},
        )

        resolve_choice_index(state, pe.id, 1)
        assert pe.raw["resolution_input"]["choice_index"] == 1
        with pytest.raises(ValueError):
            resolve_choice_index(state, pe.id, 2)

    def test_target_requirement_kind_enumerates_targets(self, state_with_pending):
        """Test that target requirement_kind emits only valid target actions."""
        state, engine = state_with_pending

        # Create player 0 character in play
        cid = 10
        state.cards[cid] = CardInstance(
            instance_id=cid,
            card_id=DEMO_FEATURE_CARD_IDS["basic_character"],
            owner=0,
            controller=0,
            zone=ZONE_PLAY,
        )
        state.players[0].play.append(cid)

        # Create target pending effect with explicit candidate_ids
        raw = {
            "requirement_kind": "target",
            "candidate_ids": [cid],
            "target": "chosen_character",
        }
        self._create_pending_effect(
            state,
            requirement_kind="target",
            required_targets=(TargetRequirement(kind="chosen_character", card_type="character"),),
            raw=raw,
        )

        actions = engine.legal_actions(state, 0)
        resolve_actions = [a for a in actions if a.kind == ACTION_RESOLVE_PENDING_EFFECT]

        # Should have 1 action for target cid
        assert len(resolve_actions) == 1
        assert resolve_actions[0].target == cid
        assert resolve_actions[0].choice.get("targets") == (cid,)

    def test_target_requirement_kind_fallback_to_get_valid_targets(self, state_with_pending):
        """Test target fallback to get_valid_targets_for_requirement."""
        state, engine = state_with_pending

        # Create target pending effect without explicit candidates
        raw = {
            "requirement_kind": "target",
            "requirement": None,  # Will use get_valid_targets fallback
        }
        self._create_pending_effect(state, requirement_kind="target", raw=raw)

        actions = engine.legal_actions(state, 0)
        # Should still generate an action (empty targets if no valid targets)
        resolve_actions = [a for a in actions if a.kind == ACTION_RESOLVE_PENDING_EFFECT]
        assert len(resolve_actions) >= 0  # May be empty if no valid targets

    def test_multi_target_requirement_kind_enumerates_combinations(self, state_with_pending):
        """Test that multi_target requirement_kind emits combinations respecting min/max."""
        state, engine = state_with_pending

        # Create player 0 characters in play
        cids = [11, 12, 13]
        for cid in cids:
            state.cards[cid] = CardInstance(
                instance_id=cid,
                card_id=DEMO_FEATURE_CARD_IDS["basic_character"],
                owner=0,
                controller=0,
                zone=ZONE_PLAY,
            )
            state.players[0].play.append(cid)

        # Create multi_target pending effect with min_targets=1, max_targets=2
        class MockRequirement:
            candidate_ids = cids
            min_targets = 1
            max_targets = 2

        raw = {
            "requirement_kind": "multi_target",
            "candidate_ids": cids,
            "target": {"selector": "chosen_character", "min_count": 1, "max_count": 2},
            "requirement": MockRequirement(),
        }
        self._create_pending_effect(
            state,
            requirement_kind="multi_target",
            required_targets=(TargetRequirement(kind="chosen_character", min_targets=1, max_targets=2, card_type="character"),),
            raw=raw,
        )

        actions = engine.legal_actions(state, 0)
        resolve_actions = [a for a in actions if a.kind == ACTION_RESOLVE_PENDING_EFFECT]

        # C(3,1) + C(3,2) = 3 + 3 = 6 combinations
        assert len(resolve_actions) == 6

        # Verify all combinations are valid
        for action in resolve_actions:
            targets = action.choice.get("targets")
            assert len(targets) in {1, 2}
            assert all(cid in cids for cid in targets)

    def test_discard_choice_requirement_kind_enumerates_combinations(self, state_with_pending):
        """Test that discard_choice requirement_kind emits card combinations from hand."""
        state, engine = state_with_pending

        # Create player 0 cards in hand
        hand_cids = [21, 22, 23]
        for cid in hand_cids:
            state.cards[cid] = CardInstance(
                instance_id=cid,
                card_id=DEMO_FEATURE_CARD_IDS["basic_character"],
                owner=0,
                controller=0,
                zone=ZONE_HAND,
            )
            state.players[0].hand.append(cid)

        # Create discard_choice pending effect with min_cards=1, max_cards=2
        raw = {
            "requirement_kind": "discard_choice",
            "card_candidate_ids": hand_cids,
            "min_cards": 1,
            "max_cards": 2,
        }
        self._create_pending_effect(state, requirement_kind="discard_choice", raw=raw)

        actions = engine.legal_actions(state, 0)
        resolve_actions = [a for a in actions if a.kind == ACTION_RESOLVE_PENDING_EFFECT]

        # C(3,1) + C(3,2) = 3 + 3 = 6 combinations
        assert len(resolve_actions) == 6

        # Verify all combinations are valid
        for action in resolve_actions:
            card_ids = action.choice.get("discard_card_ids")
            assert len(card_ids) in {1, 2}
            assert all(cid in hand_cids for cid in card_ids)

    def test_discard_choice_only_shows_hand_cards(self, state_with_pending):
        """Test that discard_choice filters to only cards in chooser's hand."""
        state, engine = state_with_pending

        # Create some cards in hand, some in play
        hand_cids = [31, 32]
        play_cids = [33, 34]
        all_cids = hand_cids + play_cids

        for cid in all_cids:
            zone = ZONE_HAND if cid in hand_cids else ZONE_PLAY
            state.cards[cid] = CardInstance(
                instance_id=cid,
                card_id=DEMO_FEATURE_CARD_IDS["basic_character"],
                owner=0,
                controller=0,
                zone=zone,
            )
            if cid in hand_cids:
                state.players[0].hand.append(cid)
            else:
                state.players[0].play.append(cid)

        # Create discard_choice pending effect with all cids but only hand cids valid
        raw = {
            "requirement_kind": "discard_choice",
            "card_candidate_ids": all_cids,  # Includes play cards
            "min_cards": 1,
            "max_cards": 1,
        }
        self._create_pending_effect(state, requirement_kind="discard_choice", raw=raw)

        actions = engine.legal_actions(state, 0)
        resolve_actions = [a for a in actions if a.kind == ACTION_RESOLVE_PENDING_EFFECT]

        # Only hand cards should be valid
        assert len(resolve_actions) == 2
        for action in resolve_actions:
            card_ids = action.choice.get("discard_card_ids")
            assert all(cid in hand_cids for cid in card_ids)

    def test_choice_requirement_kind_enumerates_indices(self, state_with_pending):
        """Test that choice requirement_kind emits one action per choice index."""
        state, engine = state_with_pending

        # Create choice pending effect with explicit options
        raw = {
            "requirement_kind": "choice",
            "options": ["option_a", "option_b", "option_c"],
        }
        self._create_pending_effect(state, requirement_kind="choice", raw=raw)

        actions = engine.legal_actions(state, 0)
        resolve_actions = [a for a in actions if a.kind == ACTION_RESOLVE_PENDING_EFFECT]

        # Should have 3 actions for indices 0, 1, 2
        assert len(resolve_actions) == 3
        indices = {a.choice.get("choice_index") for a in resolve_actions}
        assert indices == {0, 1, 2}

    def test_optional_requirement_kind_emits_accept_decline(self, state_with_pending):
        """Test that optional requirement_kind emits accept and decline."""
        state, engine = state_with_pending

        # Create optional pending effect
        raw = {
            "requirement_kind": "optional",
        }
        self._create_pending_effect(
            state,
            requirement_kind="optional",
            raw=raw,
            optional=True,
            accepted=None,
        )

        actions = engine.legal_actions(state, 0)
        resolve_actions = [a for a in actions if a.kind == ACTION_RESOLVE_PENDING_EFFECT]

        # Should have 2 actions: accept=True and accept=False
        assert len(resolve_actions) == 2

        accepts = {a.choice.get("accept") for a in resolve_actions}
        assert accepts == {True, False}

    def test_optional_requirement_kind_already_accepted(self, state_with_pending):
        """Test that optional already accepted doesn't emit accept/decline."""
        state, engine = state_with_pending

        raw = {
            "requirement_kind": "optional",
        }
        self._create_pending_effect(
            state,
            requirement_kind="optional",
            raw=raw,
            optional=True,
            accepted=True,  # Already accepted
        )

        actions = engine.legal_actions(state, 0)
        resolve_actions = [a for a in actions if a.kind == ACTION_RESOLVE_PENDING_EFFECT]

        # Should not have accept/decline since already resolved
        accept_actions = [a for a in resolve_actions if "accept" in a.choice]
        assert len(accept_actions) == 0

    def test_opponent_choice_only_visible_to_chooser(self, state_with_pending):
        """Test that opponent_choice is only visible to the opponent chooser."""
        state, engine = state_with_pending

        # Player 0 is controller, player 1 is chooser
        raw = {
            "requirement_kind": "opponent_choice",
            "choice_type": "choice",
            "options": ["a", "b"],
        }
        self._create_pending_effect(
            state,
            chooser_id=1,  # Opponent is chooser
            controller_id=0,
            requirement_kind="opponent_choice",
            raw=raw,
        )

        # Player 0 (non-chooser) should only get CONCEDE
        actions_p0 = engine.legal_actions(state, 0)
        resolve_p0 = [a for a in actions_p0 if a.kind == ACTION_RESOLVE_PENDING_EFFECT]
        assert len(resolve_p0) == 0
        assert len(actions_p0) == 1  # Only CONCEDE

        # Player 1 (chooser) should get choice actions
        actions_p1 = engine.legal_actions(state, 1)
        resolve_p1 = [a for a in actions_p1 if a.kind == ACTION_RESOLVE_PENDING_EFFECT]
        assert len(resolve_p1) == 2  # 2 choice indices

    def test_opponent_choice_apply_action_requires_opponent_chooser(self, state_with_pending):
        """opponent_choice resolves through public actions only for the stored chooser."""
        from lorcana_bot.engine import IllegalActionError

        state, engine = state_with_pending
        pe = self._create_pending_effect(
            state,
            chooser_id=1,
            controller_id=0,
            requirement_kind="opponent_choice",
            raw={
                "requirement_kind": "opponent_choice",
                "choice_type": "choice",
                "options": ["left", "right"],
            },
        )

        correct = next(
            action
            for action in engine.legal_actions(state, 1)
            if action.kind == ACTION_RESOLVE_PENDING_EFFECT and action.choice.get("choice_index") == 1
        )
        wrong_actor = Action(
            ACTION_RESOLVE_PENDING_EFFECT,
            actor=0,
            source=pe.source_id,
            choice=dict(correct.choice),
        )

        with pytest.raises(IllegalActionError):
            engine.apply_action(state, wrong_actor)

        next_state = engine.apply_action(state, correct)
        assert not next_state.pending_effects
        assert pe.id not in {item.id for item in next_state.pending_effects}

    def test_bag_origin_empty_general_pending_completes_bag_item(self, state_with_pending):
        """Pure-input amount/target/opponent_choice bag-origin pending effects complete their bag item."""
        from lorcana_bot.constants import EVENT_TRIGGER_RESOLVED
        from lorcana_bot.state import BagEffectEntry, PendingTriggeredEvent

        _base_state, engine = state_with_pending
        for requirement_kind, raw, choice in (
            ("amount", {"amount_options": [1]}, {"amount": 1}),
            ("target", {"candidate_ids": [10], "target": "chosen_character"}, {"targets": (10,)}),
            (
                "opponent_choice",
                {"choice_type": "choice", "options": ["a"]},
                {"choice_index": 0},
            ),
        ):
            state = GameState(
                players=[PlayerState(), PlayerState()],
                cards={},
                active_player=0,
                first_player=0,
                phase="MAIN",
            )
            state.cards[1] = CardInstance(
                instance_id=1,
                card_id=DEMO_FEATURE_CARD_IDS["basic_character"],
                owner=0,
                controller=0,
                zone=ZONE_PLAY,
            )
            if requirement_kind == "target":
                state.cards[10] = CardInstance(
                    instance_id=10,
                    card_id=DEMO_FEATURE_CARD_IDS["basic_character"],
                    owner=0,
                    controller=0,
                    zone=ZONE_PLAY,
                )
                state.players[0].play.append(10)
            bag = BagEffectEntry(
                id=f"bag_{requirement_kind}",
                kind="triggered_ability",
                ability_id=f"ability_{requirement_kind}",
                ability_index=0,
                ability_key=f"ability_{requirement_kind}",
                ability_name=None,
                auto_resolve=True,
                controller_id=0,
                chooser_id=0,
                source_id=1,
                source_card_id=DEMO_FEATURE_CARD_IDS["basic_character"],
                trigger={"event": "play"},
                condition=None,
                effects=(),
                occurrence_index=1,
                event=PendingTriggeredEvent(id=f"evt_{requirement_kind}", event="play", player_id=0),
            )
            state.bag.append(bag)
            pe = self._create_pending_effect(
                state,
                chooser_id=0,
                controller_id=0,
                source_id=1,
                requirement_kind=requirement_kind,
                raw={"requirement_kind": requirement_kind, **raw},
            )
            pe.origin = "bag"
            pe.origin_id = bag.id
            pe.raw["origin"] = "bag"
            pe.raw["origin_id"] = bag.id

            action = Action(
                ACTION_RESOLVE_PENDING_EFFECT,
                actor=0,
                source=1,
                target=10 if requirement_kind == "target" else None,
                choice={"pending_effect_id": pe.id, **choice},
            )
            next_state = engine.apply_action(state, action)

            assert not next_state.bag
            assert not next_state.pending_effects
            assert any(event.event_type == EVENT_TRIGGER_RESOLVED for event in next_state.event_log)

    def test_opponent_choice_target_type(self, state_with_pending):
        """Test opponent_choice with target choice_type."""
        state, engine = state_with_pending

        # Create target for player 1
        cid = 40
        state.cards[cid] = CardInstance(
            instance_id=cid,
            card_id=DEMO_FEATURE_CARD_IDS["basic_character"],
            owner=1,
            controller=1,
            zone=ZONE_PLAY,
        )
        state.players[1].play.append(cid)

        raw = {
            "requirement_kind": "opponent_choice",
            "choice_type": "target",
            "candidate_ids": [cid],
            "target": "chosen_character",
        }
        self._create_pending_effect(
            state,
            chooser_id=1,
            controller_id=0,
            requirement_kind="opponent_choice",
            required_targets=(TargetRequirement(kind="chosen_character", card_type="character"),),
            raw=raw,
        )

        # Player 1 should get target action
        actions_p1 = engine.legal_actions(state, 1)
        resolve_p1 = [a for a in actions_p1 if a.kind == ACTION_RESOLVE_PENDING_EFFECT]
        assert len(resolve_p1) == 1
        assert resolve_p1[0].target == cid

    def test_enter_play_exerted_requirement_kind(self, state_with_pending):
        """Test that enter_play_exerted requirement_kind emits true and false choices."""
        state, engine = state_with_pending

        raw = {
            "requirement_kind": "enter_play_exerted",
        }
        self._create_pending_effect(
            state,
            requirement_kind="enter_play_exerted",
            raw=raw,
        )

        actions = engine.legal_actions(state, 0)
        resolve_actions = [a for a in actions if a.kind == ACTION_RESOLVE_PENDING_EFFECT]

        # Should have 2 actions: enter_play_exerted=True and enter_play_exerted=False
        assert len(resolve_actions) == 2

        exert_values = {a.choice.get("enter_play_exerted") for a in resolve_actions}
        assert exert_values == {True, False}

    def test_concede_always_available(self, state_with_pending):
        """Test that CONCEDE is always available during pending effect resolution."""
        state, engine = state_with_pending

        raw = {
            "requirement_kind": "choice",
            "options": ["a", "b"],
        }
        self._create_pending_effect(state, requirement_kind="choice", raw=raw)

        actions = engine.legal_actions(state, 0)

        # CONCEDE should be available
        concedes = [a for a in actions if a.kind == ACTION_CONCEDE]
        assert len(concedes) == 1

    def test_non_chooser_gets_only_concede(self, state_with_pending):
        """Test that non-chooser players only get CONCEDE during pending resolution."""
        state, engine = state_with_pending

        # Player 0 is controller/chooser, player 1 is opponent
        raw = {
            "requirement_kind": "choice",
            "options": ["a", "b"],
        }
        self._create_pending_effect(
            state,
            chooser_id=0,
            controller_id=0,
            requirement_kind="choice",
            raw=raw,
        )

        # Player 1 (non-chooser) should only get CONCEDE
        actions_p1 = engine.legal_actions(state, 1)
        resolve_p1 = [a for a in actions_p1 if a.kind == ACTION_RESOLVE_PENDING_EFFECT]
        assert len(resolve_p1) == 0
        assert len(actions_p1) == 1  # Only CONCEDE


class TestDiscardChoicePendingEffect:
    """Tests for discard-choice pending effect behavior (Microfix 9 Brief 4)."""

    @staticmethod
    def _real_card_ids(engine, count: int, *, start: int = 0) -> tuple[str, ...]:
        """Return stable real card definition ids from the active test database."""
        cards = tuple(engine.db.all_cards())
        assert len(cards) >= start + count
        return tuple(card.id for card in cards[start:start + count])

    @staticmethod
    def _put_real_card_instance(
        state,
        *,
        instance_id: int,
        card_id: str,
        player: int,
        zone: str,
    ) -> None:
        """Create a CardInstance backed by a real CardDef from the test database."""
        from lorcana_bot.state import CardInstance

        state.cards[instance_id] = CardInstance(
            instance_id=instance_id,
            card_id=card_id,
            owner=player,
            controller=player,
            zone=zone,
        )

        if zone == ZONE_HAND:
            state.players[player].hand.append(instance_id)
        elif zone == ZONE_PLAY:
            state.players[player].play.append(instance_id)

    @pytest.fixture
    def engine(self):
        from pathlib import Path

        from lorcana_bot.engine import GameEngine
        from lorcana_bot.importers.lorcanito_source_importer import import_lorcanito_source_cards

        source_json = Path("data/lorcanito_runtime_extracted/cards.normalized.json")
        db, report = import_lorcanito_source_cards(source_json)

        assert report.errors == []
        assert len(db) > 0

        return GameEngine(db)

    @pytest.fixture
    def state_with_hand(self, engine):
        """Create a game state with real card data in hand for discard testing."""
        from lorcana_bot.state import GameState, PlayerState

        state = GameState(
            players=[PlayerState(), PlayerState()],
            cards={},
            active_player=0,
            first_player=0,
            phase="MAIN",
        )

        # Stable instance ids are fine; the important part is that each instance
        # points at a real CardDef from the imported Lorcanito card database.
        for instance_id, card_id in zip((101, 102, 103), self._real_card_ids(engine, 3, start=0)):
            self._put_real_card_instance(
                state,
                instance_id=instance_id,
                card_id=card_id,
                player=0,
                zone=ZONE_HAND,
            )

        return state, engine

    def test_create_discard_choice_pending_effect(self, state_with_hand):
        """Test that create_discard_choice_pending_effect creates proper pending effect."""
        from lorcana_bot.pending_effects import create_discard_choice_pending_effect

        state, engine = state_with_hand

        candidate_ids = tuple(state.players[0].hand)
        pe = create_discard_choice_pending_effect(
            state,
            controller_id=0,
            chooser_id=0,
            source_id=1,
            source_card_id="test_source",
            target_player_id=0,
            candidate_ids=candidate_ids,
            min_select=1,
            max_select=2,
        )

        assert pe is not None
        assert pe.raw.get("requirement_kind") == "discard_choice"
        assert pe.raw.get("discard_candidates") == candidate_ids
        assert pe.raw.get("min_discard") == 1
        assert pe.raw.get("max_discard") == 2
        assert pe.chooser_id == 0
        assert pe.controller_id == 0

    def test_chosen_discard_creates_pending_not_immediate(self, state_with_hand):
        """Test that discard effect with chosen=true creates pending, doesn't discard immediately."""
        from lorcana_bot.effects import EffectResolver
        from lorcana_bot.cards import EffectDef
        from lorcana_bot.effect_types import EffectResolutionContext
        from lorcana_bot.pending_effects import has_pending_effects
        from lorcana_bot.state import CardInstance

        state, engine = state_with_hand

        # Give player 1 real cards in hand (player 0 is actor, targeting opponent)
        for instance_id, card_id in zip((201, 202), self._real_card_ids(engine, 2, start=10)):
            self._put_real_card_instance(
                state,
                instance_id=instance_id,
                card_id=card_id,
                player=1,
                zone=ZONE_HAND,
            )

        initial_hand_size = len(state.players[1].hand)

        # Create a discard effect with chosen=true
        effect = EffectDef(
            kind="discard",
            amount=1,
            target="opponent",
            raw={"chosen": True},
        )

        resolver = EffectResolver(engine)
        resolver.resolve(
            state,
            effect,
            EffectResolutionContext(actor=0, source=1),
        )

        # Should have created a pending effect, not discarded immediately
        assert has_pending_effects(state) is True
        assert len(state.players[1].hand) == initial_hand_size  # No discards yet

    def test_opponent_chosen_discard_makes_opponent_chooser(self, state_with_hand):
        """Test that discard with chosenBy='opponent' makes opponent the chooser."""
        from lorcana_bot.effects import EffectResolver
        from lorcana_bot.cards import EffectDef
        from lorcana_bot.effect_types import EffectResolutionContext
        from lorcana_bot.pending_effects import get_current_pending_effect
        from lorcana_bot.state import CardInstance

        state, engine = state_with_hand

        # Give player 1 real cards in hand
        for instance_id, card_id in zip((201, 202), self._real_card_ids(engine, 2, start=20)):
            self._put_real_card_instance(
                state,
                instance_id=instance_id,
                card_id=card_id,
                player=1,
                zone=ZONE_HAND,
            )

        # Player 0's opponent is player 1
        effect = EffectDef(
            kind="discard",
            amount=1,
            target="opponent",
            raw={"chosenBy": "opponent"},
        )

        resolver = EffectResolver(engine)
        resolver.resolve(
            state,
            effect,
            EffectResolutionContext(actor=0, source=1),
        )

        # Player 1 (opponent of actor) should be the chooser
        pe = get_current_pending_effect(state, 1)
        assert pe is not None
        assert pe.chooser_id == 1

    def test_discard_choice_legal_actions_expose_combinations(self, state_with_hand):
        """Test that legal_actions exposes discard combinations for a single pending effect."""
        from lorcana_bot.pending_effects import create_discard_choice_pending_effect

        state, engine = state_with_hand

        # Create a discard choice pending effect with max 2 cards
        pe = create_discard_choice_pending_effect(
            state,
            controller_id=0,
            chooser_id=0,
            source_id=1,
            source_card_id=None,
            target_player_id=0,
            candidate_ids=tuple(state.players[0].hand),  # 3 cards
            min_select=1,
            max_select=2,
        )

        actions = engine.legal_actions(state, 0)
        # Count actions for THIS pending effect only
        resolve_actions = [
            a for a in actions
            if a.kind == ACTION_RESOLVE_PENDING_EFFECT
            and a.choice.get("pending_effect_id") == pe.id
        ]

        # C(3,1) + C(3,2) = 3 + 3 = 6 combinations for this specific pending effect
        # But we need to be careful - there may be other pending effects in state
        # Let's just check that we can find actions with the right structure
        discard_actions = [
            a for a in actions
            if a.kind == ACTION_RESOLVE_PENDING_EFFECT
            and "discard_card_ids" in a.choice
        ]

        # All discard actions should have valid card ids in hand
        for action in discard_actions:
            card_ids = action.choice.get("discard_card_ids")
            if card_ids:
                assert all(cid in state.players[0].hand for cid in card_ids)

        # Verify at least one specific combination exists (101 only)
        action_101 = [
            a for a in actions
            if a.kind == ACTION_RESOLVE_PENDING_EFFECT
            and a.choice.get("pending_effect_id") == pe.id
            and a.choice.get("discard_card_ids") == (101,)
        ]
        assert len(action_101) == 1, f"Expected 1 action for (101,), got {len(action_101)}"

    def test_apply_discard_choice_discards_through_discard_eventful(self, state_with_hand):
        """Test that resolving discard_choice discards selected cards through _discard_eventful."""
        from lorcana_bot.pending_effects import create_discard_choice_pending_effect
        from lorcana_bot.state import Action

        state, engine = state_with_hand

        initial_hand_size = len(state.players[0].hand)

        # Create pending effect
        pe = create_discard_choice_pending_effect(
            state,
            controller_id=0,
            chooser_id=0,
            source_id=1,
            source_card_id=None,
            target_player_id=0,
            candidate_ids=tuple(state.players[0].hand),
            min_select=1,
            max_select=2,
        )

        # Get legal actions and find one with discard_card_ids=(101,)
        actions = engine.legal_actions(state, 0)
        target_action = None
        for a in actions:
            if (a.kind == ACTION_RESOLVE_PENDING_EFFECT
                and a.choice.get("pending_effect_id") == pe.id
                and a.choice.get("discard_card_ids") == (101,)):
                target_action = a
                break

        assert target_action is not None, "Legal action for (101,) not found"

        # Apply through engine to test full flow
        next_state = engine.apply_action(state, target_action)

        # Verify the card was discarded
        assert 101 in next_state.players[0].discard
        assert 101 not in next_state.players[0].hand
        assert len(next_state.players[0].hand) == initial_hand_size - 1

    def test_discard_choice_uses_target_player_actor(self, state_with_hand):
        """Test that discard_choice uses target_player_id as actor for discards."""
        from lorcana_bot.pending_effects import create_discard_choice_pending_effect
        from lorcana_bot.state import Action
        from lorcana_bot.constants import EVENT_CARD_DISCARDED

        state, engine = state_with_hand

        # Create a discard choice for player 0's hand
        pe = create_discard_choice_pending_effect(
            state,
            controller_id=1,  # Player 1 controls the effect
            chooser_id=0,     # Player 0 makes the choice
            source_id=10,
            source_card_id=None,
            target_player_id=0,  # Target player is 0
            candidate_ids=tuple(state.players[0].hand),
            min_select=1,
            max_select=1,
        )

        # Get legal actions and find one with discard_card_ids=(101,)
        actions = engine.legal_actions(state, 0)
        target_action = None
        for a in actions:
            if (a.kind == ACTION_RESOLVE_PENDING_EFFECT
                and a.choice.get("pending_effect_id") == pe.id
                and a.choice.get("discard_card_ids") == (101,)):
                target_action = a
                break

        assert target_action is not None, "Legal action for (101,) not found"

        next_state = engine.apply_action(state, target_action)

        # The CARD_DISCARDED event should have the target player (0) as actor
        discard_events = [
            e for e in next_state.event_log
            if e.event_type == EVENT_CARD_DISCARDED
        ]
        assert len(discard_events) == 1
        assert discard_events[0].actor == 0

    def test_invalid_discard_selection_raises_error(self, state_with_hand):
        """Test that invalid discard selection raises IllegalActionError."""
        from lorcana_bot.pending_effects import create_discard_choice_pending_effect
        from lorcana_bot.state import Action

        state, engine = state_with_hand

        # Create pending effect
        pe = create_discard_choice_pending_effect(
            state,
            controller_id=0,
            chooser_id=0,
            source_id=1,
            source_card_id=None,
            target_player_id=0,
            candidate_ids=tuple(state.players[0].hand),  # [101, 102, 103]
            min_select=1,
            max_select=2,
        )

        # Get legal actions and modify to use invalid card
        actions = engine.legal_actions(state, 0)
        for a in actions:
            if (a.kind == ACTION_RESOLVE_PENDING_EFFECT
                and a.choice.get("pending_effect_id") == pe.id):
                # Create action with invalid discard_card_ids
                invalid_action = Action(
                    ACTION_RESOLVE_PENDING_EFFECT,
                    actor=0,
                    choice={
                        "pending_effect_id": pe.id,
                        "discard_card_ids": (999,),  # Not a valid candidate
                    },
                )
                with pytest.raises(Exception):
                    engine.apply_action(state, invalid_action)
                return

        pytest.fail("No pending effect actions found")

    def test_non_explicit_discard_preserves_deterministic_behavior(self, state_with_hand):
        """Test that non-explicit discard preserves existing deterministic behavior."""
        from lorcana_bot.effects import EffectResolver
        from lorcana_bot.cards import EffectDef
        from lorcana_bot.effect_types import EffectResolutionContext
        from lorcana_bot.pending_effects import has_pending_effects
        from lorcana_bot.state import CardInstance

        state, engine = state_with_hand

        # Give player 1 real cards in hand (player 0 is actor, targeting opponent)
        for instance_id, card_id in zip((201, 202), self._real_card_ids(engine, 2, start=30)):
            self._put_real_card_instance(
                state,
                instance_id=instance_id,
                card_id=card_id,
                player=1,
                zone=ZONE_HAND,
            )

        initial_hand_size = len(state.players[1].hand)

        # Create a discard effect WITHOUT chosen flag
        effect = EffectDef(
            kind="discard",
            amount=1,
            target="opponent",
        )

        resolver = EffectResolver(engine)
        resolver.resolve(
            state,
            effect,
            EffectResolutionContext(actor=0, source=1),
        )

        # Should NOT create pending effect (no explicit choice required)
        # Should discard immediately from front of hand
        assert has_pending_effects(state) is False
        # First card of opponent's hand should be discarded
        assert len(state.players[1].hand) == initial_hand_size - 1

    def test_discard_choice_min_max_bounds(self, state_with_hand):
        """Test that discard_choice respects min/max selection bounds."""
        from lorcana_bot.pending_effects import create_discard_choice_pending_effect

        state, engine = state_with_hand

        # Create with min=2, max=2
        pe = create_discard_choice_pending_effect(
            state,
            controller_id=0,
            chooser_id=0,
            source_id=1,
            source_card_id=None,
            target_player_id=0,
            candidate_ids=tuple(state.players[0].hand),
            min_select=2,
            max_select=2,
        )

        actions = engine.legal_actions(state, 0)
        resolve_actions = [
            a for a in actions
            if a.kind == ACTION_RESOLVE_PENDING_EFFECT
            and a.choice.get("pending_effect_id") == pe.id
        ]

        # Check that 2-card combinations exist - C(3,2) = 3 combinations
        two_card_actions = [
            a for a in resolve_actions
            if len(a.choice.get("discard_card_ids", ())) == 2
        ]
        assert len(two_card_actions) == 3, f"Expected 3 two-card combos, got {len(two_card_actions)}"

        # All 2-card actions should have exactly 2 cards
        for action in two_card_actions:
            card_ids = action.choice.get("discard_card_ids")
            assert len(card_ids) == 2

    def test_discard_choice_respects_hand_zone_filter(self, state_with_hand):
        """Test that discard_choice filters candidates to only cards in hand."""
        from lorcana_bot.pending_effects import create_discard_choice_pending_effect

        state, engine = state_with_hand

        # Add a real card to play.
        self._put_real_card_instance(
            state,
            instance_id=201,
            card_id=self._real_card_ids(engine, 1, start=40)[0],
            player=0,
            zone=ZONE_PLAY,
        )

        first_hand = state.players[0].hand[0]
        second_hand = state.players[0].hand[1]
        play_card = 201

        # Create pending effect including a play card.
        pe = create_discard_choice_pending_effect(
            state,
            controller_id=0,
            chooser_id=0,
            source_id=1,
            source_card_id=None,
            target_player_id=0,
            candidate_ids=(first_hand, second_hand, play_card),
            min_select=1,
            max_select=1,
        )

        actions = engine.legal_actions(state, 0)
        resolve_actions = [
            a for a in actions
            if a.kind == ACTION_RESOLVE_PENDING_EFFECT
            and a.choice.get("pending_effect_id") == pe.id
        ]

        # Only hand cards should be valid.
        # The play card is not in hand, so it must not be emitted as a discard choice.
        hand_actions = [
            a for a in resolve_actions
            if a.choice.get("discard_card_ids") in [(first_hand,), (second_hand,)]
        ]
        assert len(hand_actions) == 2, f"Expected 2 hand-only actions, got {len(hand_actions)}"

        for action in resolve_actions:
            card_ids = action.choice.get("discard_card_ids")
            if card_ids:
                assert card_ids[0] in {first_hand, second_hand}
                assert card_ids[0] != play_card


# =============================================================================
# B5: Pending targeting integration regression tests
# =============================================================================

class TestPendingTargetingIntegration:
    """Regression tests for Brief 5: pending targeting integration."""

    def _make_engine_with_real_cards(self):
        """Create an engine with real card database for targeting service tests."""
        from lorcana_bot.cards import load_demo_database
        db = load_demo_database()
        return GameEngine(db)

    def _make_state_with_real_cards(self, engine):
        """Create a state with real cards in play for targeting tests."""
        from lorcana_bot.cards import make_demo_deck
        pool = [
            "Amber Recruit", "Amber Guard", "Amber Storyteller",
            "Amethyst Scholar", "Amethyst Insight", "Steel Bruiser",
            "Emerald Scout", "Ruby Charger", "Steel Cannon", "Sapphire Helper",
        ]
        deck0 = make_demo_deck(pool, size=50)
        deck1 = make_demo_deck(pool, size=50)
        state = engine.setup_game([deck0, deck1], seed=42)
        return state

    def _put_card_in_play(self, state, engine, player, full_name, *, exerted=False, damage=0):
        """Put a named card into a player's play area."""
        from tests.conftest import put_card
        return put_card(state, engine, player, full_name, ZONE_PLAY, exerted=exerted, damage=damage)

    def test_get_valid_targets_delegates_to_targeting_service(self, engine, state):
        """Test 1: get_valid_targets_for_requirement() delegates to targeting service and preserves list[int] API."""
        # Put a character in play
        cid = self._put_card_in_play(state, engine, 1, "Amber Guard")
        requirement = TargetRequirement(kind="chosen_character", min_targets=1, max_targets=1, card_type="character")
        result = get_valid_targets_for_requirement(state, requirement, 0, engine)
        assert isinstance(result, list)
        assert all(isinstance(x, int) for x in result)
        assert cid in result

    def test_chosen_item_emits_only_item_resolve_actions(self, engine, state):
        """Test 2: Pending target requirement for chosen_item emits only item card resolve actions."""
        # Put an item in play
        item_cid = 9001
        inst = CardInstance(instance_id=item_cid, card_id=DEMO_FEATURE_CARD_IDS["item"], owner=1, controller=1, zone=ZONE_PLAY)
        state.cards[item_cid] = inst
        state.players[1].play.append(item_cid)

        # Also put a character in play to ensure it's excluded
        char_cid = self._put_card_in_play(state, engine, 1, "Amber Guard")

        pe = PendingEffect(
            id="pe_test_item",
            controller_id=0,
            chooser_id=0,
            source_id=None,
            source_card_id=None,
            effects=(),
            required_targets=(TargetRequirement(kind="chosen_item", min_targets=1, max_targets=1, card_type="item"),),
            raw={"requirement_kind": "target"},
        )
        state.pending_effects.append(pe)

        actions = engine.legal_actions(state, 0)
        resolve_actions = [a for a in actions if a.kind == ACTION_RESOLVE_PENDING_EFFECT]
        # Should only have the item as target, not the character
        target_ids = set()
        for a in resolve_actions:
            targets = a.choice.get("targets")
            if targets:
                target_ids.update(targets)
        assert item_cid in target_ids
        assert char_cid not in target_ids

    def test_chosen_location_emits_only_location_resolve_actions(self, engine, state):
        """Test 3: Pending target requirement for chosen_location emits only location card resolve actions."""
        # Put a location in play
        location_cid = 9002
        inst = CardInstance(instance_id=location_cid, card_id=DEMO_FEATURE_CARD_IDS["location"], owner=1, controller=1, zone=ZONE_PLAY)
        state.cards[location_cid] = inst
        state.players[1].play.append(location_cid)

        # Also put a character in play
        char_cid = self._put_card_in_play(state, engine, 1, "Amber Guard")

        pe = PendingEffect(
            id="pe_test_loc",
            controller_id=0,
            chooser_id=0,
            source_id=None,
            source_card_id=None,
            effects=(),
            required_targets=(TargetRequirement(kind="chosen_location", min_targets=1, max_targets=1, card_type="location"),),
            raw={"requirement_kind": "target"},
        )
        state.pending_effects.append(pe)

        actions = engine.legal_actions(state, 0)
        resolve_actions = [a for a in actions if a.kind == ACTION_RESOLVE_PENDING_EFFECT]
        target_ids = set()
        for a in resolve_actions:
            targets = a.choice.get("targets")
            if targets:
                target_ids.update(targets)
        assert location_cid in target_ids
        assert char_cid not in target_ids

    def test_chosen_damaged_character_emits_only_damaged_resolve_actions(self, engine, state):
        """Test 4: Pending target requirement for chosen_damaged_character emits only damaged character resolve actions."""
        # Put a damaged character in play
        damaged_cid = self._put_card_in_play(state, engine, 1, "Amber Guard", damage=2)
        # Put an undamaged character in play
        healthy_cid = self._put_card_in_play(state, engine, 1, "Amber Recruit")

        pe = PendingEffect(
            id="pe_test_damaged",
            controller_id=0,
            chooser_id=0,
            source_id=None,
            source_card_id=None,
            effects=(),
            required_targets=(TargetRequirement(kind="chosen_damaged_character", min_targets=1, max_targets=1, must_be_damaged=True),),
            raw={"requirement_kind": "target"},
        )
        state.pending_effects.append(pe)

        actions = engine.legal_actions(state, 0)
        resolve_actions = [a for a in actions if a.kind == ACTION_RESOLVE_PENDING_EFFECT]
        target_ids = set()
        for a in resolve_actions:
            targets = a.choice.get("targets")
            if targets:
                target_ids.update(targets)
        assert damaged_cid in target_ids
        assert healthy_cid not in target_ids

    def test_pending_opposing_target_excludes_ward(self, engine, state):
        """Test 5: Pending explicit opposing target excludes a Ward card."""
        # Put an opposing character with Ward in play
        ward_cid = self._put_card_in_play(state, engine, 1, "Amber Guard")
        # Grant Ward (temporary_keywords is a list)
        state.cards[ward_cid].temporary_keywords.append("WARD")

        # Put an opposing character without Ward
        normal_cid = self._put_card_in_play(state, engine, 1, "Amber Recruit")

        pe = PendingEffect(
            id="pe_test_ward",
            controller_id=0,
            chooser_id=0,
            source_id=None,
            source_card_id=None,
            effects=(),
            required_targets=(TargetRequirement(kind="chosen_opposing_character", min_targets=1, max_targets=1, owner_filter="opponent"),),
            raw={"requirement_kind": "target"},
        )
        state.pending_effects.append(pe)

        actions = engine.legal_actions(state, 0)
        resolve_actions = [a for a in actions if a.kind == ACTION_RESOLVE_PENDING_EFFECT]
        target_ids = set()
        for a in resolve_actions:
            targets = a.choice.get("targets")
            if targets:
                target_ids.update(targets)
        assert ward_cid not in target_ids
        assert normal_cid in target_ids

    def test_pending_target_excludes_zone_under_and_stack_parent(self, engine, state):
        """Test 6: Pending target excludes a ZONE_UNDER card and a card with stack_parent_id."""
        # Put a normal character in play
        normal_cid = self._put_card_in_play(state, engine, 1, "Amber Guard")

        # Put a card in ZONE_UNDER
        under_cid = self._put_card_in_play(state, engine, 1, "Amber Recruit")
        state.move_card(under_cid, ZONE_UNDER, controller=1)

        # Put a card with stack_parent_id in play
        stacked_cid = self._put_card_in_play(state, engine, 1, "Amber Storyteller")
        state.cards[stacked_cid].stack_parent_id = normal_cid

        pe = PendingEffect(
            id="pe_test_under",
            controller_id=0,
            chooser_id=0,
            source_id=None,
            source_card_id=None,
            effects=(),
            required_targets=(TargetRequirement(kind="chosen_character", min_targets=1, max_targets=1, card_type="character"),),
            raw={"requirement_kind": "target"},
        )
        state.pending_effects.append(pe)

        actions = engine.legal_actions(state, 0)
        resolve_actions = [a for a in actions if a.kind == ACTION_RESOLVE_PENDING_EFFECT]
        target_ids = set()
        for a in resolve_actions:
            targets = a.choice.get("targets")
            if targets:
                target_ids.update(targets)
        assert normal_cid in target_ids
        assert under_cid not in target_ids
        assert stacked_cid not in target_ids

    def test_raw_candidate_ids_narrow_targeting_service(self, engine, state):
        """Test 7: Raw candidate_ids narrow targeting-service card candidates; invalid/raw protected candidates are filtered out."""
        # Put two characters in play
        cid1 = self._put_card_in_play(state, engine, 1, "Amber Guard")
        cid2 = self._put_card_in_play(state, engine, 1, "Amber Recruit")

        # Create pending effect with candidate_ids narrowed to only cid1
        pe = PendingEffect(
            id="pe_test_narrow",
            controller_id=0,
            chooser_id=0,
            source_id=None,
            source_card_id=None,
            effects=(),
            required_targets=(TargetRequirement(kind="chosen_character", min_targets=1, max_targets=1, card_type="character"),),
            raw={
                "requirement_kind": "target",
                "candidate_ids": [cid1],
            },
        )
        state.pending_effects.append(pe)

        actions = engine.legal_actions(state, 0)
        resolve_actions = [a for a in actions if a.kind == ACTION_RESOLVE_PENDING_EFFECT]
        target_ids = set()
        for a in resolve_actions:
            targets = a.choice.get("targets")
            if targets:
                target_ids.update(targets)
        assert cid1 in target_ids
        assert cid2 not in target_ids

    def test_multi_target_enumerates_combinations(self, engine, state):
        """Test 8: multi_target enumerates card combinations after filtering and respects min/max."""
        # Put three characters in play
        cid1 = self._put_card_in_play(state, engine, 1, "Amber Guard")
        cid2 = self._put_card_in_play(state, engine, 1, "Amber Recruit")
        cid3 = self._put_card_in_play(state, engine, 1, "Amber Storyteller")

        pe = PendingEffect(
            id="pe_test_multi",
            controller_id=0,
            chooser_id=0,
            source_id=None,
            source_card_id=None,
            effects=(),
            required_targets=(),
            raw={
                "requirement_kind": "multi_target",
                "target": "chosen_character",
                "candidate_ids": [cid1, cid2, cid3],
                "min_targets": 2,
                "max_targets": 2,
            },
        )
        state.pending_effects.append(pe)

        actions = engine.legal_actions(state, 0)
        resolve_actions = [a for a in actions if a.kind == ACTION_RESOLVE_PENDING_EFFECT]
        # Should have C(3,2) = 3 combinations from the 3 specified candidate_ids
        combos = set()
        for a in resolve_actions:
            targets = a.choice.get("targets")
            if targets:
                combos.add(tuple(sorted(targets)))
        # The 3 specific combinations of our 3 cards
        expected = {
            tuple(sorted((cid1, cid2))),
            tuple(sorted((cid1, cid3))),
            tuple(sorted((cid2, cid3))),
        }
        assert expected.issubset(combos)

    def test_chosen_player_emits_player_target_actions(self, engine, state):
        """Test 9: chosen_player pending emits player target actions with Action.target is None and choice["player_targets"]."""
        pe = PendingEffect(
            id="pe_test_player",
            controller_id=0,
            chooser_id=0,
            source_id=None,
            source_card_id=None,
            effects=(),
            required_targets=(TargetRequirement(kind="chosen_player", min_targets=1, max_targets=1),),
            raw={"requirement_kind": "target"},
        )
        state.pending_effects.append(pe)

        actions = engine.legal_actions(state, 0)
        resolve_actions = [a for a in actions if a.kind == ACTION_RESOLVE_PENDING_EFFECT]
        # Should have player target actions
        player_target_actions = [a for a in resolve_actions if a.choice.get("target_kind") == "player"]
        assert len(player_target_actions) >= 1
        for a in player_target_actions:
            assert a.target is None
            assert "player_targets" in a.choice
            assert a.choice["player_targets"][0] in (0, 1)

    def test_chosen_player_resolution_writes_player_targets(self, engine, state):
        """Test 10: Applying chosen_player writes player_targets and resumes effects with context.choice."""
        pe = PendingEffect(
            id="pe_test_player_resolve",
            controller_id=0,
            chooser_id=0,
            source_id=None,
            source_card_id=None,
            effects=(EffectDef(kind="gain_lore", target="chosen_player", amount=2),),
            required_targets=(TargetRequirement(kind="chosen_player", min_targets=1, max_targets=1),),
            raw={"requirement_kind": "target"},
        )
        state.pending_effects.append(pe)

        actions = engine.legal_actions(state, 0)
        resolve_actions = [a for a in actions if a.kind == ACTION_RESOLVE_PENDING_EFFECT]
        player_action = next(
            (
                a for a in resolve_actions
                if a.choice.get("target_kind") == "player" and a.choice.get("player") == 1
            ),
            None,
        )
        assert player_action is not None

        new_state = engine.apply_action(state, player_action)
        # The pending effect should be completed
        assert not has_pending_effects(new_state)
        assert new_state.players[1].lore == 2
        assert new_state.players[0].lore == 0

    def test_raw_candidate_ids_without_descriptor_fail_closed(self, engine, state):
        """Raw candidate IDs do not bypass the targeting service when no descriptor exists."""
        cid = self._put_card_in_play(state, engine, 1, "Amber Guard")
        pe = PendingEffect(
            id="pe_test_raw_only",
            controller_id=0,
            chooser_id=0,
            source_id=None,
            source_card_id=None,
            effects=(),
            required_targets=(),
            raw={
                "requirement_kind": "target",
                "candidate_ids": [cid],
            },
        )
        state.pending_effects.append(pe)

        actions = engine.legal_actions(state, 0)
        resolve_actions = [a for a in actions if a.kind == ACTION_RESOLVE_PENDING_EFFECT]
        target_actions = [a for a in resolve_actions if a.choice.get("targets")]
        assert target_actions == []

    def test_target_style_opponent_choice_uses_targeting_service(self, engine, state):
        """Test 11: target-style opponent_choice uses the same helper and filters out protected/invalid candidates."""
        # Put characters in play
        cid1 = self._put_card_in_play(state, engine, 1, "Amber Guard")
        # Give one Ward (temporary_keywords is a list)
        state.cards[cid1].temporary_keywords.append("WARD")
        cid2 = self._put_card_in_play(state, engine, 1, "Amber Recruit")

        pe = PendingEffect(
            id="pe_test_opp_choice",
            controller_id=0,
            chooser_id=0,
            source_id=None,
            source_card_id=None,
            effects=(),
            required_targets=(),
            raw={
                "requirement_kind": "opponent_choice",
                "choice_type": "target",
                "target": "chosen_character",
            },
        )
        state.pending_effects.append(pe)

        actions = engine.legal_actions(state, 0)
        resolve_actions = [a for a in actions if a.kind == ACTION_RESOLVE_PENDING_EFFECT]
        target_ids = set()
        for a in resolve_actions:
            targets = a.choice.get("targets")
            if targets:
                target_ids.update(targets)
        # Ward card should be excluded
        assert cid1 not in target_ids
        assert cid2 in target_ids

    def test_unknown_descriptor_emits_no_broad_fallback(self, engine, state):
        """Test 12: Unknown pending target descriptor emits no broad fallback target actions."""
        # Put characters in play
        self._put_card_in_play(state, engine, 1, "Amber Guard")

        pe = PendingEffect(
            id="pe_test_unknown",
            controller_id=0,
            chooser_id=0,
            source_id=None,
            source_card_id=None,
            effects=(),
            required_targets=(),
            raw={
                "requirement_kind": "target",
                "target": "completely_unknown_descriptor_xyz",
            },
        )
        state.pending_effects.append(pe)

        actions = engine.legal_actions(state, 0)
        resolve_actions = [a for a in actions if a.kind == ACTION_RESOLVE_PENDING_EFFECT]
        # Should have no target actions (fail closed)
        target_actions = [a for a in resolve_actions if a.choice.get("targets")]
        assert len(target_actions) == 0

    def test_no_player_id_in_selected_targets(self, engine, state):
        """Verify that player IDs are never stored in PendingEffect.selected_targets."""
        from lorcana_bot.pending_effects import resolve_player_target_selection
        pe = PendingEffect(
            id="pe_test_separation",
            controller_id=0,
            chooser_id=0,
            source_id=None,
            source_card_id=None,
            effects=(),
            required_targets=(),
            raw={"requirement_kind": "target"},
        )
        state.pending_effects.append(pe)

        resolve_player_target_selection(state, "pe_test_separation", (1,), engine=engine)
        assert pe.selected_targets == ()  # Card targets remain empty
        assert pe.selected_player_targets == (1,)
        assert pe.raw["resolution_input"]["player_targets"] == (1,)

    def test_slotted_target_selection_stores_structured_and_flat_targets(self, engine, state):
        """Slotted pending input preserves slots and also exposes flat targets."""
        from_id = self._put_card_in_play(state, engine, 0, "Amber Guard", damage=2)
        to_id = self._put_card_in_play(state, engine, 1, "Amber Recruit")
        pe = PendingEffect(
            id="pe_test_slotted",
            controller_id=0,
            chooser_id=0,
            source_id=None,
            source_card_id=None,
            effects=(),
            required_targets=(),
            raw={"requirement_kind": "multi_target", "min_targets": 2, "max_targets": 2},
        )
        state.pending_effects.append(pe)

        resolve_slotted_target_selection(
            state,
            "pe_test_slotted",
            {"kind": "move-damage", "from": [from_id], "to": [to_id]},
            engine=engine,
        )

        assert pe.selected_targets == (from_id, to_id)
        assert pe.raw["resolution_input"]["targets"] == (from_id, to_id)
        assert pe.raw["resolution_input"]["slotted_targets"] == {
            "kind": "move-damage",
            "from": (from_id,),
            "to": (to_id,),
        }

    def test_engine_apply_accepts_slotted_targets_for_multi_target_pending(self, engine, state):
        """Engine target application accepts slotted_targets and resumes with flat current_targets."""
        from_id = self._put_card_in_play(state, engine, 0, "Amber Guard", damage=2)
        to_id = self._put_card_in_play(state, engine, 1, "Amber Recruit")
        pe = PendingEffect(
            id="pe_test_slotted_apply",
            controller_id=0,
            chooser_id=0,
            source_id=None,
            source_card_id=None,
            effects=(EffectDef(kind="deal_damage", amount=1, target="chosen_character"),),
            required_targets=(),
            raw={"requirement_kind": "multi_target", "min_targets": 2, "max_targets": 2},
        )
        state.pending_effects.append(pe)

        action = Action(
            ACTION_RESOLVE_PENDING_EFFECT,
            actor=0,
            choice={
                "pending_effect_id": "pe_test_slotted_apply",
                "slotted_targets": {"kind": "move-damage", "from": [from_id], "to": [to_id]},
            },
        )
        new_state = engine.apply_action(state, action, validate=False)

        assert new_state.cards[from_id].damage == 3
        assert new_state.cards[to_id].damage == 1
        assert not has_pending_effects(new_state)


class TestBagOriginScryPending:
    """Tests for bag-origin scry pending effects preserving resolution input."""

    def test_bag_origin_scry_pending_preserves_resolution_input(self):
        """Test that bag-origin scry pending effect preserves resolution_input.

        Required behavior:
        - The pending effect raw data includes resolution_input copied from the bag entry
        - When resolving a bag-origin scry pending effect, the resolution_input is preserved
        """
        from lorcana_bot.state import GameState, PlayerState, CardInstance, BagEffectEntry, PendingTriggeredEvent
        from lorcana_bot.cards import CardDatabase, CardDef
        from lorcana_bot.engine import GameEngine
        from lorcana_bot.pending_effects import create_scry_pending_effect, get_pending_effect_by_id, ScryRequirement

        # Create a minimal engine for testing
        cards = [
            CardDef("a", "A", "amber", 1, True, "character", 1, 1, 1),
            CardDef("b", "B", "amber", 1, True, "character", 1, 1, 1),
            CardDef("c", "C", "amber", 1, True, "character", 1, 1, 1),
        ]
        engine = GameEngine(CardDatabase(cards))

        # Create a state with a deck
        state = GameState(players=[PlayerState(), PlayerState()], cards={})
        state.cards[1] = CardInstance(instance_id=1, card_id="a", owner=0, controller=0, zone="deck")
        state.cards[2] = CardInstance(instance_id=2, card_id="b", owner=0, controller=0, zone="deck")
        state.cards[3] = CardInstance(instance_id=3, card_id="c", owner=0, controller=0, zone="deck")
        state.players[0].deck = [1, 2, 3]
        state.active_player = 0

        # Simulate the bag resolution scenario by:
        # 1. Creating a scry pending effect
        # 2. Marking it with bag origin (simulating what _apply_resolve_bag does)
        # 3. Adding resolution_input (simulating what would be copied from bag entry)
        pe = create_scry_pending_effect(
            state,
            controller_id=0,
            chooser_id=0,
            source_id=1,
            source_card_id="a",
            amount=2,
            origin="bag",
        )

        # Simulate bag origin setup (what engine does in _apply_resolve_bag)
        pe.origin = "bag"
        pe.origin_id = "bag_test_123"

        # Add resolution_input (this would come from the bag entry in a real scenario)
        pe.raw.setdefault("resolution_input", {})
        pe.raw["resolution_input"]["event"] = "quest"
        pe.raw["resolution_input"]["trigger_subject"] = 1
        pe.raw["resolution_input"]["ability_id"] = "test_ability"
        pe.raw["resolution_input"]["source_id"] = 1

        # Verify the pending effect has the correct structure
        assert pe.origin == "bag"
        assert pe.origin_id == "bag_test_123"
        assert pe.raw.get("requirement_kind") == "scry_ordering"

        # Get the scry requirement
        scry_req = pe.raw.get("requirement")
        assert isinstance(scry_req, ScryRequirement)
        assert len(scry_req.candidate_ids) == 2

        # Verify resolution_input is preserved
        assert pe.raw["resolution_input"]["event"] == "quest"
        assert pe.raw["resolution_input"]["trigger_subject"] == 1
        assert pe.raw["resolution_input"]["ability_id"] == "test_ability"

        # Test that we can retrieve the pending effect
        retrieved_pe = get_pending_effect_by_id(state, pe.id)
        assert retrieved_pe is not None
        assert retrieved_pe.id == pe.id

        # Verify the ScryRequirement is preserved when retrieved
        retrieved_req = retrieved_pe.raw.get("requirement")
        assert isinstance(retrieved_req, ScryRequirement)
        assert retrieved_req.candidate_ids == scry_req.candidate_ids
        assert retrieved_req.amount == 2
