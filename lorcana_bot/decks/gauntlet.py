from __future__ import annotations

import itertools
import json
from pathlib import Path
from typing import Any

from lorcana_bot.bots import AutomationStrategyBot
from lorcana_bot.cli import _play_with_logs
from lorcana_bot.engine import GameEngine
from lorcana_bot.importers.lorcanito_source_importer import import_lorcanito_source_cards

from .deck_loader import load_resolved_deck_dir
from .deck_mapping_report import CLASSIFICATION_SOURCE, classify_deck_playability

SCHEMA_VERSION = 1


def run_real_deck_gauntlet(
    resolved_deck_dir: str | Path,
    *,
    source_json: str | Path = "data/lorcanito_extracted/cards.normalized.json",
    strategy_a: str = "deck-aware-lore-race",
    strategy_b: str = "board-control",
    only_fully_executable: bool = True,
    allow_partial: bool = False,
    games_per_pair: int = 2,
    max_actions: int = 300,
    out: str | Path | None = None,
    log_game_jsonl: str | Path | None = None,
    log_decisions_jsonl: str | Path | None = None,
) -> dict[str, Any]:
    decks = load_resolved_deck_dir(resolved_deck_dir)
    db, _import_report = import_lorcanito_source_cards(source_json)
    card_defs = {card.id: card for card in db.all_cards()}
    current_playability = {deck.id: classify_deck_playability(deck, card_defs) for deck in decks}
    if allow_partial:
        allowed = [
            deck
            for deck in decks
            if deck.validation.get("valid")
            and current_playability[deck.id] in {"fully_executable", "mostly_executable", "partially_executable"}
        ]
    elif only_fully_executable:
        allowed = [deck for deck in decks if current_playability[deck.id] == "fully_executable"]
    else:
        allowed = [deck for deck in decks if current_playability[deck.id] == "fully_executable"]
    if len(allowed) < 2:
        report = {
            "schema_version": SCHEMA_VERSION,
            "classification_source": CLASSIFICATION_SOURCE,
            "result": "no_fully_executable_decks" if not allow_partial else "not_enough_allowed_decks",
            "games_run": 0,
            "not_strength_valid": False,
            "deck_playability": current_playability,
            "matchups": [],
        }
        return _write_optional(report, out)

    engine = GameEngine(db)
    matchups = []
    games_run = 0
    game_log_path = Path(log_game_jsonl) if log_game_jsonl else None
    decision_log_path = Path(log_decisions_jsonl) if log_decisions_jsonl else None
    for pair_index, (deck0, deck1) in enumerate(itertools.combinations(sorted(allowed, key=lambda deck: deck.id), 2)):
        for game_index in range(games_per_pair):
            seed = pair_index * 1000 + game_index
            try:
                _validate_ids(db, deck0.playable_decklist_ids, deck0.id)
                _validate_ids(db, deck1.playable_decklist_ids, deck1.id)
                state = engine.setup_game([list(deck0.playable_decklist_ids), list(deck1.playable_decklist_ids)], seed=seed)
                result = _play_with_logs(
                    engine,
                    state,
                    (AutomationStrategyBot(strategy_a), AutomationStrategyBot(strategy_b)),
                    max_actions=max_actions,
                    game_log_path=game_log_path,
                    decision_log_path=decision_log_path,
                    log_mode="public",
                    strategy_names=(strategy_a, strategy_b),
                    automation_strategy_names=(strategy_a, strategy_b),
                    seed=seed,
                )
                row = {
                    "deck_id_player_0": deck0.id,
                    "deck_id_player_1": deck1.id,
                    "deck_playability_player_0": current_playability[deck0.id],
                    "deck_playability_player_1": current_playability[deck1.id],
                    "stored_deck_playability_player_0": deck0.playability,
                    "stored_deck_playability_player_1": deck1.playability,
                    "winner": result.winner,
                    "turns": result.turns,
                    "final_lore": list(result.final_lore),
                    "reason": result.reason,
                    "action_count": result.action_count,
                    "not_strength_valid": current_playability[deck0.id] != "fully_executable" or current_playability[deck1.id] != "fully_executable",
                    "reason_not_strength_valid": "deck_contains_unsupported_mechanics"
                    if current_playability[deck0.id] != "fully_executable" or current_playability[deck1.id] != "fully_executable"
                    else None,
                }
            except Exception as exc:
                row = {
                    "deck_id_player_0": deck0.id,
                    "deck_id_player_1": deck1.id,
                    "deck_playability_player_0": current_playability[deck0.id],
                    "deck_playability_player_1": current_playability[deck1.id],
                    "stored_deck_playability_player_0": deck0.playability,
                    "stored_deck_playability_player_1": deck1.playability,
                    "error": str(exc),
                    "not_strength_valid": True,
                    "reason_not_strength_valid": "gauntlet_matchup_failed",
                }
            matchups.append(row)
            games_run += 1
    metadata = {
        "deck_id_player_0": matchups[-1]["deck_id_player_0"] if matchups else None,
        "deck_id_player_1": matchups[-1]["deck_id_player_1"] if matchups else None,
        "deck_playability_player_0": matchups[-1]["deck_playability_player_0"] if matchups else None,
        "deck_playability_player_1": matchups[-1]["deck_playability_player_1"] if matchups else None,
    }
    if game_log_path:
        _augment_jsonl(game_log_path, metadata)
    if decision_log_path:
        _augment_jsonl(decision_log_path, metadata)
    report = {
        "schema_version": SCHEMA_VERSION,
        "classification_source": CLASSIFICATION_SOURCE,
        "result": "completed",
        "games_run": games_run,
        "not_strength_valid": any(row.get("not_strength_valid") for row in matchups),
        "deck_playability": current_playability,
        "matchups": matchups,
    }
    return _write_optional(report, out)


def _validate_ids(db, decklist: tuple[str, ...], deck_id: str) -> None:
    for card_id in decklist:
        try:
            db.get(card_id)
        except KeyError as exc:
            raise ValueError(f"{deck_id} references missing card id {card_id}") from exc


def _augment_jsonl(path: Path, metadata: dict[str, Any]) -> None:
    if not path.exists():
        return
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        row.update(metadata)
        rows.append(row)
    path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows), encoding="utf-8")


def _write_optional(report: dict[str, Any], out: str | Path | None) -> dict[str, Any]:
    if out is not None:
        path = Path(out)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    return report
