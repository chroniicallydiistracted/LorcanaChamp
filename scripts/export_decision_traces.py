from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lorcana_bot.automation.planner import take_automated_action
from lorcana_bot.automation.strategy_registry import get_strategy, list_strategies
from lorcana_bot.cards import load_card_database, make_demo_deck
from lorcana_bot.engine import GameEngine


def main() -> None:
    parser = argparse.ArgumentParser(description="Export automation decision traces as JSONL.")
    parser.add_argument("--games", type=int, default=10)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--max-actions", type=int, default=500)
    parser.add_argument("--strategy", choices=list_strategies(), default="deck-aware-lore-race")
    parser.add_argument("--opponent-strategy", choices=list_strategies(), default="board-control")
    parser.add_argument("--information-policy", choices=["fair", "oracle"], default="fair")
    parser.add_argument("--database", choices=["demo", "imported"], default="demo")
    parser.add_argument("--card-data-path", default="data/cards")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    db = load_card_database("demo" if args.database == "demo" else "imported", card_data_path=args.card_data_path)
    all_traces = []
    for game_idx in range(args.games):
        engine = GameEngine(db)
        if args.database == "demo":
            deck0 = make_demo_deck(size=50)
            deck1 = make_demo_deck(["Steel Bruiser", "Emerald Scout", "Ruby Charger", "Steel Cannon", "Sapphire Helper"], size=50)
        else:
            imported_ids = [card.id for card in db.all_cards() if card.inkable]
            deck0 = imported_ids[:60]
            deck1 = imported_ids[60:120] if len(imported_ids) >= 120 else imported_ids[:60]
        state = engine.setup_game([deck0, deck1], seed=args.seed + game_idx, first_player=game_idx % 2)
        strategies = [get_strategy(args.strategy), get_strategy(args.opponent_strategy)]
        for strategy in strategies:
            strategy.information_policy = args.information_policy
        actions = 0
        while state.winner is None and actions < args.max_actions:
            strategy = strategies[state.active_player]
            state, trace = take_automated_action(state, engine, strategy)
            all_traces.append(trace)
            actions += 1
            if trace.result == "blocked":
                break

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8") as fh:
        for trace in all_traces:
            fh.write(json.dumps(trace.to_dict(), sort_keys=True) + "\n")
    print(f"wrote {len(all_traces)} automation decision traces to {args.out}")


if __name__ == "__main__":
    main()
