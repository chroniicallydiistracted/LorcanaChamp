from lorcana_engine_v2.core.random import create_random_api_for_ctx, seedrandom
from lorcana_engine_v2.core.state import CtxRandom


def test_phase4_seedrandom_matches_lorcanito_seedrandom_3_0_5_string_seed_values():
    assert seedrandom("v2-default-seed:1") == 0.557616498233769
    assert seedrandom("v2-default-seed:2") == 0.40167319350915814
    assert seedrandom("seed-1:1") == 0.8234770753436266
    assert seedrandom("abc:1") == 0.5324675331990326
    assert seedrandom("abc:2") == 0.834100008904982


def test_phase4_random_api_increments_draws_like_lorcanito_runtime_random_api():
    api = create_random_api_for_ctx(CtxRandom(seed="abc"))

    assert api.random() == 0.5324675331990326
    assert api.ctx_random.draws == 1
    assert api.random() == 0.834100008904982
    assert api.ctx_random.draws == 2


def test_phase4_random_api_shuffle_uses_lorcanito_fisher_yates_with_seeded_draws():
    api = create_random_api_for_ctx(CtxRandom(seed="phase4-seed"))

    assert api.shuffle(("p0a", "p0b", "p0c", "p0d")) == ("p0d", "p0a", "p0c", "p0b")
    assert api.ctx_random.draws == 3
    assert api.shuffle(("p1a", "p1b", "p1c")) == ("p1a", "p1c", "p1b")
    assert api.ctx_random.draws == 5
