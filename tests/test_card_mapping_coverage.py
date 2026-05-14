from lorcana_bot.cards import load_demo_database
from lorcana_bot.importers.ability_mapper import build_ability_mapping_report, map_effect_from_text


def test_coverage_report_schema():
    report = build_ability_mapping_report(load_demo_database())
    assert report.schema_version == 1
    assert report.total_cards > 0
    assert isinstance(report.unsupported_by_reason, dict)


def test_simple_effect_mapping():
    effect = map_effect_from_text("Draw 2 cards.")
    assert effect.kind == "draw"
    assert effect.amount == 2
