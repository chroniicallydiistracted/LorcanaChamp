from __future__ import annotations

from lorcana_bot.actions import Action
from lorcana_bot.cards import CardDatabase, CardDef, EffectDef
from lorcana_bot.constants import (
    ACTION_CHALLENGE,
    ACTION_PLAY_CARD,
    EVENT_CARD_DISCARDED,
    EVENT_CARD_EXERTED,
    EVENT_CARD_READIED,
    EVENT_CARD_RETURNED_TO_HAND,
    EVENT_CHARACTER_BANISHED,
    EVENT_LORE_GAINED,
    EVENT_LORE_LOST,
    ZONE_DECK,
    ZONE_DISCARD,
    ZONE_HAND,
    ZONE_PLAY,
)
from lorcana_bot.effect_types import EffectResolutionContext
from lorcana_bot.engine import GameEngine
from lorcana_bot.replacement_effects import ReplacementEffectEntry, ReplacementEffectType
from lorcana_bot.static_effects import create_keyword_grant_effect
from tests.conftest import add_ready_ink, put_card


def find_action(actions: list[Action], kind: str, **kwargs) -> Action:
    for action in actions:
        if action.kind != kind:
            continue
        if all(getattr(action, key) == value for key, value in kwargs.items()):
            return action
    raise AssertionError(f"Missing action {kind} {kwargs}; got {[a.compact() for a in actions]}")


def effects_db() -> CardDatabase:
    return CardDatabase(
        [
            CardDef("filler", "Filler", "amber", 1, True, "character", 1, 2, 1),
            CardDef("ally", "Ally", "amber", 1, True, "character", 1, 4, 1),
            CardDef("target", "Target", "steel", 1, True, "character", 1, 4, 1),
            CardDef("big", "Big Character", "amber", 3, True, "character", 3, 3, 1),
            CardDef("draw_lore", "Draw Lore", "amber", 0, True, "action", effects=(EffectDef("sequence", effects=(EffectDef("draw", 2), EffectDef("gain_lore", 2))),)),
            CardDef("lore_loss", "Lore Loss", "amber", 0, True, "action", effects=(EffectDef("lose_lore", 2, "opponent"),)),
            CardDef("bolt", "Scripted Bolt", "steel", 0, True, "action", effects=(EffectDef("deal_damage", 2, "chosen_character"),)),
            CardDef("repair", "Repair", "amber", 0, True, "action", effects=(EffectDef("remove_damage", 2, "chosen_character"),)),
            CardDef("banish", "Banish It", "steel", 0, True, "action", effects=(EffectDef("banish", target="chosen_character"),)),
            CardDef("return", "Return It", "amethyst", 0, True, "action", effects=(EffectDef("return_to_hand", target="chosen_character"),)),
            CardDef("ready", "Ready It", "sapphire", 0, True, "action", effects=(EffectDef("ready", target="chosen_character"),)),
            CardDef("exert", "Exert It", "ruby", 0, True, "action", effects=(EffectDef("exert", target="chosen_character"),)),
            CardDef("discard", "Discard One", "emerald", 0, True, "action", effects=(EffectDef("discard", 1, "opponent"),)),
            CardDef("discount", "Discount", "sapphire", 0, True, "action", effects=(EffectDef("cost_reduction", 2, value="character"),)),
            CardDef("grant_rush", "Grant Rush", "ruby", 0, True, "action", effects=(EffectDef("keyword_grant", target="chosen_character", keyword="Rush"),)),
            CardDef("pump", "Pump", "steel", 0, True, "action", effects=(EffectDef("temporary_modifier", target="chosen_character", value={"strength": 2}),)),
            CardDef("choice", "Choice", "amber", 0, True, "action", effects=(EffectDef("choice", effects=(EffectDef("gain_lore", 1), EffectDef("draw", 1)), value=0),)),
            CardDef("optional", "Optional", "amber", 0, True, "action", effects=(EffectDef("optional", effects=(EffectDef("gain_lore", 3),), optional=True, value="gain_three"),)),
            CardDef("foreach", "For Each", "amber", 0, True, "action", effects=(EffectDef("for_each", value="your_characters", effects=(EffectDef("ready", target="target"),)),)),
        ]
    )


def setup_effect_game() -> tuple[GameEngine, object]:
    db = effects_db()
    engine = GameEngine(db)
    deck = [
        "Filler",
        "Ally",
        "Target",
        "Big Character",
        "Draw Lore",
        "Lore Loss",
        "Scripted Bolt",
        "Repair",
        "Banish It",
        "Return It",
        "Ready It",
        "Exert It",
        "Discard One",
        "Discount",
        "Grant Rush",
        "Pump",
        "Choice",
        "Optional",
        "For Each",
    ] * 4
    return engine, engine.setup_game([deck, deck], seed=5)


def test_sequence_draw_gain_lore_and_lose_lore_resolve_through_engine():
    engine, state = setup_effect_game()
    draw_lore = put_card(state, engine, 0, "Draw Lore", ZONE_HAND)
    hand_before = len(state.players[0].hand)
    state = engine.apply_action(state, find_action(engine.legal_actions(state), ACTION_PLAY_CARD, card=draw_lore))

    assert len(state.players[0].hand) == hand_before + 1
    assert state.players[0].lore == 2
    gain_event = next(event for event in reversed(state.event_log) if event.event_type == EVENT_LORE_GAINED)
    assert gain_event.payload["player_id"] == 0
    assert gain_event.payload["lore_gained"] == 2

    state.players[1].lore = 5
    lore_loss = put_card(state, engine, 0, "Lore Loss", ZONE_HAND)
    state = engine.apply_action(state, find_action(engine.legal_actions(state), ACTION_PLAY_CARD, card=lore_loss))

    assert state.players[1].lore == 3
    loss_event = next(event for event in reversed(state.event_log) if event.event_type == EVENT_LORE_LOST)
    assert loss_event.payload["player_id"] == 1
    assert loss_event.payload["lore_lost"] == 2


def test_damage_remove_damage_banish_and_return_to_hand_effects():
    engine, state = setup_effect_game()
    target = put_card(state, engine, 1, "Target", ZONE_PLAY, exerted=True, drying=False)

    bolt = put_card(state, engine, 0, "Scripted Bolt", ZONE_HAND)
    state = engine.apply_action(state, find_action(engine.legal_actions(state), ACTION_PLAY_CARD, card=bolt, target=target))
    assert state.cards[target].damage == 2

    repair = put_card(state, engine, 0, "Repair", ZONE_HAND)
    state = engine.apply_action(state, find_action(engine.legal_actions(state), ACTION_PLAY_CARD, card=repair, target=target))
    assert state.cards[target].damage == 0

    return_it = put_card(state, engine, 0, "Return It", ZONE_HAND)
    state = engine.apply_action(state, find_action(engine.legal_actions(state), ACTION_PLAY_CARD, card=return_it, target=target))
    assert target in state.players[1].hand
    return_event = next(event for event in reversed(state.event_log) if event.event_type == EVENT_CARD_RETURNED_TO_HAND)
    assert return_event.payload["subject_card_id"] == target
    assert return_event.payload["from_zone"] == ZONE_PLAY
    assert return_event.payload["to_zone"] == ZONE_HAND

    target = put_card(state, engine, 1, "Target", ZONE_PLAY, exerted=True, drying=False)
    state.static_effect_registry.register_effect(create_keyword_grant_effect(source_id=target, keyword="bodyguard"))
    state.replacement_effect_registry.register_effect(
        ReplacementEffectEntry(
            source_id=target,
            effect_type=ReplacementEffectType.PREVENT_DAMAGE,
            target_mode="self",
            amount=1,
        )
    )
    banish = put_card(state, engine, 0, "Banish It", ZONE_HAND)
    state = engine.apply_action(state, find_action(engine.legal_actions(state), ACTION_PLAY_CARD, card=banish, target=target))
    assert target in state.players[1].discard
    assert state.static_effect_registry.effects == []
    assert state.replacement_effect_registry.effects == []
    banish_event = next(event for event in reversed(state.event_log) if event.event_type == EVENT_CHARACTER_BANISHED)
    assert banish_event.payload["subject_card_id"] == target
    assert banish_event.payload["from_zone"] == ZONE_PLAY
    assert banish_event.payload["to_zone"] == "discard"


def test_ready_exert_discard_and_for_each_effects():
    engine, state = setup_effect_game()
    ally = put_card(state, engine, 0, "Ally", ZONE_PLAY, exerted=False, drying=False)
    target = put_card(state, engine, 1, "Target", ZONE_PLAY, exerted=True, drying=False)

    exert = put_card(state, engine, 0, "Exert It", ZONE_HAND)
    state = engine.apply_action(state, find_action(engine.legal_actions(state), ACTION_PLAY_CARD, card=exert, target=ally))
    assert state.cards[ally].exerted is True
    exert_event = next(event for event in reversed(state.event_log) if event.event_type == EVENT_CARD_EXERTED)
    assert exert_event.payload["subject_card_id"] == ally

    ready = put_card(state, engine, 0, "Ready It", ZONE_HAND)
    state = engine.apply_action(state, find_action(engine.legal_actions(state), ACTION_PLAY_CARD, card=ready, target=ally))
    assert state.cards[ally].exerted is False
    ready_event = next(event for event in reversed(state.event_log) if event.event_type == EVENT_CARD_READIED)
    assert ready_event.payload["subject_card_id"] == ally

    opponent_hand_before = len(state.players[1].hand)
    discard = put_card(state, engine, 0, "Discard One", ZONE_HAND)
    state = engine.apply_action(state, find_action(engine.legal_actions(state), ACTION_PLAY_CARD, card=discard))
    assert len(state.players[1].hand) == opponent_hand_before - 1
    discard_event = next(event for event in reversed(state.event_log) if event.event_type == EVENT_CARD_DISCARDED)
    assert discard_event.payload["player_id"] == 1
    assert discard_event.payload["from_zone"] == ZONE_HAND
    assert discard_event.payload["to_zone"] == "discard"

    state.cards[ally].exerted = True
    foreach = put_card(state, engine, 0, "For Each", ZONE_HAND)
    state = engine.apply_action(state, find_action(engine.legal_actions(state), ACTION_PLAY_CARD, card=foreach))
    assert state.cards[ally].exerted is False
    assert state.cards[target].exerted is True


def test_cost_reduction_keyword_grant_and_temporary_modifier_affect_legal_play_and_challenge():
    engine, state = setup_effect_game()
    discount = put_card(state, engine, 0, "Discount", ZONE_HAND)
    big = put_card(state, engine, 0, "Big Character", ZONE_HAND, exclude=frozenset({discount}))
    add_ready_ink(state, engine, 0, 1, exclude=frozenset({discount, big}))

    assert not any(action.kind == ACTION_PLAY_CARD and action.card == big for action in engine.legal_actions(state))
    state = engine.apply_action(state, find_action(engine.legal_actions(state), ACTION_PLAY_CARD, card=discount))
    state = engine.apply_action(state, find_action(engine.legal_actions(state), ACTION_PLAY_CARD, card=big))
    assert big in state.players[0].play

    drying_ally = put_card(state, engine, 0, "Ally", ZONE_PLAY, drying=True, exclude=frozenset({big}))
    target = put_card(state, engine, 1, "Target", ZONE_PLAY, exerted=True, drying=False)
    grant_rush = put_card(state, engine, 0, "Grant Rush", ZONE_HAND)
    state = engine.apply_action(state, find_action(engine.legal_actions(state), ACTION_PLAY_CARD, card=grant_rush, target=drying_ally))
    assert "RUSH" in engine.keywords_for_instance(state, drying_ally)
    assert any(action.kind == ACTION_CHALLENGE and action.source == drying_ally and action.target == target for action in engine.legal_actions(state))

    pump = put_card(state, engine, 0, "Pump", ZONE_HAND)
    state = engine.apply_action(state, find_action(engine.legal_actions(state), ACTION_PLAY_CARD, card=pump, target=drying_ally))
    state = engine.apply_action(state, find_action(engine.legal_actions(state), ACTION_CHALLENGE, source=drying_ally, target=target))
    assert state.cards[target].damage == 3


def test_choice_optional_and_conditional_control_flow_are_declarative():
    engine, state = setup_effect_game()
    choice = put_card(state, engine, 0, "Choice", ZONE_HAND)
    state = engine.apply_action(state, find_action(engine.legal_actions(state), ACTION_PLAY_CARD, card=choice))
    assert state.players[0].lore == 1

    optional = EffectDef("optional", effects=(EffectDef("gain_lore", 5),), optional=True, value="skip_lore")
    engine.effect_resolver.resolve(state, optional, EffectResolutionContext(actor=0, optional_choices={"skip_lore": False}))
    assert state.players[0].lore == 1

    conditional = EffectDef(
        "conditional",
        condition={"kind": "has_lore_at_least", "player": "actor", "amount": 1},
        effects=(EffectDef("gain_lore", 2),),
    )
    engine.effect_resolver.resolve(state, conditional, EffectResolutionContext(actor=0))
    assert state.players[0].lore == 3


class TestEventContextTargets:
    """Tests for trigger context targets in effects."""

    def test_self_target_uses_source(self):
        """self target should resolve to context.source."""
        engine, state = setup_effect_game()
        ally = put_card(state, engine, 0, "Ally", ZONE_PLAY, exerted=False, drying=False)
        state.cards[ally].damage = 3

        # Use deal_damage with self target - should damage the source
        effect = EffectDef("deal_damage", 2, "self")
        engine.effect_resolver.resolve(
            state, effect,
            EffectResolutionContext(actor=0, source=ally)
        )
        assert state.cards[ally].damage == 5

    def test_trigger_subject_target(self):
        """trigger_subject target should resolve to context.trigger_subject."""
        engine, state = setup_effect_game()
        ally = put_card(state, engine, 0, "Ally", ZONE_PLAY, exerted=False, drying=False)
        target = put_card(state, engine, 1, "Target", ZONE_PLAY, exerted=True, drying=False)

        # Use deal_damage with trigger_subject target
        effect = EffectDef("deal_damage", 2, "trigger_subject")
        engine.effect_resolver.resolve(
            state, effect,
            EffectResolutionContext(actor=0, source=ally, trigger_subject=target)
        )
        assert state.cards[target].damage == 2

    def test_your_other_characters_excludes_source(self):
        """your_other_characters should exclude the source."""
        engine, state = setup_effect_game()
        ally1 = put_card(state, engine, 0, "Ally", ZONE_PLAY, exerted=False, drying=False)
        ally2 = put_card(state, engine, 0, "Filler", ZONE_PLAY, exerted=False, drying=False)

        # Use for_each with your_other_characters
        effect = EffectDef("for_each", value="your_other_characters", effects=(EffectDef("exert", target="target"),))
        context = EffectResolutionContext(actor=0, source=ally1)

        before_exerted = {cid: state.cards[cid].exerted for cid in [ally1, ally2]}
        engine.effect_resolver.resolve(state, effect, context)

        # ally1 (source) should NOT be exerted
        assert state.cards[ally1].exerted == before_exerted[ally1]
        # ally2 (other) SHOULD be exerted
        assert state.cards[ally2].exerted == True

    def test_opposing_characters_targets_opponent(self):
        """opposing_characters should target opponent's characters."""
        engine, state = setup_effect_game()
        ally = put_card(state, engine, 0, "Ally", ZONE_PLAY, exerted=False, drying=False)
        target = put_card(state, engine, 1, "Target", ZONE_PLAY, exerted=True, drying=False)

        # Use deal_damage with opposing_characters
        effect = EffectDef("deal_damage", 1, "opposing_characters")
        engine.effect_resolver.resolve(
            state, effect,
            EffectResolutionContext(actor=0, source=ally)
        )
        # Target (opponent character) should have damage
        assert state.cards[target].damage == 1
        # Ally (own character) should not have damage added
        assert state.cards[ally].damage == 0

    def test_all_characters_targets_both_players(self):
        """all_characters should target characters from both players."""
        engine, state = setup_effect_game()
        ally = put_card(state, engine, 0, "Ally", ZONE_PLAY, exerted=False, drying=False)
        target = put_card(state, engine, 1, "Target", ZONE_PLAY, exerted=True, drying=False)

        # Use deal_damage with all_characters
        effect = EffectDef("deal_damage", 1, "all_characters")
        engine.effect_resolver.resolve(
            state, effect,
            EffectResolutionContext(actor=0, source=ally)
        )
        # Both should have damage
        assert state.cards[ally].damage == 1
        assert state.cards[target].damage == 1

    def test_chosen_character_consumes_all_current_targets(self):
        """chosen_character should consume all selected current_targets, not only context.target."""
        engine, state = setup_effect_game()
        ally = put_card(state, engine, 0, "Ally", ZONE_PLAY, exerted=False, drying=False)
        target = put_card(state, engine, 1, "Target", ZONE_PLAY, exerted=True, drying=False)

        effect = EffectDef("deal_damage", 1, "chosen_character")
        engine.effect_resolver.resolve(
            state,
            effect,
            EffectResolutionContext(actor=0, source=ally, current_targets=(ally, target)),
        )

        assert state.cards[ally].damage == 1
        assert state.cards[target].damage == 1

    def test_current_targets_are_validated_by_descriptor(self):
        """Selected IDs still pass through target descriptor validation."""
        engine, state = setup_effect_game()
        ally = put_card(state, engine, 0, "Ally", ZONE_PLAY, exerted=False, drying=False)
        hand_card = put_card(state, engine, 0, "Target", ZONE_HAND, exerted=False, drying=False)

        effect = EffectDef("deal_damage", 1, "chosen_character")
        engine.effect_resolver.resolve(
            state,
            effect,
            EffectResolutionContext(actor=0, source=ally, current_targets=(ally, hand_card)),
        )

        assert state.cards[ally].damage == 1
        assert state.cards[hand_card].damage == 0

    def test_context_targets_selector_uses_context_target_set(self):
        """context_targets should resolve through the targeting service candidate path."""
        engine, state = setup_effect_game()
        ally = put_card(state, engine, 0, "Ally", ZONE_PLAY, exerted=False, drying=False)
        target = put_card(state, engine, 1, "Target", ZONE_PLAY, exerted=True, drying=False)

        effect = EffectDef("deal_damage", 2, "context_targets")
        engine.effect_resolver.resolve(
            state,
            effect,
            EffectResolutionContext(actor=0, source=ally, context_targets=(target,)),
        )

        assert state.cards[target].damage == 2
        assert state.cards[ally].damage == 0


class TestEventPayloadTargets:
    """Tests for event_payload-based targets."""

    def test_event_target_from_payload(self):
        """event_target should use event_payload event_target_id if present."""
        engine, state = setup_effect_game()
        ally = put_card(state, engine, 0, "Ally", ZONE_PLAY, exerted=False, drying=False)
        target = put_card(state, engine, 1, "Target", ZONE_PLAY, exerted=True, drying=False)

        # Use deal_damage with event_target that has payload
        effect = EffectDef("deal_damage", 2, "event_target")
        context = EffectResolutionContext(
            actor=0,
            source=ally,
            target=None,  # No direct target
            event_payload={"event_target_id": target}  # Payload has target
        )
        engine.effect_resolver.resolve(state, effect, context)

        assert state.cards[target].damage == 2

    def test_trigger_source_target(self):
        """trigger_source should resolve to context.trigger_source."""
        engine, state = setup_effect_game()
        ally = put_card(state, engine, 0, "Ally", ZONE_PLAY, exerted=False, drying=False)
        target = put_card(state, engine, 1, "Target", ZONE_PLAY, exerted=True, drying=False)

        # Use deal_damage with trigger_source (self, essentially)
        effect = EffectDef("deal_damage", 3, "event_source")
        context = EffectResolutionContext(
            actor=0,
            source=ally,
            trigger_source=ally  # Explicit trigger source
        )
        engine.effect_resolver.resolve(state, effect, context)

        assert state.cards[ally].damage == 3


class TestPlayerTargets:
    """Tests for player-based targets in triggers."""

    def test_controller_target(self):
        """controller target should resolve to context.actor."""
        engine, state = setup_effect_game()
        initial_lore = state.players[0].lore

        # Use gain_lore with controller target
        effect = EffectDef("gain_lore", 3, "controller")
        engine.effect_resolver.resolve(
            state, effect,
            EffectResolutionContext(actor=0)
        )
        assert state.players[0].lore == initial_lore + 3

    def test_opponent_target(self):
        """opponent target should resolve to opponent player."""
        engine, state = setup_effect_game()
        state.players[1].lore = 5
        initial_lore = state.players[1].lore

        # Use lose_lore with opponent target
        effect = EffectDef("lose_lore", 2, "opponent")
        engine.effect_resolver.resolve(
            state, effect,
            EffectResolutionContext(actor=0)
        )
        assert state.players[1].lore == initial_lore - 2

    def test_you_target_alias(self):
        """you target should resolve to context.actor."""
        engine, state = setup_effect_game()
        initial_lore = state.players[0].lore

        # Use draw with you target (draws for you)
        effect = EffectDef("draw", 2, "you")
        hand_before = len(state.players[0].hand)
        engine.effect_resolver.resolve(
            state, effect,
            EffectResolutionContext(actor=0)
        )
        assert len(state.players[0].hand) == hand_before + 2

    def test_chosen_player_target_uses_context_choice(self):
        """chosen_player should validate context.choice and resolve that player."""
        engine, state = setup_effect_game()

        effect = EffectDef("gain_lore", 2, "chosen_player")
        engine.effect_resolver.resolve(
            state,
            effect,
            EffectResolutionContext(actor=0, choice=1),
        )

        assert state.players[1].lore == 2
        assert state.players[0].lore == 0


class TestEffectHelperRouting:
    """Regression tests verifying core effect kinds route through engine-owned helpers.

    These tests spy on the _*_eventful helper methods to prove the effect resolver
    delegates to the engine boundary rather than mutating state directly.
    """

    def test_gain_lore_routes_through_engine_helper(self):
        """gain_lore effect must call _gain_lore_eventful with correct parameters."""
        engine, state = setup_effect_game()
        original = engine._gain_lore_eventful
        calls = []

        def spy(*args, **kwargs):
            calls.append((args, kwargs))
            return original(*args, **kwargs)

        engine._gain_lore_eventful = spy

        effect = EffectDef("gain_lore", 2, "you")
        engine.effect_resolver.resolve(state, effect, EffectResolutionContext(actor=0, source=1))

        assert len(calls) == 1
        args, kwargs = calls[0]
        assert args[0] is state  # state
        assert args[1] == 0     # player
        assert args[2] == 2      # amount
        assert kwargs.get("source_id") == 1

    def test_lose_lore_routes_through_engine_helper(self):
        """lose_lore effect must call _lose_lore_eventful with correct parameters."""
        engine, state = setup_effect_game()
        state.players[1].lore = 5
        original = engine._lose_lore_eventful
        calls = []

        def spy(*args, **kwargs):
            calls.append((args, kwargs))
            return original(*args, **kwargs)

        engine._lose_lore_eventful = spy

        effect = EffectDef("lose_lore", 2, "opponent")
        engine.effect_resolver.resolve(state, effect, EffectResolutionContext(actor=0, source=2))

        assert len(calls) == 1
        args, kwargs = calls[0]
        assert args[0] is state
        assert args[1] == 1     # opponent
        assert args[2] == 2      # amount
        assert kwargs.get("source_id") == 2

    def test_deal_damage_routes_through_engine_helper(self):
        """deal_damage effect must call _deal_damage_eventful with is_challenge=False, apply_resist=True."""
        engine, state = setup_effect_game()
        target = put_card(state, engine, 1, "Target", ZONE_PLAY, exerted=True, drying=False)

        original = engine._deal_damage_eventful
        calls = []

        def spy(*args, **kwargs):
            calls.append((args, kwargs))
            return original(*args, **kwargs)

        engine._deal_damage_eventful = spy

        effect = EffectDef("deal_damage", 3, "chosen_character")
        engine.effect_resolver.resolve(
            state, effect,
            EffectResolutionContext(actor=0, source=5, target=target)
        )

        assert len(calls) == 1
        args, kwargs = calls[0]
        assert args[0] is state
        assert kwargs.get("target_id") == target
        assert kwargs.get("source_id") == 5
        assert kwargs.get("amount") == 3
        assert kwargs.get("is_challenge") is False
        assert kwargs.get("apply_resist") is True
        assert kwargs.get("actor") == 0

    def test_remove_damage_routes_through_engine_helper(self):
        """remove_damage effect must call _remove_damage_eventful with correct parameters."""
        engine, state = setup_effect_game()
        target = put_card(state, engine, 1, "Target", ZONE_PLAY, exerted=True, drying=False, damage=5)

        original = engine._remove_damage_eventful
        calls = []

        def spy(*args, **kwargs):
            calls.append((args, kwargs))
            return original(*args, **kwargs)

        engine._remove_damage_eventful = spy

        effect = EffectDef("remove_damage", 2, "chosen_character")
        engine.effect_resolver.resolve(
            state, effect,
            EffectResolutionContext(actor=0, source=6, target=target)
        )

        assert len(calls) == 1
        args, kwargs = calls[0]
        assert args[0] is state  # state
        assert args[1] == target  # card_id
        assert args[2] == 2       # amount
        assert kwargs.get("actor") == 0
        assert kwargs.get("source_id") == 6

    def test_banish_routes_through_engine_helper(self):
        """banish effect must call _banish_eventful with reason='effect'."""
        engine, state = setup_effect_game()
        target = put_card(state, engine, 1, "Target", ZONE_PLAY, exerted=True, drying=False)

        original = engine._banish_eventful
        calls = []

        def spy(*args, **kwargs):
            calls.append((args, kwargs))
            return original(*args, **kwargs)

        engine._banish_eventful = spy

        effect = EffectDef("banish", target="chosen_character")
        engine.effect_resolver.resolve(
            state, effect,
            EffectResolutionContext(actor=0, source=7, target=target)
        )

        assert len(calls) == 1
        args, kwargs = calls[0]
        assert args[0] is state
        assert args[1] == target  # card_id
        assert kwargs.get("actor") == 0
        assert kwargs.get("source_id") == 7
        assert kwargs.get("reason") == "effect"

    def test_discard_routes_through_engine_helper(self):
        """discard effect must call _discard_eventful with reason='effect'."""
        engine, state = setup_effect_game()
        # Put target card in opponent's hand
        target = put_card(state, engine, 1, "Target", ZONE_HAND)
        opponent_hand_before = set(state.players[1].hand)

        original = engine._discard_eventful
        calls = []

        def spy(*args, **kwargs):
            calls.append((args, kwargs))
            return original(*args, **kwargs)

        engine._discard_eventful = spy

        # Discard from opponent's hand (random card since "opponent" target)
        effect = EffectDef("discard", 1, "opponent")
        engine.effect_resolver.resolve(
            state, effect,
            EffectResolutionContext(actor=0, source=8)
        )

        assert len(calls) == 1
        args, kwargs = calls[0]
        assert args[0] is state
        # Verify the discarded card was from opponent's hand before the call
        discarded_card = args[1]
        assert discarded_card in opponent_hand_before
        assert kwargs.get("reason") == "effect"

    def test_discard_random_routes_through_engine_helper(self):
        """discard effect with no specific target must call _discard_eventful for random cards."""
        engine, state = setup_effect_game()
        initial_hand_size = len(state.players[1].hand)

        original = engine._discard_eventful
        calls = []

        def spy(*args, **kwargs):
            calls.append((args, kwargs))
            return original(*args, **kwargs)

        engine._discard_eventful = spy

        # Discard 2 random cards from opponent
        effect = EffectDef("discard", 2, "opponent")
        engine.effect_resolver.resolve(state, effect, EffectResolutionContext(actor=0, source=9))

        # Should have called _discard_eventful twice for random selection
        assert len(calls) == 2
        for args, kwargs in calls:
            assert args[0] is state
            assert kwargs.get("reason") == "effect"

    def test_return_to_hand_routes_through_engine_helper(self):
        """return_to_hand effect must call _return_to_hand_eventful with correct parameters."""
        engine, state = setup_effect_game()
        target = put_card(state, engine, 1, "Target", ZONE_PLAY, exerted=True, drying=False)

        original = engine._return_to_hand_eventful
        calls = []

        def spy(*args, **kwargs):
            calls.append((args, kwargs))
            return original(*args, **kwargs)

        engine._return_to_hand_eventful = spy

        effect = EffectDef("return_to_hand", target="chosen_character")
        engine.effect_resolver.resolve(
            state, effect,
            EffectResolutionContext(actor=0, source=10, target=target)
        )

        assert len(calls) == 1
        args, kwargs = calls[0]
        assert args[0] is state
        assert args[1] == target  # card_id
        assert kwargs.get("actor") == 0
        assert kwargs.get("source_id") == 10

    def test_ready_routes_through_engine_helper(self):
        """ready effect must call _ready_eventful with correct parameters."""
        engine, state = setup_effect_game()
        target = put_card(state, engine, 0, "Ally", ZONE_PLAY, exerted=True, drying=False)

        original = engine._ready_eventful
        calls = []

        def spy(*args, **kwargs):
            calls.append((args, kwargs))
            return original(*args, **kwargs)

        engine._ready_eventful = spy

        effect = EffectDef("ready", target="chosen_character")
        engine.effect_resolver.resolve(
            state, effect,
            EffectResolutionContext(actor=0, source=11, target=target)
        )

        assert len(calls) == 1
        args, kwargs = calls[0]
        assert args[0] is state
        assert args[1] == target  # card_id
        assert kwargs.get("actor") == 0
        assert kwargs.get("source_id") == 11

    def test_exert_routes_through_engine_helper(self):
        """exert effect must call _exert_eventful with reason='effect'."""
        engine, state = setup_effect_game()
        target = put_card(state, engine, 0, "Ally", ZONE_PLAY, exerted=False, drying=False)

        original = engine._exert_eventful
        calls = []

        def spy(*args, **kwargs):
            calls.append((args, kwargs))
            return original(*args, **kwargs)

        engine._exert_eventful = spy

        effect = EffectDef("exert", target="chosen_character")
        engine.effect_resolver.resolve(
            state, effect,
            EffectResolutionContext(actor=0, source=12, target=target)
        )

        assert len(calls) == 1
        args, kwargs = calls[0]
        assert args[0] is state
        assert args[1] == target  # card_id
        assert kwargs.get("actor") == 0
        assert kwargs.get("source_id") == 12
        assert kwargs.get("reason") == "effect"


class TestEffectDrawPrivacy:
    """Tests for effect-driven draw privacy boundaries."""

    def test_effect_draw_emits_private_event_without_card_ids(self):
        """
        Effect-driven draws must emit private CARD_DRAWN events.

        This test proves that draw effects do not leak drawn card identities
        to opponents. The event payload should contain count/private metadata
        but must NOT include card_ids.
        """
        from lorcana_bot.constants import EVENT_CARD_DRAWN

        engine, state = setup_effect_game()

        # Use draw effect (2 cards)
        effect = EffectDef("draw", 2, "you")
        hand_before = len(state.players[0].hand)

        engine.effect_resolver.resolve(
            state, effect,
            EffectResolutionContext(actor=0)
        )

        # Cards should be in hand
        assert len(state.players[0].hand) == hand_before + 2

        # Find the CARD_DRAWN event
        draw_events = [e for e in state.event_log if e.event_type == EVENT_CARD_DRAWN]
        assert len(draw_events) >= 1
        draw_event = draw_events[-1]  # Most recent draw event

        # The event should be private
        assert draw_event.payload.get("private") is True

        # The event should have count
        assert draw_event.payload.get("count") == 2

        # The event must NOT have card_ids (privacy boundary)
        assert "card_ids" not in draw_event.payload

    def test_engine_draw_with_private_false_includes_card_ids(self):
        """
        Direct engine draw_cards with private=False should include card_ids.

        This test preserves the existing behavior that explicit non-private
        draws (like turn-start draws) still include card IDs.
        """
        from lorcana_bot.constants import EVENT_CARD_DRAWN

        engine, state = setup_effect_game()

        hand_before = len(state.players[0].hand)

        # Call engine directly with private=False (default)
        drawn_ids = engine.draw_cards(state, player=0, count=2, private=False)

        # Cards should be in hand
        assert len(state.players[0].hand) == hand_before + 2

        # Find the CARD_DRAWN event
        draw_events = [e for e in state.event_log if e.event_type == EVENT_CARD_DRAWN]
        assert len(draw_events) >= 1
        draw_event = draw_events[-1]

        # The event should NOT be private
        assert draw_event.payload.get("private") is False

        # The event should have count
        assert draw_event.payload.get("count") == 2

        # The event must have card_ids for non-private draws
        assert "card_ids" in draw_event.payload
        assert len(draw_event.payload["card_ids"]) == 2
        assert drawn_ids == draw_event.payload["card_ids"]


class TestZoneRoutingEffectRegression:
    """Regression tests proving zone-routing effect helpers call GameEngine._move_card_eventful.

    These tests verify that every zone-routing effect helper in EffectResolver delegates
    to the engine's _move_card_eventful boundary rather than mutating state directly.
    """

    def _spy_move_card(self, engine):
        """Install spy on _move_card_eventful and return call tracker."""
        original = engine._move_card_eventful
        calls = []

        def spy(*args, **kwargs):
            calls.append((args, kwargs))
            return original(*args, **kwargs)

        engine._move_card_eventful = spy
        return calls

    def _find_top_card(self, state, player):
        """Find the top card of player's deck (index 0)."""
        if state.players[player].deck:
            return state.players[player].deck[0]
        return None

    def test_reveal_top_card_routes_to_hand_via_engine(self):
        """reveal_top_card effect with destination='hand' must call _move_card_eventful."""
        engine, state = setup_effect_game()

        # Get the actual top card of deck (don't move it, just reference)
        top_card_id = self._find_top_card(state, 0)
        assert top_card_id is not None

        calls = self._spy_move_card(engine)

        # Reveal top card and route to hand
        effect = EffectDef("reveal_top_card", amount=1, value="hand")
        engine.effect_resolver.resolve(
            state, effect,
            EffectResolutionContext(actor=0, source=1)
        )

        # Must have called _move_card_eventful at least once
        assert len(calls) >= 1
        # Check first call - should be moving top card to hand
        first_call = calls[0]
        args, kwargs = first_call
        assert args[0] is state
        assert args[1] == top_card_id           # card_id
        assert args[2] == ZONE_HAND               # destination zone
        assert kwargs.get("actor") == 0            # resolving player
        assert kwargs.get("source_id") == 1       # source preserved

    def test_reveal_top_card_routes_to_discard_via_engine(self):
        """reveal_top_card effect with destination='discard' must call _move_card_eventful."""
        engine, state = setup_effect_game()

        top_card_id = self._find_top_card(state, 0)
        assert top_card_id is not None

        calls = self._spy_move_card(engine)

        effect = EffectDef("reveal_top_card", amount=1, value="discard")
        engine.effect_resolver.resolve(
            state, effect,
            EffectResolutionContext(actor=0, source=2)
        )

        assert len(calls) >= 1
        first_call = calls[0]
        args, kwargs = first_call
        assert args[1] == top_card_id
        assert args[2] == ZONE_DISCARD
        assert kwargs.get("actor") == 0
        assert kwargs.get("source_id") == 2

    def test_reveal_top_card_character_routes_to_play_via_engine(self):
        """reveal_top_card effect with destination='play' must call _move_card_eventful for characters."""
        engine, state = setup_effect_game()

        # Find a character in the deck to be the top card
        for cid in state.players[0].deck:
            if engine.card_def(state, cid).card_type == "character":
                # Move it to the top
                state.players[0].deck.remove(cid)
                state.players[0].deck.insert(0, cid)
                top_card_id = cid
                break
        else:
            top_card_id = self._find_top_card(state, 0)

        calls = self._spy_move_card(engine)

        effect = EffectDef("reveal_top_card", amount=1, value="play")
        engine.effect_resolver.resolve(
            state, effect,
            EffectResolutionContext(actor=0, source=3)
        )

        assert len(calls) >= 1
        first_call = calls[0]
        args, kwargs = first_call
        assert args[1] == top_card_id
        assert args[2] == ZONE_PLAY
        assert kwargs.get("actor") == 0

    def test_put_card_in_hand_routes_via_engine(self):
        """put_card_in_hand effect must call _move_card_eventful with controller=owner."""
        engine, state = setup_effect_game()

        card_id = put_card(state, engine, 0, "Filler", "discard")

        calls = self._spy_move_card(engine)

        effect = EffectDef("put_card_in_hand")
        engine.effect_resolver.resolve(
            state, effect,
            EffectResolutionContext(actor=0, source=4, choice=card_id)
        )

        assert len(calls) >= 1
        first_call = calls[0]
        args, kwargs = first_call
        assert args[1] == card_id
        assert args[2] == ZONE_HAND
        assert kwargs.get("actor") == 0
        assert kwargs.get("source_id") == 4
        assert kwargs.get("controller") == state.cards[card_id].owner

    def test_put_card_on_top_routes_via_engine_with_index_0(self):
        """put_card_on_top effect must call _move_card_eventful with index=0."""
        engine, state = setup_effect_game()

        card_id = put_card(state, engine, 0, "Filler", "discard")

        calls = self._spy_move_card(engine)

        effect = EffectDef("put_card_on_top")
        engine.effect_resolver.resolve(
            state, effect,
            EffectResolutionContext(actor=0, source=5, choice=card_id)
        )

        assert len(calls) >= 1
        first_call = calls[0]
        args, kwargs = first_call
        assert args[1] == card_id
        assert args[2] == ZONE_DECK
        assert kwargs.get("index") == 0  # Top of deck routing
        assert kwargs.get("actor") == 0
        assert kwargs.get("source_id") == 5

    def test_put_card_on_bottom_routes_via_engine(self):
        """put_card_on_bottom effect must call _move_card_eventful."""
        engine, state = setup_effect_game()

        card_id = put_card(state, engine, 0, "Filler", "hand")

        calls = self._spy_move_card(engine)

        effect = EffectDef("put_card_on_bottom")
        engine.effect_resolver.resolve(
            state, effect,
            EffectResolutionContext(actor=0, source=6, choice=card_id)
        )

        assert len(calls) >= 1
        first_call = calls[0]
        args, kwargs = first_call
        assert args[1] == card_id
        assert args[2] == ZONE_DECK
        # No index specified means bottom (default)
        assert kwargs.get("actor") == 0

    def test_put_card_in_discard_routes_via_engine(self):
        """put_card_in_discard effect must call _move_card_eventful."""
        engine, state = setup_effect_game()

        card_id = put_card(state, engine, 0, "Filler", "hand")

        calls = self._spy_move_card(engine)

        effect = EffectDef("put_card_in_discard")
        engine.effect_resolver.resolve(
            state, effect,
            EffectResolutionContext(actor=0, source=7, choice=card_id)
        )

        assert len(calls) >= 1
        first_call = calls[0]
        args, kwargs = first_call
        assert args[1] == card_id
        assert args[2] == ZONE_DISCARD
        assert kwargs.get("actor") == 0

    def test_reveal_and_route_hand_via_engine(self):
        """reveal_and_route effect with destination='hand' must call _move_card_eventful."""
        engine, state = setup_effect_game()

        top_card_id = self._find_top_card(state, 0)
        assert top_card_id is not None

        calls = self._spy_move_card(engine)

        effect = EffectDef("reveal_and_route", value="hand")
        engine.effect_resolver.resolve(
            state, effect,
            EffectResolutionContext(actor=0, source=8)
        )

        assert len(calls) >= 1
        first_call = calls[0]
        args, kwargs = first_call
        assert args[1] == top_card_id
        assert args[2] == ZONE_HAND
        assert kwargs.get("actor") == 0
        assert kwargs.get("source_id") == 8

    def test_reveal_and_route_discard_via_engine(self):
        """reveal_and_route effect with destination='discard' must call _move_card_eventful."""
        engine, state = setup_effect_game()

        top_card_id = self._find_top_card(state, 0)
        assert top_card_id is not None

        calls = self._spy_move_card(engine)

        effect = EffectDef("reveal_and_route", value="discard")
        engine.effect_resolver.resolve(
            state, effect,
            EffectResolutionContext(actor=0, source=9)
        )

        assert len(calls) >= 1
        first_call = calls[0]
        args, kwargs = first_call
        assert args[1] == top_card_id
        assert args[2] == ZONE_DISCARD

    def test_reveal_and_route_play_via_engine_character_only(self):
        """reveal_and_route effect with destination='play' calls _move_card_eventful for characters."""
        engine, state = setup_effect_game()

        # Find a character in the deck to be the top card
        for cid in state.players[0].deck:
            if engine.card_def(state, cid).card_type == "character":
                state.players[0].deck.remove(cid)
                state.players[0].deck.insert(0, cid)
                top_card_id = cid
                break
        else:
            top_card_id = self._find_top_card(state, 0)

        calls = self._spy_move_card(engine)

        effect = EffectDef("reveal_and_route", value="play")
        engine.effect_resolver.resolve(
            state, effect,
            EffectResolutionContext(actor=0, source=10)
        )

        assert len(calls) >= 1
        first_call = calls[0]
        args, kwargs = first_call
        assert args[1] == top_card_id
        assert args[2] == ZONE_PLAY

    def test_reveal_top_card_preserves_revealed_flag_before_route(self):
        """reveal_top_card must mark card as revealed before calling _move_card_eventful."""
        engine, state = setup_effect_game()

        top_card_id = self._find_top_card(state, 0)
        assert top_card_id is not None
        assert state.cards[top_card_id].revealed is False

        calls = self._spy_move_card(engine)

        # Capture the card's revealed state at time of first call
        revealed_at_call = [False]
        original_move = engine._move_card_eventful

        def capture_reveal(*args, **kwargs):
            if revealed_at_call[0] is False:
                revealed_at_call[0] = state.cards[args[1]].revealed
            return original_move(*args, **kwargs)

        engine._move_card_eventful = capture_reveal

        effect = EffectDef("reveal_top_card", amount=1, value="hand")
        engine.effect_resolver.resolve(
            state, effect,
            EffectResolutionContext(actor=0, source=11)
        )

        # Card must be marked revealed at time of first _move_card_eventful call
        assert revealed_at_call[0] is True
        assert len(calls) >= 1


import pytest


class TestAmountResolver:
    """Tests for the amount resolver supporting multiple amount shapes."""

    def test_amount_resolver_integer(self):
        """Integer amount should resolve directly."""
        engine, state = setup_effect_game()

        effect = EffectDef("gain_lore", 5, "you")
        context = EffectResolutionContext(actor=0)

        initial_lore = state.players[0].lore
        engine.effect_resolver.resolve(state, effect, context)

        assert state.players[0].lore == initial_lore + 5

    def test_amount_resolver_numeric_string_from_raw(self):
        """Numeric string amount from raw should resolve."""
        engine, state = setup_effect_game()

        # Simulate raw amount as a numeric string (Lorcanito format)
        effect = EffectDef("gain_lore", 0, "you", raw={"amount": "3"})

        initial_lore = state.players[0].lore
        context = EffectResolutionContext(actor=0)
        engine.effect_resolver.resolve(state, effect, context)

        assert state.players[0].lore == initial_lore + 3

    def test_amount_resolver_static_object(self):
        """Static object amount should resolve."""
        engine, state = setup_effect_game()

        # Simulate static object amount (Lorcanito format)
        effect = EffectDef("gain_lore", 0, "you", raw={"amount": {"type": "static", "amount": 7}})

        initial_lore = state.players[0].lore
        context = EffectResolutionContext(actor=0)
        engine.effect_resolver.resolve(state, effect, context)

        assert state.players[0].lore == initial_lore + 7

    def test_amount_resolver_event_snapshot_key(self):
        """Event-snapshot amount should resolve from context."""
        engine, state = setup_effect_game()

        # Simulate event-snapshot amount (Lorcanito format)
        effect = EffectDef("gain_lore", 0, "you", raw={"amount": {"type": "event-snapshot", "key": "drawnCount"}})

        initial_lore = state.players[0].lore
        context = EffectResolutionContext(actor=0, event_payload={"drawnCount": 4})
        engine.effect_resolver.resolve(state, effect, context)

        assert state.players[0].lore == initial_lore + 4

    def test_amount_resolver_event_snapshot_key_from_pending_event(self):
        """Event-snapshot amount should resolve from PendingTriggeredEvent.event_snapshot."""
        from lorcana_bot.state import PendingTriggeredEvent

        engine, state = setup_effect_game()
        effect = EffectDef("gain_lore", 0, "you", raw={"amount": {"type": "event-snapshot", "key": "drawnCount"}})
        event = PendingTriggeredEvent(id="evt_drawn_count", event="draw", event_snapshot={"drawnCount": 2})

        initial_lore = state.players[0].lore
        context = EffectResolutionContext(actor=0, event=event)
        engine.effect_resolver.resolve(state, effect, context)

        assert state.players[0].lore == initial_lore + 2

    def test_amount_resolver_projected_source_effect_nested_raw_amount(self):
        """Projected SourceEffectDef raw payload should still expose nested raw amount."""
        engine, state = setup_effect_game()
        effect = EffectDef(
            "gain_lore",
            0,
            "you",
            raw={
                "amount": None,
                "raw": {"amount": {"type": "event-snapshot", "key": "cardsUnderCountBeforeBanish"}},
            },
        )
        context = EffectResolutionContext(actor=0, event_payload={"cardsUnderCountBeforeBanish": 5})

        initial_lore = state.players[0].lore
        engine.effect_resolver.resolve(state, effect, context)

        assert state.players[0].lore == initial_lore + 5

    def test_amount_resolver_decimal_string_raises(self):
        """Decimal strings are unsupported numeric strings and must not truncate."""
        from lorcana_bot.effects import EffectResolutionError

        engine, state = setup_effect_game()
        effect = EffectDef("gain_lore", 0, "you", raw={"amount": "2.5"})
        context = EffectResolutionContext(actor=0)

        with pytest.raises(EffectResolutionError):
            engine.effect_resolver.resolve(state, effect, context)

    def test_amount_resolver_unsupported_shape_raises(self):
        """Unsupported amount shape should raise EffectResolutionError, not return 0."""
        from lorcana_bot.effects import EffectResolutionError

        engine, state = setup_effect_game()

        # Unsupported shape: list
        effect = EffectDef("gain_lore", 0, "you", raw={"amount": ["unsupported", "list"]})

        context = EffectResolutionContext(actor=0)

        with pytest.raises(EffectResolutionError) as exc_info:
            engine.effect_resolver.resolve(state, effect, context)

        assert "Unsupported amount shape" in str(exc_info.value)
