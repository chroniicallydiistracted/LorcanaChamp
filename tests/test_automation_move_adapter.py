import pytest

from lorcana_bot.automation.candidate_enumerator import enumerate_automated_action_candidates
from lorcana_bot.automation.move_adapter import CandidateAdapterError, candidate_to_action
from lorcana_bot.automation.candidates import AutomatedActionCandidate, make_stable_key


def test_supported_candidates_map_to_legal_actions(engine, state):
    result = enumerate_automated_action_candidates(state, engine, state.active_player)
    legal = engine.legal_actions(state, state.active_player)
    for candidate in result.candidates:
        assert candidate_to_action(candidate) in legal


def test_unsupported_candidate_family_raises():
    candidate = AutomatedActionCandidate("unknown", 0, make_stable_key("unknown", 0))
    with pytest.raises(CandidateAdapterError):
        candidate_to_action(candidate)
