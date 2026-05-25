from lorcana_engine_v2.core.commands import CommandEnvelope, MoveInput
from lorcana_engine_v2.core.ids import InstanceId, PlayerId
from lorcana_engine_v2.core.state import MatchState
from lorcana_engine_v2.core.zones import CardMeta, move_card_to_zone, patch_card_meta
from lorcana_engine_v2.effects.temporary_effects import add_temporary_player_restriction
from lorcana_engine_v2.effects.triggered_abilities import record_event, flush_triggered_events_to_bag
from lorcana_engine_v2.core.runtime import MatchRuntime
from lorcana_engine_v2.core.zones import scoped_zone
from lorcana_engine_v2.moves.play import PLAY_CARD

from .test_play_card_lorcanito_v2 import _main_state
from .helpers import resources_for


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


def test_standard_play_rejects_when_available_ink_is_too_low():
    resources = resources_for({"card": "Y1z", "i1": "XGm", "i2": "XGm", "i3": "XGm"})
    state = _main_state(resources, hand=("card",), inkwell=("i1", "i2", "i3"))
    runtime = _runtime(resources, state)

    result = runtime.process_command(_play_command("card"), "p0", actor_role="player")

    assert result.success is False
    assert result.errorCode == "INSUFFICIENT_INK"
    assert InstanceId("card") in runtime.get_state().ctx.zones.private.zoneCards[scoped_zone("hand", "p0")]


def test_available_ink_counts_only_ready_inkwell_cards_after_payment():
    resources = resources_for({"card": "XGm", "i1": "Y1z", "i2": "Y1z", "i3": "Y1z", "i4": "Y1z"})
    state = _main_state(resources, hand=("card",), inkwell=("i1", "i2", "i3", "i4"))
    runtime = _runtime(resources, state)

    before = runtime.validate_command(_play_command("card"), "p0", actor_role="player")
    assert before.valid is True

    result = runtime.process_command(_play_command("card"), "p0", actor_role="player")

    assert result.success is True
    assert result.state.ctx.zones.private.cardMeta[InstanceId("i1")].state == "exerted"
    ready = [
        card_id
        for card_id in ("i1", "i2", "i3", "i4")
        if result.state.ctx.zones.private.cardMeta[InstanceId(card_id)].state != "exerted"
    ]
    assert ready == ["i4"]


def test_standard_play_applies_static_cost_reduction_from_real_snow_white():
    resources = resources_for({"snow": "BdH", "dwarf": "hWr", "ink": "Y1z"})
    state = _main_state(resources, hand=("dwarf",), play=("snow",), inkwell=("ink",))
    runtime = _runtime(resources, state)

    result = runtime.process_command(_play_command("dwarf"), "p0", actor_role="player")

    assert result.success is True
    assert result.state.ctx.zones.private.cardMeta[InstanceId("ink")].state == "exerted"
    assert InstanceId("dwarf") in result.state.ctx.zones.private.zoneCards[scoped_zone("play", "p0")]


def test_standard_play_applies_static_cost_increase_from_real_gantu():
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


def test_play_card_is_blocked_by_pending_action_effect():
    resources = resources_for({"card": "XGm", "ink": "Y1z"})
    state = _main_state(resources, hand=("card",), inkwell=("ink",))
    state = MatchState(
        G=state.G.with_updates(pendingEffects=(object(),)),
        ctx=state.ctx,
    )
    runtime = _runtime(resources, state)

    result = runtime.process_command(_play_command("card"), "p0", actor_role="player")

    assert result.success is False
    assert result.errorCode == "EFFECT_PENDING"


def test_play_card_is_blocked_by_pending_bag_item():
    resources = resources_for({"aladdin": "ZTM", "card": "XGm", "ink": "Y1z"})
    state = _main_state(resources, hand=("card",), play=("aladdin",), inkwell=("ink",))
    state = record_event(
        state,
        {
            "event": "play",
            "subjectCardId": InstanceId("aladdin"),
            "triggerSourceCardId": InstanceId("aladdin"),
            "playerId": PlayerId("p0"),
        },
    )
    state = flush_triggered_events_to_bag(state, resources=resources)
    runtime = _runtime(resources, state)

    result = runtime.process_command(_play_command("card"), "p0", actor_role="player")

    assert result.success is False
    assert result.errorCode == "BAG_PENDING"


def test_play_card_is_blocked_by_temporary_cant_play_restriction():
    resources = resources_for({"card": "XGm", "ink": "Y1z", "ink2": "Y1z", "ink3": "Y1z"})
    state = _main_state(resources, hand=("card",), inkwell=("ink", "ink2", "ink3"))
    restrictions = add_temporary_player_restriction(
        state.G.temporaryPlayerRestrictions,
        "p0",
        "cant-play",
        expires_at_turn=1,
    )
    state = MatchState(G=state.G.with_updates(temporaryPlayerRestrictions=restrictions), ctx=state.ctx)
    runtime = _runtime(resources, state)

    result = runtime.process_command(_play_command("card"), "p0", actor_role="player")

    assert result.success is False
    assert result.errorCode == "PLAYER_PLAY_RESTRICTED"


def test_play_card_is_blocked_by_static_cant_play_actions_restriction():
    resources = resources_for(
        {"tiana": "ivr", "action": "X1Y", "i1": "Y1z", "i2": "Y1z"},
        owners={"p0": ("action", "i1", "i2"), "p1": ("tiana",)},
    )
    state = _main_state(resources, hand=("action",), inkwell=("i1", "i2"))
    zones = move_card_to_zone(state.ctx.zones, card_id="tiana", destination_zone_key=scoped_zone("play", "p1"))
    zones = patch_card_meta(zones, "tiana", CardMeta(state="exerted", isDrying=False, damage=0))
    state = MatchState(G=state.G, ctx=state.ctx.with_updates(zones=zones))
    runtime = _runtime(resources, state)

    result = runtime.process_command(_play_command("action"), "p0", actor_role="player")

    assert result.success is False
    assert result.errorCode == "PLAYER_PLAY_RESTRICTED"


def test_play_card_is_blocked_by_self_play_condition_false():
    resources = resources_for({"mirabel": "284", "i1": "Y1z", "i2": "Y1z", "i3": "Y1z", "i4": "Y1z", "i5": "Y1z"})
    state = _main_state(resources, hand=("mirabel",), inkwell=("i1", "i2", "i3", "i4", "i5"))
    runtime = _runtime(resources, state)

    result = runtime.process_command(_play_command("mirabel"), "p0", actor_role="player")

    assert result.success is False
    assert result.errorCode == "SELF_PLAY_CONDITION_NOT_MET"
