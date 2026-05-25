from __future__ import annotations

from lorcana_engine_v2.core.ids import ZoneId
from lorcana_engine_v2.core.results import GameEndResult
from lorcana_engine_v2.core.runtime_config import (
    RuntimeFlowDefinition,
    RuntimeGameSegment,
    RuntimePhaseDefinition,
    RuntimeTurnDefinition,
)
from lorcana_engine_v2.core.state import MatchState
from lorcana_engine_v2.core.zones import ZoneRef


def can_auto_advance_beginning_phase(state: MatchState) -> bool:
    return (
        state.G.pendingTurnTransition is None
        and len(state.G.triggeredAbilities.bag.items) == 0
        and state.ctx.priority.pendingChoice is None
        and len(state.G.pendingEffects) == 0
    )


def _mulligan_on_enter(ctx) -> None:
    for player_id in ctx.framework.state.playerIds:
        ctx.framework.zones.shuffle(ZoneRef(zone=ZoneId("deck"), playerId=player_id))
        ctx.framework.zones.drawCards(
            from_zone=ZoneRef(zone=ZoneId("deck"), playerId=player_id),
            to_zone=ZoneRef(zone=ZoneId("hand"), playerId=player_id),
            count=7,
        )


def _main_game_on_enter(ctx) -> None:
    ctx.framework.status.incrementTurn()
    otp = ctx.framework.state.status.otp
    if otp is not None:
        ctx.framework.priority.openWindow(otp)


def _main_game_end_if(state: MatchState) -> GameEndResult | None:
    if state.ctx.status.gameEnded:
        return GameEndResult(
            winner=state.ctx.status.winner or next(iter(state.G.lore), None),
            reason=state.ctx.status.reason or "Game ended",
        )

    for player_id, lore in state.G.lore.items():
        lore_to_win = state.G.loreToWin.get(player_id, 20) if state.G.loreToWin is not None else 20
        if lore >= lore_to_win:
            return GameEndResult(winner=player_id, reason=f"Reached {lore_to_win} lore")

    return None


lorcana_runtime_flow = RuntimeFlowDefinition(
    initialGameSegment="startingAGame",
    gameSegments={
        "startingAGame": RuntimeGameSegment(
            id="startingAGame",
            name="Starting a Game",
            order=0,
            next="mainGame",
            turn=RuntimeTurnDefinition(
                initialPhase="chooseFirstPlayer",
                phases={
                    "chooseFirstPlayer": RuntimePhaseDefinition(
                        id="chooseFirstPlayer",
                        name="Choose First Player",
                        order=1,
                        validMoves=("chooseWhoGoesFirst",),
                        nextPhase="mulligan",
                        endIf=lambda state: state.ctx.status.otp is not None,
                    ),
                    "mulligan": RuntimePhaseDefinition(
                        id="mulligan",
                        name="Alter Hand",
                        order=2,
                        onEnter=_mulligan_on_enter,
                        validMoves=("alterHand",),
                        endIf=lambda state: len(state.ctx.status.pendingMulligan or ()) == 0,
                    ),
                },
            ),
        ),
        "mainGame": RuntimeGameSegment(
            id="mainGame",
            name="Main Game",
            order=1,
            onEnter=_main_game_on_enter,
            validMoves=(
                "concede",
                "passTurn",
                "moveCharacterToLocation",
                "resolveBag",
                "resolveEffect",
            ),
            endIf=_main_game_end_if,
            turn=RuntimeTurnDefinition(
                initialPhase="beginning",
                phases={
                    "beginning": RuntimePhaseDefinition(
                        id="beginning",
                        name="Beginning Phase",
                        order=1,
                        validMoves=("concede", "resolveBag", "resolveEffect"),
                        endIf=can_auto_advance_beginning_phase,
                        nextPhase="main",
                    ),
                    "main": RuntimePhaseDefinition(
                        id="main",
                        name="Main Phase",
                        order=2,
                        validMoves=(
                            "playCard",
                            "quest",
                            "questWithAll",
                            "challenge",
                            "moveCharacterToLocation",
                            "activateAbility",
                            "putCardIntoInkwell",
                            "passTurn",
                            "resolveBag",
                            "resolveEffect",
                            "concede",
                        ),
                    ),
                    "end": RuntimePhaseDefinition(
                        id="end",
                        name="End Phase",
                        order=3,
                        validMoves=("concede", "resolveBag", "resolveEffect"),
                        nextPhase="beginning",
                    ),
                },
            ),
        ),
    },
)
