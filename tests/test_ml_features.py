import copy

from lorcana_bot.automation.candidate_enumerator import enumerate_automated_action_candidates
from lorcana_bot.automation.deck_profile import build_deck_profile
from lorcana_bot.automation.ml.candidate_encoder import candidate_feature_length, encode_candidate_features
from lorcana_bot.automation.ml.feature_extractor import extract_state_features, state_feature_length


def test_feature_vector_lengths_stable(engine, state):
    deck = [state.cards[cid].card_id for cid in state.players[0].deck + state.players[0].hand]
    profile = build_deck_profile(deck, engine.db)
    assert len(extract_state_features(state, engine, 0, "fair", profile)) == state_feature_length()
    candidate = enumerate_automated_action_candidates(state, engine, 0).candidates[0]
    assert len(encode_candidate_features(state, engine, 0, candidate, profile)) == candidate_feature_length()


def test_feature_extraction_does_not_mutate(engine, state):
    before = copy.deepcopy(state)
    extract_state_features(state, engine, 0, "fair", None)
    assert state == before
