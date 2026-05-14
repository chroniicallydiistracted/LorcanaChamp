from __future__ import annotations

from lorcana_bot.constants import CARD_CHARACTER, CARD_ITEM, CARD_LOCATION


PHASES = ("MULLIGAN", "MAIN", "GAME_OVER")
ARCHETYPES = ("aggressive", "midrange", "control")
COLORS = ("amber", "amethyst", "emerald", "ruby", "sapphire", "steel")
ROLE_NAMES = (
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


def extract_state_features(state, engine, actor: int, information_policy: str = "fair", deck_profile=None, opponent_deck_profile=None) -> list[float]:
    opponent = state.opponent(actor)
    features: list[float] = [
        state.turn_number / 50.0,
        float(state.active_player),
        float(actor),
        state.players[actor].lore / engine.lore_to_win,
        state.players[opponent].lore / engine.lore_to_win,
        (state.players[actor].lore - state.players[opponent].lore) / engine.lore_to_win,
        len(state.players[actor].hand) / 20.0,
        len(state.players[opponent].hand) / 20.0,
        len(state.players[actor].deck) / 60.0,
        len(state.players[opponent].deck) / 60.0,
        len(state.players[actor].inkwell) / 20.0,
        len(state.players[opponent].inkwell) / 20.0,
        engine.available_ink(state, actor) / 20.0,
        engine.available_ink(state, opponent) / 20.0,
    ]
    features.extend([1.0 if state.phase == phase else 0.0 for phase in PHASES])
    for player in (actor, opponent):
        board = state.players[player].play
        chars = [cid for cid in board if engine.card_def(state, cid).card_type == CARD_CHARACTER]
        items = [cid for cid in board if engine.card_def(state, cid).card_type == CARD_ITEM]
        locations = [cid for cid in board if engine.card_def(state, cid).card_type == CARD_LOCATION]
        ready = [cid for cid in chars if not state.cards[cid].exerted]
        exerted = [cid for cid in chars if state.cards[cid].exerted]
        features.extend(
            [
                len(chars) / 20.0,
                len(items) / 20.0,
                len(locations) / 20.0,
                len(ready) / 20.0,
                len(exerted) / 20.0,
                sum(int(engine.card_def(state, cid).lore or 0) for cid in chars) / 30.0,
                sum(engine.effective_strength(state, cid) for cid in chars) / 60.0,
                sum(engine.effective_willpower(state, cid) - state.cards[cid].damage for cid in chars) / 80.0,
            ]
        )
    features.append(len(getattr(state, "bag", [])) / 20.0)
    features.append(float(len(getattr(state, "pending_effects", []))) / 20.0)
    features.extend(_deck_profile_features(deck_profile))
    if information_policy == "oracle":
        features.extend(_deck_profile_features(opponent_deck_profile))
    else:
        features.extend([0.0] * deck_profile_feature_length())
    return features


def _deck_profile_features(profile) -> list[float]:
    if profile is None:
        return [0.0] * deck_profile_feature_length()
    total = max(1, profile.character_count + profile.action_count + profile.item_count + profile.location_count)
    features: list[float] = [1.0 if profile.archetype == archetype else 0.0 for archetype in ARCHETYPES]
    features.extend([1.0 if color in profile.color_pair else 0.0 for color in COLORS])
    features.extend(
        [
            profile.curve_low / total,
            profile.curve_mid / total,
            profile.curve_high / total,
            profile.inkable_count / total,
            profile.uninkable_count / total,
        ]
    )
    features.extend([profile.role_counts.get(role, 0) / total for role in ROLE_NAMES])
    return features


def deck_profile_feature_length() -> int:
    return len(ARCHETYPES) + len(COLORS) + 5 + len(ROLE_NAMES)


def state_feature_length() -> int:
    return 14 + len(PHASES) + 16 + 2 + deck_profile_feature_length() * 2
