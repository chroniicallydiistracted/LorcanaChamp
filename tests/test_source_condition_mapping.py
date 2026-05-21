from lorcana_bot.card_logic import ExecutionStatus
from lorcana_bot.importers.lorcanito_source_mapper import map_raw_condition


def test_logical_conditions_map_recursively():
    condition = map_raw_condition({"type": "and", "conditions": [{"type": "has-character-count"}, {"type": "not", "condition": {"type": "inkwell-count"}}]})
    assert condition.kind == "and"
    assert condition.operands[1].kind == "not"
    assert condition.operands[1].operands[0].kind == "inkwell-count"


def test_comparison_and_count_conditions_preserve_fields():
    comparison = map_raw_condition({"type": "comparison", "comparison": ">=", "value": 2, "subject": "lore"})
    count = map_raw_condition({"type": "has-character-count", "amount": 3})
    assert comparison.comparison == ">="
    assert comparison.value == 2
    assert count.value == 3


def test_unsupported_condition_maps_without_crash():
    condition = map_raw_condition({"type": "brand-new-condition"})
    assert condition.execution_status == ExecutionStatus.UNSUPPORTED_CONDITION


def test_used_shift_condition_maps_executable():
    condition = map_raw_condition({"type": "used-shift"})
    assert condition.execution_status == ExecutionStatus.EXECUTABLE
