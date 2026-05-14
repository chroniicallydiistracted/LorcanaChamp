from lorcana_bot.decks.deck_mapping_report import build_deck_mapping_summary, build_suite_mapping_report, classify_deck_playability
from lorcana_bot.decks.deck_schema import ResolvedDeck, ResolvedDeckCard


def _deck(playability="partially_executable", blockers=("unsupported_trigger",), valid=True):
    cards = (
        ResolvedDeckCard(
            raw_name="A",
            count=4,
            raw_type="character",
            resolved=True,
            resolution_status="resolved",
            card_id="a",
            full_name="A",
            colors=("amber",),
            card_type="character",
            source_execution_status="mapped_not_executable" if blockers else "executable",
            unsupported_blockers=blockers,
        ),
        ResolvedDeckCard(
            raw_name="B",
            count=56,
            raw_type="character",
            resolved=True,
            resolution_status="resolved",
            card_id="b",
            full_name="B",
            colors=("amethyst",),
            card_type="character",
            source_execution_status="executable",
        ),
    )
    return ResolvedDeck(
        schema_version=1,
        id="d",
        name="D",
        format="core_constructed",
        source_site=None,
        source_deck_id=None,
        player=None,
        placement=None,
        event=None,
        event_date=None,
        raw_ink_colors=("amber", "amethyst"),
        resolved_ink_colors=("amber", "amethyst"),
        archetype=None,
        purpose=(),
        deck_total_declared=60,
        deck_total_resolved=60,
        cards=cards,
        playable_decklist_ids=("a",) * 4 + ("b",) * 56,
        validation={"valid": valid, "unresolved_cards": [], "ambiguous_cards": [], "banned_cards": []},
        mapping_summary={},
        playability=playability,
    )


def test_playability_classification_is_conservative_for_critical_blockers():
    assert classify_deck_playability(_deck(blockers=("unsupported_trigger",))) == "partially_executable"
    assert classify_deck_playability(_deck(blockers=(), playability="fully_executable")) == "fully_executable"


def test_deck_and_suite_mapping_reports_rank_blockers():
    deck = _deck()
    summary = build_deck_mapping_summary(deck)
    suite = build_suite_mapping_report([deck])

    assert summary["schema_version"] == 1
    assert summary["top_blockers_by_copies"][0]["blocker"] == "unsupported_trigger"
    assert suite["top_blockers_by_copies"]
    assert suite["top_blockers_by_deck_presence"][0]["blocker"] == "unsupported_trigger"
    assert suite["recommended_engine_work_order"][0]["category"] == "real_bag_and_triggers"
