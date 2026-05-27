from lorcana_engine_v2.core.bootstrap import initialize_match_state_from_static_resources
from lorcana_engine_v2.core.commands import CommandEnvelope, MoveInput
from lorcana_engine_v2.core.ids import InstanceId, PlayerId
from lorcana_engine_v2.core.runtime import MatchRuntime
from lorcana_engine_v2.core.state import MatchState
from lorcana_engine_v2.core.zones import CardMeta, move_card_to_zone, patch_card_meta, scoped_zone
from lorcana_engine_v2.moves.ink import PUT_CARD_INTO_INKWELL
from lorcana_engine_v2.moves.play import PLAY_CARD
from lorcana_engine_v2.resolution.action_effect_types import ActionResolutionInput
from lorcana_engine_v2.resolution.action_effects import resolve_action_effect

from tests.v2.helpers import resources_for


def _state(
    resources,
    *,
    p0_hand=(),
    p1_hand=(),
    p0_play=(),
    p1_play=(),
    p0_inkwell=(),
    p0_deck=(),
    p1_deck=(),
    meta: dict[str, CardMeta] | None = None,
):
    state = initialize_match_state_from_static_resources(resources)
    zones = state.ctx.zones

    placements = (
        ("hand", "p0", p0_hand, None),
        ("hand", "p1", p1_hand, None),
        ("play", "p0", p0_play, CardMeta(state="ready", isDrying=False, damage=0)),
        ("play", "p1", p1_play, CardMeta(state="ready", isDrying=False, damage=0)),
        ("inkwell", "p0", p0_inkwell, CardMeta(state="ready", publicFaceState="faceDown")),
        ("deck", "p0", p0_deck, None),
        ("deck", "p1", p1_deck, None),
    )

    for zone, player_id, card_ids, card_meta in placements:
        for card_id in card_ids:
            zones = move_card_to_zone(
                zones,
                card_id=card_id,
                destination_zone_key=scoped_zone(zone, player_id),
            )
            if card_meta is not None:
                zones = patch_card_meta(zones, card_id, card_meta)

    if meta:
        for card_id, card_meta in meta.items():
            zones = patch_card_meta(zones, card_id, card_meta)

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
        commandID=f"turn-metrics-play-{card_id}",
        move=PLAY_CARD,
        input=MoveInput(args={"cardId": card_id, **args}),
    )


def _ink(card_id):
    return CommandEnvelope(
        commandID=f"turn-metrics-ink-{card_id}",
        move=PUT_CARD_INTO_INKWELL,
        input=MoveInput(args={"cardId": card_id}),
    )


def test_put_card_into_inkwell_records_lorcanito_ink_metrics_separately():
    resources = resources_for({"card": "Y1z"})
    state = _state(resources, p0_hand=("card",))
    runtime = _runtime(resources, state)

    result = runtime.process_command(_ink("card"), "p0", actor_role="player")

    assert result.success is True
    metadata = result.state.G.turnMetadata
    assert metadata.inkedThisTurn == (InstanceId("card"),)
    assert metadata.cardsPutIntoInkwellThisTurn == (InstanceId("card"),)


def test_fire_the_cannons_records_play_damage_and_discard_metrics():
    resources = resources_for(
        {"action": "BFV", "target": "Y1z", "ink": "Y1z"},
        owners={"p0": ("action", "ink"), "p1": ("target",)},
    )
    state = _state(resources, p0_hand=("action",), p1_play=("target",), p0_inkwell=("ink",))
    runtime = _runtime(resources, state)

    result = runtime.process_command(_play("action", targets=["target"]), "p0", actor_role="player")

    assert result.success is True
    metadata = result.state.G.turnMetadata
    assert metadata.cardsPlayedThisTurn == (InstanceId("action"),)
    assert metadata.damagedCharactersByOwnerThisTurn[PlayerId("p1")] == 1
    assert metadata.cardsPutIntoDiscardThisTurnByOwner[PlayerId("p0")] == 1
    assert result.state.ctx.zones.private.cardMeta[InstanceId("target")].damage == 2


def test_dragon_fire_records_banished_character_and_discard_entries():
    resources = resources_for(
        {
            "action": "NCd",
            "target": "Y1z",
            "i1": "Y1z",
            "i2": "Y1z",
            "i3": "Y1z",
            "i4": "Y1z",
            "i5": "Y1z",
        },
        owners={"p0": ("action", "i1", "i2", "i3", "i4", "i5"), "p1": ("target",)},
    )
    state = _state(
        resources,
        p0_hand=("action",),
        p1_play=("target",),
        p0_inkwell=("i1", "i2", "i3", "i4", "i5"),
    )
    runtime = _runtime(resources, state)

    result = runtime.process_command(_play("action", targets=["target"]), "p0", actor_role="player")

    assert result.success is True
    metadata = result.state.G.turnMetadata
    assert InstanceId("target") in metadata.banishedCharactersThisTurn
    assert metadata.cardsPutIntoDiscardThisTurnByOwner[PlayerId("p1")] == 1
    assert metadata.cardsPutIntoDiscardThisTurnByOwner[PlayerId("p0")] == 1


def test_draw_effect_records_one_draw_metric_per_real_card_drawn():
    resources = resources_for({"source": "ZTM", "d1": "Y1z", "d2": "XGm"})
    state = _state(resources, p0_play=("source",), p0_deck=("d1", "d2"))

    result = resolve_action_effect(
        state,
        {"playerId": PlayerId("p0"), "cardId": "source", "cardType": "character", "costType": "free"},
        {"type": "draw", "amount": 2, "target": "CONTROLLER"},
    )

    assert result.status == "resolved"
    assert result.state.G.turnMetadata.cardsDrawnThisTurnByPlayer[PlayerId("p0")] == 2


def test_remove_damage_effect_records_damage_removed_metric():
    resources = resources_for({"source": "ZTM", "damaged": "Y1z"})
    state = _state(
        resources,
        p0_play=("source", "damaged"),
        meta={"damaged": CardMeta(state="ready", isDrying=False, damage=3)},
    )

    result = resolve_action_effect(
        state,
        {"playerId": PlayerId("p0"), "cardId": "source", "cardType": "character", "costType": "free"},
        {"type": "remove-damage", "target": "CHOSEN_CARD", "amount": 2},
        ActionResolutionInput(targets=("damaged",)),
    )

    assert result.status == "resolved"
    assert result.state.ctx.zones.private.cardMeta[InstanceId("damaged")].damage == 1
    assert result.state.G.turnMetadata.damageRemovedByPlayerThisTurn[PlayerId("p0")] == 2


def test_put_under_effect_records_cards_under_turn_metric():
    resources = resources_for({"parent": "ZTM", "child": "Y1z"})
    state = _state(resources, p0_play=("parent",), p0_hand=("child",))

    result = resolve_action_effect(
        state,
        {"playerId": PlayerId("p0"), "cardId": "parent", "cardType": "character", "costType": "free"},
        {"type": "put-under", "under": "SELF", "target": "CHOSEN_CARD"},
        ActionResolutionInput(targets=("child",)),
    )

    assert result.status == "resolved"
    assert result.state.G.turnMetadata.cardsUnderThisTurn[InstanceId("parent")] == (InstanceId("child"),)


def test_discard_effect_records_discard_entry_metric_for_discarded_card():
    resources = resources_for(
        {"source": "ZTM", "victim": "Y1z"},
        owners={"p0": ("source",), "p1": ("victim",)},
    )
    state = _state(resources, p0_play=("source",), p1_hand=("victim",))

    result = resolve_action_effect(
        state,
        {"playerId": PlayerId("p0"), "cardId": "source", "cardType": "character", "costType": "free"},
        {"type": "discard", "target": "OPPONENT", "amount": 1},
        ActionResolutionInput(targets=("victim",)),
    )

    assert result.status == "resolved"
    assert InstanceId("victim") in result.state.ctx.zones.private.zoneCards[scoped_zone("discard", "p1")]
    assert InstanceId("victim") not in result.state.ctx.zones.private.zoneCards[scoped_zone("hand", "p1")]
    assert result.state.G.turnMetadata.cardsPutIntoDiscardThisTurnByOwner[PlayerId("p1")] == 1


def test_move_card_effect_records_discard_entry_metric_when_card_moves_to_discard():
    resources = resources_for({"source": "ZTM", "target": "Y1z"})
    state = _state(resources, p0_play=("source",), p0_hand=("target",))

    result = resolve_action_effect(
        state,
        {"playerId": PlayerId("p0"), "cardId": "source", "cardType": "character", "costType": "free"},
        {"type": "put-into-discard", "target": "CHOSEN_CARD"},
        ActionResolutionInput(targets=("target",)),
    )

    assert result.status == "resolved"
    assert InstanceId("target") in result.state.ctx.zones.private.zoneCards[scoped_zone("discard", "p0")]
    assert result.state.G.turnMetadata.cardsPutIntoDiscardThisTurnByOwner[PlayerId("p0")] == 1


def test_return_from_discard_records_discard_exit_metric_for_pure_move_card_path():
    resources = resources_for({"source": "ZTM", "returning": "Y1z"})
    state = _state(resources, p0_play=("source",), p0_hand=("returning",))
    zones = move_card_to_zone(
        state.ctx.zones,
        card_id="returning",
        destination_zone_key=scoped_zone("discard", "p0"),
    )
    state = MatchState(G=state.G, ctx=state.ctx.with_updates(zones=zones))

    result = resolve_action_effect(
        state,
        {"playerId": PlayerId("p0"), "cardId": "source", "cardType": "character", "costType": "free"},
        {"type": "return-from-discard", "target": "CHOSEN_CARD"},
        ActionResolutionInput(targets=("returning",)),
    )

    assert result.status == "resolved"
    assert InstanceId("returning") in result.state.ctx.zones.private.zoneCards[scoped_zone("hand", "p0")]
    assert InstanceId("returning") not in result.state.ctx.zones.private.zoneCards[scoped_zone("discard", "p0")]
    assert result.state.G.turnMetadata.discardCardsLeftThisTurn == 1


def test_mill_effect_records_discard_entry_metric_for_milled_cards():
    resources = resources_for(
        {"source": "ZTM", "d1": "Y1z", "d2": "XGm"},
        owners={"p0": ("source",), "p1": ("d1", "d2")},
    )
    state = _state(resources, p0_play=("source",), p1_deck=("d1", "d2"))

    result = resolve_action_effect(
        state,
        {"playerId": PlayerId("p0"), "cardId": "source", "cardType": "character", "costType": "free"},
        {"type": "mill", "target": "OPPONENT", "amount": 2},
    )

    assert result.status == "resolved"
    assert InstanceId("d1") in result.state.ctx.zones.private.zoneCards[scoped_zone("discard", "p1")]
    assert InstanceId("d2") in result.state.ctx.zones.private.zoneCards[scoped_zone("discard", "p1")]
    assert result.state.G.turnMetadata.cardsPutIntoDiscardThisTurnByOwner[PlayerId("p1")] == 2