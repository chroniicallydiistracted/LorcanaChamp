from __future__ import annotations

from typing import Sequence

from ..candidates import AutomatedActionCandidate, AutomatedActionCandidateSummary, AutomatedActionFamily, CandidateScoreContributor
from ..strategy import StrategyContext
from .lore_race_strategy import LoreRaceStrategy


class QuestOnlyStrategy(LoreRaceStrategy):
    name = "quest-only-test"

    def summarize_one(self, context: StrategyContext, candidate: AutomatedActionCandidate) -> AutomatedActionCandidateSummary:
        base = super().summarize_one(context, candidate)
        order = base.family_order
        if candidate.family in {AutomatedActionFamily.RESOLVE_BAG, AutomatedActionFamily.RESOLVE_EFFECT}:
            order = 0
        elif candidate.family == AutomatedActionFamily.QUEST:
            order = 1
        elif candidate.family == AutomatedActionFamily.PASS_TURN:
            order = 20
        elif candidate.family == AutomatedActionFamily.CONCEDE:
            order = 1000
        else:
            order = 100
        return AutomatedActionCandidateSummary(base.candidate, base.family, base.stable_key, base.score, order, base.contributors + (CandidateScoreContributor("quest_only_order", -order),), base.information_policy, base.source_definition_id, base.target_definition_id, base.actor_deck_signature)
