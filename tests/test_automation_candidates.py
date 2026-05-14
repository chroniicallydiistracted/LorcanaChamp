import copy
import json

from lorcana_bot.automation.candidate_enumerator import enumerate_automated_action_candidates
from lorcana_bot.automation.candidates import AutomatedActionCandidate, AutomatedActionFamily, candidate_to_dict, make_stable_key


def test_every_family_creates_stable_keys():
    keys = [make_stable_key(family, 0, source=1, target=2, choice=0) for family in AutomatedActionFamily]
    assert len(set(keys)) == len(keys)
    assert all("family" in json.loads(key) for key in keys)


def test_candidate_serialization():
    candidate = AutomatedActionCandidate(AutomatedActionFamily.QUEST, 0, make_stable_key("quest", 0, source=1), source_instance_id=1)
    raw = candidate_to_dict(candidate)
    assert raw["family"] == "quest"
    assert raw["source_instance_id"] == 1


def test_enumeration_deduplicates_and_does_not_mutate_state(engine, state):
    before = copy.deepcopy(state)
    result = enumerate_automated_action_candidates(state, engine, state.active_player)
    assert state == before
    assert len({candidate.stable_key for candidate in result.candidates}) == len(result.candidates)
