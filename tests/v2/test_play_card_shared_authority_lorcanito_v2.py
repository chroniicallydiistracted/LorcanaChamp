from dataclasses import replace

from lorcana_engine_v2.core.commands import CommandEnvelope, MoveInput
from lorcana_engine_v2.core.ids import InstanceId, PlayerId
from lorcana_engine_v2.core.runtime import MatchRuntime
from lorcana_engine_v2.core.state import MatchState
from lorcana_engine_v2.core.zones import scoped_zone
from lorcana_engine_v2.moves.play import PLAY_CARD

from .helpers import resources_for
from .test_play_card_lorcanito_v2 import _main_state


def _runtime(resources, state):
    runtime = MatchRuntime(resources)
    runtime.load_state(state)
    return runtime


def _play_command(card_id, **args):
    return CommandEnvelope(
        commandID=f"cmd-shared-authority-play-{card_id}",
        move=PLAY_CARD,
        input=MoveInput(args={"cardId": card_id, **args}),
    )


def _with_pending_cost_reductions(state, player_id, *entries):
    return MatchState(
        G=state.G.with_updates(
            turnMetadata=replace(
                state.G.turnMetadata,
                pendingCostReductionsByPlayer={PlayerId(str(player_id)): tuple(entries)},
            )
        ),
        ctx=state.ctx,
    )


def test_play_card_uses_shared_pending_cost_reduction_and_consumes_it():
    resources = resources_for({"card": "XGm", "ink": "Y1z"})
    state = _main_state(resources, hand=("card",), inkwell=("ink",))
    state = _with_pending_cost_reductions(
        state,
        "p0",
        {
            "amount": 2,
            "cardType": "character",
            "expiresAtTurn": 1,
            "consumeOnUse": True,
        },
    )
    runtime = _runtime(resources, state)

    result = runtime.process_command(_play_command("card"), "p0", actor_role="player")

    assert result.success is True
    assert InstanceId("card") in result.state.ctx.zones.private.zoneCards[scoped_zone("play", "p0")]
    assert result.state.ctx.zones.private.cardMeta[InstanceId("ink")].state == "exerted"
    assert result.state.G.turnMetadata.pendingCostReductionsByPlayer[PlayerId("p0")] == ()


def test_play_card_does_not_use_expired_pending_cost_reduction():
    resources = resources_for({"card": "XGm", "ink": "Y1z"})
    state = _main_state(resources, hand=("card",), inkwell=("ink",))
    state = _with_pending_cost_reductions(
        state,
        "p0",
        {
            "amount": 2,
            "cardType": "character",
            "expiresAtTurn": 0,
            "consumeOnUse": True,
        },
    )
    runtime = _runtime(resources, state)

    result = runtime.process_command(_play_command("card"), "p0", actor_role="player")

    assert result.success is False
    assert result.errorCode == "INSUFFICIENT_INK"
    assert InstanceId("card") in runtime.get_state().ctx.zones.private.zoneCards[scoped_zone("hand", "p0")]


def test_play_card_continues_to_use_shared_static_cost_reduction_from_real_snow_white():
    resources = resources_for({"snow": "BdH", "dwarf": "hWr", "ink": "Y1z"})
    state = _main_state(resources, hand=("dwarf",), play=("snow",), inkwell=("ink",))
    runtime = _runtime(resources, state)

    result = runtime.process_command(_play_command("dwarf"), "p0", actor_role="player")

    assert result.success is True
    assert result.state.ctx.zones.private.cardMeta[InstanceId("ink")].state == "exerted"
    assert InstanceId("dwarf") in result.state.ctx.zones.private.zoneCards[scoped_zone("play", "p0")]


def test_play_card_continues_to_use_shared_static_cost_increase_from_real_gantu():
    from lorcana_engine_v2.core.zones import CardMeta, move_card_to_zone, patch_card_meta

    resources = resources_for(
        {"gantu": "HlC", "action": "X1Y", "i1": "Y1z", "i2": "Y1z", "i3": "Y1z"},
        owners={"p0": ("action", "i1", "i2", "i3"), "p1": ("gantu",)},
    )
    state = _main_state(resources, hand=("action",), inkwell=("i1", "i2", "i3"))
    zones = move_card_to_zone(state.ctx.zones, card_id="gantu", destination_zone_key=scoped_zone("play", "p1"))
    zones = patch_card_meta(zones, "gantu", CardMeta(state="ready", isDrying=False, damage=0))
    state = MatchState(G=state.G, ctx=state.ctx.with_updates(zones=zones))
    runtime = _runtime(resources, state)

    result = runtime.process_command(_play_command("action"), "p0", actor_role="player")

    assert result.success is False
    assert result.errorCode == "INSUFFICIENT_INK"