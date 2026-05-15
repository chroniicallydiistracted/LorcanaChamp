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


def test_resolve_effect_is_illegal_without_pending_effect(engine, state):
    # RESOLVE_EFFECT is now supported, but validation checks engine legality.
    # Without a pending effect, the action won't be in legal_actions.
    candidate = AutomatedActionCandidate(AutomatedActionFamily.RESOLVE_EFFECT, state.active_player, make_stable_key("resolveEffect", state.active_player))
    result = validate_candidate(state, engine, candidate)
    # Should be invalid because the action is not legal (no pending effect)
    assert not result.valid
    assert result.code == "illegal_action"
