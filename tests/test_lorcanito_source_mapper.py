from lorcana_bot.card_logic import ExecutionStatus, MappingStatus
from lorcana_bot.importers.lorcanito_source_mapper import (
    map_raw_ability,
    map_replacement_ability,
    map_static_ability,
)


def test_keyword_ability_maps_to_source_ability():
    ability = map_raw_ability({"type": "keyword", "keyword": "Singer", "value": 5})
    assert ability.kind == "keyword"
    assert ability.mapping_status == MappingStatus.STRUCTURALLY_MAPPED


def test_action_ability_maps_to_source_ability():
    ability = map_raw_ability({"type": "action", "effect": {"type": "draw", "amount": 2}})
    assert ability.kind == "action"
    assert ability.effects[0].kind == "draw"


def test_triggered_ability_maps_to_source_trigger():
    ability = map_raw_ability({"type": "triggered", "trigger": {"event": "play", "on": "SELF"}, "effect": {"type": "draw"}})
    assert ability.trigger.event == "play"


def test_activated_ability_maps_to_source_cost():
    ability = map_raw_ability({"type": "activated", "cost": {"exert": True}, "effect": {"type": "draw"}})
    assert ability.costs[0].kind == "exert"


def test_static_and_replacement_abilities_are_classified():
    static = map_static_ability({"type": "static", "effect": {"type": "gain-keyword", "target": "SELF"}})
    replacement = map_replacement_ability({"type": "replacement", "replaces": "damage", "effect": {"type": "draw"}})
    assert static.execution_status == ExecutionStatus.UNSUPPORTED_STATIC_EFFECT
    assert replacement.execution_status == ExecutionStatus.UNSUPPORTED_REPLACEMENT_EFFECT


def test_unknown_ability_type_is_preserved_as_unsupported():
    ability = map_raw_ability({"type": "mystery", "custom": {"x": 1}})
    assert ability.raw["custom"] == {"x": 1}
    assert ability.mapping_status == MappingStatus.UNSUPPORTED

