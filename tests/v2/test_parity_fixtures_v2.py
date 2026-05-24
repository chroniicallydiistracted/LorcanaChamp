import json
from pathlib import Path

from lorcana_engine_v2.core.ids import InstanceId, PlayerId
from lorcana_engine_v2.core.static_resources import CardsMaps, create_match_static_resources_from_cards_maps
from lorcana_engine_v2.core.zones import LORCANA_RUNTIME_ZONES

from .helpers import real_catalog


FIXTURE_DIR = Path(__file__).parent / "parity_fixtures"


def test_phase0_cards_maps_fixture_uses_real_lorcanito_card_data():
    payload = json.loads((FIXTURE_DIR / "cards_maps_two_players.json").read_text(encoding="utf-8"))

    assert set(payload) == {"cardInstances", "owners"}
    assert set(payload["owners"]) == {"p0", "p1"}

    cards_maps = CardsMaps.from_raw(payload)
    catalog = real_catalog()

    missing_definitions = sorted(
        str(definition_id)
        for definition_id in cards_maps.card_instances.values()
        if not catalog.has(str(definition_id))
    )
    assert missing_definitions == []

    resources = create_match_static_resources_from_cards_maps(
        cards_maps,
        catalog,
        LORCANA_RUNTIME_ZONES,
    )

    assert resources.instances.ref == "cards-maps:4:kozizs"
    assert resources.instances.require("p0-c1").owner_id == PlayerId("p0")
    assert resources.instances.require("p1-c2").owner_id == PlayerId("p1")
    assert resources.instances.require("p0-c1").definition_id == "XGm"
    assert resources.instances.require("p1-c2").definition_id == "5XS"
    assert set(resources.instances.records) == {
        InstanceId("p0-c1"),
        InstanceId("p0-c2"),
        InstanceId("p1-c1"),
        InstanceId("p1-c2"),
    }

