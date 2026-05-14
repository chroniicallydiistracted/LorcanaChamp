from __future__ import annotations

import random
from typing import Sequence

from ..candidates import FAMILY_ORDER, AutomatedActionCandidate, AutomatedActionCandidateSummary, CandidateScoreContributor
from ..strategy import StrategyContext


class RandomStrategy:
    name = "random"
    information_policy = "fair"

    def __init__(self, seed: int | None = None, rng: random.Random | None = None):
        self.rng = rng or random.Random(seed)

    def summarize_candidates(self, context: StrategyContext, candidates: Sequence[AutomatedActionCandidate]) -> list[AutomatedActionCandidateSummary]:
        scores = {candidate.stable_key: self.rng.random() for candidate in candidates}
        return [
            AutomatedActionCandidateSummary(
                candidate=candidate,
                family=candidate.family,
                stable_key=candidate.stable_key,
                score=scores[candidate.stable_key],
                family_order=FAMILY_ORDER.get(candidate.family, 100),
                contributors=(CandidateScoreContributor("random", scores[candidate.stable_key]),),
                information_policy=context.information_policy,
                source_definition_id=candidate.source_card_id,
                target_definition_id=candidate.target_card_id,
                actor_deck_signature=getattr(context.actor_deck_profile, "deck_signature", None),
            )
            for candidate in candidates
        ]
