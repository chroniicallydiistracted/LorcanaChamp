from __future__ import annotations

from .strategies import (
    BoardControlStrategy,
    ChallengeOnlyStrategy,
    DeckAwareBoardControlStrategy,
    DeckAwareLoreRaceStrategy,
    LoreRaceStrategy,
    QuestOnlyStrategy,
    RandomStrategy,
)

DEFAULT_STRATEGY = "deck-aware-lore-race"


def get_strategy(name: str):
    if name == "random":
        return RandomStrategy(seed=0)
    if name in {"greedy", "heuristic", "lore-race"}:
        return LoreRaceStrategy()
    if name == "board-control":
        return BoardControlStrategy()
    if name == "aggressive-board-control":
        return BoardControlStrategy(aggressive=True)
    if name == "deck-aware-lore-race":
        return DeckAwareLoreRaceStrategy()
    if name == "deck-aware-board-control":
        return DeckAwareBoardControlStrategy()
    if name == "quest-only-test":
        return QuestOnlyStrategy()
    if name == "challenge-only-test":
        return ChallengeOnlyStrategy()
    if name == "ml-ranked-lore-control":
        from .strategies.ml_ranked_strategy import MLRankedStrategy

        return MLRankedStrategy()
    raise ValueError(f"Unknown automation strategy {name}")


def list_strategies() -> list[str]:
    return [
        "random",
        "lore-race",
        "board-control",
        "aggressive-board-control",
        "deck-aware-lore-race",
        "deck-aware-board-control",
        "quest-only-test",
        "challenge-only-test",
        "ml-ranked-lore-control",
    ]
