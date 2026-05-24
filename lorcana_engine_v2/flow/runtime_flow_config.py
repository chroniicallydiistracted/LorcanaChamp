from __future__ import annotations

from lorcana_engine_v2.core.runtime_config import (
    RuntimeFlowDefinition,
    RuntimeGameSegment,
    RuntimePhaseDefinition,
    RuntimeTurnDefinition,
)


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
                    ),
                    "mulligan": RuntimePhaseDefinition(
                        id="mulligan",
                        name="Alter Hand",
                        order=2,
                        validMoves=("alterHand",),
                    ),
                },
            ),
        ),
        "mainGame": RuntimeGameSegment(
            id="mainGame",
            name="Main Game",
            order=1,
            validMoves=(
                "concede",
                "passTurn",
                "moveCharacterToLocation",
                "resolveBag",
                "resolveEffect",
            ),
            turn=RuntimeTurnDefinition(
                initialPhase="beginning",
                phases={
                    "beginning": RuntimePhaseDefinition(
                        id="beginning",
                        name="Beginning Phase",
                        order=1,
                        validMoves=("concede", "resolveBag", "resolveEffect"),
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
