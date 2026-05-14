from __future__ import annotations

import hashlib
import json
from collections import Counter
from dataclasses import dataclass

from lorcana_bot.cards import CardDatabase, CardDef
from lorcana_bot.constants import CARD_ACTION, CARD_CHARACTER, CARD_ITEM, CARD_LOCATION


ROLES = (
    "mulliganKeep",
    "inkAvoid",
    "earlyPlay",
    "latePlay",
    "mustAnswerThreat",
    "removal",
    "sweeper",
    "ramp",
    "drawEngine",
    "tempoThreat",
    "evasiveThreat",
    "synergyAnchor",
    "bodyguard",
    "locationPayoff",
    "songPayoff",
    "singer",
    "shiftTarget",
    "shiftPayoff",
)


@dataclass
class CardRoleProfile:
    card_id: str
    roles: set[str]
    ink_preference: float
    mulligan_keep_score: float
    early_play_score: float
    late_play_score: float
    target_priority: float


@dataclass
class DeckProfile:
    deck_signature: str
    color_pair: tuple[str, ...]
    archetype: str
    curve_low: int
    curve_mid: int
    curve_high: int
    character_count: int
    action_count: int
    item_count: int
    location_count: int
    inkable_count: int
    uninkable_count: int
    role_counts: dict[str, int]
    card_profiles: dict[str, CardRoleProfile]


def build_deck_profile(decklist: list[str], db: CardDatabase) -> DeckProfile:
    cards = [db.get(card) for card in decklist]
    counts = Counter(card.id for card in cards)
    signature_payload = sorted(counts.items())
    deck_signature = hashlib.sha256(json.dumps(signature_payload, sort_keys=True).encode("utf-8")).hexdigest()[:24]
    colors = tuple(sorted({color for card in cards for color in card.colors if color}))
    profiles = {card.id: infer_card_role_profile(card) for card in cards}
    role_counts = Counter(role for card in cards for role in profiles[card.id].roles)
    curve_low = sum(1 for card in cards if card.cost <= 2)
    curve_mid = sum(1 for card in cards if 3 <= card.cost <= 5)
    curve_high = sum(1 for card in cards if card.cost >= 6)
    character_count = sum(1 for card in cards if card.card_type == CARD_CHARACTER)
    action_count = sum(1 for card in cards if card.card_type == CARD_ACTION)
    removal_count = role_counts.get("removal", 0)
    draw_ramp = role_counts.get("drawEngine", 0) + role_counts.get("ramp", 0)
    lore_density = sum(int(card.lore or 0) for card in cards) / max(1, character_count)
    if curve_low >= curve_mid + curve_high and lore_density >= 1.4:
        archetype = "aggressive"
    elif action_count + removal_count + draw_ramp > character_count * 0.55 or curve_high > curve_low:
        archetype = "control"
    else:
        archetype = "midrange"
    return DeckProfile(
        deck_signature=deck_signature,
        color_pair=colors,
        archetype=archetype,
        curve_low=curve_low,
        curve_mid=curve_mid,
        curve_high=curve_high,
        character_count=character_count,
        action_count=action_count,
        item_count=sum(1 for card in cards if card.card_type == CARD_ITEM),
        location_count=sum(1 for card in cards if card.card_type == CARD_LOCATION),
        inkable_count=sum(1 for card in cards if card.inkable),
        uninkable_count=sum(1 for card in cards if not card.inkable),
        role_counts=dict(sorted(role_counts.items())),
        card_profiles=profiles,
    )


def infer_card_role_profile(card: CardDef) -> CardRoleProfile:
    roles: set[str] = set()
    text = " ".join([card.rules_text or "", *card.text_effects, *(str(a) for a in card.unsupported_abilities)]).casefold()
    effect_kinds = {effect.kind for effect in card.effects}
    if card.cost <= 2 and card.card_type == CARD_CHARACTER:
        roles.update({"earlyPlay", "mulliganKeep"})
    if card.cost >= 5:
        roles.add("latePlay")
    if card.card_type == CARD_CHARACTER and int(card.lore or 0) >= 2 and card.cost <= 3:
        roles.add("tempoThreat")
    if "EVASIVE" in card.keywords:
        roles.update({"evasiveThreat", "mustAnswerThreat"})
    if "BODYGUARD" in card.keywords:
        roles.add("bodyguard")
    if effect_kinds.intersection({"draw"}) or "draw" in text:
        roles.add("drawEngine")
    if effect_kinds.intersection({"deal_damage", "banish", "return_to_hand"}) or any(word in text for word in ("damage", "banish", "return")):
        roles.add("removal")
    if effect_kinds.intersection({"cost_reduction"}) or any(word in text for word in ("inkwell", "ink")) and "additional" in text:
        roles.add("ramp")
    if "shift" in text:
        roles.add("shiftPayoff")
    if "singer" in text or "sing" in text:
        roles.add("singer")
    if card.card_type == CARD_LOCATION:
        roles.add("locationPayoff")
    if not card.inkable or "mustAnswerThreat" in roles or "drawEngine" in roles:
        roles.add("inkAvoid")
    early = 8.0 if "earlyPlay" in roles else max(0.0, 5.0 - card.cost)
    late = float(card.cost + int(card.lore or 0) + int(card.strength or 0))
    target = float(2 * int(card.lore or 0) + int(card.strength or 0) + int(card.willpower or 0))
    if "mustAnswerThreat" in roles:
        target += 8
    return CardRoleProfile(
        card_id=card.id,
        roles=roles,
        ink_preference=-5.0 if "inkAvoid" in roles else (3.0 if card.cost >= 5 else 0.0),
        mulligan_keep_score=early + (2.0 if card.inkable else -1.0),
        early_play_score=early,
        late_play_score=late,
        target_priority=target,
    )


def public_profile_for_policy(profile: DeckProfile | None, *, information_policy: str, is_actor: bool, known_public: bool = False) -> DeckProfile | None:
    if profile is None:
        return None
    if information_policy == "oracle" or is_actor or known_public:
        return profile
    return None
