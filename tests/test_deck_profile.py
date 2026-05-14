from lorcana_bot.automation.deck_profile import build_deck_profile, public_profile_for_policy


def test_deck_profile_deterministic(db):
    deck = ["Amber Recruit", "Amber Guard", "Amethyst Scholar"] * 4
    assert build_deck_profile(deck, db).deck_signature == build_deck_profile(list(reversed(deck)), db).deck_signature


def test_deck_profile_roles_and_archetype(db):
    profile = build_deck_profile(["Amber Recruit", "Amber Storyteller", "Amethyst Insight"] * 4, db)
    assert "amber" in profile.color_pair
    assert profile.archetype in {"aggressive", "midrange", "control"}
    assert profile.role_counts


def test_fair_policy_hides_opponent_profile(db):
    profile = build_deck_profile(["Amber Recruit"] * 10, db)
    assert public_profile_for_policy(profile, information_policy="fair", is_actor=False) is None
    assert public_profile_for_policy(profile, information_policy="oracle", is_actor=False) is profile
