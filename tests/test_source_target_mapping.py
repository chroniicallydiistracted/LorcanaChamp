from lorcana_bot.importers.lorcanito_source_mapper import map_raw_target


def test_alias_targets_map():
    assert map_raw_target("SELF").alias == "SELF"
    assert map_raw_target("CONTROLLER").alias == "CONTROLLER"
    assert map_raw_target("CHOSEN_CHARACTER").alias == "CHOSEN_CHARACTER"


def test_structured_target_preserves_distinct_actor_fields():
    target = map_raw_target(
        {
            "selector": "chosen",
            "owner": "self",
            "controller": "opponent",
            "chooser": "controller",
            "zones": ["play"],
            "cardTypes": ["character"],
            "filters": [{"type": "damaged"}],
            "excludeSelf": True,
        }
    )
    assert target.selector == "chosen"
    assert target.owner == "self"
    assert target.controller == "opponent"
    assert target.chooser == "controller"
    assert target.filters == ({"type": "damaged"},)
    assert target.exclude_self is True

