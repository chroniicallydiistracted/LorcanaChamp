import json

from lorcana_bot.decks.deck_loader import write_resolved_deck
from lorcana_bot.decks.deck_schema import ResolvedDeck, ResolvedDeckCard
from lorcana_bot.decks.gauntlet import run_real_deck_gauntlet
from lorcana_bot.importers.lorcanito_source_importer import import_lorcanito_source_cards


def _resolved_deck(deck_id, card_ids, playability="partially_executable"):
    cards = (
        ResolvedDeckCard(
            raw_name="A",
            count=60,
            raw_type="character",
            resolved=True,
            resolution_status="resolved",
            card_id=card_ids[0],
            full_name="A",
            colors=("amber",),
            card_type="character",
            source_execution_status="mapped_not_executable",
            unsupported_blockers=("unsupported_trigger",),
        ),
    )
    return ResolvedDeck(
        schema_version=1,
        id=deck_id,
        name=deck_id,
        format="core_constructed",
        source_site=None,
        source_deck_id=None,
        player=None,
        placement=None,
        event=None,
        event_date=None,
        raw_ink_colors=("amber",),
        resolved_ink_colors=("amber",),
        archetype=None,
        purpose=(),
        deck_total_declared=60,
        deck_total_resolved=60,
        cards=cards,
        playable_decklist_ids=(card_ids[0],) * 60,
        validation={"valid": True, "unresolved_cards": [], "ambiguous_cards": [], "banned_cards": []},
        mapping_summary={},
        playability=playability,
    )


def test_no_fully_executable_decks_uses_current_runtime_not_stored_playability(tmp_path):
    write_resolved_deck(_resolved_deck("d1", ["x"], playability="fully_executable"), tmp_path / "d1.resolved.json")

    report = run_real_deck_gauntlet(tmp_path, only_fully_executable=True)

    assert report["result"] == "no_fully_executable_decks"
    assert report["games_run"] == 0
    assert report["classification_source"] == "current_python_runtime"
    assert report["deck_playability"]["d1"] == "source_only"


def test_partial_gauntlet_requires_allow_partial_and_marks_not_strength_valid(tmp_path):
    db, _ = import_lorcanito_source_cards("data/lorcanito_extracted/cards.normalized.json")
    card_id = next(card.id for card in db.all_cards() if card.card_type == "character" and card.source_static_abilities)
    write_resolved_deck(_resolved_deck("d1", [card_id], playability="fully_executable"), tmp_path / "d1.resolved.json")
    write_resolved_deck(_resolved_deck("d2", [card_id], playability="fully_executable"), tmp_path / "d2.resolved.json")
    decisions = tmp_path / "decisions.jsonl"

    without_partial = run_real_deck_gauntlet(tmp_path, only_fully_executable=True)
    with_partial = run_real_deck_gauntlet(tmp_path, allow_partial=True, games_per_pair=1, max_actions=1, log_decisions_jsonl=decisions)

    assert without_partial["games_run"] == 0
    assert with_partial["games_run"] == 1
    assert with_partial["matchups"][0]["not_strength_valid"] is True
    assert with_partial["matchups"][0]["stored_deck_playability_player_0"] == "fully_executable"
    assert with_partial["matchups"][0]["deck_playability_player_0"] == "partially_executable"
    if decisions.exists() and decisions.read_text().strip():
        row = json.loads(decisions.read_text().splitlines()[0])
        assert row["deck_id_player_0"] == "d1"
        assert row["deck_id_player_1"] == "d2"
