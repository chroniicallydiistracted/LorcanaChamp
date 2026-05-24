from lorcana_engine_v2.core.bootstrap import initialize_match_state_from_static_resources
from lorcana_engine_v2.core.ids import PlayerId
from lorcana_engine_v2.core.runtime_config import (
    MatchInitContext,
    Player,
    extract_initial_flow_state,
    initialize_match_state,
)
from lorcana_engine_v2.core.zones import scoped_zone
from lorcana_engine_v2.flow.runtime_flow_config import lorcana_runtime_flow
from lorcana_engine_v2.runtime_game.definition import (
    lorcana_runtime_config,
    lorcana_runtime_zones,
)

from .helpers import resources_for


def test_phase4_flow_config_starts_where_lorcanito_starts():
    status = extract_initial_flow_state(lorcana_runtime_flow)

    assert status.initialGameSegment == "startingAGame"
    assert status.initialPhase == "chooseFirstPlayer"
    assert lorcana_runtime_flow.gameSegments["startingAGame"].next == "mainGame"
    assert lorcana_runtime_flow.gameSegments["startingAGame"].turn.phases[
        "chooseFirstPlayer"
    ].validMoves == ("chooseWhoGoesFirst",)
    assert lorcana_runtime_flow.gameSegments["startingAGame"].turn.phases[
        "mulligan"
    ].validMoves == ("alterHand",)
    assert "putCardIntoInkwell" in lorcana_runtime_flow.gameSegments["mainGame"].turn.phases[
        "main"
    ].validMoves


def test_phase4_initialize_match_state_uses_runtime_config_flow_and_board_setup():
    resources = resources_for(
        {
            "p0a": "XGm",
            "p0b": "Y1z",
            "p0c": "Z2D",
            "p0d": "5XS",
            "p1a": "HyV",
            "p1b": "XGm",
            "p1c": "Y1z",
        },
        owners={"p0": ("p0a", "p0b", "p0c", "p0d"), "p1": ("p1a", "p1b", "p1c")},
    )

    result = initialize_match_state(
        MatchInitContext(
            config=lorcana_runtime_config,
            players=(Player(PlayerId("p0")), Player(PlayerId("p1"))),
            staticResources=resources,
            seed="phase4-seed",
            matchID="match-fixed",
            gameID="game-fixed",
        )
    )
    state = result.state

    assert result.staticResources is resources
    assert result.board == {}
    assert state.ctx.matchID == "match-fixed"
    assert state.ctx.gameID == "game-fixed"
    assert state.ctx.rulesetHash.startswith("ruleset-Disney Lorcana TCG-")
    assert state.ctx.playerIds == (PlayerId("p0"), PlayerId("p1"))
    assert state.ctx.status.gameSegment == "startingAGame"
    assert state.ctx.status.phase == "chooseFirstPlayer"
    assert state.ctx.status.turn == 0
    assert state.ctx.status.turnOwnerId is None
    assert state.ctx.priority.holder is None
    assert state.ctx.priority.windowOpen is False
    assert state.G.lore == {PlayerId("p0"): 0, PlayerId("p1"): 0}

    assert state.ctx.zones.private.zoneCards[scoped_zone("deck", "p0")] == (
        "p0d",
        "p0a",
        "p0c",
        "p0b",
    )
    assert state.ctx.zones.private.zoneCards[scoped_zone("deck", "p1")] == (
        "p1a",
        "p1c",
        "p1b",
    )
    assert state.ctx.random.seed == "phase4-seed"
    assert state.ctx.random.draws == 5
    assert state.ctx.zones.private.cardMeta == {}
    assert state.ctx.zones.public.zoneSummaries[scoped_zone("deck", "p0")].revision == 1
    assert state.ctx.zones.public.zoneSummaries[scoped_zone("deck", "p0")].count == 4
    assert state.ctx.zones.public.zoneSummaries[scoped_zone("deck", "p0")].topPublicCardID is None


def test_phase4_initialize_match_state_opens_priority_only_for_choosing_first_player():
    resources = resources_for({"p0a": "XGm", "p1a": "HyV"}, owners={"p0": ("p0a",), "p1": ("p1a",)})

    state = initialize_match_state_from_static_resources(
        resources,
        seed="phase4-seed",
        match_id="match-fixed",
        game_id="game-fixed",
        choosing_first_player=PlayerId("p1"),
    )

    assert state.ctx.status.gameSegment == "startingAGame"
    assert state.ctx.status.phase == "chooseFirstPlayer"
    assert state.ctx.status.choosingFirstPlayer == PlayerId("p1")
    assert state.ctx.priority.holder == PlayerId("p1")
    assert state.ctx.priority.windowOpen is True


def test_phase4_lorcana_runtime_config_requires_exactly_two_players():
    resources = resources_for({"p0a": "XGm"}, owners={"p0": ("p0a",)})

    try:
        initialize_match_state(
            MatchInitContext(
                config=lorcana_runtime_config,
                players=(Player(PlayerId("p0")),),
                staticResources=resources,
                seed="phase4-seed",
            )
        )
    except ValueError as exc:
        assert "Lorcana requires exactly 2 players" in str(exc)
    else:
        raise AssertionError("expected one-player Lorcana initialization to fail")


def test_phase4_runtime_zones_are_the_lorcanito_zone_config():
    assert lorcana_runtime_zones["deck"].visibility == "secret"
    assert lorcana_runtime_zones["deck"].ordered is True
    assert lorcana_runtime_zones["deck"].owner_scoped is True
    assert lorcana_runtime_zones["deck"].face_down is True
    assert lorcana_runtime_zones["inkwell"].visibility == "public"
    assert lorcana_runtime_zones["inkwell"].face_down is True
