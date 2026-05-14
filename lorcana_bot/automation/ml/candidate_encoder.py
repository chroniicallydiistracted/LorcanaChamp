from __future__ import annotations

from lorcana_bot.constants import CARD_ACTION, CARD_CHARACTER, CARD_ITEM, CARD_LOCATION, KEYWORD_BODYGUARD, KEYWORD_EVASIVE, KEYWORD_RESIST, KEYWORD_WARD

from ..candidates import AutomatedActionFamily
from .feature_extractor import ROLE_NAMES

FAMILIES = tuple(f.value for f in AutomatedActionFamily)
CARD_TYPES = (CARD_CHARACTER, CARD_ACTION, CARD_ITEM, CARD_LOCATION)
COLORS = ("amber", "amethyst", "emerald", "ruby", "sapphire", "steel")
KEYWORDS = ("EVASIVE", "RUSH", "BODYGUARD", "WARD", "RESIST", "RECKLESS")


def encode_candidate_features(state, engine, actor: int, candidate, deck_profile=None) -> list[float]:
    features: list[float] = [1.0 if candidate.family == family else 0.0 for family in FAMILIES]
    features.extend(_card_features(state, engine, candidate.source_instance_id or candidate.card_instance_id, deck_profile))
    features.extend(_card_features(state, engine, candidate.target_instance_id, deck_profile))
    metadata = candidate.metadata
    features.extend(
        [
            _quest_lore(state, engine, candidate) / 10.0,
            float(metadata.get("defender_lore", 0)) / 10.0,
            float(metadata.get("attacker_strength", 0)) / 10.0,
            float(metadata.get("defender_strength", 0)) / 10.0,
            1.0 if metadata.get("attacker_would_be_banished") else 0.0,
            1.0 if metadata.get("defender_would_be_banished") else 0.0,
            (1.0 if metadata.get("defender_would_be_banished") else 0.0) - (1.0 if metadata.get("attacker_would_be_banished") else 0.0),
            1.0 if candidate.card_instance_id is not None and engine.play_cost(state, actor, candidate.card_instance_id) == engine.available_ink(state, actor) else 0.0,
            1.0 if candidate.cost_selections.get("exert") else 0.0,
            float(candidate.cost_selections.get("discard", 0)) / 5.0,
            1.0 if candidate.cost_selections.get("banish") else 0.0,
            1.0 if candidate.resolve_optional is True else 0.0,
            float(candidate.choice_index or 0) / 10.0,
            len(candidate.targets) / 10.0,
            len(candidate.singer_instance_ids) / 10.0,
            1.0 if candidate.shift_target_instance_id is not None else 0.0,
            1.0 if candidate.payment_mode == "free" else 0.0,
            _move_cost(state, engine, candidate) / 10.0,
        ]
    )
    return features


def _card_features(state, engine, instance_id: int | None, deck_profile=None) -> list[float]:
    length = card_feature_length()
    if instance_id is None or instance_id not in state.cards:
        return [0.0] * length
    cdef = engine.card_def(state, instance_id)
    inst = state.cards[instance_id]
    features: list[float] = [1.0 if cdef.card_type == card_type else 0.0 for card_type in CARD_TYPES]
    features.extend([1.0 if color in cdef.colors else 0.0 for color in COLORS])
    features.extend(
        [
            cdef.cost / 10.0,
            1.0 if cdef.inkable else 0.0,
            int(cdef.strength or 0) / 10.0,
            int(cdef.willpower or 0) / 10.0,
            (engine.effective_willpower(state, instance_id) - inst.damage) / 10.0,
            int(cdef.lore or 0) / 5.0,
            int(cdef.move_cost or 0) / 10.0,
            inst.damage / 10.0,
            1.0 if inst.exerted else 0.0,
            1.0 if inst.drying else 0.0,
        ]
    )
    features.extend([1.0 if engine.has_keyword(state, instance_id, keyword) else 0.0 for keyword in KEYWORDS])
    profile = getattr(deck_profile, "card_profiles", {}).get(cdef.id) if deck_profile else None
    features.extend([1.0 if profile and role in profile.roles else 0.0 for role in ROLE_NAMES])
    features.append(len(cdef.unsupported_abilities) / 5.0)
    return features


def _quest_lore(state, engine, candidate) -> float:
    if candidate.family == AutomatedActionFamily.QUEST and candidate.source_instance_id:
        return float(engine.card_def(state, candidate.source_instance_id).lore or 0)
    return 0.0


def _move_cost(state, engine, candidate) -> float:
    if candidate.family == AutomatedActionFamily.MOVE_CHARACTER_TO_LOCATION and candidate.target_instance_id:
        return float(engine.card_def(state, candidate.target_instance_id).move_cost or 0)
    return 0.0


def card_feature_length() -> int:
    return len(CARD_TYPES) + len(COLORS) + 10 + len(KEYWORDS) + len(ROLE_NAMES) + 1


def candidate_feature_length() -> int:
    return len(FAMILIES) + card_feature_length() * 2 + 18
