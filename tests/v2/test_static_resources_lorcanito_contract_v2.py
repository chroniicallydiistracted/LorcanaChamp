import pytest

from lorcana_engine_v2.core.ids import CardId, InstanceId, PlayerId
from lorcana_engine_v2.core.static_resources import (
    CardsMaps,
    create_cards_maps_from_static_resources,
    create_match_static_resources_from_cards_maps,
)
from lorcana_engine_v2.core.zones import LORCANA_RUNTIME_ZONES

from .helpers import real_catalog


def _cards_maps() -> CardsMaps:
    return CardsMaps(
        card_instances={
            InstanceId("a1"): CardId("XGm"),
            InstanceId("a2"): CardId("Z2D"),
        },
        owners={
            PlayerId("p0"): (InstanceId("a1"),),
            PlayerId("p1"): (InstanceId("a2"),),
        },
    )


def test_phase1_cards_maps_ref_matches_lorcanito_static_resources_hash():
    resources = create_match_static_resources_from_cards_maps(
        _cards_maps(),
        real_catalog(),
        LORCANA_RUNTIME_ZONES,
    )

    assert resources.instances.ref == "cards-maps:2:12t0iyy"


def test_phase1_cards_maps_ref_sorts_map_entries_but_preserves_owner_card_order():
    first = CardsMaps.from_raw(
        {
            "cardInstances": {"a2": "Z2D", "a1": "XGm"},
            "owners": {"p1": ["a2"], "p0": ["a1"]},
        }
    )
    same_logical_maps = CardsMaps.from_raw(
        {
            "cardInstances": {"a1": "XGm", "a2": "Z2D"},
            "owners": {"p0": ["a1"], "p1": ["a2"]},
        }
    )
    different_owner_order = CardsMaps.from_raw(
        {
            "cardInstances": {"a1": "XGm", "a2": "Z2D"},
            "owners": {"p0": ["a2", "a1"], "p1": []},
        }
    )

    first_ref = create_match_static_resources_from_cards_maps(
        first,
        real_catalog(),
        LORCANA_RUNTIME_ZONES,
    ).instances.ref
    same_ref = create_match_static_resources_from_cards_maps(
        same_logical_maps,
        real_catalog(),
        LORCANA_RUNTIME_ZONES,
    ).instances.ref
    different_ref = create_match_static_resources_from_cards_maps(
        different_owner_order,
        real_catalog(),
        LORCANA_RUNTIME_ZONES,
    ).instances.ref

    assert first_ref == same_ref == "cards-maps:2:12t0iyy"
    assert different_ref != first_ref


def test_phase1_cards_maps_from_raw_rejects_non_mapping_fields():
    with pytest.raises(TypeError, match="cardInstances must be a mapping"):
        CardsMaps.from_raw({"cardInstances": ["a1"], "owners": {}})

    with pytest.raises(TypeError, match="owners must be a mapping"):
        CardsMaps.from_raw({"cardInstances": {}, "owners": ["p0"]})

    with pytest.raises(TypeError, match="owners values must be lists"):
        CardsMaps.from_raw({"cardInstances": {"a1": "XGm"}, "owners": {"p0": "a1"}})


def test_phase1_static_resources_reject_owner_reference_to_unknown_instance():
    cards_maps = CardsMaps(
        card_instances={InstanceId("known"): CardId("XGm")},
        owners={PlayerId("p0"): (InstanceId("known"), InstanceId("missing"))},
    )

    with pytest.raises(ValueError, match="references unknown instance 'missing'"):
        create_match_static_resources_from_cards_maps(cards_maps, real_catalog(), LORCANA_RUNTIME_ZONES)


def test_phase1_static_resources_reject_unowned_instance():
    cards_maps = CardsMaps(
        card_instances={InstanceId("unowned"): CardId("XGm")},
        owners={PlayerId("p0"): ()},
    )

    with pytest.raises(ValueError, match="missing owner for instance 'unowned'"):
        create_match_static_resources_from_cards_maps(cards_maps, real_catalog(), LORCANA_RUNTIME_ZONES)


def test_phase1_static_resources_reject_duplicate_owner_assignment():
    cards_maps = CardsMaps(
        card_instances={InstanceId("dup"): CardId("XGm")},
        owners={
            PlayerId("p0"): (InstanceId("dup"),),
            PlayerId("p1"): (InstanceId("dup"),),
        },
    )

    with pytest.raises(ValueError, match="duplicate instance 'dup'"):
        create_match_static_resources_from_cards_maps(cards_maps, real_catalog(), LORCANA_RUNTIME_ZONES)


def test_phase1_static_resources_reject_missing_card_definition():
    cards_maps = CardsMaps(
        card_instances={InstanceId("bad"): CardId("missing-definition")},
        owners={PlayerId("p0"): (InstanceId("bad"),)},
    )

    with pytest.raises(ValueError, match="missing card definition 'missing-definition'"):
        create_match_static_resources_from_cards_maps(cards_maps, real_catalog(), LORCANA_RUNTIME_ZONES)


def test_phase1_static_resources_round_trip_preserves_lorcanito_cards_maps_shape():
    resources = create_match_static_resources_from_cards_maps(
        _cards_maps(),
        real_catalog(),
        LORCANA_RUNTIME_ZONES,
    )

    round_tripped = create_cards_maps_from_static_resources(resources)

    assert round_tripped.to_raw() == {
        "cardInstances": {
            "a1": "XGm",
            "a2": "Z2D",
        },
        "owners": {
            "p0": ["a1"],
            "p1": ["a2"],
        },
    }

