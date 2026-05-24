from lorcana_engine_v2.core.bootstrap import initialize_match_state_from_static_resources
from lorcana_engine_v2.core.ids import InstanceId, PlayerId, ZoneId
from lorcana_engine_v2.core.zones import (
    ZoneRef,
    build_zone_registry,
    clear_reveals_by_zone,
    create_zone_operations,
    draw_specific_card,
    expire_reveals,
    get_bottom_card,
    get_top_card,
    reveal_cards,
    resolve_zone_id_from_registry,
    scoped_zone,
)

from .helpers import resources_for


def _resources():
    return resources_for(
        {
            "a": "XGm",
            "b": "Y1z",
            "c": "Z2D",
            "d": "5XS",
        },
        owners={"p0": ("a", "b", "c", "d")},
    )


def _state_and_registry():
    resources = _resources()
    state = initialize_match_state_from_static_resources(resources)
    registry = build_zone_registry(resources.zone_definitions, state.ctx.playerIds)
    return state, registry


def test_phase3_resolve_zone_id_matches_lorcanito_owner_scoped_rules():
    state, registry = _state_and_registry()

    assert resolve_zone_id_from_registry(
        ZoneRef(ZoneId("deck"), PlayerId("p0")),
        registry,
        state.ctx.zones.private.cardIndex,
    ) == scoped_zone("deck", "p0")

    try:
        resolve_zone_id_from_registry(
            ZoneRef(ZoneId("deck")),
            registry,
            state.ctx.zones.private.cardIndex,
        )
    except ValueError as exc:
        assert "Owner-scoped zone requires player id: deck" in str(exc)
    else:
        raise AssertionError("expected missing owner-scoped player id to fail")


def test_phase3_draw_cards_moves_from_top_to_hand_and_emits_lorcanito_events():
    state, registry = _state_and_registry()
    events = []
    ops = create_zone_operations(state.ctx.zones, registry, emit_event=events.append)

    drawn = ops.draw_cards(
        from_zone=ZoneRef(ZoneId("deck"), PlayerId("p0")),
        to_zone=ZoneRef(ZoneId("hand"), PlayerId("p0")),
        count=2,
    )

    assert drawn == (InstanceId("c"), InstanceId("b"))
    assert ops.zones.private.zoneCards[scoped_zone("deck", "p0")] == (InstanceId("d"), InstanceId("a"))
    assert ops.zones.private.zoneCards[scoped_zone("hand", "p0")] == (InstanceId("c"), InstanceId("b"))
    assert ops.zones.private.cardIndex[InstanceId("c")].zoneKey == scoped_zone("hand", "p0")
    assert ops.zones.private.cardIndex[InstanceId("c")].index == 0
    assert ops.zones.private.cardIndex[InstanceId("b")].index == 1
    assert ops.zones.public.zoneSummaries[scoped_zone("deck", "p0")].count == 2
    assert ops.zones.public.zoneSummaries[scoped_zone("hand", "p0")].count == 2
    assert any(event["kind"] == "CARD_MOVED" for event in events)
    assert events[-1]["kind"] == "CARDS_DRAWN"
    assert events[-1]["cardIds"] == drawn


def test_phase3_mill_cards_moves_from_top_to_discard_in_order():
    state, registry = _state_and_registry()
    events = []
    ops = create_zone_operations(state.ctx.zones, registry, emit_event=events.append)

    milled = ops.mill(
        from_zone=ZoneRef(ZoneId("deck"), PlayerId("p0")),
        to_zone=ZoneRef(ZoneId("discard"), PlayerId("p0")),
        count=3,
    )

    assert milled == (InstanceId("c"), InstanceId("b"), InstanceId("a"))
    assert ops.zones.private.zoneCards[scoped_zone("discard", "p0")] == milled
    assert ops.zones.private.zoneCards[scoped_zone("deck", "p0")] == (InstanceId("d"),)
    assert events[-1]["kind"] == "CARDS_MILLED"
    assert events[-1]["cardIds"] == milled


def test_phase3_draw_specific_card_returns_false_without_mutation_when_card_missing():
    state, _ = _state_and_registry()

    next_zones, moved = draw_specific_card(
        state.ctx.zones,
        card_id="missing",
        from_zone_key=scoped_zone("deck", "p0"),
        to_zone_key=scoped_zone("hand", "p0"),
    )

    assert moved is False
    assert next_zones == state.ctx.zones


def test_phase3_move_card_at_index_reindexes_destination_zone():
    state, registry = _state_and_registry()
    ops = create_zone_operations(state.ctx.zones, registry)

    ops.move_card("d", ZoneRef(ZoneId("hand"), PlayerId("p0")))
    ops.move_card("c", ZoneRef(ZoneId("hand"), PlayerId("p0")), index=0)

    assert ops.zones.private.zoneCards[scoped_zone("hand", "p0")] == (InstanceId("c"), InstanceId("d"))
    assert ops.zones.private.cardIndex[InstanceId("c")].index == 0
    assert ops.zones.private.cardIndex[InstanceId("d")].index == 1


def test_phase3_shuffle_zone_uses_lorcanito_fisher_yates_and_reindexes():
    state, registry = _state_and_registry()
    random_values = iter((0.0, 0.0, 0.0))
    ops = create_zone_operations(
        state.ctx.zones,
        registry,
        random_float=lambda: next(random_values),
    )

    ops.shuffle(ZoneRef(ZoneId("deck"), PlayerId("p0")))

    assert ops.zones.private.zoneCards[scoped_zone("deck", "p0")] == (
        InstanceId("a"),
        InstanceId("b"),
        InstanceId("c"),
        InstanceId("d"),
    )
    assert ops.zones.private.cardIndex[InstanceId("a")].index == 0
    assert ops.zones.private.cardIndex[InstanceId("d")].index == 3


def test_phase3_public_summary_top_card_only_for_public_face_up_zones():
    state, registry = _state_and_registry()
    ops = create_zone_operations(state.ctx.zones, registry)

    ops.move_card("d", ZoneRef(ZoneId("discard"), PlayerId("p0")))
    assert ops.zones.public.zoneSummaries[scoped_zone("discard", "p0")].topPublicCardID == InstanceId("d")

    ops.move_card("d", ZoneRef(ZoneId("inkwell"), PlayerId("p0")))
    assert ops.zones.public.zoneSummaries[scoped_zone("inkwell", "p0")].topPublicCardID is None


def test_phase3_reveal_windows_allocate_clear_and_expire_like_lorcanito():
    state, _ = _state_and_registry()

    zones, first = reveal_cards(state.ctx.zones, ("a",), "all", expires_at_state_id=3)
    zones, second = reveal_cards(zones, ("b",), (PlayerId("p0"),), expires_at_state_id=10)

    assert (first, second) == ("reveal-0", "reveal-1")
    assert zones.reveals.nextSeq == 2
    assert zones.reveals.active[0].cardIDs == (InstanceId("a"),)
    assert zones.reveals.active[1].visibleTo == (PlayerId("p0"),)

    zones = expire_reveals(zones, current_state_id=5)
    assert tuple(reveal.revealID for reveal in zones.reveals.active) == ("reveal-1",)


def test_phase3_clear_reveals_by_zone_removes_only_reveals_touching_zone_cards():
    state, registry = _state_and_registry()
    ops = create_zone_operations(state.ctx.zones, registry)
    ops.move_card("d", ZoneRef(ZoneId("hand"), PlayerId("p0")))
    zones, _ = reveal_cards(ops.zones, ("d",), "all")
    zones, _ = reveal_cards(zones, ("a",), "all")

    zones = clear_reveals_by_zone(zones, zone_key=scoped_zone("hand", "p0"))

    assert tuple(reveal.revealID for reveal in zones.reveals.active) == ("reveal-1",)


def test_phase3_top_and_bottom_queries_use_lorcanito_array_orientation():
    state, _ = _state_and_registry()

    assert get_bottom_card(state.ctx.zones, scoped_zone("deck", "p0")) == InstanceId("d")
    assert get_top_card(state.ctx.zones, scoped_zone("deck", "p0")) == InstanceId("c")
