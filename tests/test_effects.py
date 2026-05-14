from __future__ import annotations

from lorcana_bot.actions import Action
from lorcana_bot.cards import CardDatabase, CardDef, EffectDef
from lorcana_bot.constants import ACTION_CHALLENGE, ACTION_PLAY_CARD, ZONE_HAND, ZONE_PLAY
from lorcana_bot.effect_types import EffectResolutionContext
from lorcana_bot.engine import GameEngine
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

    state.players[1].lore = 5
    lore_loss = put_card(state, engine, 0, "Lore Loss", ZONE_HAND)
    state = engine.apply_action(state, find_action(engine.legal_actions(state), ACTION_PLAY_CARD, card=lore_loss))

    assert state.players[1].lore == 3


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

    target = put_card(state, engine, 1, "Target", ZONE_PLAY, exerted=True, drying=False)
    banish = put_card(state, engine, 0, "Banish It", ZONE_HAND)
    state = engine.apply_action(state, find_action(engine.legal_actions(state), ACTION_PLAY_CARD, card=banish, target=target))
    assert target in state.players[1].discard


def test_ready_exert_discard_and_for_each_effects():
    engine, state = setup_effect_game()
    ally = put_card(state, engine, 0, "Ally", ZONE_PLAY, exerted=False, drying=False)
    target = put_card(state, engine, 1, "Target", ZONE_PLAY, exerted=True, drying=False)

    exert = put_card(state, engine, 0, "Exert It", ZONE_HAND)
    state = engine.apply_action(state, find_action(engine.legal_actions(state), ACTION_PLAY_CARD, card=exert, target=ally))
    assert state.cards[ally].exerted is True

    ready = put_card(state, engine, 0, "Ready It", ZONE_HAND)
    state = engine.apply_action(state, find_action(engine.legal_actions(state), ACTION_PLAY_CARD, card=ready, target=ally))
    assert state.cards[ally].exerted is False

    opponent_hand_before = len(state.players[1].hand)
    discard = put_card(state, engine, 0, "Discard One", ZONE_HAND)
    state = engine.apply_action(state, find_action(engine.legal_actions(state), ACTION_PLAY_CARD, card=discard))
    assert len(state.players[1].hand) == opponent_hand_before - 1

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
