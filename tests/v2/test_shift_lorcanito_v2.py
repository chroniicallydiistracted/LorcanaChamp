from lorcana_engine_v2.core.commands import CommandEnvelope, MoveInput
from lorcana_engine_v2.core.ids import InstanceId
from lorcana_engine_v2.core.runtime import MatchRuntime
from lorcana_engine_v2.core.zones import patch_card_meta, scoped_zone
from lorcana_engine_v2.effects.continuous_effects import add_stat_modifier_effect
from lorcana_engine_v2.moves.play import PLAY_CARD
from lorcana_engine_v2.rules.play_card_rules import get_shift_rules

from .helpers import resources_for
from .test_play_card_lorcanito_v2 import _main_state


def _play_command(card_id, **args):
    return CommandEnvelope(
        commandID=f"cmd-shift-{card_id}",
        move=PLAY_CARD,
        input=MoveInput(args={"cardId": card_id, **args}),
    )


def test_real_shift_rules_parse_ink_cost_from_lorcanito_keyword_data():
    resources = resources_for({"shift": "0Rd"})
    definition = resources.cards.get("0Rd")

    rules = get_shift_rules(definition)

    assert rules is not None
    assert rules.inkCost == 5
    assert rules.targetMode.type == "name"
    assert rules.targetMode.name == "Gramma Tala"


def test_real_shift_play_stacks_target_in_limbo_and_inherits_meta():
    resources = resources_for(
        {
            "shift": "0Rd",
            "base": "ROE",
            "i1": "XGm",
            "i2": "XGm",
            "i3": "XGm",
            "i4": "XGm",
            "i5": "XGm",
        }
    )
    state = _main_state(
        resources,
        hand=("shift",),
        play=("base",),
        inkwell=("i1", "i2", "i3", "i4", "i5"),
    )
    zones = patch_card_meta(
        state.ctx.zones,
        "base",
        state.ctx.zones.private.cardMeta[InstanceId("base")].with_updates(
            state="ready",
            isDrying=False,
            damage=1,
        ),
    )
    state = type(state)(G=state.G, ctx=state.ctx.with_updates(zones=zones))
    runtime = MatchRuntime(resources)
    runtime.load_state(state)

    result = runtime.process_command(
        _play_command("shift", cost="shift", shiftTarget="base"),
        "p0",
        actor_role="player",
    )

    assert result.success is True
    assert result.state.G.turnMetadata.shiftPlayedThisTurn == (InstanceId("shift"),)
    assert result.state.ctx.zones.private.zoneCards[scoped_zone("play", "p0")] == (InstanceId("shift"),)
    assert result.state.ctx.zones.private.zoneCards[scoped_zone("limbo", "p0")] == (InstanceId("base"),)
    meta = result.state.ctx.zones.private.cardMeta[InstanceId("shift")]
    assert meta.cardsUnder == (InstanceId("base"),)
    assert meta.damage == 1
    assert meta.playedViaShift is True
    assert meta.playedCostType == "shift"


def test_shift_discard_cost_is_paid_from_hand_when_lorcanito_shift_cost_uses_discard():
    resources = resources_for({"shift": "KQ7", "base": "K3y", "location": "XhY"})
    state = _main_state(resources, hand=("shift", "location"), play=("base",))
    runtime = MatchRuntime(resources)
    runtime.load_state(state)

    result = runtime.process_command(
        _play_command("shift", cost="shift", shiftTarget="base", discardCards=["location"]),
        "p0",
        actor_role="player",
    )

    assert result.success is True
    assert InstanceId("location") in result.state.ctx.zones.private.zoneCards[scoped_zone("discard", "p0")]
    assert result.state.ctx.zones.private.zoneCards[scoped_zone("play", "p0")] == (InstanceId("shift"),)


def test_shift_lethal_inherited_damage_banishes_immediately_and_suppresses_normal_play_trigger():
    resources = resources_for({"shift": "KQ7", "base": "K3y", "location": "XhY"})
    state = _main_state(resources, hand=("shift", "location"), play=("base",))
    zones = patch_card_meta(
        state.ctx.zones,
        "base",
        state.ctx.zones.private.cardMeta[InstanceId("base")].with_updates(damage=3),
    )
    state = type(state)(G=state.G, ctx=state.ctx.with_updates(zones=zones))
    runtime = MatchRuntime(resources)
    runtime.load_state(state)

    result = runtime.process_command(
        _play_command("shift", cost="shift", shiftTarget="base", discardCards=["location"]),
        "p0",
        actor_role="player",
    )

    assert result.success is True
    assert InstanceId("shift") in result.state.ctx.zones.private.zoneCards[scoped_zone("discard", "p0")]
    assert InstanceId("base") in result.state.ctx.zones.private.zoneCards[scoped_zone("discard", "p0")]
    assert result.state.G.turnMetadata.banishedCharactersThisTurn == (InstanceId("shift"),)
    assert not any(event.event.kind == "cardPlayed" for event in result.gameEvents)


def test_shift_retargets_continuous_effects_from_old_top_to_new_top():
    resources = resources_for(
        {
            "shift": "0Rd",
            "base": "ROE",
            "i1": "XGm",
            "i2": "XGm",
            "i3": "XGm",
            "i4": "XGm",
            "i5": "XGm",
        }
    )
    state = _main_state(resources, hand=("shift",), play=("base",), inkwell=("i1", "i2", "i3", "i4", "i5"))
    state, effect = add_stat_modifier_effect(
        state,
        source_id="base",
        target_id="base",
        stat="strength",
        modifier=2,
        duration="this-turn",
        controller_id="p0",
    )
    runtime = MatchRuntime(resources)
    runtime.load_state(state)

    result = runtime.process_command(
        _play_command("shift", cost="shift", shiftTarget="base"),
        "p0",
        actor_role="player",
    )

    assert result.success is True
    retargeted = result.state.G.continuousEffects.byTarget[InstanceId("shift")][0]
    assert retargeted.id == effect.id
    assert retargeted.targetId == InstanceId("shift")
