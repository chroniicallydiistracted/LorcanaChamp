from lorcana_bot.card_logic import ExecutionStatus
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


def test_lorcanito_scry_destination_requirements_are_runtime_supported():
    effect = map_raw_effect({
        "type": "scry",
        "amount": 4,
        "destinations": [
            {
                "zone": "hand",
                "min": 0,
                "max": 1,
                "reveal": True,
                "filter": {"type": "song"},
            },
            {
                "zone": "deck-bottom",
                "remainder": True,
                "ordering": "player-choice",
            },
        ],
    })

    report = analyze_resolution_requirements(effect)

    assert report.requires_ordering is True
    assert report.requires_destination is True
    assert report.unsupported_requirements == ()
    assert effect.execution_status == ExecutionStatus.EXECUTABLE
