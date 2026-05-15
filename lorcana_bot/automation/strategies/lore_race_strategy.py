from __future__ import annotations

from typing import Sequence

from lorcana_bot.constants import CARD_CHARACTER, CARD_LOCATION, KEYWORD_EVASIVE

from ..candidates import (
    FAMILY_ORDER,
    AutomatedActionCandidate,
    AutomatedActionCandidateSummary,
    AutomatedActionFamily,
    CandidateScoreContributor,
)
from ..deck_profile import infer_card_role_profile
from ..strategy import StrategyContext


class LoreRaceStrategy:
    name = "lore-race"
    information_policy = "fair"

    def summarize_candidates(self, context: StrategyContext, candidates: Sequence[AutomatedActionCandidate]) -> list[AutomatedActionCandidateSummary]:
        return [self.summarize_one(context, candidate) for candidate in candidates]

    def summarize_one(self, context: StrategyContext, candidate: AutomatedActionCandidate) -> AutomatedActionCandidateSummary:
        score, contributors = score_lore_race(context, candidate)
        source_id = candidate.source_card_id
        if source_id is None and candidate.card_instance_id is not None:
            source_id = context.state.cards[candidate.card_instance_id].card_id
        return AutomatedActionCandidateSummary(
            candidate=candidate,
            family=candidate.family,
            stable_key=candidate.stable_key,
            score=score,
            family_order=FAMILY_ORDER.get(candidate.family, 100),
            contributors=tuple(contributors),
            information_policy=context.information_policy,
            source_definition_id=source_id,
            target_definition_id=candidate.target_card_id,
            actor_deck_signature=getattr(context.actor_deck_profile, "deck_signature", None),
        )


def score_lore_race(context: StrategyContext, candidate: AutomatedActionCandidate) -> tuple[float, list[CandidateScoreContributor]]:
    state = context.state
    engine = context.engine
    score = 0.0
    cs: list[CandidateScoreContributor] = []

    def add(name: str, value: float, detail: str | None = None) -> None:
        nonlocal score
        score += value
        cs.append(CandidateScoreContributor(name, float(value), detail))

    if candidate.family == AutomatedActionFamily.QUEST and candidate.source_instance_id:
        cdef = engine.card_def(state, candidate.source_instance_id)
        lore = int(cdef.lore or 0)
        if state.players[candidate.actor].lore + lore >= engine.lore_to_win:
            add("lethal_quest", 10000)
        add("printed_lore", 10 * lore)
        if engine.has_keyword(state, candidate.source_instance_id, KEYWORD_EVASIVE):
            add("evasive", 2)
    elif candidate.family == AutomatedActionFamily.PLAY_CARD and candidate.card_instance_id:
        cdef = engine.card_def(state, candidate.card_instance_id)
        if cdef.card_type == CARD_CHARACTER:
            add("character_lore", 4 * int(cdef.lore or 0))
            add("strength", int(cdef.strength or 0))
            add("willpower", int(cdef.willpower or 0))
        elif cdef.card_type == CARD_LOCATION:
            add("location_lore", 6 * int(cdef.lore or 0))
            add("location_willpower", int(cdef.willpower or 0))
        else:
            add("action", 4)
        if cdef.cost == engine.available_ink(state, candidate.actor):
            add("on_curve", 5)
        add("unsupported_abilities", -2 * len(cdef.unsupported_abilities))
    elif candidate.family == AutomatedActionFamily.PUT_CARD_INTO_INKWELL and candidate.card_instance_id:
        cdef = engine.card_def(state, candidate.card_instance_id)
        profile = infer_card_role_profile(cdef)
        if len(state.players[candidate.actor].inkwell) < max(1, state.turn_number):
            add("below_turn_curve", 8)
        if cdef.cost >= 5:
            add("high_cost", 5)
        if cdef.cost > engine.available_ink(state, candidate.actor):
            add("currently_unplayable", 4)
        if "inkAvoid" in profile.roles:
            add("ink_avoid", -10)
        if cdef.cost <= 2:
            add("early_play_penalty", -8)
    elif candidate.family == AutomatedActionFamily.CHALLENGE:
        if candidate.metadata.get("defender_would_be_banished") and not candidate.metadata.get("attacker_would_be_banished"):
            add("clean_banish", 20)
        elif candidate.metadata.get("defender_would_be_banished"):
            add("trade", 10)
        add("defender_lore", 3 * float(candidate.metadata.get("defender_lore", 0)))
        if candidate.metadata.get("attacker_would_be_banished") and not candidate.metadata.get("defender_would_be_banished"):
            add("bad_attack", -8)
    elif candidate.family == AutomatedActionFamily.MOVE_CHARACTER_TO_LOCATION and candidate.target_instance_id:
        loc = engine.card_def(state, candidate.target_instance_id)
        add("location_lore", 3 * int(loc.lore or 0))
        add("move_cost", -2 * int(loc.move_cost or 0))
    elif candidate.family in {AutomatedActionFamily.RESOLVE_BAG, AutomatedActionFamily.RESOLVE_EFFECT}:
        # B7: Resolution candidates score based on polarity and projected benefit
        add("resolve_required", 100)  # High base score for resolution priority
        
        # Score based on effect polarity
        polarity = candidate.effect_polarity
        if polarity == "beneficial":
            add("beneficial_effect", 50)
        elif polarity == "harmful":
            add("harmful_effect", -30)
        elif polarity == "mixed":
            add("mixed_effect", 10)
        
        # Score based on projected benefit/harm
        projected_benefit = candidate.projected_benefit
        projected_harm = candidate.projected_harm
        add("projected_benefit", projected_benefit)
        add("projected_harm", -projected_harm)
        
        # Handle optional effects
        if candidate.resolve_optional is not None:
            if candidate.resolve_optional:  # Accepting
                if polarity == "beneficial" or projected_benefit > projected_harm:
                    add("accept_beneficial_optional", 20)
                else:
                    add("accept_harmful_optional", -40)
            else:  # Declining
                if polarity == "harmful" or projected_harm > projected_benefit:
                    add("decline_harmful_optional", 20)
                else:
                    add("decline_beneficial_optional", -30)
        
        # Bonus for mandatory resolution (no optional choice)
        if candidate.metadata.get("optional") is not True:
            add("mandatory_resolution", 25)
    elif candidate.family == AutomatedActionFamily.PASS_TURN:
        add("pass", -50)
    elif candidate.family == AutomatedActionFamily.CONCEDE:
        add("concede", -1_000_000)
    else:
        add("baseline", 0)
    return score, cs
