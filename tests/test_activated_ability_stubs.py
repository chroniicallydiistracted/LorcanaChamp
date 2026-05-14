from lorcana_bot.automation.candidates import AutomatedActionCandidate, AutomatedActionFamily, make_stable_key
from lorcana_bot.automation.candidate_validator import validate_candidate


def test_activate_ability_family_exists():
    assert AutomatedActionFamily.ACTIVATE_ABILITY == "activateAbility"


def test_activated_ability_candidate_shape_and_rejection(engine, state):
    candidate = AutomatedActionCandidate(
        AutomatedActionFamily.ACTIVATE_ABILITY,
        state.active_player,
        make_stable_key("activateAbility", state.active_player, source=1, ability="a"),
        source_instance_id=1,
        ability_id="a",
        ability_index=0,
        cost_selections={"exert_source": True},
        targets=(2,),
    )
    result = validate_candidate(state, engine, candidate)
    assert not result.valid
    assert result.code == "unsupported_cost"
