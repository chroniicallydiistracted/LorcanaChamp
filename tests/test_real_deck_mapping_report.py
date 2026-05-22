from lorcana_bot.card_logic import SourceStaticEffectDef
from lorcana_bot.cards import CardDef
from lorcana_bot.decks.deck_mapping_report import build_deck_mapping_summary, build_suite_mapping_report, classify_deck_playability
from lorcana_bot.decks.deck_schema import ResolvedDeck, ResolvedDeckCard


def _card_def(card_id, *, source_static_abilities=()):
    return CardDef(
        id=card_id,
        full_name=card_id.upper(),
        ink="amber",
        cost=1,
        inkable=True,
        card_type="character",
        strength=1,
        willpower=1,
        lore=1,
        source_static_abilities=source_static_abilities,
        source_execution_status="executable",
    )


def _card_defs(*, static_blocker=False):
    return {
        "a": _card_def("a", source_static_abilities=(SourceStaticEffectDef(kind="evasive"),) if static_blocker else ()),
        "b": _card_def("b"),
    }


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


def test_playability_ignores_stale_resolved_deck_blockers_when_current_runtime_is_executable():
    deck = _deck(blockers=("unsupported_trigger",), playability="source_only")
    card_defs = _card_defs()

    summary = build_deck_mapping_summary(deck, card_defs)
    suite = build_suite_mapping_report([deck], card_defs)

    assert classify_deck_playability(deck, card_defs) == "fully_executable"
    assert summary["classification_source"] == "current_python_runtime"
    assert summary["playability"] == "fully_executable"
    assert summary["stored_playability"] == "source_only"
    assert summary["top_blockers_by_copies"] == []
    assert summary["runtime_blockers_by_card"] == []
    assert suite["fully_executable_decks"] == 1
    assert suite["source_only_decks"] == 0


def test_current_runtime_blockers_override_stored_fully_executable_claims():
    deck = _deck(blockers=(), playability="fully_executable")
    card_defs = _card_defs(static_blocker=True)

    summary = build_deck_mapping_summary(deck, card_defs)

    assert summary["schema_version"] == 1
    assert classify_deck_playability(deck, card_defs) == "partially_executable"
    assert summary["playability"] == "partially_executable"
    assert summary["stored_playability"] == "fully_executable"
    assert summary["top_blockers_by_copies"][0]["blocker"] == "unsupported_static_effect:evasive"
    assert summary["runtime_blockers_by_card"][0]["runtime_blockers"] == ["unsupported_static_effect:evasive"]


def test_deck_and_suite_mapping_reports_rank_current_blockers():
    deck = _deck(playability="fully_executable", blockers=())
    card_defs = _card_defs(static_blocker=True)

    suite = build_suite_mapping_report([deck], card_defs)

    assert suite["classification_source"] == "current_python_runtime"
    assert suite["fully_executable_decks"] == 0
    assert suite["partially_executable_decks"] == 1
    assert suite["top_blockers_by_copies"]
    assert suite["top_blockers_by_deck_presence"][0]["blocker"] == "unsupported_static_effect:evasive"
    assert suite["recommended_engine_work_order"][0]["category"] == "static_effect_registry"
