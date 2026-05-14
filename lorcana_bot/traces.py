from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

from .actions import Action
from .engine import BotProtocol, GameEngine, GameResult, GameState


@dataclass(frozen=True, slots=True)
class ActionTrace:
    index: int
    kind: str
    compact: str
    source: int | None = None
    card: int | None = None
    target: int | None = None

    @classmethod
    def from_action(cls, index: int, action: Action) -> "ActionTrace":
        return cls(
            index=index,
            kind=action.kind,
            compact=action.compact(),
            source=action.source,
            card=action.card,
            target=action.target,
        )


@dataclass(frozen=True, slots=True)
class ObservationTrace:
    player: int
    active_player: int
    turn_number: int
    own_lore: int
    opponent_lore: int
    own_deck_count: int
    opponent_deck_count: int
    own_hand_count: int
    opponent_hand_count: int
    own_play_count: int
    opponent_play_count: int
    own_ink_count: int
    own_available_ink: int
    opponent_ink_count: int
    public_cards: dict[str, dict]


@dataclass(frozen=True, slots=True)
class DecisionTrace:
    ply: int
    player: int
    observation: ObservationTrace
    legal_actions: list[ActionTrace]
    selected_index: int
    selected_action: ActionTrace


@dataclass(frozen=True, slots=True)
class TraceRolloutResult:
    game: GameResult
    traces: list[DecisionTrace]


def observation_to_trace(engine: GameEngine, state: GameState, player: int) -> ObservationTrace:
    obs = engine.observe(state, player)
    public_cards: dict[str, dict] = {}
    for cid, raw in obs.cards_public.items():
        # Preserve public and acting-player-owned private card metadata. The trace
        # intentionally excludes opponent hand/deck instance IDs.
        if raw.get("zone") == "hand" and raw.get("controller") != player:
            continue
        public_cards[str(cid)] = dict(raw)
    return ObservationTrace(
        player=obs.player,
        active_player=obs.active_player,
        turn_number=obs.turn_number,
        own_lore=obs.own_lore,
        opponent_lore=obs.opponent_lore,
        own_deck_count=obs.own_deck_count,
        opponent_deck_count=obs.opponent_deck_count,
        own_hand_count=len(obs.own_hand),
        opponent_hand_count=obs.opponent_hand_count,
        own_play_count=len(obs.own_play),
        opponent_play_count=len(obs.opponent_play),
        own_ink_count=obs.own_ink_count,
        own_available_ink=obs.own_available_ink,
        opponent_ink_count=obs.opponent_ink_count,
        public_cards=public_cards,
    )


def rollout_with_traces(
    engine: GameEngine,
    state: GameState,
    bots: tuple[BotProtocol, BotProtocol],
    *,
    max_actions: int = 1000,
) -> TraceRolloutResult:
    traces: list[DecisionTrace] = []
    actions_taken = 0
    while state.winner is None and actions_taken < max_actions:
        player = state.active_player
        legal = engine.legal_actions(state, player)
        if not legal:
            state.winner = state.opponent(player)
            state.loss_reason = f"player_{player}_had_no_legal_actions"
            break
        obs = engine.observe(state, player)
        selected = bots[player].choose_action(obs, legal, engine)
        if selected < 0 or selected >= len(legal):
            state.winner = state.opponent(player)
            state.loss_reason = f"player_{player}_bot_returned_illegal_index"
            break
        legal_traces = [ActionTrace.from_action(idx, action) for idx, action in enumerate(legal)]
        traces.append(
            DecisionTrace(
                ply=actions_taken,
                player=player,
                observation=observation_to_trace(engine, state, player),
                legal_actions=legal_traces,
                selected_index=selected,
                selected_action=legal_traces[selected],
            )
        )
        state = engine.apply_action(state, legal[selected])
        actions_taken += 1

    if state.winner is None:
        if state.players[0].lore > state.players[1].lore:
            state.winner = 0
            state.loss_reason = "max_actions_lore_tiebreak"
        elif state.players[1].lore > state.players[0].lore:
            state.winner = 1
            state.loss_reason = "max_actions_lore_tiebreak"
        else:
            state.loss_reason = "max_actions_draw"

    return TraceRolloutResult(
        GameResult(
            winner=state.winner,
            turns=state.turn_number,
            final_lore=(state.players[0].lore, state.players[1].lore),
            reason=state.loss_reason,
            action_count=actions_taken,
        ),
        traces,
    )


def export_traces_jsonl(traces: Iterable[DecisionTrace], path: str | Path) -> None:
    with Path(path).open("w", encoding="utf-8") as fh:
        for trace in traces:
            fh.write(json.dumps(asdict(trace), sort_keys=True) + "\n")
