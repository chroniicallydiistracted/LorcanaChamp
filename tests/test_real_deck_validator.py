from lorcana_bot.decks.deck_schema import ResolvedDeck, ResolvedDeckCard
from lorcana_bot.decks.deck_validator import validate_resolved_deck


def _card(name, count=4, colors=("amber",), resolved=True):
    return ResolvedDeckCard(
        raw_name=name,
        count=count,
        raw_type="character",
        resolved=resolved,
        resolution_status="resolved_exact_full_name" if resolved else "unresolved",
        resolution_error=None if resolved else "not_found",
        card_id=name.casefold().replace(" ", "_") if resolved else None,
        canonical_id=name,
        full_name=name,
        colors=colors,
        card_type="character" if resolved else None,
        source_execution_status="executable" if resolved else None,
    )


def _deck(cards, total=60, colors=("amber", "amethyst"), fmt="core_constructed"):
    return ResolvedDeck(
        schema_version=1,
        id="d",
        name="D",
        format=fmt,
        source_site=None,
        source_deck_id=None,
        player=None,
        placement=None,
        event=None,
        event_date=None,
        raw_ink_colors=colors,
        resolved_ink_colors=tuple(sorted({color for card in cards for color in card.colors})),
        archetype=None,
        purpose=(),
        deck_total_declared=total,
        deck_total_resolved=sum(card.count for card in cards if card.resolved),
        cards=tuple(cards),
        playable_decklist_ids=tuple(card.card_id for card in cards if card.card_id for _ in range(card.count)),
        validation={},
        mapping_summary={},
        playability="invalid",
    )


def test_valid_60_card_two_ink_deck_passes_with_unknown_legality_warning():
    cards = [_card(f"Card {i}", count=4, colors=("amber",) if i < 10 else ("amethyst",)) for i in range(15)]

    result = validate_resolved_deck(_deck(cards))

    assert result["valid"] is True
    assert result["unknown_legality_cards"]


def test_validation_failures():
    assert validate_resolved_deck(_deck([_card("A", count=59)], total=59))["valid"] is False
    assert validate_resolved_deck(_deck([_card("A", 20, ("amber",)), _card("B", 20, ("amethyst",)), _card("C", 20, ("ruby",))]))["valid"] is False
    assert validate_resolved_deck(_deck([_card("A", count=5), *[_card(f"C{i}") for i in range(14)]], total=61))["copy_limit_violations"]
    assert validate_resolved_deck(_deck([_card("Missing", count=4, resolved=False), *[_card(f"C{i}") for i in range(14)]], total=60))["valid"] is False
    assert validate_resolved_deck(_deck([_card(f"C{i}") for i in range(15)], total=61))["valid"] is False
