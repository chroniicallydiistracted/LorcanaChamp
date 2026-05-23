from dataclasses import replace

from lorcana_bot.card_logic import ExecutionStatus
from lorcana_bot.cards import CardDef
from lorcana_bot.importers.lorcanito_source_mapper import (
    map_raw_ability,
    project_action_effects,
    project_keywords,
    project_unsupported_abilities,
)


def _card(*abilities):
    return CardDef(
        "c1",
        "Card",
        "amber",
        1,
        True,
        "action",
        source_abilities=tuple(abilities),
        raw_lorcanito_source={"id": "c1"},
    )


def test_simple_keyword_projects_to_compatibility_keywords():
    card = _card(map_raw_ability({"type": "keyword", "keyword": "Rush"}))
    assert project_keywords(card) == ("RUSH",)


def test_simple_targetless_draw_action_projects_to_effects():
    card = _card(map_raw_ability({"type": "action", "effect": {"type": "draw", "amount": 2}}))
    effects = project_action_effects(card)
    assert effects[0].kind == "draw"


def test_unsupported_target_or_condition_prevents_projection():
    target_card = _card(map_raw_ability({"type": "action", "effect": {"type": "draw", "target": {"selector": "chosen"}}}))
    condition_card = _card(map_raw_ability({"type": "action", "effect": {"type": "draw", "condition": {"type": "inkwell-count"}}}))
    assert project_action_effects(target_card) == ()
    assert project_action_effects(condition_card) == ()


def test_static_and_replacement_do_not_project_as_one_shot_effects():
    card = _card(
        map_raw_ability({"type": "static", "effect": {"type": "draw"}}),
        map_raw_ability({"type": "replacement", "effect": {"type": "draw"}}),
    )
    assert project_action_effects(card) == ()
    assert len(project_unsupported_abilities(card)) == 2


def test_lorcanito_scry_destination_action_projects_to_engine_effect():
    ability = map_raw_ability({
        "type": "action",
        "effect": {
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
        },
    })

    assert ability.execution_status == ExecutionStatus.EXECUTABLE

    card = _card(ability)
    effects = project_action_effects(card)

    assert len(effects) == 1
    assert effects[0].kind == "scry"
    assert effects[0].amount == 4
    assert effects[0].raw["raw"]["destinations"][0]["zone"] == "hand"
    assert effects[0].raw["raw"]["destinations"][1]["zone"] == "deck-bottom"
    assert effects[0].raw["raw"]["destinations"][1]["remainder"] is True
