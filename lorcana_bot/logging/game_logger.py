from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any, Literal

from lorcana_bot.actions import Action
from lorcana_bot.engine import GameEngine
from lorcana_bot.state import GameEvent, GameState

GameLogMode = Literal["public", "private", "training", "oracle"]
PRIVATE_MODES = {"private", "oracle"}


class GameLogger:
    def __init__(self, path: str | Path, *, game_id: str, mode: GameLogMode = "public"):
        if mode not in {"public", "private", "training", "oracle"}:
            raise ValueError(f"Unsupported game log mode {mode!r}")
        self.path = Path(path)
        self.game_id = game_id
        self.mode = mode
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._fh = self.path.open("w", encoding="utf-8")

    def close(self) -> None:
        self._fh.close()

    def __enter__(self) -> "GameLogger":
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()

    def log_move(
        self,
        *,
        ply: int,
        before: GameState,
        after: GameState,
        engine: GameEngine,
        action: Action,
        strategy_name: str | None,
        selected_candidate: dict[str, Any] | None = None,
        fallback_status: str | None = None,
        event_start_index: int | None = None,
    ) -> dict[str, Any]:
        row = build_game_log_row(
            game_id=self.game_id,
            ply=ply,
            before=before,
            after=after,
            engine=engine,
            action=action,
            strategy_name=strategy_name,
            selected_candidate=selected_candidate,
            fallback_status=fallback_status,
            mode=self.mode,
            event_start_index=event_start_index,
        )
        self._fh.write(json.dumps(row, sort_keys=True) + "\n")
        self._fh.flush()
        return row


def build_game_log_row(
    *,
    game_id: str,
    ply: int,
    before: GameState,
    after: GameState,
    engine: GameEngine,
    action: Action,
    strategy_name: str | None,
    selected_candidate: dict[str, Any] | None = None,
    fallback_status: str | None = None,
    mode: GameLogMode = "public",
    event_start_index: int | None = None,
) -> dict[str, Any]:
    actor = action.actor
    start = len(before.event_log) if event_start_index is None else event_start_index
    return {
        "schema_version": 1,
        "game_id": game_id,
        "ply": ply,
        "turn": before.turn_number,
        "active_player": before.active_player,
        "actor": actor,
        "phase": before.phase,
        "strategy_name": strategy_name,
        "selected_candidate": selected_candidate,
        "selected_action": action_to_dict(action),
        "before_summary": state_summary(before, engine, actor=actor, mode=mode),
        "after_summary": state_summary(after, engine, actor=actor, mode=mode),
        "new_events_emitted": [event_to_dict(event) for event in after.event_log[start:]],
        "winner": after.winner,
        "loss_reason": after.loss_reason,
        "fallback_status": fallback_status,
        "log_mode": mode,
    }


def action_to_dict(action: Action) -> dict[str, Any]:
    data = asdict(action)
    data["compact"] = action.compact()
    return data


def event_to_dict(event: GameEvent) -> dict[str, Any]:
    return asdict(event)


def state_summary(state: GameState, engine: GameEngine, *, actor: int, mode: GameLogMode = "public") -> dict[str, Any]:
    private = mode in PRIVATE_MODES
    players = []
    for idx, ps in enumerate(state.players):
        player: dict[str, Any] = {
            "lore": ps.lore,
            "deck_count": len(ps.deck),
            "hand_count": len(ps.hand),
            "play": [_public_card(state, engine, cid) for cid in ps.play],
            "discard": [_public_card(state, engine, cid) for cid in ps.discard],
            "inkwell_count": len(ps.inkwell),
            "turn_flags": asdict(ps.turn_flags),
        }
        if private:
            player.update(
                {
                    "deck": [_private_card(state, engine, cid) for cid in ps.deck],
                    "hand": [_private_card(state, engine, cid) for cid in ps.hand],
                    "inkwell": [_private_card(state, engine, cid) for cid in ps.inkwell],
                    "mulliganed_card_ids": list(ps.mulliganed_card_ids),
                }
            )
        elif idx == actor:
            player["hand"] = [_private_card(state, engine, cid) for cid in ps.hand]
            player["inkwell"] = [_private_card(state, engine, cid) for cid in ps.inkwell]
        players.append(player)

    summary: dict[str, Any] = {
        "active_player": state.active_player,
        "first_player": state.first_player,
        "turn_number": state.turn_number,
        "phase": state.phase,
        "turn_player_has_inked": state.turn_player_has_inked,
        "winner": state.winner,
        "loss_reason": state.loss_reason,
        "players": players,
        "bag_size": len(state.bag),
        "event_count": len(state.event_log),
        "action_count": len(state.action_log),
    }
    if private:
        summary.update(
            {
                "seed": state.seed,
                "shuffle_counter": state.shuffle_counter,
                "cards": {str(cid): _private_card(state, engine, cid) for cid in sorted(state.cards)},
                "bag": [asdict(trigger) for trigger in state.bag],
            }
        )
    return summary


def _public_card(state: GameState, engine: GameEngine, cid: int) -> dict[str, Any]:
    cdef = engine.card_def(state, cid)
    inst = state.cards[cid]
    return {
        "instance_id": cid,
        "card_id": cdef.id,
        "name": cdef.full_name,
        "type": cdef.card_type,
        "owner": inst.owner,
        "controller": inst.controller,
        "zone": inst.zone,
        "exerted": inst.exerted,
        "drying": inst.drying,
        "damage": inst.damage,
        "location_instance_id": inst.location_instance_id,
    }


def _private_card(state: GameState, engine: GameEngine, cid: int) -> dict[str, Any]:
    card = _public_card(state, engine, cid)
    inst = state.cards[cid]
    card.update(
        {
            "revealed": inst.revealed,
            "facedown": inst.facedown,
            "just_played": inst.just_played,
            "added_to_ink_this_turn": inst.added_to_ink_this_turn,
            "has_quested_this_turn": inst.has_quested_this_turn,
            "used_abilities_this_turn": list(inst.used_abilities_this_turn),
            "last_damage_source": inst.last_damage_source,
            "last_damage_was_challenge": inst.last_damage_was_challenge,
            "was_challenged_this_turn": inst.was_challenged_this_turn,
            "temporary_keywords": list(inst.temporary_keywords),
            "temporary_modifiers": dict(inst.temporary_modifiers),
        }
    )
    return card
