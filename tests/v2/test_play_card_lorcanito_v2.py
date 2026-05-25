from lorcana_engine_v2.core.bootstrap import initialize_match_state_from_static_resources
from lorcana_engine_v2.core.commands import CommandEnvelope, MoveInput
from lorcana_engine_v2.core.ids import InstanceId, PlayerId
from lorcana_engine_v2.core.runtime import MatchRuntime
from lorcana_engine_v2.core.state import MatchState
from lorcana_engine_v2.core.zones import move_card_to_zone, patch_card_meta, scoped_zone
from lorcana_engine_v2.moves.play import PLAY_CARD

from .helpers import resources_for


def _main_state(resources, *, hand=(), play=(), inkwell=(), discard=(), lore=None):
    state = initialize_match_state_from_static_resources(resources)
    zones = state.ctx.zones
    for card_id in hand:
        zones = move_card_to_zone(zones, card_id=card_id, destination_zone_key=scoped_zone("hand", "p0"))
    for card_id in play:
        zones = move_card_to_zone(zones, card_id=card_id, destination_zone_key=scoped_zone("play", "p0"))
        zones = patch_card_meta(
            zones,
            card_id,
            zones.private.cardMeta[InstanceId(card_id)].with_updates(state="ready", isDrying=False, damage=0),
        )
    for card_id in inkwell:
        zones = move_card_to_zone(zones, card_id=card_id, destination_zone_key=scoped_zone("inkwell", "p0"))
        zones = patch_card_meta(
            zones,
            card_id,
            zones.private.cardMeta[InstanceId(card_id)].with_updates(state="ready", publicFaceState="faceDown"),
        )
    for card_id in discard:
        zones = move_card_to_zone(zones, card_id=card_id, destination_zone_key=scoped_zone("discard", "p0"))
    next_g = state.G
    if lore is not None:
        next_g = next_g.with_updates(lore=lore)
    return MatchState(
        G=next_g,
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


def _play_command(card_id, **args):
    return CommandEnvelope(
        commandID=f"cmd-play-{card_id}",
        move=PLAY_CARD,
        input=MoveInput(args={"cardId": card_id, **args}),
    )


def test_real_character_play_pays_ink_enters_play_drying_and_emits_play_event():
    resources = resources_for({"card": "XGm", "i1": "Y1z", "i2": "Y1z", "i3": "Y1z"})
    state = _main_state(resources, hand=("card",), inkwell=("i1", "i2", "i3"))
    runtime = _runtime(resources, state)

    assert runtime.enumerate_moves_for_player("p0", actor_role="player") == (PLAY_CARD, "putCardIntoInkwell")

    result = runtime.process_command(_play_command("card"), "p0", actor_role="player")

    assert result.success is True
    assert InstanceId("card") in result.state.ctx.zones.private.zoneCards[scoped_zone("play", "p0")]
    assert result.state.G.turnMetadata.cardsPlayedThisTurn == (InstanceId("card"),)
    assert result.moveLogs[0].defaultMessage.key == "lorcana.move.playCard"
    meta = result.state.ctx.zones.private.cardMeta[InstanceId("card")]
    assert meta.state == "ready"
    assert meta.isDrying is True
    assert meta.playedCostType == "standard"
    assert all(
        result.state.ctx.zones.private.cardMeta[InstanceId(card_id)].state == "exerted"
        for card_id in ("i1", "i2", "i3")
    )
    assert any(event.event.kind == "cardPlayed" for event in result.gameEvents)


def test_real_action_play_resolves_foundational_effect_and_moves_to_discard():
    resources = resources_for(
        {"action": "X1Y", "i1": "Y1z", "i2": "Y1z"},
        owners={"p0": ("action", "i1", "i2"), "p1": ()},
    )
    state = _main_state(
        resources,
        hand=("action",),
        inkwell=("i1", "i2"),
        lore={PlayerId("p0"): 0, PlayerId("p1"): 3},
    )
    runtime = _runtime(resources, state)

    result = runtime.process_command(_play_command("action"), "p0", actor_role="player")

    assert result.success is True
    assert result.state.G.lore[PlayerId("p1")] == 2
    assert InstanceId("action") in result.state.ctx.zones.private.zoneCards[scoped_zone("discard", "p0")]
    assert result.state.G.turnMetadata.cardsPlayedThisTurn == (InstanceId("action"),)


def test_real_play_trigger_flushes_to_bag_after_character_enters_play():
    resources = resources_for({"aladdin": "ZTM", "i1": "Y1z", "i2": "Y1z", "i3": "Y1z"})
    state = _main_state(resources, hand=("aladdin",), inkwell=("i1", "i2", "i3"))
    runtime = _runtime(resources, state)

    result = runtime.process_command(_play_command("aladdin"), "p0", actor_role="player")

    assert result.success is True
    bag_items = result.state.G.triggeredAbilities.bag.items
    assert len(bag_items) == 1
    assert bag_items[0].sourceId == InstanceId("aladdin")
    assert bag_items[0].trigger["event"] == "play"
