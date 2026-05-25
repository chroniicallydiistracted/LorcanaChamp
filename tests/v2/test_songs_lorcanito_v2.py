from lorcana_engine_v2.core.commands import CommandEnvelope, MoveInput
from lorcana_engine_v2.core.ids import InstanceId
from lorcana_engine_v2.core.runtime import MatchRuntime
from lorcana_engine_v2.core.state import MatchState
from lorcana_engine_v2.core.zones import CardMeta, move_card_to_zone, patch_card_meta, scoped_zone
from lorcana_engine_v2.effects.continuous_effects import add_stat_modifier_effect
from lorcana_engine_v2.effects.temporary_effects import add_temporary_restriction
from lorcana_engine_v2.moves.play import PLAY_CARD
from lorcana_engine_v2.rules.play_card_rules import get_singer_threshold_for_instance, is_song_card

from .helpers import resources_for
from .test_play_card_lorcanito_v2 import _main_state


def _play_command(card_id, **args):
    return CommandEnvelope(
        commandID=f"cmd-song-{card_id}",
        move=PLAY_CARD,
        input=MoveInput(args={"cardId": card_id, **args}),
    )


def test_real_song_can_be_sung_by_ready_non_drying_character():
    resources = resources_for({"song": "3E2", "singer": "Y1z", "deck1": "XGm", "deck2": "XGm"})
    state = _main_state(resources, hand=("song",), play=("singer",))
    runtime = MatchRuntime(resources)
    runtime.load_state(state)

    assert is_song_card(resources.cards.get("3E2")) is True
    assert get_singer_threshold_for_instance(
        framework=None,
        singerId=InstanceId("singer"),
        singerDef=resources.cards.get("Y1z"),
        getDefinitionByInstanceId=lambda _: None,
    ) == 4

    result = runtime.process_command(
        _play_command("song", cost="sing", singer="singer"),
        "p0",
        actor_role="player",
    )

    assert result.success is True
    assert result.state.ctx.zones.private.cardMeta[InstanceId("singer")].state == "exerted"
    assert InstanceId("song") in result.state.ctx.zones.private.zoneCards[scoped_zone("discard", "p0")]
    assert result.moveLogs[0].defaultMessage.key == "lorcana.move.playCard.sing"
    assert any(event.event.kind == "cardPlayed" for event in result.gameEvents)


def test_sing_rejects_drying_singer():
    resources = resources_for({"song": "3E2", "singer": "Y1z"})
    state = _main_state(resources, hand=("song",), play=("singer",))
    zones = state.ctx.zones
    zones = type(zones)(
        public=zones.public,
        reveals=zones.reveals,
        private=type(zones.private)(
            zoneCards=zones.private.zoneCards,
            cardIndex=zones.private.cardIndex,
            cardMeta={
                **zones.private.cardMeta,
                InstanceId("singer"): zones.private.cardMeta[InstanceId("singer")].with_updates(isDrying=True),
            },
        ),
    )
    state = type(state)(G=state.G, ctx=state.ctx.with_updates(zones=zones))
    runtime = MatchRuntime(resources)
    runtime.load_state(state)

    result = runtime.process_command(
        _play_command("song", cost="sing", singer="singer"),
        "p0",
        actor_role="player",
    )

    assert result.success is False
    assert result.errorCode == "SINGER_DRYING"


def test_singer_with_temporary_cant_sing_restriction_cannot_sing():
    resources = resources_for({"song": "3E2", "singer": "Y1z"})
    state = _main_state(resources, hand=("song",), play=("singer",))
    meta = add_temporary_restriction(
        state.ctx.zones.private.cardMeta[InstanceId("singer")],
        "cant-sing",
        expires_at_turn=1,
    )
    zones = patch_card_meta(state.ctx.zones, "singer", meta)
    runtime = MatchRuntime(resources)
    runtime.load_state(MatchState(G=state.G, ctx=state.ctx.with_updates(zones=zones)))

    result = runtime.process_command(
        _play_command("song", cost="sing", singer="singer"),
        "p0",
        actor_role="player",
    )

    assert result.success is False
    assert result.errorCode == "CANT_SING_RESTRICTION"


def test_singer_threshold_includes_static_singer_threshold_modifier():
    resources = resources_for({"song": "3E2", "singer": "1PU", "record": "2w7"})
    state = _main_state(resources, hand=("song",), play=("singer", "record"))
    runtime = MatchRuntime(resources)
    runtime.load_state(state)

    result = runtime.process_command(
        _play_command("song", cost="sing", singer="singer"),
        "p0",
        actor_role="player",
    )

    assert result.success is True
    assert result.state.ctx.zones.private.cardMeta[InstanceId("singer")].state == "exerted"


def test_singer_threshold_includes_continuous_singer_threshold_modifier():
    resources = resources_for({"song": "3E2", "singer": "1PU"})
    state = _main_state(resources, hand=("song",), play=("singer",))
    state, _ = add_stat_modifier_effect(
        state,
        source_id="singer",
        target_id="singer",
        stat="singer-threshold",
        modifier=1,
        duration="this-turn",
        controller_id="p0",
    )
    runtime = MatchRuntime(resources)
    runtime.load_state(state)

    result = runtime.process_command(
        _play_command("song", cost="sing", singer="singer"),
        "p0",
        actor_role="player",
    )

    assert result.success is True


def test_sing_together_validates_unique_singers_and_summed_thresholds():
    resources = resources_for({"song": "EhX", "s1": "Y1z", "s2": "Y1z"})
    state = _main_state(resources, hand=("song",), play=("s1", "s2"))
    runtime = MatchRuntime(resources)
    runtime.load_state(state)

    duplicate = runtime.process_command(
        _play_command("song", cost="singTogether", singers=["s1", "s1"]),
        "p0",
        actor_role="player",
    )

    assert duplicate.success is False
    assert duplicate.errorCode == "DUPLICATE_SINGERS"

    valid_runtime = MatchRuntime(resources)
    valid_runtime.load_state(state)
    result = valid_runtime.process_command(
        _play_command("song", cost="singTogether", singers=["s1", "s2"]),
        "p0",
        actor_role="player",
    )

    assert result.success is True
