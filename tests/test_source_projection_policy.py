from dataclasses import replace

from lorcana_bot.card_logic import ExecutionStatus
from lorcana_bot.cards import CardDef
from lorcana_bot.importers.lorcanito_source_mapper import (
    map_raw_ability,
    map_raw_target,
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


def test_microfix19_lorcanito_player_target_alias_challenging_player_maps_executable():
    ability = map_raw_ability({
        "type": "triggered",
        "trigger": {"event": "challenged", "on": "SELF", "timing": "whenever"},
        "effect": {
            "type": "discard",
            "target": "CHALLENGING_PLAYER",
            "amount": 1,
            "chosen": True,
            "from": "hand",
        },
    })

    assert ability.execution_status == ExecutionStatus.EXECUTABLE
    assert ability.effects[0].target is not None
    assert ability.effects[0].target.execution_status == ExecutionStatus.EXECUTABLE

    card = CardDef(
        "challenging_player_card",
        "Challenging Player Card",
        "emerald",
        2,
        True,
        "character",
        strength=1,
        willpower=3,
        lore=1,
        source_abilities=(ability,),
    )

    assert card.source_abilities[0].effects[0].target.alias == "CHALLENGING_PLAYER"


def test_microfix19_lorcanito_your_chosen_character_alias_projects():
    ability = map_raw_ability({
        "type": "action",
        "effect": {
            "type": "remove-damage",
            "amount": {"type": "up-to", "value": 3},
            "target": "YOUR_CHOSEN_CHARACTER",
        },
    })

    assert ability.execution_status == ExecutionStatus.EXECUTABLE

    effects = project_action_effects(_card(ability))

    assert len(effects) == 1
    assert effects[0].kind == "remove_damage"
    assert effects[0].target == "your_chosen_character"


def test_microfix19_lorcanito_status_filter_and_card_wildcard_project():
    status_ability = map_raw_ability({
        "type": "action",
        "effect": {
            "type": "deal-damage",
            "amount": 2,
            "target": {
                "selector": "chosen",
                "count": 1,
                "owner": "any",
                "zones": ["play"],
                "cardTypes": ["character"],
                "filter": [{"type": "status", "status": "damaged"}],
            },
        },
    })
    wildcard_ability = map_raw_ability({
        "type": "triggered",
        "trigger": {"event": "play", "on": "SELF", "timing": "when"},
        "effect": {
            "type": "shuffle-into-deck",
            "target": {
                "selector": "chosen",
                "count": 1,
                "owner": "any",
                "zones": ["discard"],
                "cardTypes": ["card"],
            },
        },
    })

    assert status_ability.execution_status == ExecutionStatus.EXECUTABLE
    assert wildcard_ability.execution_status == ExecutionStatus.EXECUTABLE
    assert status_ability.effects[0].target.execution_status == ExecutionStatus.EXECUTABLE
    assert wildcard_ability.effects[0].target.execution_status == ExecutionStatus.EXECUTABLE


def test_microfix19_lorcanito_seven_dwarfs_alias_maps_executable():
    ability = map_raw_ability({
        "type": "triggered",
        "trigger": {"event": "banish", "on": "SELF", "timing": "when"},
        "effect": {
            "type": "modify-stat",
            "stat": "strength",
            "modifier": 2,
            "duration": "until-start-of-next-turn",
            "target": "YOUR_OTHER_SEVEN_DWARFS_CHARACTERS",
        },
    })

    assert ability.execution_status == ExecutionStatus.EXECUTABLE
    assert ability.effects[0].target is not None
    assert ability.effects[0].target.execution_status == ExecutionStatus.EXECUTABLE


def test_microfix20_lorcanito_chosen_count_two_target_projects():
    ability = map_raw_ability({
        "type": "action",
        "effect": {
            "type": "deal-damage",
            "amount": 1,
            "target": {
                "selector": "chosen",
                "count": 2,
                "owner": "opponent",
                "zones": ["play"],
                "cardTypes": ["character"],
            },
        },
    })

    assert ability.execution_status == ExecutionStatus.EXECUTABLE
    assert ability.effects[0].target is not None
    assert ability.effects[0].target.execution_status == ExecutionStatus.EXECUTABLE

    effects = project_action_effects(_card(ability))

    assert len(effects) == 1
    assert effects[0].kind == "deal_damage"
    assert isinstance(effects[0].target, dict)
    assert effects[0].target["selector"] == "chosen"
    assert effects[0].target["count"] == 2
    assert effects[0].target["cardTypes"] == ["character"]


def test_microfix20_lorcanito_exactly_count_target_projects():
    ability = map_raw_ability({
        "type": "action",
        "effect": {
            "type": "exert",
            "target": {
                "selector": "chosen",
                "count": {"exactly": 2},
                "owner": "any",
                "zones": ["play"],
                "cardTypes": ["character"],
            },
        },
    })

    assert ability.execution_status == ExecutionStatus.EXECUTABLE
    assert ability.effects[0].target is not None
    assert ability.effects[0].target.execution_status == ExecutionStatus.EXECUTABLE


def test_microfix21_remaining_target_aliases_project():
    for alias in (
        "OPPONENTS",
        "UP_TO_2_CHOSEN_CHARACTERS",
        "CHOSEN_OPPOSING_CHARACTER_3_STRENGTH_OR_LESS",
        "YOUR_EXERTED_CHARACTERS",
    ):
        target = map_raw_target(alias)
        assert target.execution_status == ExecutionStatus.EXECUTABLE


def test_microfix21_selector_self_object_is_executable():
    target = map_raw_target({
        "selector": "self",
        "count": 1,
        "owner": "any",
        "zones": ["play"],
        "cardTypes": ["character"],
    })

    assert target.execution_status == ExecutionStatus.EXECUTABLE


def test_microfix21_challenged_this_turn_filter_is_supported():
    target = map_raw_target({
        "selector": "chosen",
        "count": 1,
        "owner": "any",
        "zones": ["play"],
        "cardTypes": ["character"],
        "filter": [{"type": "challenged-this-turn"}],
    })

    assert target.execution_status == ExecutionStatus.EXECUTABLE
