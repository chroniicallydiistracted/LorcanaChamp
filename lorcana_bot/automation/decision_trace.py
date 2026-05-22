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
        raw = redact_private_trace_payload(raw, information_policy)
        ordered.append(raw)
    selected_candidate = (
        redact_private_trace_payload(candidate_summary_to_dict(selected_summary), information_policy)
        if selected_summary
        else None
    )
    action_dict = redact_private_trace_payload(asdict(selected_action), information_policy) if selected_action else None
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


PRIVATE_TRACE_KEYS = {
    "selected_card_id",
    "top_cards",
    "bottom_cards",
    "destinations",
    "candidate_ids",
    "card_candidate_ids",
    "target_candidate_ids",
    "reveal_window_ids",
    "revealed_card_ids",
}


def redact_private_trace_payload(value: Any, information_policy: str) -> Any:
    if information_policy != "fair":
        return value
    redacted = _redact_private_value(value)
    if isinstance(redacted, dict) and "stable_key" in redacted:
        redacted["stable_key"] = _redacted_stable_key(redacted)
    if isinstance(redacted, dict) and isinstance(redacted.get("candidate"), dict):
        redacted["candidate"]["stable_key"] = redacted.get("stable_key", redacted["candidate"].get("stable_key"))
    return redacted


def _redact_private_value(value: Any, *, key: str | None = None) -> Any:
    if key in PRIVATE_TRACE_KEYS:
        if isinstance(value, (list, tuple, set)):
            return ["<private>"] * len(value)
        if isinstance(value, dict):
            if key == "destinations":
                return [
                    {"zone": item.get("zone"), "cards": ["<private>"] * len(item.get("cards", ()) or ())}
                    for item in value
                    if isinstance(item, dict)
                ] if isinstance(value, list) else "<private>"
            return "<private>"
        return "<private>"
    if isinstance(value, dict):
        return {str(k): _redact_private_value(v, key=str(k)) for k, v in value.items()}
    if isinstance(value, list):
        return [_redact_private_value(item, key=key) for item in value]
    if isinstance(value, tuple):
        return [_redact_private_value(item, key=key) for item in value]
    return value


def _redacted_stable_key(value: dict[str, Any]) -> str:
    payload = dict(value)
    payload.pop("stable_key", None)
    payload.pop("rank", None)
    payload.pop("validation_status", None)
    candidate = payload.get("candidate")
    if isinstance(candidate, dict):
        candidate = dict(candidate)
        candidate.pop("stable_key", None)
        payload["candidate"] = candidate
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()[:24]
    return f"fair:{digest}"
