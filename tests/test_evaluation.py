from lorcana_bot.automation.ml.evaluation import evaluate_strategy
from lorcana_bot.automation.strategy_registry import get_strategy
from lorcana_bot.cards import make_demo_deck


def test_evaluation_smoke(db):
    report = evaluate_strategy(get_strategy("deck-aware-lore-race"), get_strategy("board-control"), make_demo_deck(size=50), make_demo_deck(size=50), [1], db=db, max_actions=20)
    assert report.average_actions > 0
    assert report.wins + report.losses + report.draws_timeouts == 1
