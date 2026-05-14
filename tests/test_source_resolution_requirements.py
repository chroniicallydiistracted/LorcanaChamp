from lorcana_bot.card_logic.resolution_requirements import analyze_resolution_requirements
from lorcana_bot.importers.lorcanito_source_mapper import map_raw_effect


def test_resolution_requirement_detection():
    assert analyze_resolution_requirements(map_raw_effect({"type": "deal-damage", "target": "CHOSEN_CHARACTER"})).requires_target
    assert analyze_resolution_requirements(map_raw_effect({"type": "optional", "effects": [{"type": "draw"}]})).requires_optional
    assert analyze_resolution_requirements(map_raw_effect({"type": "choice", "branches": [{"type": "draw"}]})).requires_choice
    assert analyze_resolution_requirements(map_raw_effect({"type": "name-a-card"})).requires_named_card
    assert analyze_resolution_requirements(map_raw_effect({"type": "scry", "destinations": [{"ordering": "player-choice"}]})).requires_ordering
    report = analyze_resolution_requirements(map_raw_effect({"type": "draw", "amount": 1}))
    assert not report.requires_target
    assert not report.unsupported_requirements

