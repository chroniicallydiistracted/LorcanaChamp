from lorcana_bot.cards import FormatRules, validate_deck


def test_core_constructed_validation_accepts_valid_small_test_deck(db):
    deck = ["Amber Recruit"] * 4 + ["Amber Guard"] * 4 + ["Amethyst Scholar"] * 2
    rules = FormatRules(min_cards=10, max_copies_by_full_name=4, max_inks=2)
    assert validate_deck(deck, db, rules) == []


def test_core_constructed_validation_rejects_too_many_copies(db):
    deck = ["Amber Recruit"] * 5 + ["Amber Guard"] * 4 + ["Amethyst Scholar"]
    rules = FormatRules(min_cards=10, max_copies_by_full_name=4, max_inks=2)
    errors = validate_deck(deck, db, rules)
    assert any("copies of Amber Recruit" in error for error in errors)


def test_core_constructed_validation_rejects_more_than_two_inks(db):
    deck = ["Amber Recruit"] * 4 + ["Amethyst Scholar"] * 4 + ["Steel Bruiser"] * 2
    rules = FormatRules(min_cards=10, max_copies_by_full_name=4, max_inks=2)
    errors = validate_deck(deck, db, rules)
    assert any("maximum is 2" in error for error in errors)


def test_core_constructed_validation_rejects_banned_card(db):
    deck = ["Amber Recruit"] * 4 + ["Amber Guard"] * 4 + ["Amethyst Scholar"] * 2
    rules = FormatRules(min_cards=10, banned_full_names=frozenset({"Amber Guard"}))
    errors = validate_deck(deck, db, rules)
    assert any("Amber Guard is banned" in error for error in errors)
