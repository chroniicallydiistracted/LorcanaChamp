import json

from lorcana_bot.decks.deck_loader import write_resolved_deck
from lorcana_bot.decks.deck_schema import ResolvedDeck, ResolvedDeckCard
from lorcana_bot.decks.gauntlet import run_real_deck_gauntlet
from lorcana_bot.decks.runtime_executability import classify_card_runtime_support
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
    card_id = next(
        card.id
        for card in db.all_cards()
        if card.card_type == "character" and classify_card_runtime_support(card).status == "projected_but_requires_pending_input"
    )
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


def test_gauntlet_gate_allows_current_executable_decks_despite_stale_blockers(tmp_path):
    db, _ = import_lorcanito_source_cards("data/lorcanito_extracted/cards.normalized.json")
    card_id = next(card.id for card in db.all_cards() if card.card_type == "character" and classify_card_runtime_support(card).status == "executable")
    write_resolved_deck(_resolved_deck("d1", [card_id], playability="source_only"), tmp_path / "d1.resolved.json")
    write_resolved_deck(_resolved_deck("d2", [card_id], playability="source_only"), tmp_path / "d2.resolved.json")

    report = run_real_deck_gauntlet(tmp_path, only_fully_executable=True, games_per_pair=1, max_actions=1)

    assert report["games_run"] == 1
    assert report["deck_playability"] == {"d1": "fully_executable", "d2": "fully_executable"}
    assert report["matchups"][0]["stored_deck_playability_player_0"] == "source_only"
    assert report["matchups"][0]["deck_playability_player_0"] == "fully_executable"


def test_gauntlet_logs_all_games_with_per_game_metadata(tmp_path):
    db, _ = import_lorcanito_source_cards("data/lorcanito_extracted/cards.normalized.json")
    card_id = next(
        card.id
        for card in db.all_cards()
        if card.card_type == "character" and classify_card_runtime_support(card).status == "executable"
    )
    write_resolved_deck(_resolved_deck("d1", [card_id], playability="source_only"), tmp_path / "d1.resolved.json")
    write_resolved_deck(_resolved_deck("d2", [card_id], playability="source_only"), tmp_path / "d2.resolved.json")
    write_resolved_deck(_resolved_deck("d3", [card_id], playability="source_only"), tmp_path / "d3.resolved.json")

    game_log = tmp_path / "game_log.jsonl"
    decisions = tmp_path / "decisions.jsonl"

    report = run_real_deck_gauntlet(
        tmp_path,
        only_fully_executable=True,
        games_per_pair=2,
        max_actions=5,
        log_game_jsonl=game_log,
        log_decisions_jsonl=decisions,
    )

    assert report["games_run"] == 6
    assert game_log.exists()
    assert decisions.exists()

    game_rows = [json.loads(line) for line in game_log.read_text().splitlines() if line.strip()]
    decision_rows = [json.loads(line) for line in decisions.read_text().splitlines() if line.strip()]
    total_action_count = sum(row.get("action_count", 0) for row in report["matchups"])

    assert len(game_rows) == total_action_count
    assert len(decision_rows) >= total_action_count

    game_ids_in_report = {row["game_id"] for row in report["matchups"]}
    game_ids_in_game_log = {row["game_id"] for row in game_rows}
    game_ids_in_decisions = {row["game_id"] for row in decision_rows}

    assert game_ids_in_report == {
        "gauntlet-0-0-seed-0",
        "gauntlet-0-1-seed-1",
        "gauntlet-1-0-seed-1000",
        "gauntlet-1-1-seed-1001",
        "gauntlet-2-0-seed-2000",
        "gauntlet-2-1-seed-2001",
    }
    assert game_ids_in_game_log == game_ids_in_report
    assert game_ids_in_decisions == game_ids_in_report

    for row in game_rows + decision_rows:
        assert row["deck_id_player_0"] in {"d1", "d2", "d3"}
        assert row["deck_id_player_1"] in {"d1", "d2", "d3"}
        assert row["deck_playability_player_0"] == "fully_executable"
        assert row["deck_playability_player_1"] == "fully_executable"
        assert row["stored_deck_playability_player_0"] == "source_only"
        assert row["stored_deck_playability_player_1"] == "source_only"
        assert row["strategy_player_0"] == "deck-aware-lore-race"
        assert row["strategy_player_1"] == "board-control"
        assert isinstance(row["seed"], int)
        assert isinstance(row["pair_index"], int)
        assert isinstance(row["game_index"], int)

    for row in report["matchups"]:
        assert row["strategy_player_0"] == "deck-aware-lore-race"
        assert row["strategy_player_1"] == "board-control"


def test_gauntlet_log_paths_are_reset_between_runs(tmp_path):
    db, _ = import_lorcanito_source_cards("data/lorcanito_extracted/cards.normalized.json")
    card_id = next(
        card.id
        for card in db.all_cards()
        if card.card_type == "character" and classify_card_runtime_support(card).status == "executable"
    )
    write_resolved_deck(_resolved_deck("d1", [card_id], playability="source_only"), tmp_path / "d1.resolved.json")
    write_resolved_deck(_resolved_deck("d2", [card_id], playability="source_only"), tmp_path / "d2.resolved.json")

    game_log = tmp_path / "game_log.jsonl"
    decisions = tmp_path / "decisions.jsonl"

    first = run_real_deck_gauntlet(
        tmp_path,
        only_fully_executable=True,
        games_per_pair=2,
        max_actions=5,
        log_game_jsonl=game_log,
        log_decisions_jsonl=decisions,
    )
    first_game_rows = [json.loads(line) for line in game_log.read_text().splitlines() if line.strip()]
    first_decision_rows = [json.loads(line) for line in decisions.read_text().splitlines() if line.strip()]

    second = run_real_deck_gauntlet(
        tmp_path,
        only_fully_executable=True,
        games_per_pair=1,
        max_actions=5,
        log_game_jsonl=game_log,
        log_decisions_jsonl=decisions,
    )
    second_game_rows = [json.loads(line) for line in game_log.read_text().splitlines() if line.strip()]
    second_decision_rows = [json.loads(line) for line in decisions.read_text().splitlines() if line.strip()]

    assert first["games_run"] == 2
    assert second["games_run"] == 1
    assert len(second_game_rows) < len(first_game_rows)
    assert len(second_decision_rows) < len(first_decision_rows)

    second_game_ids = {row["game_id"] for row in second_game_rows}
    second_decision_ids = {row["game_id"] for row in second_decision_rows}
    assert second_game_ids == {"gauntlet-0-0-seed-0"}
    assert second_decision_ids == {"gauntlet-0-0-seed-0"}
