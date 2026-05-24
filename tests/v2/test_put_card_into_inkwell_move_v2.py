from lorcana_engine_v2.core.bootstrap import initialize_match_state_from_static_resources
from lorcana_engine_v2.core.commands import Command
from lorcana_engine_v2.core.ids import InstanceId, PlayerId, ZoneId
from lorcana_engine_v2.core.runtime import MatchRuntime
from lorcana_engine_v2.core.state import MatchState
from lorcana_engine_v2.core.zones import move_card_to_zone, scoped_zone
from lorcana_engine_v2.moves import PUT_CARD_INTO_INKWELL, MoveSpec

from .helpers import context_for, resources_for


def _interim_main_phase_state(state: MatchState, active: PlayerId = PlayerId("p0")) -> MatchState:
    return MatchState(
        G=state.G,
        ctx=state.ctx.with_updates(
            status=state.ctx.status.with_updates(
                turn=1,
                gameSegment="mainGame",
                phase="main",
                turnOwnerId=active,
            ),
            priority=state.ctx.priority.with_updates(
                holder=active,
                windowOpen=True,
                passSequence=(),
                stackDepth=0,
            ),
        ),
    )


def _state_with_hand(resources, *, p0=(), p1=()) -> MatchState:
    state = initialize_match_state_from_static_resources(resources)
    zones = state.ctx.zones
    for card_id in p0:
        zones = move_card_to_zone(
            zones,
            card_id=InstanceId(str(card_id)),
            destination_zone_key=scoped_zone("hand", "p0"),
        )
    for card_id in p1:
        zones = move_card_to_zone(
            zones,
            card_id=InstanceId(str(card_id)),
            destination_zone_key=scoped_zone("hand", "p1"),
        )
    return _interim_main_phase_state(MatchState(G=state.G, ctx=state.ctx.with_updates(zones=zones)))


def test_v2_enumerates_real_inkable_hand_card_as_put_card_into_inkwell_move():
    resources = resources_for({"c1": "XGm"})  # Chi-Fu - Imperial Advisor, inkable real card
    state = _state_with_hand(resources, p0=("c1",))
    runtime = MatchRuntime(resources)

    moves = runtime.legal_moves(state, "p0")

    assert moves == (
        MoveSpec(
            kind=PUT_CARD_INTO_INKWELL,
            actor=PlayerId("p0"),
            card=InstanceId("c1"),
        ),
    )


def test_v2_put_card_into_inkwell_moves_real_card_and_records_turn_metadata():
    resources = resources_for({"c1": "XGm"})
    state = _state_with_hand(resources, p0=("c1",))
    runtime = MatchRuntime(resources)

    result = runtime.apply(
        state,
        Command(kind=PUT_CARD_INTO_INKWELL, actor=PlayerId("p0"), card=InstanceId("c1")),
    )

    assert result.accepted is True
    assert result.reason is None
    assert len(result.events) == 1
    assert result.events[0].kind == "card.inked"
    assert result.events[0].actor == PlayerId("p0")
    assert result.events[0].source == InstanceId("c1")

    next_state = result.state
    assert InstanceId("c1") not in next_state.ctx.zones.private.zoneCards[scoped_zone("hand", "p0")]
    assert InstanceId("c1") in next_state.ctx.zones.private.zoneCards[scoped_zone("inkwell", "p0")]
    assert next_state.ctx.zones.private.cardIndex[InstanceId("c1")].zoneKey == ZoneId("inkwell:p0")
    assert next_state.ctx._stateID == state.ctx._stateID + 1
    assert next_state.G.turnMetadata.inkedThisTurn == (InstanceId("c1"),)
    assert next_state.G.turnMetadata.cardsPutIntoInkwellThisTurn == (InstanceId("c1"),)

    meta = next_state.ctx.zones.private.cardMeta[InstanceId("c1")]
    assert meta.state == "ready"
    assert meta.publicFaceState == "faceDown"


def test_v2_put_card_into_inkwell_rejects_second_ink_same_turn():
    resources = resources_for({"c1": "XGm", "c2": "Y1z"})
    state = _state_with_hand(resources, p0=("c1", "c2"))
    runtime = MatchRuntime(resources)

    first = runtime.apply(
        state,
        Command(kind=PUT_CARD_INTO_INKWELL, actor=PlayerId("p0"), card=InstanceId("c1")),
    )
    assert first.accepted is True

    assert runtime.legal_moves(first.state, "p0") == ()

    second = runtime.apply(
        first.state,
        Command(kind=PUT_CARD_INTO_INKWELL, actor=PlayerId("p0"), card=InstanceId("c2")),
    )
    assert second.accepted is False
    assert second.reason == "Already inked this turn"
    assert InstanceId("c2") in second.state.ctx.zones.private.zoneCards[scoped_zone("hand", "p0")]


def test_v2_put_card_into_inkwell_rejects_real_non_inkable_card():
    resources = resources_for({"c1": "5XS"})  # Ariel - Whoseit Collector, non-inkable real card
    state = _state_with_hand(resources, p0=("c1",))
    runtime = MatchRuntime(resources)

    assert resources.cards.get("5XS").inkable is False
    assert runtime.legal_moves(state, "p0") == ()

    result = runtime.apply(
        state,
        Command(kind=PUT_CARD_INTO_INKWELL, actor=PlayerId("p0"), card=InstanceId("c1")),
    )
    assert result.accepted is False
    assert result.reason == "Card is not inkable"
    assert InstanceId("c1") in state.ctx.zones.private.zoneCards[scoped_zone("hand", "p0")]


def test_v2_put_card_into_inkwell_rejects_card_not_in_hand():
    resources = resources_for({"c1": "XGm"})
    state = _interim_main_phase_state(initialize_match_state_from_static_resources(resources))
    runtime = MatchRuntime(resources)

    result = runtime.apply(
        state,
        Command(kind=PUT_CARD_INTO_INKWELL, actor=PlayerId("p0"), card=InstanceId("c1")),
    )
    assert result.accepted is False
    assert result.reason == "Card not in hand"


def test_v2_put_card_into_inkwell_rejects_non_priority_player():
    resources = resources_for(
        {"c1": "XGm", "c2": "Y1z"},
        owners={"p0": ("c1",), "p1": ("c2",)},
    )
    state = _state_with_hand(resources, p1=("c2",))
    runtime = MatchRuntime(resources)

    assert state.ctx.priority.holder == PlayerId("p0")
    assert runtime.legal_moves(state, "p1") == ()

    result = runtime.apply(
        state,
        Command(kind=PUT_CARD_INTO_INKWELL, actor=PlayerId("p1"), card=InstanceId("c2")),
    )
    assert result.accepted is False
    assert result.reason == "Player 'p1' does not currently have priority"


def test_v2_put_card_into_inkwell_accepts_payload_card_id_for_lorcanito_style_input():
    resources = resources_for({"c1": "XGm"})
    state = _state_with_hand(resources, p0=("c1",))
    runtime = MatchRuntime(resources)

    result = runtime.apply(
        state,
        Command(
            kind=PUT_CARD_INTO_INKWELL,
            actor=PlayerId("p0"),
            payload={"cardId": "c1"},
        ),
    )

    assert result.accepted is True
    assert InstanceId("c1") in result.state.ctx.zones.private.zoneCards[scoped_zone("inkwell", "p0")]
