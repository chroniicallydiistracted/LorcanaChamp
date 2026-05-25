from lorcana_engine_v2.core.bootstrap import initialize_match_state_from_static_resources
from lorcana_engine_v2.core.commands import CommandEnvelope, MoveInput
from lorcana_engine_v2.core.ids import InstanceId, PlayerId
from lorcana_engine_v2.core.runtime import MatchRuntime
from lorcana_engine_v2.core.state import MatchState
from lorcana_engine_v2.core.zones import CardMeta, move_card_to_zone, patch_card_meta, scoped_zone
from lorcana_engine_v2.effects.replacement_effects import register_replacement_effect
from lorcana_engine_v2.moves.play import PLAY_CARD
from lorcana_engine_v2.moves.resolve_pending import RESOLVE_EFFECT
from lorcana_engine_v2.resolution.action_effects import resolve_action_effect
from lorcana_engine_v2.resolution.pending import finalize_resolved_action_card

from tests.v2.helpers import resources_for


def _state(resources, *, p0_hand=(), p1_hand=(), p0_play=(), p1_play=(), p0_inkwell=()):
    state = initialize_match_state_from_static_resources(resources)
    zones = state.ctx.zones
    placements = (
        ("hand", "p0", p0_hand, None),
        ("hand", "p1", p1_hand, None),
        ("play", "p0", p0_play, CardMeta(state="ready", isDrying=False, damage=0)),
        ("play", "p1", p1_play, CardMeta(state="ready", isDrying=False, damage=0)),
        ("inkwell", "p0", p0_inkwell, CardMeta(state="ready", publicFaceState="faceDown")),
    )
    for zone, player_id, card_ids, meta in placements:
        for card_id in card_ids:
            zones = move_card_to_zone(zones, card_id=card_id, destination_zone_key=scoped_zone(zone, player_id))
            if meta is not None:
                zones = patch_card_meta(zones, card_id, meta)
    return MatchState(
        G=state.G,
        ctx=state.ctx.with_updates(
            zones=zones,
            status=state.ctx.status.with_updates(
                turn=1,
                gameSegment="mainGame",
                phase="main",
                turnOwnerId=PlayerId("p0"),
            ),
            priority=state.ctx.priority.with_updates(holder=PlayerId("p0"), windowOpen=True),
        ),
    )


def _runtime(resources, state):
    runtime = MatchRuntime(resources)
    runtime.load_state(state)
    return runtime


def _play(card_id, **args):
    return CommandEnvelope(
        commandID=f"play-{card_id}",
        move=PLAY_CARD,
        input=MoveInput(args={"cardId": card_id, **args}),
    )


def _resolve(effect_id, **args):
    return CommandEnvelope(
        commandID=f"resolve-{effect_id}",
        move=RESOLVE_EFFECT,
        input=MoveInput(args={"effectId": effect_id, "params": dict(args)}),
    )


def test_fire_the_cannons_deals_damage_to_chosen_character():
    resources = resources_for(
        {"action": "BFV", "target": "Y1z", "ink": "Y1z"},
        owners={"p0": ("action", "ink"), "p1": ("target",)},
    )
    runtime = _runtime(resources, _state(resources, p0_hand=("action",), p1_play=("target",), p0_inkwell=("ink",)))

    result = runtime.process_command(_play("action", targets=["target"]), "p0", actor_role="player")

    assert result.success is True
    assert result.state.ctx.zones.private.cardMeta[InstanceId("target")].damage == 2
    assert InstanceId("action") in result.state.ctx.zones.private.zoneCards[scoped_zone("discard", "p0")]


def test_dragon_fire_banishes_chosen_character():
    resources = resources_for(
        {"action": "NCd", "target": "Y1z", "i1": "Y1z", "i2": "Y1z", "i3": "Y1z", "i4": "Y1z", "i5": "Y1z"},
        owners={"p0": ("action", "i1", "i2", "i3", "i4", "i5"), "p1": ("target",)},
    )
    runtime = _runtime(
        resources,
        _state(resources, p0_hand=("action",), p1_play=("target",), p0_inkwell=("i1", "i2", "i3", "i4", "i5")),
    )

    result = runtime.process_command(_play("action", targets=["target"]), "p0", actor_role="player")

    assert result.success is True
    assert InstanceId("target") in result.state.ctx.zones.private.zoneCards[scoped_zone("discard", "p1")]
    assert InstanceId("action") in result.state.ctx.zones.private.zoneCards[scoped_zone("discard", "p0")]


def test_freeze_exerts_chosen_opposing_character():
    resources = resources_for(
        {"action": "D1e", "target": "Y1z", "i1": "Y1z", "i2": "Y1z"},
        owners={"p0": ("action", "i1", "i2"), "p1": ("target",)},
    )
    runtime = _runtime(resources, _state(resources, p0_hand=("action",), p1_play=("target",), p0_inkwell=("i1", "i2")))

    result = runtime.process_command(_play("action", targets=["target"]), "p0", actor_role="player")

    assert result.success is True
    assert result.state.ctx.zones.private.cardMeta[InstanceId("target")].state == "exerted"


def test_fan_the_flames_readies_and_restricts_chosen_character():
    resources = resources_for(
        {"action": "iMK", "target": "Y1z", "ink": "Y1z"},
        owners={"p0": ("action", "target", "ink"), "p1": ()},
    )
    state = _state(resources, p0_hand=("action",), p0_play=("target",), p0_inkwell=("ink",))
    zones = patch_card_meta(
        state.ctx.zones,
        "target",
        state.ctx.zones.private.cardMeta[InstanceId("target")].with_updates(state="exerted"),
    )
    runtime = _runtime(resources, MatchState(G=state.G, ctx=state.ctx.with_updates(zones=zones)))

    result = runtime.process_command(_play("action", targets=["target"]), "p0", actor_role="player")

    meta = result.state.ctx.zones.private.cardMeta[InstanceId("target")]
    assert result.success is True
    assert meta.state == "ready"
    assert meta.temporaryRestrictions == {"cant-quest": 1}


def test_sudden_chill_suspends_for_opponent_discard_choice_and_resolve_effect_finalizes_action():
    resources = resources_for(
        {"action": "DDi", "opp_card": "Y1z", "i1": "Y1z", "i2": "Y1z"},
        owners={"p0": ("action", "i1", "i2"), "p1": ("opp_card",)},
    )
    runtime = _runtime(resources, _state(resources, p0_hand=("action",), p1_hand=("opp_card",), p0_inkwell=("i1", "i2")))

    play_result = runtime.process_command(_play("action"), "p0", actor_role="player")

    assert play_result.success is True
    assert len(play_result.state.G.pendingEffects) == 1
    pending = play_result.state.G.pendingEffects[0]
    assert pending.kind == "discard-choice"
    assert pending.chooserId == PlayerId("p1")
    assert InstanceId("action") in play_result.state.ctx.zones.private.zoneCards[scoped_zone("limbo", "p0")]

    resolve_result = runtime.process_command(_resolve(pending.id, targets=["opp_card"]), "p1", actor_role="player")

    assert resolve_result.success is True
    assert resolve_result.state.G.pendingEffects == ()
    assert resolve_result.state.ctx.priority.pendingChoice is None
    assert InstanceId("opp_card") in resolve_result.state.ctx.zones.private.zoneCards[scoped_zone("discard", "p1")]
    assert InstanceId("action") in resolve_result.state.ctx.zones.private.zoneCards[scoped_zone("discard", "p0")]


def test_conditional_false_branch_does_not_execute_then_branch():
    resources = resources_for({"source": "ZTM"})
    state = _state(resources, p0_play=("source",))
    state = MatchState(G=state.G.with_updates(lore={PlayerId("p0"): 0, PlayerId("p1"): 3}), ctx=state.ctx)

    result = resolve_action_effect(
        state,
        {"playerId": PlayerId("p0"), "cardId": "source", "cardType": "character", "costType": "free"},
        {
            "type": "conditional",
            "condition": {"type": "during-turn", "whose": "opponent"},
            "then": {"type": "lose-lore", "target": "OPPONENT", "amount": 1},
        },
    )

    assert result.status == "resolved"
    assert result.state.G.lore[PlayerId("p1")] == 3


def test_conditional_false_branch_executes_else_branch_when_present():
    resources = resources_for({"source": "ZTM"})
    state = _state(resources, p0_play=("source",))
    state = MatchState(G=state.G.with_updates(lore={PlayerId("p0"): 0, PlayerId("p1"): 3}), ctx=state.ctx)

    result = resolve_action_effect(
        state,
        {"playerId": PlayerId("p0"), "cardId": "source", "cardType": "character", "costType": "free"},
        {
            "type": "conditional",
            "condition": {"type": "during-turn", "whose": "opponent"},
            "then": {"type": "lose-lore", "target": "OPPONENT", "amount": 1},
            "else": {"type": "gain-lore", "target": "CONTROLLER", "amount": 1},
        },
    )

    assert result.status == "resolved"
    assert result.state.G.lore[PlayerId("p0")] == 1
    assert result.state.G.lore[PlayerId("p1")] == 3


def test_sequence_continuation_preserves_remaining_effects_after_optional_suspension():
    resources = resources_for({"source": "ZTM"})
    state = _state(resources, p0_play=("source",))
    runtime = _runtime(resources, MatchState(G=state.G.with_updates(lore={PlayerId("p0"): 0, PlayerId("p1"): 3}), ctx=state.ctx))

    first = resolve_action_effect(
        runtime.get_state(),
        {"playerId": PlayerId("p0"), "cardId": "source", "cardType": "character", "costType": "free"},
        {
            "type": "sequence",
            "effects": [
                {"type": "optional", "effect": {"type": "gain-lore", "target": "CONTROLLER", "amount": 1}},
                {"type": "lose-lore", "target": "OPPONENT", "amount": 1},
            ],
        },
    )
    runtime.load_state(first.state)
    pending = first.state.G.pendingEffects[0]

    result = runtime.process_command(_resolve(pending.id, resolveOptional=False), "p0", actor_role="player")

    assert result.success is True
    assert result.state.G.lore[PlayerId("p0")] == 0
    assert result.state.G.lore[PlayerId("p1")] == 2


def test_action_finalization_applies_zone_change_replacement():
    resources = resources_for({"action": "X1Y"})
    state = _state(resources)
    zones = move_card_to_zone(state.ctx.zones, card_id="action", destination_zone_key=scoped_zone("limbo", "p0"))
    state = MatchState(G=state.G, ctx=state.ctx.with_updates(zones=zones))
    state = register_replacement_effect(
        state,
        {"playerId": PlayerId("p0"), "cardId": "action", "cardType": "action", "costType": "standard"},
        {
            "type": "zone-destination",
            "targetRef": "source",
            "toZone": "discard",
            "replacementZone": "deck",
            "replacementPosition": "bottom",
        },
        "this-turn",
    )

    state = finalize_resolved_action_card(
        state,
        {"playerId": PlayerId("p0"), "cardId": "action", "cardType": "action", "costType": "standard"},
    )

    assert InstanceId("action") in state.ctx.zones.private.zoneCards[scoped_zone("deck", "p0")]


def test_explicit_unsupported_action_effect_records_evidence():
    resources = resources_for({"source": "ZTM"})
    state = _state(resources, p0_play=("source",))

    result = resolve_action_effect(
        state,
        {"playerId": PlayerId("p0"), "cardId": "source", "cardType": "character", "costType": "free"},
        {"type": "not-yet-real"},
    )

    assert result.status == "unsupported"
    assert result.resolutionInput.eventSnapshot["unsupportedActionEffect"] == "not-yet-real"
