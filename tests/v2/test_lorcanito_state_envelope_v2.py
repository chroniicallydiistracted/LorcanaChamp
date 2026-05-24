from lorcana_engine_v2.core.ids import PlayerId
from lorcana_engine_v2.core.state import (
    CtxPriority,
    CtxStatus,
    MatchState,
    create_initial_lorcana_g,
    create_initial_tcg_ctx,
)
from lorcana_engine_v2.core.zones import (
    LORCANA_RUNTIME_ZONES,
    CardMeta,
    build_zone_registry,
    initialize_zone_state_from_registry,
)


def test_phase2_create_initial_tcg_ctx_matches_lorcanito_defaults():
    ctx = create_initial_tcg_ctx(
        matchID="match-123",
        gameID="lorcana",
        rulesetHash="ruleset-v1",
        players=(PlayerId("p0"), PlayerId("p1")),
        seed="seed-1",
        initialGameSegment="startingAGame",
        initialPhase="chooseFirstPlayer",
    )

    assert ctx.protocolVersion == 1
    assert ctx.matchID == "match-123"
    assert ctx.gameID == "lorcana"
    assert ctx.rulesetHash == "ruleset-v1"
    assert ctx._stateID == 0
    assert ctx.playerIds == (PlayerId("p0"), PlayerId("p1"))
    assert ctx.status == CtxStatus(
        turn=0,
        gameEnded=False,
        gameSegment="startingAGame",
        phase="chooseFirstPlayer",
        choosingFirstPlayer=None,
        pendingMulligan=None,
    )
    assert ctx.priority == CtxPriority(holder=None, windowOpen=False, passSequence=(), stackDepth=0)
    assert ctx.zones.public.zoneSummaries == {}
    assert ctx.zones.private.zoneCards == {}
    assert ctx.zones.private.cardIndex == {}
    assert ctx.zones.private.cardMeta == {}
    assert ctx.zones.reveals.active == ()
    assert ctx.zones.reveals.nextSeq == 0
    assert ctx.time.mode == "none"
    assert ctx.random.seed == "seed-1"
    assert ctx.random.state is None
    assert ctx.random.draws == 0


def test_phase2_create_initial_tcg_ctx_opens_priority_for_first_player_chooser():
    ctx = create_initial_tcg_ctx(
        matchID="match-123",
        gameID="lorcana",
        rulesetHash="ruleset-v1",
        players=(PlayerId("p0"), PlayerId("p1")),
        choosingFirstPlayer=PlayerId("p1"),
    )

    assert ctx.status.choosingFirstPlayer == PlayerId("p1")
    assert ctx.priority.holder == PlayerId("p1")
    assert ctx.priority.windowOpen is True


def test_phase2_create_initial_lorcana_g_matches_lorcanito_defaults():
    G = create_initial_lorcana_g(PlayerId("p0"), PlayerId("p1"))

    assert G.lore == {PlayerId("p0"): 0, PlayerId("p1"): 0}
    assert G.turnMetadata.cardsPlayedThisTurn == ()
    assert G.turnMetadata.charactersQuesting == ()
    assert G.turnMetadata.inkedThisTurn == ()
    assert G.turnMetadata.cardsPutIntoInkwellThisTurn == ()
    assert G.turnMetadata.additionalInkwellActions == 0
    assert G.turnMetadata.shiftPlayedThisTurn == ()
    assert G.turnMetadata.challengesByPlayerThisTurn == {}
    assert G.turnMetadata.damagedCharactersByOwnerThisTurn == {}
    assert G.turnMetadata.damageRemovedByPlayerThisTurn == {}
    assert G.turnMetadata.challengedCharactersThisTurn == ()
    assert G.turnMetadata.banishedCharactersThisTurn == ()
    assert G.turnMetadata.banishedCharactersInChallengeByOwnerThisTurn == {}
    assert G.turnMetadata.discardCardsLeftThisTurn == 0
    assert G.turnMetadata.cardsPutIntoDiscardThisTurnByOwner == {}
    assert G.turnMetadata.pendingCostReductionsByPlayer == {}
    assert G.turnMetadata.cardsDrawnThisTurnByPlayer == {}
    assert G.triggeredAbilities.pendingEvents == ()
    assert G.triggeredAbilities.registrations == ()
    assert G.triggeredAbilities.bag.nextSeq == 1
    assert G.triggeredAbilities.bag.items == ()
    assert G.triggeredAbilities.usageLedger.occurrences == {}
    assert G.triggeredAbilities.usageLedger.resolutions == {}
    assert G.pendingEffects == ()
    assert G.turnsCompletedByPlayer == {PlayerId("p0"): 0, PlayerId("p1"): 0}
    assert G.continuousEffects.nextSeq == 1
    assert G.continuousEffects.instances == ()
    assert G.continuousEffects.byTarget == {}
    assert G.temporaryPlayerRestrictions.restrictionsByPlayer == {}
    assert G.temporaryPlayerRestrictions.startsByPlayer == {}
    assert G.temporaryPlayerRestrictions.payloadsByPlayer == {}
    assert G.playFromUnderPermissions.permissionsByPlayer == {}
    assert G.replacementEffects.nextSeq == 1
    assert G.replacementEffects.registrations == ()
    assert G.replacementEffects.usageLedger.perTurn == {}
    assert G.replacementEffects.byEventKind == {}
    assert G.challengeState is None
    assert G.staticEffectsVersion == 0


def test_phase3_zone_runtime_state_uses_lorcanito_public_reveals_private_shape():
    registry = build_zone_registry(LORCANA_RUNTIME_ZONES, (PlayerId("p0"), PlayerId("p1")))
    zones = initialize_zone_state_from_registry(registry)

    assert "deck:p0" in zones.public.zoneSummaries
    assert "deck:p0" in zones.private.zoneCards
    assert zones.private.cardIndex == {}
    assert zones.private.cardMeta == {}
    assert zones.reveals.active == ()
    assert zones.reveals.nextSeq == 0


def test_phase2_match_state_exposes_lorcanito_G_ctx_envelope_only():
    state = MatchState.empty()

    assert state.G.lore == {PlayerId("p0"): 0, PlayerId("p1"): 0}
    assert state.ctx.playerIds == (PlayerId("p0"), PlayerId("p1"))
    assert not hasattr(state, "framework")
    assert not hasattr(state, "game")


def test_phase3_lorcanito_card_meta_uses_source_field_names():
    meta = CardMeta(damage=2, state="exerted", isDrying=True, publicFaceState="faceDown")

    assert meta.damage == 2
    assert meta.state == "exerted"
    assert meta.isDrying is True
    assert meta.publicFaceState == "faceDown"
    assert not hasattr(meta, "exerted")
    assert not hasattr(meta, "drying")
