import pytest

from lorcana_engine_v2.core.ids import CardId, InstanceId, PlayerId
from lorcana_engine_v2.core.static_resources import (
    CardsMaps,
    create_cards_maps_from_static_resources,
    create_match_static_resources_from_cards_maps,
    get_static_resource_refs,
)
from lorcana_engine_v2.core.zones import LORCANA_RUNTIME_ZONES

from .helpers import real_catalog


def test_static_resources_build_instance_registry_from_cards_maps():
    catalog = real_catalog()
    cards_maps = CardsMaps(
        card_instances={InstanceId("a1"): CardId("XGm"), InstanceId("a2"): CardId("Z2D")},
        owners={PlayerId("p0"): (InstanceId("a1"),), PlayerId("p1"): (InstanceId("a2"),)},
    )
    resources = create_match_static_resources_from_cards_maps(cards_maps, catalog, LORCANA_RUNTIME_ZONES)

    assert resources.cards.get("XGm").full_name == "Chi-Fu - Imperial Advisor"
    assert resources.instances.require("a1").definition_id == "XGm"
    assert resources.instances.require("a1").owner_id == "p0"
    assert resources.instances.require("a2").owner_id == "p1"
    assert resources.instances.ref.startswith("cards-maps:2:")

    refs = get_static_resource_refs(resources)
    assert refs.cards_catalog_ref == "lorcana:cards"
    assert refs.card_instances_ref == resources.instances.ref


def test_static_resources_round_trip_to_cards_maps():
    catalog = real_catalog()
    cards_maps = CardsMaps(
        card_instances={InstanceId("c1"): CardId("XGm")},
        owners={PlayerId("p0"): (InstanceId("c1"),)},
    )
    resources = create_match_static_resources_from_cards_maps(cards_maps, catalog, LORCANA_RUNTIME_ZONES)
    round_tripped = create_cards_maps_from_static_resources(resources)
    assert round_tripped.to_raw() == cards_maps.to_raw()


def test_static_resources_reject_missing_card_definition():
    catalog = real_catalog()
    cards_maps = CardsMaps(
        card_instances={InstanceId("bad1"): CardId("missing")},
        owners={PlayerId("p0"): (InstanceId("bad1"),)},
    )
    with pytest.raises(ValueError, match="missing card definition"):
        create_match_static_resources_from_cards_maps(cards_maps, catalog, LORCANA_RUNTIME_ZONES)


def test_static_resources_reject_missing_owner_for_instance():
    catalog = real_catalog()
    cards_maps = CardsMaps(
        card_instances={InstanceId("bad1"): CardId("XGm")},
        owners={PlayerId("p0"): ()},
    )
    with pytest.raises(ValueError, match="missing owner"):
        create_match_static_resources_from_cards_maps(cards_maps, catalog, LORCANA_RUNTIME_ZONES)


def test_static_resources_reject_duplicate_owner_assignment():
    catalog = real_catalog()
    cards_maps = CardsMaps(
        card_instances={InstanceId("dup"): CardId("XGm")},
        owners={PlayerId("p0"): (InstanceId("dup"),), PlayerId("p1"): (InstanceId("dup"),)},
    )
    with pytest.raises(ValueError, match="duplicate instance"):
        create_match_static_resources_from_cards_maps(cards_maps, catalog, LORCANA_RUNTIME_ZONES)
