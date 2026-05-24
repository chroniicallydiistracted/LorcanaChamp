from lorcana_engine_v2.core.bootstrap import initialize_match_state_from_static_resources
from lorcana_engine_v2.core.ids import PlayerId
from lorcana_engine_v2.core.zones import scoped_zone

from .helpers import resources_for


def test_zone_bootstrap_creates_owner_scoped_deck_zones_from_static_resources():
    resources = resources_for(
        {"p0a": "XGm", "p0b": "Z2D", "p1a": "HyV"},
        owners={"p0": ("p0a", "p0b"), "p1": ("p1a",)},
    )
    state = initialize_match_state_from_static_resources(resources)

    assert state.ctx.playerIds == (PlayerId("p0"), PlayerId("p1"))
    assert state.ctx.zones.private.zoneCards[scoped_zone("deck", "p0")] == ("p0a", "p0b")
    assert state.ctx.zones.private.zoneCards[scoped_zone("deck", "p1")] == ("p1a",)

    p0a = state.ctx.zones.private.cardIndex["p0a"]
    assert p0a.zoneKey == scoped_zone("deck", "p0")
    assert p0a.index == 0
    assert p0a.ownerID == "p0"
    assert p0a.controllerID == "p0"

    assert state.ctx.zones.public.zoneSummaries[scoped_zone("deck", "p0")].count == 2
    assert state.ctx.zones.public.zoneSummaries[scoped_zone("deck", "p1")].count == 1


def test_zone_bootstrap_ignores_static_resource_owner_not_in_match_like_lorcanito_board_setup():
    resources = resources_for({"x1": "XGm"}, owners={"stranger": ("x1",)})
    state = initialize_match_state_from_static_resources(resources)

    assert state.ctx.zones.private.zoneCards[scoped_zone("deck", "p0")] == ()
    assert state.ctx.zones.private.zoneCards[scoped_zone("deck", "p1")] == ()
    assert "x1" not in state.ctx.zones.private.cardIndex
