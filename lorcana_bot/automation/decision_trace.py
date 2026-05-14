from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from typing import Any

from lorcana_bot.actions import Action
from lorcana_bot.engine import GameEngine
from lorcana_bot.state import GameState

from .actor_resolution import ActorResolution
from .candidates import AutomatedActionCandidateSummary, candidate_summary_to_dict


@dataclass
class AutomatedDecisionTrace:
    schema_version: int
    trace_id: str
    actor: int | None
    actor_resolution: dict[str, Any]
    strategy_name: str
    information_policy: str
    turn_number: int
    phase: str
    state_fingerprint: str
    board_snapshot: dict[str, Any]
    candidate_count: int
    ordered_candidates: list[dict[str, Any]]
    validation_rejections: list[dict[str, Any]]
    unsupported_skips: list[dict[str, Any]]
    execution_attempts: list[dict[str, Any]]
    selected_candidate: dict[str, Any] | None
    selected_action: dict[str, Any] | None
    fallback_taken: str | None
    result: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True)


def state_fingerprint(state: GameState, actor: int | None = None, information_policy: str = "fair") -> str:
    payload = {
        "active_player": state.active_player,
        "turn_number": state.turn_number,
        "phase": state.phase,
        "winner": state.winner,
        "players": [
            {
                "lore": ps.lore,
                "deck_count": len(ps.deck),
                "hand": list(ps.hand) if information_policy == "oracle" or idx == actor else len(ps.hand),
                "play": list(ps.play),
                "discard": list(ps.discard),
                "inkwell": list(ps.inkwell) if information_policy == "oracle" or idx == actor else len(ps.inkwell),
            }
            for idx, ps in enumerate(state.players)
        ],
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()[:24]


def board_snapshot(state: GameState, engine: GameEngine, actor: int | None, information_policy: str) -> dict[str, Any]:
    players: list[dict[str, Any]] = []
    for idx, ps in enumerate(state.players):
        player: dict[str, Any] = {
            "lore": ps.lore,
            "deck_count": len(ps.deck),
            "hand_count": len(ps.hand),
            "discard": [_card_public(state, engine, cid) for cid in ps.discard],
            "play": [_card_public(state, engine, cid) for cid in ps.play],
            "inkwell_count": len(ps.inkwell),
        }
        if information_policy == "oracle" or idx == actor:
            player["hand"] = [_card_private(state, engine, cid) for cid in ps.hand]
            player["inkwell"] = [_card_private(state, engine, cid) for cid in ps.inkwell]
        players.append(player)
    return {"players": players, "bag_size": len(getattr(state, "bag", []))}


def build_trace(
    *,
    state: GameState,
    engine: GameEngine,
    actor_resolution: ActorResolution,
    strategy_name: str,
    information_policy: str,
    summaries: list[AutomatedActionCandidateSummary],
    validation_rejections: list[dict[str, Any]],
    unsupported_skips: list[dict[str, Any]],
    execution_attempts: list[dict[str, Any]],
    selected_summary: AutomatedActionCandidateSummary | None,
    selected_action: Action | None,
    fallback_taken: str | None,
    result: str,
) -> AutomatedDecisionTrace:
    actor = actor_resolution.actor
    ordered = []
    for rank, summary in enumerate(summaries):
        raw = candidate_summary_to_dict(summary)
        raw["rank"] = rank
        raw["validation_status"] = "valid"
        ordered.append(raw)
    selected_candidate = candidate_summary_to_dict(selected_summary) if selected_summary else None
    action_dict = asdict(selected_action) if selected_action else None
    fingerprint = state_fingerprint(state, actor, information_policy)
    trace_id = hashlib.sha256(f"{fingerprint}:{strategy_name}:{len(summaries)}:{state.turn_number}".encode("utf-8")).hexdigest()[:24]
    return AutomatedDecisionTrace(
        schema_version=1,
        trace_id=trace_id,
        actor=actor,
        actor_resolution=asdict(actor_resolution),
        strategy_name=strategy_name,
        information_policy=information_policy,
        turn_number=state.turn_number,
        phase=state.phase,
        state_fingerprint=fingerprint,
        board_snapshot=board_snapshot(state, engine, actor, information_policy),
        candidate_count=len(summaries),
        ordered_candidates=ordered,
        validation_rejections=validation_rejections,
        unsupported_skips=unsupported_skips,
        execution_attempts=execution_attempts,
        selected_candidate=selected_candidate,
        selected_action=action_dict,
        fallback_taken=fallback_taken,
        result=result,
    )


def _card_public(state: GameState, engine: GameEngine, cid: int) -> dict[str, Any]:
    cdef = engine.card_def(state, cid)
    inst = state.cards[cid]
    return {
        "instance_id": cid,
        "card_id": cdef.id,
        "name": cdef.full_name,
        "type": cdef.card_type,
        "controller": inst.controller,
        "exerted": inst.exerted,
        "damage": inst.damage,
    }


def _card_private(state: GameState, engine: GameEngine, cid: int) -> dict[str, Any]:
    return _card_public(state, engine, cid)
