from __future__ import annotations

import argparse

from lorcana_bot.decks.gauntlet import run_real_deck_gauntlet


def main() -> None:
    parser = argparse.ArgumentParser(description="Run real resolved deck gauntlet safely.")
    parser.add_argument("--resolved-deck-dir", default="data/decks/resolved/real_core")
    parser.add_argument("--source-json", default="data/lorcanito_extracted/cards.normalized.json")
    parser.add_argument("--strategy-a", default="deck-aware-lore-race")
    parser.add_argument("--strategy-b", default="board-control")
    parser.add_argument("--only-fully-executable", action="store_true")
    parser.add_argument("--allow-partial", action="store_true")
    parser.add_argument("--games-per-pair", type=int, default=2)
    parser.add_argument("--max-actions", type=int, default=300)
    parser.add_argument("--out", default="data/decks/reports/real_deck_suite_gauntlet.json")
    parser.add_argument("--log-game-jsonl", default=None)
    parser.add_argument("--log-decisions-jsonl", default=None)
    args = parser.parse_args()
    report = run_real_deck_gauntlet(
        args.resolved_deck_dir,
        source_json=args.source_json,
        strategy_a=args.strategy_a,
        strategy_b=args.strategy_b,
        only_fully_executable=args.only_fully_executable or not args.allow_partial,
        allow_partial=args.allow_partial,
        games_per_pair=args.games_per_pair,
        max_actions=args.max_actions,
        out=args.out,
        log_game_jsonl=args.log_game_jsonl,
        log_decisions_jsonl=args.log_decisions_jsonl,
    )
    print(f"result: {report['result']}")
    print(f"games run: {report['games_run']}")


if __name__ == "__main__":
    main()
