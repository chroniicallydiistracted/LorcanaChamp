from __future__ import annotations

from ..candidates import AutomatedActionCandidate, AutomatedActionCandidateSummary, CandidateScoreContributor
from ..strategy import StrategyContext
from .board_control_strategy import BoardControlStrategy
from .lore_race_strategy import LoreRaceStrategy


class DeckAwareLoreRaceStrategy(LoreRaceStrategy):
    name = "deck-aware-lore-race"

    def summarize_one(self, context: StrategyContext, candidate: AutomatedActionCandidate) -> AutomatedActionCandidateSummary:
        base = super().summarize_one(context, candidate)
        score = base.score
        contributors = list(base.contributors)
        profile = context.actor_deck_profile
        source_id = base.source_definition_id
        if profile and source_id in profile.card_profiles:
            card_profile = profile.card_profiles[source_id]
            if candidate.family == "putCardIntoInkwell":
                score += card_profile.ink_preference
                contributors.append(CandidateScoreContributor("deck_ink_preference", card_profile.ink_preference))
            elif candidate.family == "playCard":
                value = card_profile.early_play_score if context.turn_number <= 4 else card_profile.late_play_score
                score += value * 0.5
                contributors.append(CandidateScoreContributor("deck_play_profile", value * 0.5))
        return AutomatedActionCandidateSummary(base.candidate, base.family, base.stable_key, score, base.family_order, tuple(contributors), base.information_policy, base.source_definition_id, base.target_definition_id, base.actor_deck_signature)


class DeckAwareBoardControlStrategy(BoardControlStrategy):
    name = "deck-aware-board-control"

    def summarize_one(self, context: StrategyContext, candidate: AutomatedActionCandidate) -> AutomatedActionCandidateSummary:
        base = super().summarize_one(context, candidate)
        return base
