from lorcana_bot.automation.candidate_enumerator import enumerate_automated_action_candidates
from lorcana_bot.automation.candidate_validator import validate_candidate
from lorcana_bot.automation.candidates import AutomatedActionCandidate, AutomatedActionFamily, make_stable_key


def test_legal_candidates_pass(engine, state):
    result = enumerate_automated_action_candidates(state, engine, state.active_player)
    assert result.candidates
    assert validate_candidate(state, engine, result.candidates[0]).valid


def test_illegal_candidate_rejects(engine, state):
    candidate = AutomatedActionCandidate(AutomatedActionFamily.QUEST, state.active_player, make_stable_key("quest", state.active_player, source=999), source_instance_id=999)
    result = validate_candidate(state, engine, candidate)
    assert not result.valid
    assert result.code == "source_missing"


def test_unsupported_family_rejects_cleanly(engine, state):
    candidate = AutomatedActionCandidate(AutomatedActionFamily.RESOLVE_EFFECT, state.active_player, make_stable_key("resolveEffect", state.active_player))
    result = validate_candidate(state, engine, candidate)
    assert not result.valid
    assert result.code == "unsupported_candidate_family"
