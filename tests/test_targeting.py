from __future__ import annotations

import pytest

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
from lorcana_bot.targeting import (
    TargetCandidate,
    TargetDescriptor,
    TargetQueryContext,
    infer_candidate_zones,
    is_card_target_candidate,
    is_player_target_candidate,
    normalize_target_descriptor,
    normalize_target_descriptors,
    resolve_candidate_card_ids,
    resolve_candidate_player_ids,
    resolve_candidate_targets,
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
