from lorcana_engine_v2.core.commands import CommandEnvelope, MoveInput
from lorcana_engine_v2.core.ids import InstanceId
from lorcana_engine_v2.core.runtime import MatchRuntime
from lorcana_engine_v2.core.zones import scoped_zone
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
