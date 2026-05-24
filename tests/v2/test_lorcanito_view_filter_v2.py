from lorcana_engine_v2.core.bootstrap import initialize_match_state_from_static_resources
from lorcana_engine_v2.core.ids import InstanceId, PlayerId, ZoneId
from lorcana_engine_v2.core.state import CtxRandom
from lorcana_engine_v2.core.view_filter import (
    ViewRoleContext,
    filter_match_view,
    get_public_zone_summary,
    verify_no_secret_leakage,
)
from lorcana_engine_v2.core.zones import ZoneRef, build_zone_registry, create_zone_operations, scoped_zone

from .helpers import resources_for


def _resources():
    return resources_for(
        {
            "a": "XGm",
            "b": "Y1z",
            "c": "Z2D",
            "d": "5XS",
        },
        owners={"p0": ("a", "b"), "p1": ("c", "d")},
    )


def _state_registry_and_ops(*, reveal_to_all: bool = False):
    resources = _resources()
    state = initialize_match_state_from_static_resources(resources)
    registry = build_zone_registry(resources.zone_definitions, state.ctx.playerIds)
    ops = create_zone_operations(state.ctx.zones, registry)

    ops.move_card("b", ZoneRef(ZoneId("hand"), PlayerId("p0")))
    ops.move_card("d", ZoneRef(ZoneId("hand"), PlayerId("p1")))
    ops.move_card("c", ZoneRef(ZoneId("play"), PlayerId("p1")))
    if reveal_to_all:
        ops.reveal(("d",), "all")
    else:
        ops.reveal(("d",), (PlayerId("p0"),))

    state = type(state)(G=state.G, ctx=state.ctx.with_updates(zones=ops.zones))
    return state, registry


def test_phase3_player_view_matches_lorcanito_private_public_secret_and_reveal_filtering():
    state, registry = _state_registry_and_ops()

    view = filter_match_view(
        state,
        ViewRoleContext(role="player", playerID=PlayerId("p0")),
        registry,
    )
    private = view.ctx.zones.private

    assert private.zoneCards[scoped_zone("hand", "p0")] == (InstanceId("b"),)
    assert scoped_zone("hand", "p1") not in private.zoneCards
    assert private.zoneCards[scoped_zone("deck", "p0")] == ()
    assert scoped_zone("deck", "p1") not in private.zoneCards
    assert private.zoneCards[scoped_zone("play", "p1")] == (InstanceId("c"),)

    assert private.cardIndex[InstanceId("a")].zoneKey == scoped_zone("deck", "p0")
    assert private.cardIndex[InstanceId("d")].zoneKey == scoped_zone("hand", "p1")
    assert view.ctx.zones.reveals.active[0].cardIDs == (InstanceId("d"),)

    check = verify_no_secret_leakage(
        state,
        view,
        ViewRoleContext(role="player", playerID=PlayerId("p0")),
        registry,
    )
    assert check.valid is True
    assert check.violations == ()


def test_phase3_spectator_view_has_public_summaries_and_all_reveals_without_private_zone_cards():
    state, registry = _state_registry_and_ops(reveal_to_all=True)

    view = filter_match_view(state, ViewRoleContext(role="spectator"), registry)

    assert view.ctx.zones.private.zoneCards == {}
    assert view.ctx.zones.private.cardIndex[InstanceId("d")].zoneKey == scoped_zone("hand", "p1")
    assert view.ctx.zones.reveals.active[0].visibleTo == "all"
    assert view.ctx.zones.public.zoneSummaries[scoped_zone("play", "p1")].count == 1


def test_phase3_judge_view_sees_all_private_zones_and_all_reveals():
    state, registry = _state_registry_and_ops()

    view = filter_match_view(state, ViewRoleContext(role="judge"), registry)

    assert view.ctx.zones.private.zoneCards[scoped_zone("hand", "p0")] == (InstanceId("b"),)
    assert view.ctx.zones.private.zoneCards[scoped_zone("hand", "p1")] == (InstanceId("d"),)
    assert view.ctx.zones.private.zoneCards[scoped_zone("deck", "p0")] == (InstanceId("a"),)
    assert view.ctx.zones.private.zoneCards[scoped_zone("play", "p1")] == (InstanceId("c"),)
    assert view.ctx.zones.reveals.active[0].cardIDs == (InstanceId("d"),)


def test_phase3_filtered_random_keeps_seed_and_draws_but_removes_server_rng_state():
    state, registry = _state_registry_and_ops()
    state = type(state)(
        G=state.G,
        ctx=state.ctx.with_updates(random=CtxRandom(seed="seed-7", state={"server": "private"}, draws=4)),
    )

    view = filter_match_view(
        state,
        ViewRoleContext(role="player", playerID=PlayerId("p0")),
        registry,
    )

    assert view.ctx.random.seed == "seed-7"
    assert view.ctx.random.draws == 4
    assert view.ctx.random.state is None


def test_phase3_public_zone_summary_returns_count_revision_and_safe_top_card_id():
    state, registry = _state_registry_and_ops()
    ops = create_zone_operations(state.ctx.zones, registry)

    ops.move_card("c", ZoneRef(ZoneId("discard"), PlayerId("p1")))
    discard_summary = get_public_zone_summary(ops.zones, registry, scoped_zone("discard", "p1"))
    assert discard_summary.count == 1
    assert discard_summary.revision > 0
    assert discard_summary.topCardID == InstanceId("c")

    ops.move_card("c", ZoneRef(ZoneId("inkwell"), PlayerId("p1")))
    inkwell_summary = get_public_zone_summary(ops.zones, registry, scoped_zone("inkwell", "p1"))
    assert inkwell_summary.count == 1
    assert inkwell_summary.topCardID is None


def test_phase3_player_view_hides_player_only_reveals_from_other_players():
    state, registry = _state_registry_and_ops()

    view = filter_match_view(
        state,
        ViewRoleContext(role="player", playerID=PlayerId("p1")),
        registry,
    )

    assert view.ctx.zones.reveals.active == ()
    assert InstanceId("d") in view.ctx.zones.private.cardIndex
    assert InstanceId("b") not in view.ctx.zones.private.cardIndex
