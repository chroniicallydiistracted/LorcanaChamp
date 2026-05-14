from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lorcana_bot.cards import load_demo_database
from lorcana_bot.training import save_training_result, train_linear_policy_evolution


def main() -> None:
    parser = argparse.ArgumentParser(description="Train the demo LinearPolicyBot with evolutionary search.")
    parser.add_argument("--generations", type=int, default=4)
    parser.add_argument("--population", type=int, default=8)
    parser.add_argument("--games-per-candidate", type=int, default=4)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--out", default="linear_policy_result.json")
    args = parser.parse_args()

    db = load_demo_database()
    result = train_linear_policy_evolution(
        db,
        generations=args.generations,
        population=args.population,
        games_per_candidate=args.games_per_candidate,
        seed=args.seed,
    )
    save_training_result(result, args.out)
    print(result)


if __name__ == "__main__":
    main()
