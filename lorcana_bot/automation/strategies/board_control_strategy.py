from __future__ import annotations

from typing import Sequence

from lorcana_bot.constants import KEYWORD_EVASIVE

from ..candidates import AutomatedActionCandidate, AutomatedActionCandidateSummary, AutomatedActionFamily, CandidateScoreContributor
from ..strategy import StrategyContext
from .lore_race_strategy import LoreRaceStrategy, score_lore_race


class BoardControlStrategy(LoreRaceStrategy):
    name = "board-control"

    def __init__(self, aggressive: bool = False):
        self.aggressive = aggressive
        self.name = "aggressive-board-control" if aggressive else "board-control"

    def summarize_one(self, context: StrategyContext, candidate: AutomatedActionCandidate) -> AutomatedActionCandidateSummary:
        base = super().summarize_one(context, candidate)
        score = base.score
        family_order = base.family_order
        contributors = list(base.contributors)
        if candidate.family == AutomatedActionFamily.CHALLENGE:
            urgent = _is_urgent_challenge(context, candidate)
            score += 25 if urgent else 8
            contributors.append(CandidateScoreContributor("board_control_challenge", 25 if urgent else 8, "urgent" if urgent else None))
            if urgent:
                family_order = 3.5
            if self.aggressive and candidate.metadata.get("defender_would_be_banished"):
                score += 10
                contributors.append(CandidateScoreContributor("aggressive_trade_value", 10))
        elif candidate.family == AutomatedActionFamily.QUEST and _opponent_can_reach_20(context):
            score -= 20
            contributors.append(CandidateScoreContributor("dangerous_opponent_board", -20))
        return AutomatedActionCandidateSummary(
            candidate=base.candidate,
            family=base.family,
            stable_key=base.stable_key,
            score=score,
            family_order=family_order,
            contributors=tuple(contributors),
            information_policy=base.information_policy,
            source_definition_id=base.source_definition_id,
            target_definition_id=base.target_definition_id,
            actor_deck_signature=base.actor_deck_signature,
        )


def _is_urgent_challenge(context: StrategyContext, candidate: AutomatedActionCandidate) -> bool:
    if candidate.target_instance_id is None:
        return False
    state = context.state
    engine = context.engine
    target = candidate.target_instance_id
    cdef = engine.card_def(state, target)
    return (
        _opponent_can_reach_20(context)
        or int(cdef.lore or 0) >= 2
        or engine.has_keyword(state, target, KEYWORD_EVASIVE)
        or candidate.metadata.get("defender_would_be_banished", False)
    )


def _opponent_can_reach_20(context: StrategyContext) -> bool:
    state = context.state
    opponent = state.opponent(context.actor)
    board_lore = 0
    for cid in state.players[opponent].play:
        inst = state.cards[cid]
        if not inst.exerted and not inst.drying:
            board_lore += int(context.engine.card_def(state, cid).lore or 0)
    return state.players[opponent].lore + board_lore >= context.engine.lore_to_win
