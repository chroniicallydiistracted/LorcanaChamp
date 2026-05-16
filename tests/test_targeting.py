from __future__ import annotations

import pytest

from lorcana_bot.constants import (
    CARD_CHARACTER,
    CARD_ITEM,
    CARD_LOCATION,
    ZONE_DECK,
    ZONE_DISCARD,
    ZONE_HAND,
    ZONE_PLAY,
    ZONE_UNDER,
)
from lorcana_bot.targeting import (
    TargetCandidate,
    TargetDescriptor,
    TargetQueryContext,
    infer_candidate_zones,
    is_card_target_candidate,
    is_player_target_candidate,
    normalize_target_descriptor,
    normalize_target_descriptors,
)
from tests.conftest import find_card, put_card


@pytest.mark.parametrize(
    ("alias", "expected"),
    [
        ("chosen_character", {"card_types": (CARD_CHARACTER,)}),
        ("chosen_card", {"card_types": ()}),
        ("chosen_item", {"card_types": (CARD_ITEM,)}),
        ("chosen_location", {"card_types": (CARD_LOCATION,)}),
        ("chosen_opposing_character", {"card_types": (CARD_CHARACTER,), "controller": "opponent"}),
        (
            "chosen_damaged_character",
            {"card_types": (CARD_CHARACTER,), "filters": ({"type": "damaged", "min": 1},)},
        ),
        ("opposing_character", {"card_types": (CARD_CHARACTER,), "controller": "opponent"}),
        ("self", {"zones": (ZONE_PLAY,)}),
        ("event_source", {"zones": ()}),
        ("event_target", {"zones": ()}),
        ("trigger_subject", {"zones": ()}),
        ("your_characters", {"card_types": (CARD_CHARACTER,), "controller": "you", "max_count": None}),
        (
            "your_other_characters",
            {"card_types": (CARD_CHARACTER,), "controller": "you", "exclude_self": True, "max_count": None},
        ),
        ("opposing_characters", {"card_types": (CARD_CHARACTER,), "controller": "opponent", "max_count": None}),
        ("all_characters", {"card_types": (CARD_CHARACTER,), "max_count": None}),
        (
            "damaged_characters",
            {"card_types": (CARD_CHARACTER,), "filters": ({"type": "damaged", "min": 1},), "max_count": None},
        ),
        (
            "opposing_damaged_characters",
            {
                "card_types": (CARD_CHARACTER,),
                "controller": "opponent",
                "filters": ({"type": "damaged", "min": 1},),
                "max_count": None,
            },
        ),
        ("chosen_player", {"allow_players": True}),
        ("you", {"allow_players": True}),
        ("opponent", {"allow_players": True}),
        ("each_player", {"allow_players": True, "min_count": 2, "max_count": 2}),
    ],
)
def test_normalize_target_descriptor_supports_required_aliases(alias, expected):
    descriptor = normalize_target_descriptor(alias)

    assert descriptor is not None
    assert descriptor.selector == alias
    for attr, value in expected.items():
        assert getattr(descriptor, attr) == value


def test_normalize_target_descriptor_accepts_lorcanito_and_python_field_names():
    descriptor = normalize_target_descriptor({
        "selector": "Chosen-Character",
        "minCount": 0,
        "maxCount": "all",
        "zones": [ZONE_HAND, ZONE_DISCARD],
        "cardType": CARD_ITEM,
        "filter": {"type": "exerted"},
        "excludeSelf": True,
        "allowPlayers": False,
    })

    assert descriptor == TargetDescriptor(
        selector="chosen_character",
        min_count=0,
        max_count=None,
        zones=(ZONE_HAND, ZONE_DISCARD),
        card_types=(CARD_ITEM,),
        owner="any",
        filters=({"type": "exerted"},),
        exclude_self=True,
    )


def test_normalize_target_descriptors_flattens_valid_entries():
    descriptors = normalize_target_descriptors(["chosen_character", None, {"selector": "opponent"}])

    assert tuple(desc.selector for desc in descriptors) == ("chosen_character", "opponent")


def test_target_candidate_and_context_dataclasses_are_stable_shapes():
    candidate = TargetCandidate(kind="card", id=17, controller=1, zone=ZONE_PLAY)
    context = TargetQueryContext(
        actor=0,
        source_id=3,
        event_payload={"target": 17},
        current_targets=(17,),
        context_targets=(4,),
    )

    assert candidate.kind == "card"
    assert candidate.id == 17
    assert candidate.controller == 1
    assert context.actor == 0
    assert context.event_payload["target"] == 17
    assert context.current_targets == (17,)
    assert context.context_targets == (4,)


def test_infer_candidate_zones_matches_lorcanito_action_selection_zones(engine, state):
    hand = put_card(state, engine, 0, "Amber Recruit", ZONE_HAND)
    play = put_card(state, engine, 0, "Amber Guard", ZONE_PLAY, exclude=frozenset({hand}))
    discard = put_card(state, engine, 1, "Ruby Charger", ZONE_DISCARD)
    deck = find_card(state, engine, 0, "Steel Bruiser", exclude=frozenset({hand, play}))
    under = put_card(state, engine, 0, "Emerald Scout", ZONE_UNDER, exclude=frozenset({hand, play, deck}))

    assert state.cards[under].zone == ZONE_UNDER
    assert infer_candidate_zones((under, play, hand, discard, deck, 999999), state) == (
        ZONE_DECK,
        ZONE_HAND,
        ZONE_PLAY,
        ZONE_DISCARD,
    )


def test_is_card_target_candidate_applies_foundation_constraints(engine, state):
    source = put_card(state, engine, 0, "Amber Recruit", ZONE_PLAY)
    own = put_card(state, engine, 0, "Amber Guard", ZONE_PLAY, exclude=frozenset({source}))
    opponent = put_card(state, engine, 1, "Ruby Charger", ZONE_PLAY)
    damaged = put_card(state, engine, 1, "Steel Bruiser", ZONE_PLAY, exclude=frozenset({opponent}), damage=2)
    under = put_card(state, engine, 0, "Emerald Scout", ZONE_UNDER, exclude=frozenset({source, own}))
    state.cards[under].stack_parent_id = source

    own_descriptor = TargetDescriptor(selector="your_characters", controller="you", zones=(ZONE_PLAY,))
    opposing_descriptor = TargetDescriptor(selector="opposing_characters", controller="opponent", zones=(ZONE_PLAY,))
    damaged_descriptor = TargetDescriptor(
        selector="damaged_characters",
        zones=(ZONE_PLAY,),
        filters=({"type": "damaged", "min": 1},),
    )
    other_descriptor = TargetDescriptor(selector="your_other_characters", controller="you", zones=(ZONE_PLAY,), exclude_self=True)

    assert is_card_target_candidate(state, own, own_descriptor, actor=0)
    assert not is_card_target_candidate(state, opponent, own_descriptor, actor=0)
    assert is_card_target_candidate(state, opponent, opposing_descriptor, actor=0)
    assert is_card_target_candidate(state, damaged, damaged_descriptor, actor=0)
    assert not is_card_target_candidate(state, own, damaged_descriptor, actor=0)
    assert not is_card_target_candidate(state, source, other_descriptor, actor=0, source_id=source)
    assert not is_card_target_candidate(state, under, TargetDescriptor(selector="chosen_card", zones=(ZONE_UNDER,)), actor=0)


def test_is_player_target_candidate_supports_required_player_aliases():
    assert is_player_target_candidate(0, normalize_target_descriptor("chosen_player"), actor=1)
    assert is_player_target_candidate(0, normalize_target_descriptor("you"), actor=0)
    assert not is_player_target_candidate(1, normalize_target_descriptor("you"), actor=0)
    assert is_player_target_candidate(1, normalize_target_descriptor("opponent"), actor=0)
    assert not is_player_target_candidate(0, normalize_target_descriptor("opponent"), actor=0)
    assert is_player_target_candidate(0, normalize_target_descriptor("each_player"), actor=0)
    assert is_player_target_candidate(1, normalize_target_descriptor("each_player"), actor=0)
    assert not is_player_target_candidate(2, normalize_target_descriptor("each_player"), actor=0)
    assert not is_player_target_candidate(0, normalize_target_descriptor("chosen_character"), actor=0)
