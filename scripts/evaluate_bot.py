from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lorcana_bot.automation.ml.evaluation import evaluate_strategy
from lorcana_bot.automation.strategy_registry import get_strategy, list_strategies
from lorcana_bot.cards import load_card_database, make_demo_deck


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate two automation strategies.")
    parser.add_argument("--strategy-a", choices=list_strategies(), default="deck-aware-lore-race")
    parser.add_argument("--strategy-b", choices=list_strategies(), default="board-control")
    parser.add_argument("--database", choices=["demo", "imported"], default="demo")
    parser.add_argument("--card-data-path", default="data/cards")
    parser.add_argument("--games", type=int, default=10)
    parser.add_argument("--seed-start", type=int, default=1)
    parser.add_argument("--max-actions", type=int, default=300)
    parser.add_argument("--swap-sides", action="store_true")
    args = parser.parse_args()

    db = load_card_database("demo" if args.database == "demo" else "imported", card_data_path=args.card_data_path)
    if args.database == "demo":
        deck_a = make_demo_deck(size=50)
        deck_b = make_demo_deck(["Steel Bruiser", "Emerald Scout", "Ruby Charger", "Steel Cannon", "Sapphire Helper"], size=50)
    else:
        ids = [card.id for card in db.all_cards() if card.inkable]
        deck_a = ids[:60]
        deck_b = ids[60:120] if len(ids) >= 120 else ids[:60]
    strategy_a = get_strategy(args.strategy_a)
    strategy_b = get_strategy(args.strategy_b)
    seeds = range(args.seed_start, args.seed_start + args.games)
    report = evaluate_strategy(strategy_a, strategy_b, deck_a, deck_b, seeds, games_per_side=2 if args.swap_sides else 1, db=db, max_actions=args.max_actions)
    print(json.dumps(asdict(report), sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
