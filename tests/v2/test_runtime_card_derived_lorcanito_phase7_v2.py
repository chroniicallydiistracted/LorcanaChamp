from lorcana_engine_v2.core.bootstrap import initialize_match_state_from_static_resources
from lorcana_engine_v2.core.ids import InstanceId, PlayerId
from lorcana_engine_v2.core.state import MatchState
from lorcana_engine_v2.core.zones import move_card_to_zone, scoped_zone

from .helpers import resources_for, state_with_play


def _state_with_hand(resources, card_id: str, player_id: str = "p0") -> MatchState:
    state = initialize_match_state_from_static_resources(resources)
    zones = move_card_to_zone(
        state.ctx.zones,
        card_id=InstanceId(card_id),
        destination_zone_key=scoped_zone("hand", player_id),
    )
    return MatchState(G=state.G, ctx=state.ctx.with_updates(zones=zones))


def test_runtime_card_projection_uses_lorcanito_base_fields_and_derived_fields():
    resources = resources_for({"chi": "XGm"})
    state = state_with_play(resources, p0=("chi",))

    from .helpers import context_for

    ctx = context_for(resources)
    card = ctx.query.runtime_card(state, "chi", actor_player_id="p0")

    assert card.instanceId == "chi"
    assert card.definitionId == "XGm"
    assert card.ownerID == PlayerId("p0")
    assert card.controllerID == PlayerId("p0")
    assert card.zoneID == scoped_zone("play", "p0")
    assert card.fullName == "Chi-Fu - Imperial Advisor"
    assert card.willpower == 5
    assert card.lore == 3


def test_can_be_put_in_inkwell_uses_actor_owner_zone_inkability_and_turn_limit():
    from .helpers import context_for

    resources = resources_for({"inkable": "XGm", "non_inkable": "5XS"})
    ctx = context_for(resources)
    state = _state_with_hand(resources, "inkable")
    state = MatchState(
        G=state.G,
        ctx=state.ctx.with_updates(
            status=state.ctx.status.with_updates(gameSegment="mainGame", phase="main", turn=1),
            priority=state.ctx.priority.with_updates(holder=PlayerId("p0"), windowOpen=True),
        ),
    )

    assert ctx.query.runtime_card(state, "inkable", actor_player_id="p0").canBePutInInkwell is True
    assert ctx.query.runtime_card(state, "inkable", actor_player_id="p1").canBePutInInkwell is False

    non_inkable_state = _state_with_hand(resources, "non_inkable")
    assert ctx.query.runtime_card(non_inkable_state, "non_inkable", actor_player_id="p0").canBePutInInkwell is False

    already_inked = MatchState(
        G=state.G.with_updates(turnMetadata=state.G.turnMetadata.record_ink("inkable")),
        ctx=state.ctx,
    )
    assert ctx.query.runtime_card(already_inked, "inkable", actor_player_id="p0").canBePutInInkwell is False
