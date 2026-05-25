from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
import secrets
import time
from typing import Any

from .ids import PlayerId
from .random import RandomAPI, create_random_api_for_ctx
from .state import LorcanaG, MatchState, create_initial_tcg_ctx
from .static_resources import MatchStaticResources
from .zones import ZoneConfig, build_zone_registry, initialize_zone_state_from_registry


@dataclass(frozen=True, slots=True)
class Player:
    id: PlayerId
    name: str | None = None


@dataclass(frozen=True, slots=True)
class RuntimePhaseDefinition:
    id: str
    name: str
    order: int
    validMoves: tuple[str, ...] = ()
    nextPhase: str | Callable[[MatchState], str | None] | None = None
    onEnter: Callable[..., object] | None = None
    onExit: Callable[..., object] | None = None
    endIf: Callable[[MatchState], bool | str | None] | None = None


@dataclass(frozen=True, slots=True)
class RuntimeTurnDefinition:
    initialPhase: str
    phases: Mapping[str, RuntimePhaseDefinition]
    validMoves: tuple[str, ...] = ()
    onBegin: Callable[..., object] | None = None
    onEnd: Callable[..., object] | None = None
    endIf: Callable[[MatchState], bool] | None = None


@dataclass(frozen=True, slots=True)
class RuntimeGameSegment:
    id: str
    name: str
    order: int
    next: str | None = None
    validMoves: tuple[str, ...] = ()
    turn: RuntimeTurnDefinition | None = None
    onEnter: Callable[..., object] | None = None
    onExit: Callable[..., object] | None = None
    endIf: Callable[[MatchState], object | None] | None = None


@dataclass(frozen=True, slots=True)
class RuntimeFlowDefinition:
    initialGameSegment: str | None
    gameSegments: Mapping[str, RuntimeGameSegment]


@dataclass(frozen=True, slots=True)
class InitialStatusConfig:
    initialGameSegment: str | None
    initialPhase: str | None


@dataclass(frozen=True, slots=True)
class SetupArgs:
    players: tuple[Player, ...]
    seed: str | None
    staticResources: MatchStaticResources


@dataclass(frozen=True, slots=True)
class BoardSetupContext:
    players: tuple[Player, ...]
    staticResources: MatchStaticResources
    random: RandomAPI


@dataclass(frozen=True, slots=True)
class MatchRuntimeConfig:
    name: str
    moves: Mapping[str, object]
    flow: RuntimeFlowDefinition
    zones: Mapping[str, ZoneConfig]
    setup: Callable[[SetupArgs], LorcanaG]
    boardSetup: Callable[[MatchState, BoardSetupContext], MatchState] | None = None
    playerView: Callable[..., object] | None = None
    projectBoard: Callable[..., object] | None = None
    deriveRuntimeCard: Callable[..., object] | None = None
    derivePacketAnimations: Callable[..., object] | None = None
    timeControl: object | None = None


@dataclass(frozen=True, slots=True)
class MatchInitContext:
    config: MatchRuntimeConfig
    players: tuple[Player, ...]
    staticResources: MatchStaticResources
    seed: str | None = None
    matchID: str | None = None
    gameID: str | None = None
    choosingFirstPlayer: PlayerId | None = None


@dataclass(frozen=True, slots=True)
class MatchInitResult:
    state: MatchState
    board: object
    staticResources: MatchStaticResources


def generate_match_id() -> str:
    return f"match-{int(time.time() * 1000)}-{secrets.token_hex(5)[:9]}"


def generate_game_id() -> str:
    return f"game-{int(time.time() * 1000)}-{secrets.token_hex(5)[:9]}"


def compute_ruleset_hash(config: MatchRuntimeConfig) -> str:
    return f"ruleset-{config.name}-{int(time.time() * 1000)}"


def extract_initial_flow_state(flow: RuntimeFlowDefinition) -> InitialStatusConfig:
    segment_id = flow.initialGameSegment
    if segment_id is None:
        segment_id = next(iter(flow.gameSegments), None)
    segment = flow.gameSegments.get(segment_id) if segment_id is not None else None
    initial_phase = segment.turn.initialPhase if segment and segment.turn else None
    return InitialStatusConfig(
        initialGameSegment=segment_id,
        initialPhase=initial_phase,
    )


def initialize_match_state(ctx: MatchInitContext) -> MatchInitResult:
    player_ids = tuple(player.id for player in ctx.players)
    status_config = extract_initial_flow_state(ctx.config.flow)
    tcg_ctx = create_initial_tcg_ctx(
        matchID=ctx.matchID or generate_match_id(),
        gameID=ctx.gameID or generate_game_id(),
        rulesetHash=compute_ruleset_hash(ctx.config),
        players=player_ids,
        seed=ctx.seed or "default-seed",
        initialGameSegment=status_config.initialGameSegment,
        initialPhase=status_config.initialPhase,
        choosingFirstPlayer=ctx.choosingFirstPlayer,
    )

    if ctx.config.zones:
        zone_registry = build_zone_registry(ctx.config.zones, player_ids)
        tcg_ctx = tcg_ctx.with_updates(zones=initialize_zone_state_from_registry(zone_registry))

    game_state = ctx.config.setup(
        SetupArgs(
            players=ctx.players,
            seed=ctx.seed,
            staticResources=ctx.staticResources,
        )
    )
    state = MatchState(G=game_state, ctx=tcg_ctx)

    if ctx.config.boardSetup is not None:
        random_api = create_random_api_for_ctx(state.ctx.random)
        state = ctx.config.boardSetup(
            state,
            BoardSetupContext(
                players=ctx.players,
                staticResources=ctx.staticResources,
                random=random_api,
            ),
        )
        state = MatchState(G=state.G, ctx=state.ctx.with_updates(random=random_api.ctx_random))

    return MatchInitResult(state=state, board={}, staticResources=ctx.staticResources)
