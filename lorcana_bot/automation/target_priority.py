from __future__ import annotations

from typing import Any

from lorcana_bot.constants import CARD_CHARACTER, KEYWORD_BODYGUARD, KEYWORD_EVASIVE, ZONE_PLAY


def score_target_for_effect(state, engine, actor, source, target, effect_polarity, deck_profile=None) -> float:
    if target is None or target not in state.cards:
        return 0.0
    inst = state.cards[target]
    cdef = engine.card_def(state, target)
    relation = "own" if inst.controller == actor else "opponent"
    score = 0.0
    if effect_polarity == "beneficial":
        score += 20 if relation == "own" else -20
        if cdef.card_type == CARD_CHARACTER:
            score += min(inst.damage, 4) * 3
            score += int(cdef.lore or 0) * 2
            if inst.exerted:
                score += 2
    elif effect_polarity == "harmful":
        score += 20 if relation == "opponent" else -20
        score += _threat_score(state, engine, target, deck_profile)
    elif effect_polarity == "mixed":
        score += _threat_score(state, engine, target, deck_profile)
    else:
        score += int(cdef.cost)
    return score


def score_challenge_target(state, engine, attacker: int, defender: int, deck_profile: Any | None = None) -> float:
    attacker_def = engine.card_def(state, attacker)
    defender_def = engine.card_def(state, defender)
    attacker_inst = state.cards[attacker]
    defender_inst = state.cards[defender]
    damage_to_defender = engine.damage_after_resist(defender_def, engine.effective_strength(state, attacker))
    defender_banished = defender_inst.damage + damage_to_defender >= engine.effective_willpower(state, defender)
    damage_to_attacker = 0
    attacker_banished = False
    if defender_def.card_type == CARD_CHARACTER:
        damage_to_attacker = engine.damage_after_resist(attacker_def, engine.effective_strength(state, defender))
        attacker_banished = attacker_inst.damage + damage_to_attacker >= engine.effective_willpower(state, attacker)
    score = _threat_score(state, engine, defender, deck_profile)
    if defender_banished:
        score += 25
    if not attacker_banished:
        score += 10
    else:
        score -= 8 + int(attacker_def.lore or 0) * 5
    return score


def _threat_score(state, engine, target: int, deck_profile=None) -> float:
    if state.cards[target].zone != ZONE_PLAY:
        return 0.0
    cdef = engine.card_def(state, target)
    score = float(3 * int(cdef.lore or 0) + int(cdef.strength or 0) + int(cdef.willpower or 0))
    if engine.has_keyword(state, target, KEYWORD_EVASIVE):
        score += 8
    if engine.has_keyword(state, target, KEYWORD_BODYGUARD):
        score += 6
    if deck_profile and cdef.id in getattr(deck_profile, "card_profiles", {}):
        score += deck_profile.card_profiles[cdef.id].target_priority
    return score
