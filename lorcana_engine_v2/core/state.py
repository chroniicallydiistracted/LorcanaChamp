from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any, Mapping

from .ids import InstanceId, PlayerId
from .zones import (
    LORCANA_RUNTIME_ZONES,
    LorcanaCardMeta,
    ZoneRuntimeState,
    ZoneRuntimePublicState,
    ZoneRuntimePrivateState,
    ZoneRuntimeRevealState,
    build_zone_registry,
    initialize_zone_state_from_registry,
)


@dataclass(frozen=True, slots=True)
class PendingChoice:
    type: str
    playerID: PlayerId
    requestID: str


@dataclass(frozen=True, slots=True)
class CtxStatus:
    turn: int = 0
    gameEnded: bool = False
    gameSegment: str | None = None
    phase: str | None = None
    step: str | None = None
    winner: PlayerId | None = None
    reason: str | None = None
    turnOwnerId: PlayerId | None = None
    otp: PlayerId | None = None
    choosingFirstPlayer: PlayerId | None = None
    pendingMulligan: tuple[PlayerId, ...] | None = None

    def with_updates(self, **updates: Any) -> "CtxStatus":
        return replace(self, **updates)


@dataclass(frozen=True, slots=True)
class CtxPriority:
    holder: PlayerId | None = None
    windowOpen: bool = False
    passSequence: tuple[PlayerId, ...] = ()
    stackDepth: int = 0
    pendingChoice: PendingChoice | None = None

    def with_updates(self, **updates: Any) -> "CtxPriority":
        return replace(self, **updates)


@dataclass(frozen=True, slots=True)
class NoTimeContext:
    mode: str = "none"


@dataclass(frozen=True, slots=True)
class CtxRandom:
    seed: str
    state: object | None = None
    draws: int = 0


@dataclass(frozen=True, slots=True)
class TCGCtx:
    matchID: str
    gameID: str
    rulesetHash: str
    playerIds: tuple[PlayerId, ...]
    zones: ZoneRuntimeState
    random: CtxRandom
    protocolVersion: int = 1
    _stateID: int = 0
    status: CtxStatus = field(default_factory=CtxStatus)
    priority: CtxPriority = field(default_factory=CtxPriority)
    time: NoTimeContext = field(default_factory=NoTimeContext)

    def with_updates(self, **updates: Any) -> "TCGCtx":
        return replace(self, **updates)


@dataclass(frozen=True, slots=True)
class TurnMetadata:
    cardsPlayedThisTurn: tuple[InstanceId, ...] = ()
    charactersQuesting: tuple[InstanceId, ...] = ()
    inkedThisTurn: tuple[InstanceId, ...] = ()
    cardsPutIntoInkwellThisTurn: tuple[InstanceId, ...] = ()
    additionalInkwellActions: int = 0
    shiftPlayedThisTurn: tuple[InstanceId, ...] = ()
    challengesByPlayerThisTurn: Mapping[PlayerId, int] = field(default_factory=dict)
    damagedCharactersByOwnerThisTurn: Mapping[PlayerId, int] = field(default_factory=dict)
    damageRemovedByPlayerThisTurn: Mapping[PlayerId, int] = field(default_factory=dict)
    challengedCharactersThisTurn: tuple[InstanceId, ...] = ()
    banishedCharactersThisTurn: tuple[InstanceId, ...] = ()
    banishedCharactersInChallengeByOwnerThisTurn: Mapping[PlayerId, int] = field(default_factory=dict)
    discardCardsLeftThisTurn: int = 0
    cardsPutIntoDiscardThisTurnByOwner: Mapping[PlayerId, int] = field(default_factory=dict)
    pendingCostReductionsByPlayer: Mapping[PlayerId, tuple[object, ...]] = field(default_factory=dict)
    cardsDrawnThisTurnByPlayer: Mapping[PlayerId, int] = field(default_factory=dict)
    cardsUnderThisTurn: Mapping[InstanceId, tuple[InstanceId, ...]] | None = None

    def record_ink(self, card_id: InstanceId | str) -> "TurnMetadata":
        cid = InstanceId(str(card_id))
        inked = self.inkedThisTurn if cid in self.inkedThisTurn else self.inkedThisTurn + (cid,)
        put_into_inkwell = (
            self.cardsPutIntoInkwellThisTurn
            if cid in self.cardsPutIntoInkwellThisTurn
            else self.cardsPutIntoInkwellThisTurn + (cid,)
        )
        return replace(self, inkedThisTurn=inked, cardsPutIntoInkwellThisTurn=put_into_inkwell)

    def reset_for_new_turn(self) -> "TurnMetadata":
        return TurnMetadata()


@dataclass(frozen=True, slots=True)
class BagState:
    nextSeq: int = 1
    items: tuple[object, ...] = ()
    lastResolvedPlayerId: PlayerId | None = None


@dataclass(frozen=True, slots=True)
class TriggeredAbilitiesUsageLedger:
    occurrences: Mapping[str, int] = field(default_factory=dict)
    resolutions: Mapping[str, int] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class TriggeredAbilitiesState:
    pendingEvents: tuple[object, ...] = ()
    registrations: tuple[object, ...] = ()
    bag: BagState = field(default_factory=BagState)
    usageLedger: TriggeredAbilitiesUsageLedger = field(default_factory=TriggeredAbilitiesUsageLedger)


@dataclass(frozen=True, slots=True)
class ContinuousEffectState:
    nextSeq: int = 1
    instances: tuple[object, ...] = ()
    byTarget: Mapping[InstanceId, tuple[object, ...]] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class TemporaryPlayerRestrictionsState:
    restrictionsByPlayer: Mapping[PlayerId, Mapping[str, int]] = field(default_factory=dict)
    startsByPlayer: Mapping[PlayerId, Mapping[str, int]] = field(default_factory=dict)
    payloadsByPlayer: Mapping[PlayerId, Mapping[str, object]] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class PlayFromUnderPermissionsState:
    permissionsByPlayer: Mapping[PlayerId, tuple[object, ...]] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ReplacementUsageLedger:
    perTurn: Mapping[str, int] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ReplacementEffectsState:
    nextSeq: int = 1
    registrations: tuple[object, ...] = ()
    usageLedger: ReplacementUsageLedger = field(default_factory=ReplacementUsageLedger)
    byEventKind: Mapping[str, tuple[str, ...]] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class LorcanaG:
    lore: Mapping[PlayerId, int]
    turnMetadata: TurnMetadata = field(default_factory=TurnMetadata)
    triggeredAbilities: TriggeredAbilitiesState = field(default_factory=TriggeredAbilitiesState)
    pendingEffects: tuple[object, ...] = ()
    pendingTurnTransition: object | None = None
    turnsCompletedByPlayer: Mapping[PlayerId, int] = field(default_factory=dict)
    continuousEffects: ContinuousEffectState = field(default_factory=ContinuousEffectState)
    temporaryPlayerRestrictions: TemporaryPlayerRestrictionsState = field(default_factory=TemporaryPlayerRestrictionsState)
    playFromUnderPermissions: PlayFromUnderPermissionsState = field(default_factory=PlayFromUnderPermissionsState)
    replacementEffects: ReplacementEffectsState = field(default_factory=ReplacementEffectsState)
    challengeState: object | None = None
    staticEffectsVersion: int = 0
    loreToWin: Mapping[PlayerId, int] | None = None

    def with_updates(self, **updates: Any) -> "LorcanaG":
        return replace(self, **updates)


@dataclass(frozen=True, slots=True)
class MatchState:
    G: LorcanaG
    ctx: TCGCtx

    def opponent(self, player: PlayerId | str) -> PlayerId:
        player_id = PlayerId(str(player))
        for candidate in self.ctx.playerIds:
            if candidate != player_id:
                return candidate
        raise ValueError(f"Unknown player id: {player}")

    @staticmethod
    def empty(player_ids: tuple[PlayerId, PlayerId] = (PlayerId("p0"), PlayerId("p1"))) -> "MatchState":
        registry = build_zone_registry(LORCANA_RUNTIME_ZONES, player_ids)
        zones = initialize_zone_state_from_registry(registry)
        ctx = create_initial_tcg_ctx(
            matchID="match-empty",
            gameID="lorcana",
            rulesetHash="empty",
            players=player_ids,
            seed="v2-default-seed",
        ).with_updates(zones=zones)
        return MatchState(G=create_initial_lorcana_g(player_ids[0], player_ids[1]), ctx=ctx)


def create_initial_lorcana_g(player1_id: PlayerId, player2_id: PlayerId) -> LorcanaG:
    return LorcanaG(
        lore={
            player1_id: 0,
            player2_id: 0,
        },
        turnsCompletedByPlayer={
            player1_id: 0,
            player2_id: 0,
        },
    )


def create_initial_tcg_ctx(
    *,
    matchID: str,
    gameID: str,
    rulesetHash: str,
    players: tuple[PlayerId, ...] = (),
    seed: str = "default-seed",
    initialGameSegment: str | None = None,
    initialPhase: str | None = None,
    choosingFirstPlayer: PlayerId | None = None,
) -> TCGCtx:
    return TCGCtx(
        protocolVersion=1,
        matchID=matchID,
        gameID=gameID,
        rulesetHash=rulesetHash,
        _stateID=0,
        playerIds=tuple(players),
        zones=ZoneRuntimeState(
            public=ZoneRuntimePublicState(zoneSummaries={}),
            reveals=ZoneRuntimeRevealState(active=(), nextSeq=0),
            private=ZoneRuntimePrivateState(zoneCards={}, cardIndex={}, cardMeta={}),
        ),
        status=CtxStatus(
            turn=0,
            gameEnded=False,
            gameSegment=initialGameSegment,
            phase=initialPhase,
            choosingFirstPlayer=choosingFirstPlayer,
            pendingMulligan=None,
        ),
        priority=CtxPriority(
            holder=choosingFirstPlayer,
            windowOpen=choosingFirstPlayer is not None,
            passSequence=(),
            stackDepth=0,
        ),
        time=NoTimeContext(),
        random=CtxRandom(seed=seed, state=None, draws=0),
    )
