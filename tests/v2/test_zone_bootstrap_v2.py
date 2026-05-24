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

    assert state.framework.player_ids == (PlayerId("p0"), PlayerId("p1"))
    assert state.framework.zones.zone_cards[scoped_zone("deck", "p0")] == ("p0a", "p0b")
    assert state.framework.zones.zone_cards[scoped_zone("deck", "p1")] == ("p1a",)

    p0a = state.framework.zones.card_index["p0a"]
    assert p0a.zone_key == scoped_zone("deck", "p0")
    assert p0a.index == 0
    assert p0a.owner_id == "p0"
    assert p0a.controller_id == "p0"

    assert state.framework.zones.zone_summaries[scoped_zone("deck", "p0")].count == 2
    assert state.framework.zones.zone_summaries[scoped_zone("deck", "p1")].count == 1


def test_zone_bootstrap_rejects_owner_not_in_match():
    resources = resources_for({"x1": "XGm"}, owners={"stranger": ("x1",)})
    try:
        initialize_match_state_from_static_resources(resources)
    except ValueError as exc:
        assert "not a match player" in str(exc)
    else:
        raise AssertionError("expected owner outside match to fail")
