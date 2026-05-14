from lorcana_bot.bots import GreedyLoreBot, HeuristicBot, LinearPolicyBot, RandomLegalBot
from lorcana_bot.cards import make_demo_deck
from lorcana_bot.constants import ACTION_CONCEDE
from lorcana_bot.engine import GameEngine, GameRunner
from lorcana_bot.env import LorcanaSelfPlayEnv
from lorcana_bot.training import FEATURE_COUNT


def test_bots_choose_legal_indices(engine, state):
    legal = engine.legal_actions(state)
    obs = engine.observe(state, state.active_player)
    for bot in [RandomLegalBot(seed=1), GreedyLoreBot(), HeuristicBot(), LinearPolicyBot()]:
        idx = bot.choose_action(obs, legal, engine)
        assert 0 <= idx < len(legal)


def test_non_random_bots_do_not_choose_concede_when_other_actions_exist(engine, state):
    legal = engine.legal_actions(state)
    assert any(action.kind == ACTION_CONCEDE for action in legal)
    assert any(action.kind != ACTION_CONCEDE for action in legal)
    obs = engine.observe(state, state.active_player)

    for bot in [GreedyLoreBot(), HeuristicBot(), LinearPolicyBot()]:
        assert legal[bot.choose_action(obs, legal, engine)].kind != ACTION_CONCEDE


def test_linear_bot_masks_concede_even_with_bad_weights(engine, state):
    legal = engine.legal_actions(state)
    obs = engine.observe(state, state.active_player)
    bot = LinearPolicyBot(weights=[0.0] * FEATURE_COUNT)
    concede_feature_index = bot.encoder.action_order.index(ACTION_CONCEDE)
    bot.weights[concede_feature_index] = 10_000

    assert legal[bot.choose_action(obs, legal, engine)].kind != ACTION_CONCEDE


def test_runner_completes_demo_game(db):
    engine = GameEngine(db)
    deck0 = make_demo_deck(["Amber Recruit", "Amber Guard", "Amber Storyteller", "Amethyst Scholar", "Amethyst Insight"], size=60)
    deck1 = make_demo_deck(["Steel Bruiser", "Emerald Scout", "Ruby Charger", "Steel Cannon", "Sapphire Helper"], size=60)
    state = engine.setup_game([deck0, deck1], seed=9)
    result = GameRunner(engine, max_actions=500).play(state, (HeuristicBot(), GreedyLoreBot()))
    assert result.winner in {0, 1, None}
    assert result.action_count <= 500


def test_env_reset_step_and_rollout(db):
    env = LorcanaSelfPlayEnv(db, seed=4)
    obs = env.reset()
    legal = env.legal_actions()
    assert legal
    result = env.step(0)
    assert result.observation.active_player in {0, 1}
    winner = env.rollout_random(max_actions=30, seed=5)
    assert winner in {0, 1, None}


def test_linear_training_smoke(db):
    from lorcana_bot.training import train_linear_policy_evolution

    result = train_linear_policy_evolution(db, generations=1, population=2, games_per_candidate=1, seed=2)
    assert len(result.weights) == FEATURE_COUNT
    assert result.evaluation.games == 1
