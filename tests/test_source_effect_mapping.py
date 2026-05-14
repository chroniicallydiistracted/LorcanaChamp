from lorcana_bot.card_logic import ExecutionStatus, MappingStatus
from lorcana_bot.importers.lorcanito_source_mapper import map_raw_effect


def test_sequence_optional_conditional_and_choice_map_recursively():
    sequence = map_raw_effect({"type": "sequence", "effects": [{"type": "draw"}, {"type": "gain-lore", "amount": 1}]})
    optional = map_raw_effect({"type": "optional", "effects": [{"type": "draw"}]})
    conditional = map_raw_effect({"type": "conditional", "condition": {"type": "always"}, "effects": [{"type": "draw"}]})
    choice = map_raw_effect({"type": "choice", "branches": [{"type": "draw"}, {"type": "gain-lore"}]})
    assert [effect.kind for effect in sequence.effects] == ["draw", "gain-lore"]
    assert optional.optional is True and optional.effects[0].kind == "draw"
    assert conditional.condition.kind == "always"
    assert [branch.kind for branch in choice.branches] == ["draw", "gain-lore"]


def test_common_effects_map_structurally():
    assert map_raw_effect({"type": "draw", "amount": 2}).kind == "draw"
    assert map_raw_effect({"type": "deal-damage", "target": "CHOSEN_CHARACTER", "amount": 2}).target.alias == "CHOSEN_CHARACTER"
    assert map_raw_effect({"type": "banish", "target": "SELF"}).target.alias == "SELF"


def test_unsupported_effect_type_is_preserved():
    effect = map_raw_effect({"type": "future-effect", "payload": 1})
    assert effect.mapping_status == MappingStatus.UNSUPPORTED
    assert effect.execution_status == ExecutionStatus.UNSUPPORTED_ENGINE_MECHANIC
    assert effect.raw["payload"] == 1

