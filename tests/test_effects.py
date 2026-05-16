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
