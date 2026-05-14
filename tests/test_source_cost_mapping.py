from lorcana_bot.importers.lorcanito_source_mapper import map_raw_cost


def test_known_cost_fields_map_structurally():
    costs = map_raw_cost({"exert": True, "ink": 2, "discardCards": 1, "banishSelf": True})
    assert {cost.kind for cost in costs} == {"exert", "ink", "discardCards", "banishSelf"}


def test_composite_cost_maps_recursively():
    costs = map_raw_cost({"components": [{"exert": True}, {"ink": 1}]})
    assert costs[0].kind == "components"
    assert [cost.kind for cost in costs[0].components] == ["exert", "ink"]


def test_unknown_cost_field_is_preserved():
    costs = map_raw_cost({"newCost": {"x": 1}})
    assert costs[0].kind == "newCost"
    assert costs[0].raw == {"newCost": {"x": 1}}

