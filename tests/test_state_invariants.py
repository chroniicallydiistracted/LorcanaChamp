from __future__ import annotations

from pathlib import Path

from lorcana_bot.cards import CardDatabase, CardDef
from lorcana_bot.constants import ZONE_DISCARD, ZONE_HAND, ZONE_PLAY, ZONE_UNDER
from lorcana_bot.engine import GameEngine
from lorcana_bot.pending_effects import create_search_pending_effect
from lorcana_bot.play_modes import execute_shift_play
from lorcana_bot.state import CardInstance, GameState, PlayerState


def _shift_card(card_id: str, name: str, cost: int) -> CardDef:
    return CardDef(
        id=card_id,
        full_name=name,
        ink="amber",
        cost=5,
        inkable=True,
        card_type="character",
        strength=3,
        willpower=4,
        lore=1,
        keywords=(f"SHIFT({cost})",),
    )


def _character(card_id: str, name: str) -> CardDef:
    return CardDef(
        id=card_id,
        full_name=name,
        ink="amber",
        cost=2,
        inkable=True,
        card_type="character",
        strength=2,
        willpower=2,
        lore=1,
    )


def _state_with_shift_stack() -> tuple[GameEngine, GameState]:
    engine = GameEngine(CardDatabase([
        _character("base", "Maleficent"),
        _shift_card("shifted", "Maleficent", 3),
        _character("ink", "Ink"),
    ]))
    state = GameState(players=[PlayerState(), PlayerState()], cards={})
    state.cards[1] = CardInstance(1, "base", owner=0, controller=0, zone=ZONE_PLAY)
    state.players[0].play.append(1)
    state.cards[2] = CardInstance(2, "shifted", owner=0, controller=0, zone=ZONE_HAND)
    state.players[0].hand.append(2)
    for cid in (100, 101, 102):
        state.cards[cid] = CardInstance(cid, "ink", owner=0, controller=0, zone="inkwell")
        state.players[0].inkwell.append(cid)
    return engine, state


def _assert_zone_membership_is_consistent(state: GameState) -> None:
    zone_lists = {
        0: {
            "deck": state.players[0].deck,
            "hand": state.players[0].hand,
            "play": state.players[0].play,
            "discard": state.players[0].discard,
            "inkwell": state.players[0].inkwell,
            "limbo": state.players[0].limbo,
            "under": state.players[0].under,
        },
        1: {
            "deck": state.players[1].deck,
            "hand": state.players[1].hand,
            "play": state.players[1].play,
            "discard": state.players[1].discard,
            "inkwell": state.players[1].inkwell,
            "limbo": state.players[1].limbo,
            "under": state.players[1].under,
        },
    }
    seen: dict[int, tuple[int, str]] = {}
    for player, zones in zone_lists.items():
        for zone, cards in zones.items():
            for cid in cards:
                assert cid not in seen, f"card {cid} appears in both {seen[cid]} and {(player, zone)}"
                seen[cid] = (player, zone)
                assert state.cards[cid].controller == player
                assert state.cards[cid].zone == zone

    assert set(seen) == set(state.cards)


def test_shift_target_moves_to_under_and_stack_leaves_play_together() -> None:
    engine, state = _state_with_shift_stack()

    execute_shift_play(state, engine, shifted_card_id=2, target_character_id=1)

    assert state.cards[1].zone == ZONE_UNDER
    assert 1 in state.players[0].under
    assert 1 not in state.players[0].play
    assert state.cards[2].cards_under == [1]
    assert state.cards[1].stack_parent_id == 2
    _assert_zone_membership_is_consistent(state)

    engine._return_to_hand_eventful(state, 2, actor=0)

    assert state.cards[2].zone == ZONE_HAND
    assert state.cards[1].zone == ZONE_HAND
    assert 2 in state.players[0].hand
    assert 1 in state.players[0].hand
    assert state.cards[2].cards_under == []
    assert state.cards[1].stack_parent_id is None
    _assert_zone_membership_is_consistent(state)


def test_banish_shift_stack_moves_every_card_to_resolved_destination() -> None:
    engine, state = _state_with_shift_stack()
    execute_shift_play(state, engine, shifted_card_id=2, target_character_id=1)

    engine._banish_eventful(state, 2, actor=0, reason="test")

    assert state.cards[2].zone == ZONE_DISCARD
    assert state.cards[1].zone == ZONE_DISCARD
    assert 2 in state.players[0].discard
    assert 1 in state.players[0].discard
    assert state.cards[2].cards_under == []
    assert state.cards[1].stack_parent_id is None
    _assert_zone_membership_is_consistent(state)


def test_location_leaving_play_clears_character_location_association() -> None:
    engine = GameEngine(CardDatabase([
        CardDef(
            id="location",
            full_name="Test Location",
            ink="amber",
            cost=2,
            inkable=True,
            card_type="location",
            move_cost=1,
            willpower=5,
            lore=1,
        ),
        _character("character", "Character"),
    ]))
    state = GameState(players=[PlayerState(), PlayerState()], cards={})
    state.cards[1] = CardInstance(1, "location", owner=0, controller=0, zone=ZONE_PLAY)
    state.players[0].play.append(1)
    state.cards[2] = CardInstance(
        2,
        "character",
        owner=0,
        controller=0,
        zone=ZONE_PLAY,
        location_instance_id=1,
    )
    state.players[0].play.append(2)

    engine._move_card_eventful(state, 1, ZONE_DISCARD, actor=0)

    assert state.cards[1].zone == ZONE_DISCARD
    assert state.cards[2].zone == ZONE_PLAY
    assert state.cards[2].location_instance_id is None
    _assert_zone_membership_is_consistent(state)


def test_pending_search_engine_path_uses_engine_move_boundary(monkeypatch) -> None:
    engine = GameEngine(CardDatabase([_character("target", "Target")]))
    state = GameState(players=[PlayerState(), PlayerState()], cards={})
    state.cards[1] = CardInstance(1, "target", owner=0, controller=0, zone="deck")
    state.players[0].deck.append(1)
    pending = create_search_pending_effect(
        state,
        controller_id=0,
        chooser_id=0,
        source_id=None,
        source_card_id=None,
        candidate_ids=(1,),
        destination=ZONE_HAND,
        shuffle_after=False,
    )

    calls: list[tuple[int, str]] = []
    original = engine._move_card_eventful

    def spy_move(state_arg, card_id, destination, **kwargs):
        calls.append((card_id, destination))
        return original(state_arg, card_id, destination, **kwargs)

    monkeypatch.setattr(engine, "_move_card_eventful", spy_move)

    from lorcana_bot.pending_effects import resolve_search_selection

    resolve_search_selection(state, pending.id, 1, engine=engine)

    assert calls == [(1, ZONE_HAND)]
    assert state.cards[1].zone == ZONE_HAND
    _assert_zone_membership_is_consistent(state)


def test_non_engine_modules_do_not_call_state_move_card_directly() -> None:
    root = Path(__file__).resolve().parents[1]
    checked_files = [
        root / "lorcana_bot" / "effects.py",
        root / "lorcana_bot" / "play_modes.py",
        root / "lorcana_bot" / "costs.py",
        root / "lorcana_bot" / "replacement_effects.py",
    ]

    for path in checked_files:
        assert "state.move_card(" not in path.read_text()
