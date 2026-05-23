from __future__ import annotations

import pytest

from lorcana_bot.cards import DEMO_FEATURE_CARD_IDS
from lorcana_bot.constants import (
    CARD_CHARACTER,
    CARD_ITEM,
    CARD_LOCATION,
    ZONE_DECK,
    ZONE_DISCARD,
    ZONE_HAND,
    ZONE_INKWELL,
    ZONE_PLAY,
    ZONE_UNDER,
)
from lorcana_bot.state import CardInstance
from lorcana_bot.targeting import (
    TargetCandidate,
    TargetDescriptor,
    TargetQueryContext,
    TargetSelectionAvailability,
    analyze_target_selection_availability,
    apply_target_protections,
    flatten_slotted_targets,
    infer_candidate_zones,
    is_card_target_candidate,
    is_player_target_candidate,
    is_slotted_target_input,
    normalize_slotted_target_input,
    normalize_target_descriptor,
    normalize_target_descriptors,
    requires_explicit_target_selection,
    resolve_candidate_card_ids,
    resolve_candidate_player_ids,
    resolve_candidate_targets,
    validate_slotted_targets,
)
from tests.conftest import find_card, put_card


# ---------------------------------------------------------------------------
# Brief 1 foundation tests (preserved)
# ---------------------------------------------------------------------------


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
        (
            "chosen_opposing_damaged_character",
            {
                "card_types": (CARD_CHARACTER,),
                "controller": "opponent",
                "filters": ({"type": "status", "status": "damaged"},),
            },
        ),
        ("your_chosen_character", {"card_types": (CARD_CHARACTER,), "owner": "you"}),
        (
            "your_chosen_damaged_character",
            {
                "card_types": (CARD_CHARACTER,),
                "owner": "you",
                "filters": ({"type": "status", "status": "damaged"},),
            },
        ),
        (
            "another_chosen_character_of_yours",
            {"card_types": (CARD_CHARACTER,), "owner": "you", "exclude_self": True},
        ),
        ("chosen_card_from_discard", {"zones": (ZONE_DISCARD,), "owner": "any"}),
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
        (
            "your_other_seven_dwarfs_characters",
            {
                "card_types": (CARD_CHARACTER,),
                "owner": "you",
                "exclude_self": True,
                "filters": ({"type": "has-classification", "classification": "Seven Dwarfs"},),
                "max_count": None,
            },
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
        ("challenging_player", {"allow_players": True}),
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


def test_slotted_target_input_guard_requires_known_kind_and_slot_arrays():
    assert is_slotted_target_input({"kind": "move-damage", "from": [1], "to": [2]})
    assert is_slotted_target_input({"kind": "move-to-location", "subject": [1], "location": [2]})
    assert is_slotted_target_input({"kind": "shift-and-choose", "chosenCard": [1]})
    assert is_slotted_target_input({"kind": "banish-and-play", "banish": [1], "play": [2]})
    assert not is_slotted_target_input({"kind": "move-damage", "from": [1]})
    assert not is_slotted_target_input({"kind": "unknown", "from": [1], "to": [2]})
    assert not is_slotted_target_input(["move-damage", [1], [2]])


def test_flatten_slotted_targets_uses_lorcanito_slot_order():
    assert flatten_slotted_targets({"kind": "move-damage", "from": [1, 2], "to": [3]}) == (1, 2, 3)
    assert flatten_slotted_targets({"kind": "move-to-location", "subject": [4], "location": [5]}) == (4, 5)
    assert flatten_slotted_targets({"kind": "shift-and-choose", "chosenCard": [6]}) == (6,)
    assert flatten_slotted_targets({"kind": "banish-and-play", "banish": [7], "play": [8, 9]}) == (7, 8, 9)


def test_normalize_slotted_target_input_preserves_kind_and_tuple_slots():
    normalized = normalize_slotted_target_input({"kind": "move-damage", "from": [1], "to": (2,)})

    assert normalized == {"kind": "move-damage", "from": (1,), "to": (2,)}


def test_validate_slotted_targets_checks_existence_and_slot_descriptors(engine, state):
    subject = put_card(state, engine, 0, "Amber Guard", ZONE_PLAY)
    location = max(state.cards) + 1
    state.cards[location] = CardInstance(
        instance_id=location,
        card_id=DEMO_FEATURE_CARD_IDS["location"],
        owner=0,
        controller=0,
        zone=ZONE_PLAY,
    )
    state.players[0].play.append(location)
    hand_card = put_card(state, engine, 0, "Amber Recruit", ZONE_HAND)

    validate_slotted_targets(
        state,
        {"kind": "move-to-location", "subject": [subject], "location": [location]},
        descriptor_by_slot={
            "subject": normalize_target_descriptor("chosen_character"),
            "location": normalize_target_descriptor("chosen_location"),
        },
        actor=0,
        engine=engine,
    )

    with pytest.raises(ValueError):
        validate_slotted_targets(state, {"kind": "shift-and-choose", "chosenCard": [999]})

    with pytest.raises(ValueError):
        validate_slotted_targets(
            state,
            {"kind": "move-to-location", "subject": [hand_card], "location": [location]},
            descriptor_by_slot={"subject": normalize_target_descriptor("chosen_character")},
            actor=0,
            engine=engine,
        )


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


# ---------------------------------------------------------------------------
# Brief 2: Candidate resolution tests
# ---------------------------------------------------------------------------


class TestResolveCandidateCardIds:
    """Tests for resolve_candidate_card_ids."""

    def test_your_characters_returns_own_play_characters(self, engine, state):
        own1 = put_card(state, engine, 0, "Amber Recruit", ZONE_PLAY)
        own2 = put_card(state, engine, 0, "Amber Guard", ZONE_PLAY, exclude=frozenset({own1}))
        opp = put_card(state, engine, 1, "Ruby Charger", ZONE_PLAY)

        desc = normalize_target_descriptor("your_characters")
        ctx = TargetQueryContext(actor=0, source_id=own1)

        result = resolve_candidate_card_ids(state, engine, desc, ctx)
        assert own1 in result
        assert own2 in result
        assert opp not in result

    def test_your_other_characters_excludes_source(self, engine, state):
        source = put_card(state, engine, 0, "Amber Recruit", ZONE_PLAY)
        other = put_card(state, engine, 0, "Amber Guard", ZONE_PLAY, exclude=frozenset({source}))

        desc = normalize_target_descriptor("your_other_characters")
        ctx = TargetQueryContext(actor=0, source_id=source)

        result = resolve_candidate_card_ids(state, engine, desc, ctx)
        assert source not in result
        assert other in result

    def test_opposing_characters_returns_opponent_play_characters(self, engine, state):
        own = put_card(state, engine, 0, "Amber Recruit", ZONE_PLAY)
        opp1 = put_card(state, engine, 1, "Ruby Charger", ZONE_PLAY)
        opp2 = put_card(state, engine, 1, "Steel Bruiser", ZONE_PLAY, exclude=frozenset({opp1}))

        desc = normalize_target_descriptor("opposing_characters")
        ctx = TargetQueryContext(actor=0)

        result = resolve_candidate_card_ids(state, engine, desc, ctx)
        assert opp1 in result
        assert opp2 in result
        assert own not in result

    def test_all_characters_returns_both_players_characters(self, engine, state):
        own = put_card(state, engine, 0, "Amber Recruit", ZONE_PLAY)
        opp = put_card(state, engine, 1, "Ruby Charger", ZONE_PLAY)

        desc = normalize_target_descriptor("all_characters")
        ctx = TargetQueryContext(actor=0)

        result = resolve_candidate_card_ids(state, engine, desc, ctx)
        assert own in result
        assert opp in result

    def test_damaged_characters_filter(self, engine, state):
        healthy = put_card(state, engine, 0, "Amber Recruit", ZONE_PLAY)
        hurt = put_card(state, engine, 0, "Amber Guard", ZONE_PLAY, exclude=frozenset({healthy}), damage=3)
        opp_hurt = put_card(state, engine, 1, "Ruby Charger", ZONE_PLAY, damage=1)

        desc = normalize_target_descriptor("damaged_characters")
        ctx = TargetQueryContext(actor=0)

        result = resolve_candidate_card_ids(state, engine, desc, ctx)
        assert healthy not in result
        assert hurt in result
        assert opp_hurt in result

    def test_opposing_damaged_characters_filter(self, engine, state):
        own = put_card(state, engine, 0, "Amber Recruit", ZONE_PLAY, damage=2)
        opp_hurt = put_card(state, engine, 1, "Ruby Charger", ZONE_PLAY, damage=1)
        opp_healthy = put_card(state, engine, 1, "Steel Bruiser", ZONE_PLAY, exclude=frozenset({opp_hurt}))

        desc = normalize_target_descriptor("opposing_damaged_characters")
        ctx = TargetQueryContext(actor=0)

        result = resolve_candidate_card_ids(state, engine, desc, ctx)
        assert own not in result
        assert opp_hurt in result
        assert opp_healthy not in result

    def test_zone_under_excluded(self, engine, state):
        play_card = put_card(state, engine, 0, "Amber Recruit", ZONE_PLAY)
        under_card = put_card(state, engine, 0, "Amber Guard", ZONE_UNDER, exclude=frozenset({play_card}))

        desc = normalize_target_descriptor("your_characters")
        ctx = TargetQueryContext(actor=0)

        result = resolve_candidate_card_ids(state, engine, desc, ctx)
        assert play_card in result
        assert under_card not in result

    def test_cards_not_in_play_zone_excluded_for_play_descriptors(self, engine, state):
        play_card = put_card(state, engine, 0, "Amber Recruit", ZONE_PLAY)
        hand_card = put_card(state, engine, 0, "Amber Guard", ZONE_HAND, exclude=frozenset({play_card}))
        discard_card = put_card(state, engine, 0, "Amber Storyteller", ZONE_DISCARD, exclude=frozenset({play_card, hand_card}))

        desc = normalize_target_descriptor("your_characters")
        ctx = TargetQueryContext(actor=0)

        result = resolve_candidate_card_ids(state, engine, desc, ctx)
        assert play_card in result
        assert hand_card not in result
        assert discard_card not in result

    def test_chosen_card_returns_all_play_cards(self, engine, state):
        own_char = put_card(state, engine, 0, "Amber Recruit", ZONE_PLAY)
        opp_char = put_card(state, engine, 1, "Ruby Charger", ZONE_PLAY)

        desc = normalize_target_descriptor("chosen_card")
        ctx = TargetQueryContext(actor=0)

        result = resolve_candidate_card_ids(state, engine, desc, ctx)
        assert own_char in result
        assert opp_char in result

    def test_chosen_character_only_characters(self, engine, state):
        char = put_card(state, engine, 0, "Amber Recruit", ZONE_PLAY)
        # Find an action card to put in play for testing
        action_card = find_card(state, engine, 0, "Steel Cannon", exclude=frozenset({char}))
        state.move_card(action_card, ZONE_PLAY, controller=0)
        state.cards[action_card].zone = ZONE_PLAY

        desc = normalize_target_descriptor("chosen_character")
        ctx = TargetQueryContext(actor=0)

        result = resolve_candidate_card_ids(state, engine, desc, ctx)
        assert char in result
        # Action cards should not be returned by chosen_character
        assert action_card not in result

    def test_chosen_item_only_items(self, engine, state):
        # Demo DB has no items, so with item filter, should return empty
        char = put_card(state, engine, 0, "Amber Recruit", ZONE_PLAY)

        desc = normalize_target_descriptor("chosen_item")
        ctx = TargetQueryContext(actor=0)

        result = resolve_candidate_card_ids(state, engine, desc, ctx)
        assert char not in result

    def test_self_selector_returns_source(self, engine, state):
        source = put_card(state, engine, 0, "Amber Recruit", ZONE_PLAY)
        other = put_card(state, engine, 0, "Amber Guard", ZONE_PLAY, exclude=frozenset({source}))

        desc = normalize_target_descriptor("self")
        ctx = TargetQueryContext(actor=0, source_id=source)

        result = resolve_candidate_card_ids(state, engine, desc, ctx)
        assert result == (source,)
        assert other not in result

    def test_event_source_returns_payload_source(self, engine, state):
        source = put_card(state, engine, 0, "Amber Recruit", ZONE_PLAY)

        desc = normalize_target_descriptor("event_source")
        ctx = TargetQueryContext(actor=0, event_payload={"source": source})

        result = resolve_candidate_card_ids(state, engine, desc, ctx)
        assert result == (source,)

    def test_event_target_returns_payload_target(self, engine, state):
        target = put_card(state, engine, 1, "Ruby Charger", ZONE_PLAY)

        desc = normalize_target_descriptor("event_target")
        ctx = TargetQueryContext(actor=0, event_payload={"target": target})

        result = resolve_candidate_card_ids(state, engine, desc, ctx)
        assert result == (target,)

    def test_trigger_subject_returns_payload_subject(self, engine, state):
        subject = put_card(state, engine, 0, "Amber Recruit", ZONE_PLAY)

        desc = normalize_target_descriptor("trigger_subject")
        ctx = TargetQueryContext(actor=0, event_payload={"subject": subject})

        result = resolve_candidate_card_ids(state, engine, desc, ctx)
        assert result == (subject,)

    def test_trigger_subject_with_trigger_subject_key(self, engine, state):
        subject = put_card(state, engine, 0, "Amber Recruit", ZONE_PLAY)

        desc = normalize_target_descriptor("trigger_subject")
        ctx = TargetQueryContext(actor=0, event_payload={"trigger_subject": subject})

        result = resolve_candidate_card_ids(state, engine, desc, ctx)
        assert result == (subject,)

    def test_lorcanito_context_ref_targets_resolve_from_event_context(self, engine, state):
        source = put_card(state, engine, 0, "Amber Recruit", ZONE_PLAY)
        attacker = put_card(state, engine, 0, "Ruby Charger", ZONE_PLAY, exclude=frozenset({source}))
        defender = put_card(state, engine, 1, "Amber Guard", ZONE_PLAY)
        previous = put_card(state, engine, 1, "Steel Bruiser", ZONE_PLAY, exclude=frozenset({defender}))

        context = TargetQueryContext(
            actor=0,
            source_id=source,
            event_payload={
                "attacker_id": attacker,
                "defender_id": defender,
                "trigger_source_card_id": defender,
                "subject_card_id": defender,
            },
            current_targets=(previous, attacker),
        )

        assert normalize_target_descriptor({"ref": "self"}).selector == "self"

        assert resolve_candidate_card_ids(
            state,
            engine,
            normalize_target_descriptor({"ref": "attacker"}),
            context,
        ) == (attacker,)

        assert resolve_candidate_card_ids(
            state,
            engine,
            normalize_target_descriptor({"ref": "defender"}),
            context,
        ) == (defender,)

        assert resolve_candidate_card_ids(
            state,
            engine,
            normalize_target_descriptor({"ref": "trigger-source"}),
            context,
        ) == (defender,)

        assert resolve_candidate_card_ids(
            state,
            engine,
            normalize_target_descriptor({"ref": "trigger-subject"}),
            context,
        ) == (defender,)

        assert resolve_candidate_card_ids(
            state,
            engine,
            normalize_target_descriptor({"ref": "previous-target"}),
            context,
        ) == (attacker,)

        assert resolve_candidate_card_ids(
            state,
            engine,
            normalize_target_descriptor({"ref": "selected-all"}),
            context,
        ) == (previous, attacker)

    def test_challenging_player_resolves_from_challenge_payload(self, engine, state):
        attacker = put_card(state, engine, 0, "Ruby Charger", ZONE_PLAY)
        desc = normalize_target_descriptor("challenging_player")
        ctx = TargetQueryContext(actor=1, event_payload={"attacker_id": attacker})

        assert resolve_candidate_player_ids(state, desc, ctx) == (0,)

    def test_status_filter_matches_lorcanito_status_damaged(self, engine, state):
        damaged = put_card(state, engine, 0, "Amber Guard", ZONE_PLAY)
        undamaged = put_card(state, engine, 0, "Amber Recruit", ZONE_PLAY, exclude=frozenset({damaged}))
        state.cards[damaged].damage = 2
        state.cards[undamaged].damage = 0

        desc = normalize_target_descriptor({
            "selector": "chosen",
            "count": 1,
            "owner": "you",
            "zones": [ZONE_PLAY],
            "cardTypes": [CARD_CHARACTER],
            "filter": [{"type": "status", "status": "damaged"}],
        })
        ctx = TargetQueryContext(actor=0)

        assert resolve_candidate_card_ids(state, engine, desc, ctx) == (damaged,)

    def test_card_type_card_is_wildcard_for_discard_card_targets(self, engine, state):
        character = put_card(state, engine, 0, "Amber Guard", ZONE_DISCARD)
        item = put_card(state, engine, 0, "Steel Cannon", ZONE_DISCARD, exclude=frozenset({character}))

        desc = normalize_target_descriptor({
            "selector": "chosen",
            "count": 1,
            "owner": "any",
            "zones": [ZONE_DISCARD],
            "cardTypes": ["card"],
        })
        ctx = TargetQueryContext(actor=0)

        assert set(resolve_candidate_card_ids(state, engine, desc, ctx)) == {character, item}

    def test_player_selectors_return_no_card_ids(self, engine, state):
        for selector in ("chosen_player", "you", "opponent", "each_player"):
            desc = normalize_target_descriptor(selector)
            ctx = TargetQueryContext(actor=0)
            result = resolve_candidate_card_ids(state, engine, desc, ctx)
            assert result == (), f"{selector} should return no card IDs"

    def test_current_targets_passthrough(self, engine, state):
        c1 = put_card(state, engine, 0, "Amber Recruit", ZONE_PLAY)
        c2 = put_card(state, engine, 1, "Ruby Charger", ZONE_PLAY)

        desc = TargetDescriptor(selector="current_targets", zones=())
        ctx = TargetQueryContext(actor=0, current_targets=(c1, c2))

        result = resolve_candidate_card_ids(state, engine, desc, ctx)
        assert c1 in result
        assert c2 in result

    def test_context_targets_passthrough(self, engine, state):
        c1 = put_card(state, engine, 0, "Amber Recruit", ZONE_PLAY)

        desc = TargetDescriptor(selector="context_targets", zones=())
        ctx = TargetQueryContext(actor=0, context_targets=(c1,))

        result = resolve_candidate_card_ids(state, engine, desc, ctx)
        assert result == (c1,)

    def test_empty_when_no_source_for_self(self, engine, state):
        desc = normalize_target_descriptor("self")
        ctx = TargetQueryContext(actor=0, source_id=None)

        result = resolve_candidate_card_ids(state, engine, desc, ctx)
        assert result == ()

    def test_self_selector_respects_descriptor_zone(self, engine, state):
        source = put_card(state, engine, 0, "Amber Recruit", ZONE_DISCARD)

        desc = normalize_target_descriptor("self")
        ctx = TargetQueryContext(actor=0, source_id=source)

        assert resolve_candidate_card_ids(state, engine, desc, ctx) == ()

    def test_event_target_respects_card_type_filter(self, engine, state):
        action = find_card(state, engine, 0, "Steel Cannon")
        state.move_card(action, ZONE_PLAY, controller=0)

        desc = TargetDescriptor(
            selector="event_target",
            zones=(ZONE_PLAY,),
            card_types=(CARD_CHARACTER,),
        )
        ctx = TargetQueryContext(actor=0, event_payload={"target": action})

        assert resolve_candidate_card_ids(state, engine, desc, ctx) == ()

    def test_trigger_subject_supports_subject_card_id_payload_key(self, engine, state):
        subject = put_card(state, engine, 0, "Amber Recruit", ZONE_PLAY)

        desc = normalize_target_descriptor("trigger_subject")
        ctx = TargetQueryContext(actor=0, event_payload={"subject_card_id": subject})

        assert resolve_candidate_card_ids(state, engine, desc, ctx) == (subject,)

    def test_exclude_trigger_subject_uses_context_subject(self, engine, state):
        subject = put_card(state, engine, 0, "Amber Recruit", ZONE_PLAY)
        other = put_card(state, engine, 0, "Amber Guard", ZONE_PLAY, exclude=frozenset({subject}))

        desc = TargetDescriptor(selector="chosen_card", zones=(ZONE_PLAY,), exclude_trigger_subject=True)
        ctx = TargetQueryContext(actor=0, event_payload={"subject": subject})

        result = resolve_candidate_card_ids(state, engine, desc, ctx)
        assert subject not in result
        assert other in result

    def test_current_targets_are_validated_against_zone_and_under_rules(self, engine, state):
        play = put_card(state, engine, 0, "Amber Recruit", ZONE_PLAY)
        hand = put_card(state, engine, 0, "Amber Guard", ZONE_HAND, exclude=frozenset({play}))
        under = put_card(state, engine, 0, "Emerald Scout", ZONE_UNDER, exclude=frozenset({play, hand}))

        desc = TargetDescriptor(selector="current_targets", zones=(ZONE_PLAY,))
        ctx = TargetQueryContext(actor=0, current_targets=(play, hand, under, 999999))

        assert resolve_candidate_card_ids(state, engine, desc, ctx) == (play,)


class TestResolveCandidatePlayerIds:
    """Tests for resolve_candidate_player_ids."""

    def test_you_returns_actor(self, engine, state):
        desc = normalize_target_descriptor("you")
        ctx = TargetQueryContext(actor=0)
        assert resolve_candidate_player_ids(state, desc, ctx) == (0,)

    def test_opponent_returns_other_player(self, engine, state):
        desc = normalize_target_descriptor("opponent")
        ctx = TargetQueryContext(actor=0)
        assert resolve_candidate_player_ids(state, desc, ctx) == (1,)

    def test_each_player_returns_both(self, engine, state):
        desc = normalize_target_descriptor("each_player")
        ctx = TargetQueryContext(actor=0)
        assert resolve_candidate_player_ids(state, desc, ctx) == (0, 1)

    def test_chosen_player_returns_both(self, engine, state):
        desc = normalize_target_descriptor("chosen_player")
        ctx = TargetQueryContext(actor=0)
        assert resolve_candidate_player_ids(state, desc, ctx) == (0, 1)

    def test_card_selectors_return_no_players(self, engine, state):
        for selector in ("chosen_character", "your_characters", "all_characters"):
            desc = normalize_target_descriptor(selector)
            ctx = TargetQueryContext(actor=0)
            assert resolve_candidate_player_ids(state, desc, ctx) == ()

    def test_unknown_allow_players_selector_returns_no_players(self, state):
        desc = TargetDescriptor(selector="unsupported_player_selector", allow_players=True)
        ctx = TargetQueryContext(actor=0)

        assert resolve_candidate_player_ids(state, desc, ctx) == ()


class TestResolveCandidateTargets:
    """Tests for resolve_candidate_targets (mixed card + player candidates)."""

    def test_card_and_player_candidates_combined(self, engine, state):
        char = put_card(state, engine, 0, "Amber Recruit", ZONE_PLAY)

        # Use a player descriptor
        desc = normalize_target_descriptor("you")
        ctx = TargetQueryContext(actor=0)

        result = resolve_candidate_targets(state, engine, desc, ctx)
        assert len(result) == 1
        assert result[0].kind == "player"
        assert result[0].id == 0

    def test_card_only_descriptor(self, engine, state):
        own = put_card(state, engine, 0, "Amber Recruit", ZONE_PLAY)
        opp = put_card(state, engine, 1, "Ruby Charger", ZONE_PLAY)

        desc = normalize_target_descriptor("chosen_character")
        ctx = TargetQueryContext(actor=0)

        result = resolve_candidate_targets(state, engine, desc, ctx)
        card_candidates = [c for c in result if c.kind == "card"]
        player_candidates = [c for c in result if c.kind == "player"]
        assert len(card_candidates) >= 2
        assert len(player_candidates) == 0

    def test_card_candidates_have_correct_fields(self, engine, state):
        char = put_card(state, engine, 0, "Amber Recruit", ZONE_PLAY)

        desc = normalize_target_descriptor("your_characters")
        ctx = TargetQueryContext(actor=0, source_id=char)

        result = resolve_candidate_targets(state, engine, desc, ctx)
        card_cands = [c for c in result if c.kind == "card"]
        assert len(card_cands) >= 1
        for c in card_cands:
            assert c.kind == "card"
            assert c.zone == ZONE_PLAY
            assert c.controller == 0


# ---------------------------------------------------------------------------
# Brief 2: Filter tests
# ---------------------------------------------------------------------------


class TestFilterCardType:
    """Tests for card_type filter."""

    def test_card_type_filter_via_descriptor(self, engine, state):
        char = put_card(state, engine, 0, "Amber Recruit", ZONE_PLAY)
        action = find_card(state, engine, 0, "Steel Cannon", exclude=frozenset({char}))
        state.move_card(action, ZONE_PLAY, controller=0)
        state.cards[action].zone = ZONE_PLAY

        desc = TargetDescriptor(
            selector="test",
            zones=(ZONE_PLAY,),
            card_types=(CARD_CHARACTER,),
            owner="any",
        )
        ctx = TargetQueryContext(actor=0)

        result = resolve_candidate_card_ids(state, engine, desc, ctx)
        assert char in result
        assert action not in result

    def test_card_type_filter_in_filter_dict(self, engine, state):
        char = put_card(state, engine, 0, "Amber Recruit", ZONE_PLAY)
        action = find_card(state, engine, 0, "Steel Cannon", exclude=frozenset({char}))
        state.move_card(action, ZONE_PLAY, controller=0)
        state.cards[action].zone = ZONE_PLAY

        desc = TargetDescriptor(
            selector="test",
            zones=(ZONE_PLAY,),
            filters=({"card_type": "character"},),
            owner="any",
        )
        ctx = TargetQueryContext(actor=0)

        result = resolve_candidate_card_ids(state, engine, desc, ctx)
        assert char in result
        assert action not in result

    def test_card_type_filter_lorcanito_alias(self, engine, state):
        char = put_card(state, engine, 0, "Amber Recruit", ZONE_PLAY)
        action = find_card(state, engine, 0, "Steel Cannon", exclude=frozenset({char}))
        state.move_card(action, ZONE_PLAY, controller=0)
        state.cards[action].zone = ZONE_PLAY

        desc = TargetDescriptor(
            selector="test",
            zones=(ZONE_PLAY,),
            filters=({"cardType": "action"},),
            owner="any",
        )
        ctx = TargetQueryContext(actor=0)

        result = resolve_candidate_card_ids(state, engine, desc, ctx)
        assert char not in result
        assert action in result


class TestFilterKeyword:
    """Tests for keyword filter."""

    def test_keyword_filter_matches(self, engine, state):
        # Amber Guard has BODYGUARD
        guard = put_card(state, engine, 0, "Amber Guard", ZONE_PLAY)
        recruit = put_card(state, engine, 0, "Amber Recruit", ZONE_PLAY, exclude=frozenset({guard}))

        desc = TargetDescriptor(
            selector="test",
            zones=(ZONE_PLAY,),
            filters=({"keyword": "BODYGUARD"},),
            owner="any",
        )
        ctx = TargetQueryContext(actor=0)

        result = resolve_candidate_card_ids(state, engine, desc, ctx)
        assert guard in result
        assert recruit not in result

    def test_keyword_filter_case_insensitive(self, engine, state):
        guard = put_card(state, engine, 0, "Amber Guard", ZONE_PLAY)

        desc = TargetDescriptor(
            selector="test",
            zones=(ZONE_PLAY,),
            filters=({"keyword": "bodyguard"},),
            owner="any",
        )
        ctx = TargetQueryContext(actor=0)

        result = resolve_candidate_card_ids(state, engine, desc, ctx)
        assert guard in result

    def test_keyword_filter_alias_keywords(self, engine, state):
        # Emerald Scout has EVASIVE
        scout = put_card(state, engine, 0, "Emerald Scout", ZONE_PLAY)

        desc = TargetDescriptor(
            selector="test",
            zones=(ZONE_PLAY,),
            filters=({"keywords": "EVASIVE"},),
            owner="any",
        )
        ctx = TargetQueryContext(actor=0)

        result = resolve_candidate_card_ids(state, engine, desc, ctx)
        assert scout in result

    def test_keyword_filter_no_match(self, engine, state):
        recruit = put_card(state, engine, 0, "Amber Recruit", ZONE_PLAY)

        desc = TargetDescriptor(
            selector="test",
            zones=(ZONE_PLAY,),
            filters=({"keyword": "RUSH"},),
            owner="any",
        )
        ctx = TargetQueryContext(actor=0)

        result = resolve_candidate_card_ids(state, engine, desc, ctx)
        assert recruit not in result


class TestFilterInk:
    """Tests for ink/color filter."""

    def test_ink_filter_matches(self, engine, state):
        amber = put_card(state, engine, 0, "Amber Recruit", ZONE_PLAY)
        ruby = put_card(state, engine, 1, "Ruby Charger", ZONE_PLAY)

        desc = TargetDescriptor(
            selector="test",
            zones=(ZONE_PLAY,),
            filters=({"ink": "amber"},),
            owner="any",
        )
        ctx = TargetQueryContext(actor=0)

        result = resolve_candidate_card_ids(state, engine, desc, ctx)
        assert amber in result
        assert ruby not in result

    def test_color_alias(self, engine, state):
        ruby = put_card(state, engine, 1, "Ruby Charger", ZONE_PLAY)
        amber = put_card(state, engine, 0, "Amber Recruit", ZONE_PLAY)

        desc = TargetDescriptor(
            selector="test",
            zones=(ZONE_PLAY,),
            filters=({"color": "ruby"},),
            owner="any",
        )
        ctx = TargetQueryContext(actor=0)

        result = resolve_candidate_card_ids(state, engine, desc, ctx)
        assert ruby in result
        assert amber not in result


class TestFilterDamaged:
    """Tests for damaged filter (both styles)."""

    def test_damaged_type_style(self, engine, state):
        healthy = put_card(state, engine, 0, "Amber Recruit", ZONE_PLAY)
        hurt = put_card(state, engine, 0, "Amber Guard", ZONE_PLAY, exclude=frozenset({healthy}), damage=2)

        desc = TargetDescriptor(
            selector="test",
            zones=(ZONE_PLAY,),
            filters=({"type": "damaged", "min": 1},),
            owner="any",
        )
        ctx = TargetQueryContext(actor=0)

        result = resolve_candidate_card_ids(state, engine, desc, ctx)
        assert healthy not in result
        assert hurt in result

    def test_damaged_field_alias_style(self, engine, state):
        healthy = put_card(state, engine, 0, "Amber Recruit", ZONE_PLAY)
        hurt = put_card(state, engine, 0, "Amber Guard", ZONE_PLAY, exclude=frozenset({healthy}), damage=1)

        desc = TargetDescriptor(
            selector="test",
            zones=(ZONE_PLAY,),
            filters=({"damaged": True},),
            owner="any",
        )
        ctx = TargetQueryContext(actor=0)

        result = resolve_candidate_card_ids(state, engine, desc, ctx)
        assert healthy not in result
        assert hurt in result


class TestFilterExerted:
    """Tests for exerted filter."""

    def test_exerted_type_style(self, engine, state):
        ready_card = put_card(state, engine, 0, "Amber Recruit", ZONE_PLAY)
        exerted_card = put_card(state, engine, 0, "Amber Guard", ZONE_PLAY, exclude=frozenset({ready_card}), exerted=True)

        desc = TargetDescriptor(
            selector="test",
            zones=(ZONE_PLAY,),
            filters=({"type": "exerted"},),
            owner="any",
        )
        ctx = TargetQueryContext(actor=0)

        result = resolve_candidate_card_ids(state, engine, desc, ctx)
        assert ready_card not in result
        assert exerted_card in result

    def test_exerted_field_alias_style(self, engine, state):
        ready_card = put_card(state, engine, 0, "Amber Recruit", ZONE_PLAY)
        exerted_card = put_card(state, engine, 0, "Amber Guard", ZONE_PLAY, exclude=frozenset({ready_card}), exerted=True)

        desc = TargetDescriptor(
            selector="test",
            zones=(ZONE_PLAY,),
            filters=({"exerted": True},),
            owner="any",
        )
        ctx = TargetQueryContext(actor=0)

        result = resolve_candidate_card_ids(state, engine, desc, ctx)
        assert ready_card not in result
        assert exerted_card in result


class TestFilterReady:
    """Tests for ready filter."""

    def test_ready_type_style(self, engine, state):
        ready_card = put_card(state, engine, 0, "Amber Recruit", ZONE_PLAY)
        exerted_card = put_card(state, engine, 0, "Amber Guard", ZONE_PLAY, exclude=frozenset({ready_card}), exerted=True)

        desc = TargetDescriptor(
            selector="test",
            zones=(ZONE_PLAY,),
            filters=({"type": "ready"},),
            owner="any",
        )
        ctx = TargetQueryContext(actor=0)

        result = resolve_candidate_card_ids(state, engine, desc, ctx)
        assert ready_card in result
        assert exerted_card not in result

    def test_ready_field_alias_style(self, engine, state):
        ready_card = put_card(state, engine, 0, "Amber Recruit", ZONE_PLAY)
        exerted_card = put_card(state, engine, 0, "Amber Guard", ZONE_PLAY, exclude=frozenset({ready_card}), exerted=True)

        desc = TargetDescriptor(
            selector="test",
            zones=(ZONE_PLAY,),
            filters=({"ready": True},),
            owner="any",
        )
        ctx = TargetQueryContext(actor=0)

        result = resolve_candidate_card_ids(state, engine, desc, ctx)
        assert ready_card in result
        assert exerted_card not in result


class TestFilterDrying:
    """Tests for drying filter."""

    def test_drying_type_style(self, engine, state):
        dry_card = put_card(state, engine, 0, "Amber Recruit", ZONE_PLAY, drying=True)
        normal_card = put_card(state, engine, 0, "Amber Guard", ZONE_PLAY, exclude=frozenset({dry_card}))

        desc = TargetDescriptor(
            selector="test",
            zones=(ZONE_PLAY,),
            filters=({"type": "drying"},),
            owner="any",
        )
        ctx = TargetQueryContext(actor=0)

        result = resolve_candidate_card_ids(state, engine, desc, ctx)
        assert dry_card in result
        assert normal_card not in result

    def test_drying_field_alias_style(self, engine, state):
        dry_card = put_card(state, engine, 0, "Amber Recruit", ZONE_PLAY, drying=True)
        normal_card = put_card(state, engine, 0, "Amber Guard", ZONE_PLAY, exclude=frozenset({dry_card}))

        desc = TargetDescriptor(
            selector="test",
            zones=(ZONE_PLAY,),
            filters=({"drying": True},),
            owner="any",
        )
        ctx = TargetQueryContext(actor=0)

        result = resolve_candidate_card_ids(state, engine, desc, ctx)
        assert dry_card in result
        assert normal_card not in result


class TestFilterOwnerController:
    """Tests for owner/controller filter in filter dict."""

    def test_owner_filter_you(self, engine, state):
        own = put_card(state, engine, 0, "Amber Recruit", ZONE_PLAY)
        opp = put_card(state, engine, 1, "Ruby Charger", ZONE_PLAY)

        desc = TargetDescriptor(
            selector="test",
            zones=(ZONE_PLAY,),
            filters=({"owner": "you"},),
        )
        ctx = TargetQueryContext(actor=0)

        result = resolve_candidate_card_ids(state, engine, desc, ctx)
        assert own in result
        assert opp not in result

    def test_controller_filter_opponent(self, engine, state):
        own = put_card(state, engine, 0, "Amber Recruit", ZONE_PLAY)
        opp = put_card(state, engine, 1, "Ruby Charger", ZONE_PLAY)

        desc = TargetDescriptor(
            selector="test",
            zones=(ZONE_PLAY,),
            filters=({"controller": "opponent"},),
        )
        ctx = TargetQueryContext(actor=0)

        result = resolve_candidate_card_ids(state, engine, desc, ctx)
        assert own not in result
        assert opp in result


class TestFilterLocation:
    """Tests for location_instance_id / at_location filter."""

    def test_location_instance_id_filter(self, engine, state):
        card_at_loc = put_card(state, engine, 0, "Amber Recruit", ZONE_PLAY)
        card_no_loc = put_card(state, engine, 0, "Amber Guard", ZONE_PLAY, exclude=frozenset({card_at_loc}))
        state.cards[card_at_loc].location_instance_id = 42

        desc = TargetDescriptor(
            selector="test",
            zones=(ZONE_PLAY,),
            filters=({"location_instance_id": 42},),
            owner="any",
        )
        ctx = TargetQueryContext(actor=0)

        result = resolve_candidate_card_ids(state, engine, desc, ctx)
        assert card_at_loc in result
        assert card_no_loc not in result

    def test_at_location_alias(self, engine, state):
        card_at_loc = put_card(state, engine, 0, "Amber Recruit", ZONE_PLAY)
        state.cards[card_at_loc].location_instance_id = 99

        desc = TargetDescriptor(
            selector="test",
            zones=(ZONE_PLAY,),
            filters=({"at_location": 99},),
            owner="any",
        )
        ctx = TargetQueryContext(actor=0)

        result = resolve_candidate_card_ids(state, engine, desc, ctx)
        assert card_at_loc in result

    def test_location_instance_id_none_means_not_at_location(self, engine, state):
        card_at_loc = put_card(state, engine, 0, "Amber Recruit", ZONE_PLAY)
        card_no_loc = put_card(state, engine, 0, "Amber Guard", ZONE_PLAY, exclude=frozenset({card_at_loc}))
        state.cards[card_at_loc].location_instance_id = 42

        desc = TargetDescriptor(
            selector="test",
            zones=(ZONE_PLAY,),
            filters=({"location_instance_id": None},),
            owner="any",
        )
        ctx = TargetQueryContext(actor=0)

        result = resolve_candidate_card_ids(state, engine, desc, ctx)
        assert card_at_loc not in result
        assert card_no_loc in result


class TestFilterClassification:
    """Tests for classification/subtypes filter."""

    def test_classification_filter_no_match_in_demo(self, engine, state):
        """Demo cards have no subtypes, so classification filter should exclude all."""
        recruit = put_card(state, engine, 0, "Amber Recruit", ZONE_PLAY)

        desc = TargetDescriptor(
            selector="test",
            zones=(ZONE_PLAY,),
            filters=({"classification": "Fairy"},),
            owner="any",
        )
        ctx = TargetQueryContext(actor=0)

        result = resolve_candidate_card_ids(state, engine, desc, ctx)
        assert recruit not in result


class TestFilterMultiple:
    """Tests for multiple simultaneous filters."""

    def test_multiple_filters_all_must_pass(self, engine, state):
        amber_char = put_card(state, engine, 0, "Amber Recruit", ZONE_PLAY)
        amber_damaged = put_card(state, engine, 0, "Amber Guard", ZONE_PLAY, exclude=frozenset({amber_char}), damage=1)
        ruby_healthy = put_card(state, engine, 1, "Ruby Charger", ZONE_PLAY)

        desc = TargetDescriptor(
            selector="test",
            zones=(ZONE_PLAY,),
            filters=(
                {"ink": "amber"},
                {"damaged": True},
            ),
            owner="any",
        )
        ctx = TargetQueryContext(actor=0)

        result = resolve_candidate_card_ids(state, engine, desc, ctx)
        assert amber_char not in result  # not damaged
        assert amber_damaged in result  # amber + damaged
        assert ruby_healthy not in result  # not amber


class TestIsoCardTargetCandidateWithEngine:
    """Tests that is_card_target_candidate correctly uses engine for card_type filtering."""

    def test_card_type_filtering_with_engine(self, engine, state):
        char = put_card(state, engine, 0, "Amber Recruit", ZONE_PLAY)
        action = find_card(state, engine, 0, "Steel Cannon", exclude=frozenset({char}))
        state.move_card(action, ZONE_PLAY, controller=0)
        state.cards[action].zone = ZONE_PLAY

        desc = TargetDescriptor(
            selector="chosen_character",
            zones=(ZONE_PLAY,),
            card_types=(CARD_CHARACTER,),
            owner="any",
        )

        assert is_card_target_candidate(state, char, desc, actor=0, engine=engine)
        assert not is_card_target_candidate(state, action, desc, actor=0, engine=engine)

    def test_no_engine_skips_card_type_check(self, engine, state):
        """Without engine, card_type check is skipped (backward compatible)."""
        char = put_card(state, engine, 0, "Amber Recruit", ZONE_PLAY)
        action = find_card(state, engine, 0, "Steel Cannon", exclude=frozenset({char}))
        state.move_card(action, ZONE_PLAY, controller=0)
        state.cards[action].zone = ZONE_PLAY

        desc = TargetDescriptor(
            selector="chosen_character",
            zones=(ZONE_PLAY,),
            card_types=(CARD_CHARACTER,),
            owner="any",
        )

        # Without engine, card_type filter is skipped so both pass
        assert is_card_target_candidate(state, char, desc, actor=0)
        assert is_card_target_candidate(state, action, desc, actor=0)


class TestZoneUnderExclusion:
    """ZONE_UNDER cards must stay excluded from all public candidate resolution."""

    def test_zone_under_excluded_from_all_characters(self, engine, state):
        play = put_card(state, engine, 0, "Amber Recruit", ZONE_PLAY)
        under = put_card(state, engine, 0, "Amber Guard", ZONE_UNDER, exclude=frozenset({play}))

        desc = normalize_target_descriptor("all_characters")
        ctx = TargetQueryContext(actor=0)

        result = resolve_candidate_card_ids(state, engine, desc, ctx)
        assert play in result
        assert under not in result

    def test_zone_under_excluded_from_chosen_card(self, engine, state):
        play = put_card(state, engine, 0, "Amber Recruit", ZONE_PLAY)
        under = put_card(state, engine, 0, "Amber Guard", ZONE_UNDER, exclude=frozenset({play}))

        desc = normalize_target_descriptor("chosen_card")
        ctx = TargetQueryContext(actor=0)

        result = resolve_candidate_card_ids(state, engine, desc, ctx)
        assert play in result
        assert under not in result


# ---------------------------------------------------------------------------
# Brief 3: Availability and protection tests
# ---------------------------------------------------------------------------


class TestTargetSelectionAvailability:
    """Tests for TargetSelectionAvailability dataclass and analyze function."""

    def test_availability_dataclass_fields(self):
        avail = TargetSelectionAvailability(
            candidate_count=5,
            card_candidate_count=3,
            player_candidate_count=2,
            min_selections=1,
            max_selections=1,
            allows_explicit_empty_target_selection=False,
            can_satisfy_required_selection=True,
            requires_explicit_target_selection=True,
            should_auto_reject_for_no_valid_targets=False,
        )
        assert avail.candidate_count == 5
        assert avail.card_candidate_count == 3
        assert avail.player_candidate_count == 2
        assert avail.min_selections == 1
        assert avail.max_selections == 1
        assert avail.allows_explicit_empty_target_selection is False
        assert avail.can_satisfy_required_selection is True
        assert avail.requires_explicit_target_selection is True
        assert avail.should_auto_reject_for_no_valid_targets is False

    def test_chosen_character_with_candidates_satisfied(self):
        desc = normalize_target_descriptor("chosen_character")
        candidates = (
            TargetCandidate(kind="card", id=1, controller=0, zone=ZONE_PLAY),
            TargetCandidate(kind="card", id=2, controller=1, zone=ZONE_PLAY),
        )
        avail = analyze_target_selection_availability(desc, candidates)

        assert avail.candidate_count == 2
        assert avail.card_candidate_count == 2
        assert avail.player_candidate_count == 0
        assert avail.min_selections == 1
        assert avail.max_selections == 1
        assert avail.can_satisfy_required_selection is True
        assert avail.requires_explicit_target_selection is True
        assert avail.should_auto_reject_for_no_valid_targets is False

    def test_chosen_character_with_no_candidates_auto_rejects(self):
        desc = normalize_target_descriptor("chosen_character")
        avail = analyze_target_selection_availability(desc, ())

        assert avail.candidate_count == 0
        assert avail.can_satisfy_required_selection is False
        assert avail.requires_explicit_target_selection is True
        assert avail.should_auto_reject_for_no_valid_targets is True

    def test_chosen_character_optional_does_not_auto_reject(self):
        desc = normalize_target_descriptor("chosen_character")
        avail = analyze_target_selection_availability(desc, (), is_optional=True)

        assert avail.candidate_count == 0
        assert avail.should_auto_reject_for_no_valid_targets is False

    def test_your_characters_not_explicit_selection(self):
        desc = normalize_target_descriptor("your_characters")
        candidates = (TargetCandidate(kind="card", id=1, controller=0, zone=ZONE_PLAY),)
        avail = analyze_target_selection_availability(desc, candidates)

        assert avail.requires_explicit_target_selection is False
        assert avail.should_auto_reject_for_no_valid_targets is False

    def test_lorcanito_expanded_chosen_aliases_are_explicit_selection(self):
        assert requires_explicit_target_selection("your_chosen_character")
        assert requires_explicit_target_selection("your_chosen_damaged_character")
        assert requires_explicit_target_selection("another_chosen_character_of_yours")

    def test_player_only_candidates(self):
        desc = normalize_target_descriptor("chosen_player")
        candidates = (
            TargetCandidate(kind="player", id=0),
            TargetCandidate(kind="player", id=1),
        )
        avail = analyze_target_selection_availability(desc, candidates)

        assert avail.candidate_count == 2
        assert avail.card_candidate_count == 0
        assert avail.player_candidate_count == 2
        assert avail.can_satisfy_required_selection is True

    def test_mixed_card_and_player_candidates(self):
        desc = normalize_target_descriptor("chosen_player")
        candidates = (
            TargetCandidate(kind="card", id=1, controller=0, zone=ZONE_PLAY),
            TargetCandidate(kind="player", id=0),
            TargetCandidate(kind="player", id=1),
        )
        avail = analyze_target_selection_availability(desc, candidates)

        assert avail.candidate_count == 3
        assert avail.card_candidate_count == 1
        assert avail.player_candidate_count == 2

    def test_max_count_none_means_unbounded(self):
        desc = normalize_target_descriptor("your_characters")
        candidates = tuple(TargetCandidate(kind="card", id=i, controller=0, zone=ZONE_PLAY) for i in range(10))
        avail = analyze_target_selection_availability(desc, candidates)

        assert avail.max_selections == 10  # unbounded = total candidates
        assert avail.can_satisfy_required_selection is True

    def test_min_count_zero(self):
        desc = TargetDescriptor(selector="chosen_card", min_count=0, max_count=1, zones=(ZONE_PLAY,), owner="any")
        avail = analyze_target_selection_availability(desc, ())

        assert avail.min_selections == 0
        assert avail.allows_explicit_empty_target_selection is True
        assert avail.can_satisfy_required_selection is True
        assert avail.requires_explicit_target_selection is True
        assert avail.should_auto_reject_for_no_valid_targets is True

    def test_min_count_greater_than_candidates_cannot_satisfy(self):
        desc = TargetDescriptor(selector="chosen_character", min_count=3, max_count=3, zones=(ZONE_PLAY,), card_types=(CARD_CHARACTER,), owner="any")
        candidates = (
            TargetCandidate(kind="card", id=1, controller=0, zone=ZONE_PLAY),
            TargetCandidate(kind="card", id=2, controller=1, zone=ZONE_PLAY),
        )
        avail = analyze_target_selection_availability(desc, candidates)

        assert avail.candidate_count == 2
        assert avail.min_selections == 3
        assert avail.can_satisfy_required_selection is False
        assert avail.should_auto_reject_for_no_valid_targets is True

    def test_duplicate_allowed_requirement_can_satisfy_with_one_candidate(self):
        desc = TargetDescriptor(
            selector="chosen_character",
            min_count=3,
            max_count=3,
            zones=(ZONE_PLAY,),
            card_types=(CARD_CHARACTER,),
            allow_duplicate_targets=True,
        )
        candidates = (TargetCandidate(kind="card", id=1, controller=0, zone=ZONE_PLAY),)
        avail = analyze_target_selection_availability(desc, candidates)

        assert avail.candidate_count == 1
        assert avail.can_satisfy_required_selection is True
        assert avail.should_auto_reject_for_no_valid_targets is False


class TestApplyTargetProtections:
    """Tests for apply_target_protections."""

    def test_zone_under_cards_excluded(self, engine, state):
        play = put_card(state, engine, 0, "Amber Recruit", ZONE_PLAY)
        under = put_card(state, engine, 0, "Amber Guard", ZONE_UNDER, exclude=frozenset({play}))

        candidates = (
            TargetCandidate(kind="card", id=play, controller=0, zone=ZONE_PLAY),
            TargetCandidate(kind="card", id=under, controller=0, zone=ZONE_UNDER),
        )
        desc = normalize_target_descriptor("chosen_card")
        ctx = TargetQueryContext(actor=0)

        result = apply_target_protections(state, engine, candidates, desc, ctx)
        assert len(result) == 1
        assert result[0].id == play

    def test_stack_parent_id_cards_excluded(self, engine, state):
        parent = put_card(state, engine, 0, "Amber Recruit", ZONE_PLAY)
        child = put_card(state, engine, 0, "Amber Guard", ZONE_PLAY, exclude=frozenset({parent}))
        state.cards[child].stack_parent_id = parent

        candidates = (
            TargetCandidate(kind="card", id=parent, controller=0, zone=ZONE_PLAY),
            TargetCandidate(kind="card", id=child, controller=0, zone=ZONE_PLAY),
        )
        desc = normalize_target_descriptor("chosen_card")
        ctx = TargetQueryContext(actor=0)

        result = apply_target_protections(state, engine, candidates, desc, ctx)
        assert len(result) == 1
        assert result[0].id == parent

    def test_ward_blocks_chosen_opposing(self, engine, state):
        """Opposing Ward cards cannot be chosen by opponent effects."""
        own = put_card(state, engine, 0, "Amber Recruit", ZONE_PLAY)
        # Amber Guard has BODYGUARD, not WARD. Use Emerald Scout (EVASIVE) - no Ward either.
        # We need to give a card Ward via temporary_keywords.
        opp = put_card(state, engine, 1, "Ruby Charger", ZONE_PLAY)
        state.cards[opp].temporary_keywords = ["WARD"]

        candidates = (
            TargetCandidate(kind="card", id=own, controller=0, zone=ZONE_PLAY),
            TargetCandidate(kind="card", id=opp, controller=1, zone=ZONE_PLAY),
        )
        desc = normalize_target_descriptor("chosen_character")
        ctx = TargetQueryContext(actor=0)

        result = apply_target_protections(state, engine, candidates, desc, ctx)
        result_ids = [c.id for c in result]
        assert own in result_ids
        assert opp not in result_ids

    def test_ward_does_not_block_own_cards(self, engine, state):
        """Ward only blocks opponent's chosen effects, not your own."""
        own = put_card(state, engine, 0, "Amber Recruit", ZONE_PLAY)
        state.cards[own].temporary_keywords = ["WARD"]

        candidates = (TargetCandidate(kind="card", id=own, controller=0, zone=ZONE_PLAY),)
        desc = normalize_target_descriptor("chosen_character")
        ctx = TargetQueryContext(actor=0)

        result = apply_target_protections(state, engine, candidates, desc, ctx)
        assert len(result) == 1
        assert result[0].id == own

    def test_ward_does_not_block_non_explicit_collection_selectors(self, engine, state):
        """Ward blocks chosen target selection, not automatic collection effects."""
        opp = put_card(state, engine, 1, "Ruby Charger", ZONE_PLAY)
        state.cards[opp].temporary_keywords = ["WARD"]

        candidates = (TargetCandidate(kind="card", id=opp, controller=1, zone=ZONE_PLAY),)
        desc = normalize_target_descriptor("all_characters")
        ctx = TargetQueryContext(actor=0)

        result = apply_target_protections(state, engine, candidates, desc, ctx)
        assert len(result) == 1
        assert result[0].id == opp

    def test_ward_does_not_block_player_selectors(self, engine, state):
        """Ward does not block player selectors (allow_players=True)."""
        candidates = (TargetCandidate(kind="player", id=0),)
        desc = normalize_target_descriptor("you")
        ctx = TargetQueryContext(actor=0)

        result = apply_target_protections(state, engine, candidates, desc, ctx)
        assert len(result) == 1

    def test_cannot_be_targeted_replacement_effect_blocks_candidate(self, engine, state):
        from lorcana_bot.replacement_effects import (
            ReplacementEffectEntry,
            ReplacementEffectType,
            register_replacement_effect,
        )

        protected = put_card(state, engine, 0, "Amber Recruit", ZONE_PLAY)
        open_target = put_card(state, engine, 0, "Amber Guard", ZONE_PLAY, exclude=frozenset({protected}))
        register_replacement_effect(
            state,
            ReplacementEffectEntry(
                source_id=protected,
                effect_type=ReplacementEffectType.CANNOT_BE_TARGETED,
                target_mode="self",
            ),
        )

        candidates = (
            TargetCandidate(kind="card", id=protected, controller=0, zone=ZONE_PLAY),
            TargetCandidate(kind="card", id=open_target, controller=0, zone=ZONE_PLAY),
        )
        desc = normalize_target_descriptor("chosen_character")
        ctx = TargetQueryContext(actor=1)

        result = apply_target_protections(state, engine, candidates, desc, ctx)
        assert tuple(c.id for c in result) == (open_target,)

    def test_duplicate_candidates_rejected(self, engine, state):
        card = put_card(state, engine, 0, "Amber Recruit", ZONE_PLAY)

        candidates = (
            TargetCandidate(kind="card", id=card, controller=0, zone=ZONE_PLAY),
            TargetCandidate(kind="card", id=card, controller=0, zone=ZONE_PLAY),
        )
        desc = normalize_target_descriptor("chosen_card")
        ctx = TargetQueryContext(actor=0)

        result = apply_target_protections(state, engine, candidates, desc, ctx)
        assert len(result) == 1

    def test_duplicate_candidates_preserved_when_descriptor_allows_duplicates(self, engine, state):
        card = put_card(state, engine, 0, "Amber Recruit", ZONE_PLAY)

        candidates = (
            TargetCandidate(kind="card", id=card, controller=0, zone=ZONE_PLAY),
            TargetCandidate(kind="card", id=card, controller=0, zone=ZONE_PLAY),
        )
        desc = TargetDescriptor(selector="chosen_card", zones=(ZONE_PLAY,), allow_duplicate_targets=True)
        ctx = TargetQueryContext(actor=0)

        result = apply_target_protections(state, engine, candidates, desc, ctx)
        assert tuple(c.id for c in result) == (card, card)

    def test_protection_rechecks_descriptor_zone(self, engine, state):
        play_card = put_card(state, engine, 0, "Amber Recruit", ZONE_PLAY)
        hand_card = put_card(state, engine, 0, "Amber Guard", ZONE_HAND, exclude=frozenset({play_card}))

        candidates = (
            TargetCandidate(kind="card", id=play_card, controller=0, zone=ZONE_PLAY),
            TargetCandidate(kind="card", id=hand_card, controller=0, zone=ZONE_HAND),
        )
        desc = TargetDescriptor(selector="chosen_card", zones=(ZONE_PLAY,))
        ctx = TargetQueryContext(actor=0)

        result = apply_target_protections(state, engine, candidates, desc, ctx)
        assert tuple(c.id for c in result) == (play_card,)

    def test_player_candidates_pass_through(self, engine, state):
        candidates = (
            TargetCandidate(kind="player", id=0),
            TargetCandidate(kind="player", id=1),
        )
        desc = normalize_target_descriptor("chosen_player")
        ctx = TargetQueryContext(actor=0)

        result = apply_target_protections(state, engine, candidates, desc, ctx)
        assert len(result) == 2
        assert result[0].kind == "player"
        assert result[1].kind == "player"

    def test_mixed_candidates_protections(self, engine, state):
        own = put_card(state, engine, 0, "Amber Recruit", ZONE_PLAY)
        opp_ward = put_card(state, engine, 1, "Ruby Charger", ZONE_PLAY)
        state.cards[opp_ward].temporary_keywords = ["WARD"]
        under = put_card(state, engine, 0, "Amber Guard", ZONE_UNDER, exclude=frozenset({own}))

        candidates = (
            TargetCandidate(kind="card", id=own, controller=0, zone=ZONE_PLAY),
            TargetCandidate(kind="card", id=opp_ward, controller=1, zone=ZONE_PLAY),
            TargetCandidate(kind="card", id=under, controller=0, zone=ZONE_UNDER),
            TargetCandidate(kind="player", id=0),
            TargetCandidate(kind="player", id=1),
        )
        desc = normalize_target_descriptor("chosen_character")
        ctx = TargetQueryContext(actor=0)

        result = apply_target_protections(state, engine, candidates, desc, ctx)
        result_ids = [(c.kind, c.id) for c in result]
        assert ("card", own) in result_ids
        assert ("card", opp_ward) not in result_ids  # Ward blocked
        assert ("card", under) not in result_ids  # ZONE_UNDER
        assert ("player", 0) in result_ids
        assert ("player", 1) in result_ids

    def test_protection_preserves_candidate_fields(self, engine, state):
        card = put_card(state, engine, 0, "Amber Recruit", ZONE_PLAY)

        candidates = (TargetCandidate(kind="card", id=card, controller=0, zone=ZONE_PLAY),)
        desc = normalize_target_descriptor("chosen_card")
        ctx = TargetQueryContext(actor=0)

        result = apply_target_protections(state, engine, candidates, desc, ctx)
        assert len(result) == 1
        assert result[0].kind == "card"
        assert result[0].id == card
        assert result[0].controller == 0
        assert result[0].zone == ZONE_PLAY

    def test_empty_candidates_returns_empty(self, engine, state):
        desc = normalize_target_descriptor("chosen_character")
        ctx = TargetQueryContext(actor=0)

        result = apply_target_protections(state, engine, (), desc, ctx)
        assert result == ()

    def test_nonexistent_card_filtered_out(self, engine, state):
        candidates = (TargetCandidate(kind="card", id=999999, controller=0, zone=ZONE_PLAY),)
        desc = normalize_target_descriptor("chosen_card")
        ctx = TargetQueryContext(actor=0)

        result = apply_target_protections(state, engine, candidates, desc, ctx)
        assert result == ()

    def test_context_derived_candidates_stay_validated_after_protection(self, engine, state):
        """Context selectors that go through Brief 2 validation must also
        pass protection filtering."""
        source = put_card(state, engine, 0, "Amber Recruit", ZONE_PLAY)
        opp_ward = put_card(state, engine, 1, "Ruby Charger", ZONE_PLAY)
        state.cards[opp_ward].temporary_keywords = ["WARD"]

        # Resolve via chosen_card (includes both), then protect with chosen_character
        desc = normalize_target_descriptor("chosen_character")
        ctx = TargetQueryContext(actor=0, source_id=source)

        raw_candidates = resolve_candidate_targets(state, engine, desc, ctx)
        protected = apply_target_protections(state, engine, raw_candidates, desc, ctx)

        protected_ids = [c.id for c in protected if c.kind == "card"]
        assert source in protected_ids
        assert opp_ward not in protected_ids  # Ward blocked

    def test_unknown_allow_players_selector_still_returns_no_players_after_protection(self, state, engine):
        desc = TargetDescriptor(selector="unsupported_player_selector", allow_players=True)
        ctx = TargetQueryContext(actor=0)

        candidates = resolve_candidate_targets(state, engine, desc, ctx)
        protected = apply_target_protections(state, engine, candidates, desc, ctx)

        assert protected == ()


# ---------------------------------------------------------------------------
# Brief 4: Engine-path action-card target tests
# ---------------------------------------------------------------------------


from lorcana_bot.cards import CardDef, CardDatabase, DEMO_FEATURE_CARD_IDS, EffectDef, load_demo_database, make_demo_deck
from lorcana_bot.constants import ACTION_PLAY_CARD
from lorcana_bot.engine import GameEngine
from tests.conftest import add_ready_ink


class TestEngineActionCardTargets:
    """Tests for engine legal_actions integration with targeting service."""

    def _engine_with_extra_cards(self, extra_cards):
        db = CardDatabase(load_demo_database().all_cards() + list(extra_cards))
        return GameEngine(db)

    def _find_play_card_action(self, actions, card_id, *, target=None):
        """Find a PLAY_CARD action for a specific card."""
        for a in actions:
            if a.kind == ACTION_PLAY_CARD and a.card == card_id:
                if target is not None and a.target != target:
                    continue
                return a
        return None

    def test_chosen_character_excludes_opposing_ward(self, engine, state):
        """Ward cards should not be legal action targets for opposing_character."""
        cannon = put_card(state, engine, 0, "Steel Cannon", ZONE_HAND)
        add_ready_ink(state, engine, 0, 2, exclude=frozenset({cannon}))
        # Opposing character with Ward
        opp_ward = put_card(state, engine, 1, "Amber Guard", ZONE_PLAY)
        state.cards[opp_ward].temporary_keywords = ["WARD"]
        # Opposing character without Ward
        opp_no_ward = put_card(state, engine, 1, "Ruby Charger", ZONE_PLAY, exclude=frozenset({opp_ward}))

        actions = engine.legal_actions(state, 0)
        # Ward card should not appear as a target
        ward_targets = [
            a for a in actions
            if a.kind == ACTION_PLAY_CARD and a.card == cannon and a.target == opp_ward
        ]
        assert len(ward_targets) == 0

        # Non-Ward opposing card should still be a target
        ok_targets = [
            a for a in actions
            if a.kind == ACTION_PLAY_CARD and a.card == cannon and a.target == opp_no_ward
        ]
        assert len(ok_targets) == 1

    def test_zone_under_card_not_legal_action_target(self, engine, state):
        """ZONE_UNDER cards must not appear as legal action targets."""
        cannon = put_card(state, engine, 0, "Steel Cannon", ZONE_HAND)
        add_ready_ink(state, engine, 0, 2, exclude=frozenset({cannon}))
        play = put_card(state, engine, 1, "Amber Recruit", ZONE_PLAY)
        under = put_card(state, engine, 1, "Amber Guard", ZONE_UNDER, exclude=frozenset({play}))

        actions = engine.legal_actions(state, 0)
        under_targets = [
            a for a in actions
            if a.kind == ACTION_PLAY_CARD and a.card == cannon and a.target == under
        ]
        assert len(under_targets) == 0

    def test_mandatory_target_no_candidates_emits_no_no_target_action(self, engine, state):
        """Action card with mandatory chosen_character target but zero candidates
        must not emit a no-target PLAY_CARD action."""
        cannon = put_card(state, engine, 0, "Steel Cannon", ZONE_HAND)
        add_ready_ink(state, engine, 0, 2, exclude=frozenset({cannon}))
        # No opposing characters (target=opponent_controller=1)

        actions = engine.legal_actions(state, 0)
        # Steel Cannon targets opposing_character, so no targets = no action
        cannon_actions = [a for a in actions if a.kind == ACTION_PLAY_CARD and a.card == cannon]
        assert len(cannon_actions) == 0

    def test_unsupported_target_descriptor_emits_no_broad_fallback(self, engine, state):
        """Action card with an unknown/unsupported target descriptor must not
        emit broad fallback targets."""
        # Create an action card with an unknown target descriptor
        unknown_target_card = CardDef(
            "test_unknown_target",
            "Mystery Action",
            "amber",
            1,
            True,
            "action",
            effects=[{"kind": "draw", "amount": 1, "target": "totally_unknown_selector_xyz"}],
        )
        db2 = CardDatabase(engine.db.all_cards() + [unknown_target_card])
        engine2 = GameEngine(db2)
        state2 = engine2.setup_game(
            [make_demo_deck(["Mystery Action"], 50), make_demo_deck(["Amber Recruit"], 50)],
            seed=42,
        )
        mystery = find_card(state2, engine2, 0, "Mystery Action")
        add_ready_ink(state2, engine2, 0, 1, exclude=frozenset({mystery}))

        actions = engine2.legal_actions(state2, 0)
        mystery_actions = [a for a in actions if a.kind == ACTION_PLAY_CARD and a.card == mystery]
        # Unknown selector should not produce any target actions
        assert len(mystery_actions) == 0

    def test_effect_targets_for_card_backward_compat_returns_list_int(self, engine, state):
        """_effect_targets_for_card returns sorted list[int] for backward compatibility."""
        cannon = put_card(state, engine, 0, "Steel Cannon", ZONE_HAND)
        opp = put_card(state, engine, 1, "Amber Recruit", ZONE_PLAY)

        result = engine._effect_targets_for_card(state, 0, cannon)
        assert isinstance(result, list)
        assert all(isinstance(x, int) for x in result)
        assert opp in result

    def test_effect_target_candidates_for_card_returns_target_candidates(self, engine, state):
        """_effect_target_candidates_for_card returns TargetCandidate objects."""
        from lorcana_bot.targeting import TargetCandidate
        cannon = put_card(state, engine, 0, "Steel Cannon", ZONE_HAND)
        opp = put_card(state, engine, 1, "Amber Recruit", ZONE_PLAY)

        result = engine._effect_target_candidates_for_card(state, 0, cannon)
        assert isinstance(result, tuple)
        assert all(isinstance(c, TargetCandidate) for c in result)
        card_ids = [c.id for c in result if c.kind == "card"]
        assert opp in card_ids

    def test_effect_target_descriptors_for_card_returns_descriptors(self, engine, state):
        """_effect_target_descriptors_for_card returns TargetDescriptor objects."""
        from lorcana_bot.targeting import TargetDescriptor
        cannon = put_card(state, engine, 0, "Steel Cannon", ZONE_HAND)

        result = engine._effect_target_descriptors_for_card(state, cannon)
        assert isinstance(result, tuple)
        assert len(result) >= 1
        assert all(isinstance(d, TargetDescriptor) for d in result)

    def test_chosen_item_action_can_target_items(self):
        engine = GameEngine(load_demo_database())
        state = engine.setup_game(
            [
                make_demo_deck(["Demo Target Item Action", "Demo Item"], 50),
                make_demo_deck(["Amber Recruit"], 50),
            ],
            seed=101,
        )
        action_card = put_card(state, engine, 0, "Demo Target Item Action", ZONE_HAND)
        item = put_card(state, engine, 0, "Demo Item", ZONE_PLAY, exclude=frozenset({action_card}))
        assert engine.card_def(state, action_card).id == DEMO_FEATURE_CARD_IDS["target_item_action"]
        assert engine.card_def(state, item).id == DEMO_FEATURE_CARD_IDS["item"]
        add_ready_ink(state, engine, 0, 1, exclude=frozenset({action_card, item}))

        actions = engine.legal_actions(state, 0)
        assert any(a.kind == ACTION_PLAY_CARD and a.card == action_card and a.target == item for a in actions)

    def test_chosen_location_action_can_target_locations(self):
        engine = GameEngine(load_demo_database())
        state = engine.setup_game(
            [
                make_demo_deck(["Demo Target Location Action", "Demo Location"], 50),
                make_demo_deck(["Amber Recruit"], 50),
            ],
            seed=102,
        )
        action_card = put_card(state, engine, 0, "Demo Target Location Action", ZONE_HAND)
        location = put_card(state, engine, 0, "Demo Location", ZONE_PLAY, exclude=frozenset({action_card}))
        assert engine.card_def(state, action_card).id == DEMO_FEATURE_CARD_IDS["target_location_action"]
        assert engine.card_def(state, location).id == DEMO_FEATURE_CARD_IDS["location"]
        add_ready_ink(state, engine, 0, 1, exclude=frozenset({action_card, location}))

        actions = engine.legal_actions(state, 0)
        assert any(a.kind == ACTION_PLAY_CARD and a.card == action_card and a.target == location for a in actions)

    def test_chosen_player_action_uses_choice_and_resolves_player_choice(self):
        engine = GameEngine(load_demo_database())
        state = engine.setup_game(
            [make_demo_deck(["Demo Target Player Action"], 50), make_demo_deck(["Amber Recruit"], 50)],
            seed=103,
        )
        action_card = put_card(state, engine, 0, "Demo Target Player Action", ZONE_HAND)
        assert engine.card_def(state, action_card).id == DEMO_FEATURE_CARD_IDS["target_player_action"]
        add_ready_ink(state, engine, 0, 1, exclude=frozenset({action_card}))

        actions = engine.legal_actions(state, 0)
        player_actions = [
            a for a in actions
            if a.kind == ACTION_PLAY_CARD and a.card == action_card and isinstance(a.choice, dict)
        ]
        assert {(a.target, a.choice["target_kind"], a.choice["player"]) for a in player_actions} == {
            (None, "player", 0),
            (None, "player", 1),
        }

        chosen = next(a for a in player_actions if a.choice["player"] == 1)
        state = engine.apply_action(state, chosen)
        assert state.players[1].lore == 1
        assert state.players[0].lore == 0

    def test_chosen_damaged_character_only_emits_damaged_characters(self):
        engine = GameEngine(load_demo_database())
        state = engine.setup_game(
            [make_demo_deck(["Demo Target Damaged Action"], 50), make_demo_deck(["Amber Recruit", "Amber Guard"], 50)],
            seed=104,
        )
        action_card = put_card(state, engine, 0, "Demo Target Damaged Action", ZONE_HAND)
        assert engine.card_def(state, action_card).id == DEMO_FEATURE_CARD_IDS["target_damaged_action"]
        healthy = put_card(state, engine, 1, "Amber Recruit", ZONE_PLAY)
        damaged = put_card(state, engine, 1, "Amber Guard", ZONE_PLAY, exclude=frozenset({healthy}), damage=1)
        add_ready_ink(state, engine, 0, 1, exclude=frozenset({action_card}))

        actions = engine.legal_actions(state, 0)
        action_targets = {
            a.target for a in actions
            if a.kind == ACTION_PLAY_CARD and a.card == action_card
        }
        assert damaged in action_targets
        assert healthy not in action_targets

    def test_fixed_opponent_player_target_does_not_require_choice_action(self):
        engine = GameEngine(load_demo_database())
        state = engine.setup_game(
            [make_demo_deck(["Demo Fixed Opponent Action"], 50), make_demo_deck(["Amber Recruit"], 50)],
            seed=105,
        )
        lore_loss = put_card(state, engine, 0, "Demo Fixed Opponent Action", ZONE_HAND)
        assert engine.card_def(state, lore_loss).id == DEMO_FEATURE_CARD_IDS["fixed_opponent_action"]

        actions = [a for a in engine.legal_actions(state, 0) if a.kind == ACTION_PLAY_CARD and a.card == lore_loss]
        assert actions == [a for a in actions if a.target is None and a.choice is None]

    def test_unsupported_target_descriptor_does_not_fallback_to_play_cards(self, engine):
        unknown_target_card = CardDef(
            "test_unknown_target_with_board",
            "Mystery Board Action",
            "amber",
            1,
            True,
            "action",
            effects=(EffectDef("draw", 1, "totally_unknown_selector_xyz"),),
        )
        db2 = CardDatabase(engine.db.all_cards() + [unknown_target_card])
        engine2 = GameEngine(db2)
        state = engine2.setup_game(
            [make_demo_deck(["Mystery Board Action"], 50), make_demo_deck(["Amber Recruit"], 50)],
            seed=106,
        )
        mystery = put_card(state, engine2, 0, "Mystery Board Action", ZONE_HAND)
        put_card(state, engine2, 1, "Amber Recruit", ZONE_PLAY)
        add_ready_ink(state, engine2, 0, 1, exclude=frozenset({mystery}))

        actions = engine2.legal_actions(state, 0)
        assert not any(a.kind == ACTION_PLAY_CARD and a.card == mystery for a in actions)

    def test_lorcanito_chosen_strength_target_resolves_through_play_action(self):
        from lorcana_bot.engine import IllegalActionError

        action_def = CardDef(
            "test_worlds_greatest_criminal_mind",
            "Test Criminal Mind",
            "amber",
            1,
            True,
            "action",
            effects=(
                EffectDef(
                    "banish",
                    target={
                        "selector": "chosen",
                        "count": 1,
                        "owner": "any",
                        "zones": ["play"],
                        "cardTypes": ["character"],
                        "filter": [
                            {
                                "type": "strength-comparison",
                                "comparison": "greater-or-equal",
                                "value": 5,
                            }
                        ],
                    },
                ),
            ),
        )
        big = CardDef("test_big", "Big Target", "amber", 1, True, "character", 5, 5, 1)
        small = CardDef("test_small", "Small Target", "amber", 1, True, "character", 4, 4, 1)
        db = CardDatabase(load_demo_database().all_cards() + [action_def, big, small])
        engine = GameEngine(db)
        state = engine.setup_game(
            [make_demo_deck(["Test Criminal Mind"], 50), make_demo_deck(["Big Target", "Small Target"], 50)],
            seed=201,
        )
        action_card = put_card(state, engine, 0, "Test Criminal Mind", ZONE_HAND)
        legal = put_card(state, engine, 1, "Big Target", ZONE_PLAY)
        illegal = put_card(state, engine, 1, "Small Target", ZONE_PLAY)
        add_ready_ink(state, engine, 0, 1, exclude=frozenset({action_card}))

        actions = [a for a in engine.legal_actions(state, 0) if a.kind == ACTION_PLAY_CARD and a.card == action_card]
        assert {a.target for a in actions} == {legal}

        next_state = engine.apply_action(state, actions[0])
        assert legal in next_state.players[1].discard
        assert illegal in next_state.players[1].play

        with pytest.raises(IllegalActionError):
            engine.apply_action(state, actions[0].__class__(ACTION_PLAY_CARD, actor=0, card=action_card, target=illegal, choice={"targets": (illegal,)}))

    def test_lorcanito_chosen_up_to_targets_rejects_duplicates_and_excludes_under(self):
        action_def = CardDef(
            "test_grab_your_bow",
            "Test Grab Your Bow",
            "steel",
            1,
            True,
            "action",
            effects=(
                EffectDef(
                    "banish",
                    target={
                        "selector": "chosen",
                        "count": {"upTo": 2},
                        "owner": "any",
                        "zones": ["play"],
                        "cardTypes": ["character"],
                        "filter": [
                            {
                                "type": "strength-comparison",
                                "comparison": "less-or-equal",
                                "value": 2,
                            }
                        ],
                    },
                ),
            ),
        )
        weak = CardDef("test_weak", "Weak Target", "amber", 1, True, "character", 2, 3, 1)
        db = CardDatabase(load_demo_database().all_cards() + [action_def, weak])
        engine = GameEngine(db)
        state = engine.setup_game(
            [make_demo_deck(["Test Grab Your Bow"], 50), make_demo_deck(["Weak Target"], 50)],
            seed=202,
        )
        action_card = put_card(state, engine, 0, "Test Grab Your Bow", ZONE_HAND)
        target = put_card(state, engine, 1, "Weak Target", ZONE_PLAY)
        under = find_card(state, engine, 1, "Weak Target", exclude=frozenset({target}))
        state.move_card(under, ZONE_UNDER, controller=1)
        add_ready_ink(state, engine, 0, 1, exclude=frozenset({action_card}))

        actions = [a for a in engine.legal_actions(state, 0) if a.kind == ACTION_PLAY_CARD and a.card == action_card]
        assert all(under not in (a.choice or {}).get("targets", ()) for a in actions)
        assert any((a.choice or {}).get("targets") == (target,) for a in actions)
        assert not any((a.choice or {}).get("targets") == (target, target) for a in actions)
