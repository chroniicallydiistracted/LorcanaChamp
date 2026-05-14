from __future__ import annotations

import pytest

from lorcana_bot.cards import load_demo_database, make_demo_deck
from lorcana_bot.constants import ZONE_DECK, ZONE_DISCARD, ZONE_HAND, ZONE_INKWELL, ZONE_PLAY
from lorcana_bot.engine import GameEngine


@pytest.fixture()
def db():
    return load_demo_database()


@pytest.fixture()
def engine(db):
    return GameEngine(db)


@pytest.fixture()
def state(engine):
    pool = [
        "Amber Recruit",
        "Amber Guard",
        "Amber Storyteller",
        "Amethyst Scholar",
        "Amethyst Insight",
        "Steel Bruiser",
        "Emerald Scout",
        "Ruby Charger",
        "Steel Cannon",
        "Sapphire Helper",
    ]
    deck0 = make_demo_deck(pool, size=50)
    deck1 = make_demo_deck(pool, size=50)
    return engine.setup_game([deck0, deck1], seed=123)


def all_player_cards(state, player):
    ps = state.players[player]
    return list(ps.deck + ps.hand + ps.play + ps.discard + ps.inkwell)


def find_card(state, engine, player, full_name, exclude=frozenset()):
    for cid in all_player_cards(state, player):
        if cid in exclude:
            continue
        if engine.card_def(state, cid).full_name == full_name:
            return cid
    raise AssertionError(f"No {full_name} for player {player}")


def put_card(state, engine, player, full_name, zone, *, exclude=frozenset(), exerted=False, drying=False, damage=0):
    cid = find_card(state, engine, player, full_name, exclude=exclude)
    state.move_card(cid, zone, controller=player)
    state.cards[cid].exerted = exerted
    state.cards[cid].drying = drying
    state.cards[cid].damage = damage
    return cid


def add_ready_ink(state, engine, player, count, exclude=frozenset()):
    used = set(exclude)
    for _ in range(count):
        # Use any available card; its identity does not matter for abstract payment.
        cid = all_player_cards(state, player)[0]
        while cid in used or state.cards[cid].zone == ZONE_INKWELL:
            candidates = [c for c in all_player_cards(state, player) if c not in used and state.cards[c].zone != ZONE_INKWELL]
            if not candidates:
                raise AssertionError("Not enough cards to ink")
            cid = candidates[0]
        state.move_card(cid, ZONE_INKWELL, controller=player)
        state.cards[cid].exerted = False
        used.add(cid)
    return used
