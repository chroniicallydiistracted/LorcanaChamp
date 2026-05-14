from __future__ import annotations

from typing import Sequence

from ..candidates import FAMILY_ORDER, AutomatedActionCandidate, AutomatedActionCandidateSummary, CandidateScoreContributor
from ..ml.candidate_encoder import encode_candidate_features
from ..ml.feature_extractor import extract_state_features
from ..ml.model import CandidateRanker
from ..strategy import StrategyContext
from .deck_aware_strategy import DeckAwareLoreRaceStrategy


class MLRankedStrategy:
    name = "ml-ranked-lore-control"
    information_policy = "fair"

    def __init__(self, ranker: CandidateRanker | None = None, hybrid_weight: float = 0.25):
        self.ranker = ranker
        self.hybrid_weight = hybrid_weight
        self.fallback = DeckAwareLoreRaceStrategy()

    def summarize_candidates(self, context: StrategyContext, candidates: Sequence[AutomatedActionCandidate]) -> list[AutomatedActionCandidateSummary]:
        heuristic = self.fallback.summarize_candidates(context, candidates)
        if self.ranker is None:
            return [
                AutomatedActionCandidateSummary(
                    summary.candidate,
                    summary.family,
                    summary.stable_key,
                    summary.score,
                    summary.family_order,
                    summary.contributors + (CandidateScoreContributor("model_unavailable_fallback", 0),),
                    context.information_policy,
                    summary.source_definition_id,
                    summary.target_definition_id,
                    summary.actor_deck_signature,
                )
                for summary in heuristic
            ]
        state_features = extract_state_features(context.state, context.engine, context.actor, context.information_policy, context.actor_deck_profile, context.opponent_deck_profile)
        rows = [
            state_features + encode_candidate_features(context.state, context.engine, context.actor, candidate, context.actor_deck_profile)
            for candidate in candidates
        ]
        model_scores = self.ranker.score_candidates(rows, candidates)
        by_key = {summary.stable_key: summary for summary in heuristic}
        summaries = []
        for candidate, model_score in zip(candidates, model_scores):
            fallback = by_key[candidate.stable_key]
            final_score = float(model_score) + self.hybrid_weight * fallback.score
            summaries.append(
                AutomatedActionCandidateSummary(
                    candidate,
                    candidate.family,
                    candidate.stable_key,
                    final_score,
                    fallback.family_order,
                    (
                        CandidateScoreContributor("model_score", float(model_score)),
                        CandidateScoreContributor("heuristic_fallback", self.hybrid_weight * fallback.score),
                    ),
                    context.information_policy,
                    fallback.source_definition_id,
                    fallback.target_definition_id,
                    fallback.actor_deck_signature,
                )
            )
        return summaries
